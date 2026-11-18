import logging
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

logger = logging.getLogger('judge.jplag')

_SAFE_NAME_RE = re.compile(r'[^A-Za-z0-9_.-]+')

# 예전 코드는 보고서를 정적 폴더에 두고 .../jplag_reports/<대회>/<문제>/<언어>/results.jplag 주소를 저장했다.
# 이런 행은 DB를 고치지 않고, 보여줄 때 권한 확인 뷰(contest_jplag_report) 주소로 바꾼다.
_LEGACY_REPORT_PATH_RE = re.compile(r'/jplag_reports/([^/]+)/([^/]+)/([^/]+)/results\.jplag$')

REPORT_FILE_NAME = 'results.jplag'

# JPlag 한 번(문제 하나 × 언어 하나)에 주는 시간(초). settings.JPLAG_TIMEOUT으로 바꿀 수 있고, None이나 0이면 제한하지 않는다.
DEFAULT_JPLAG_TIMEOUT = 600

# 실패했을 때 로그에 남기는 JPlag 출력 줄 수
_LOG_TAIL_LINES = 40

# ```c, ``` 처럼 마크다운 코드 블록을 여닫는 줄 (앞 공백 허용)
_MARKDOWN_FENCE_LINE_RE = re.compile(r'^[ \t]*```.*$', re.MULTILINE)

# JPlag 6.3.0 출력에서 실패 이유를 찾는 패턴
_NOT_ENOUGH_RE = re.compile(r'Not enough valid submissions!?\s*\(found (\d+) valid submissions?\)')
_PARSE_FAILED_RE = re.compile(r'Failed to parse submission (\S+?):')
_TOO_SHORT_RE = re.compile(r'Submission (\S+) contains \d+ tokens, which is below the minimum match length (\d+)')
_SKIPPED_RE = re.compile(r'(\d+) submissions? were skipped')
_ERROR_LINE_RE = re.compile(r'\[ERROR\]\s+\S+\s+-\s+(.+)')


class JplagError(Exception):
    """JPlag가 한 문제·언어 조합을 비교하지 못했다.

    str(e)는 조교가 읽을 수 있는 문장이고, submission_count는 비교하려던 학생 수다.
    JPlag 출력은 예외에 담지 않고 로그(judge.jplag)에 남긴다.
    """

    def __init__(self, message, submission_count=0):
        super().__init__(message)
        self.submission_count = submission_count


def strip_markdown_fences(source):
    """```로 시작하는 줄(마크다운 코드 블록 표시)을 빈 줄로 바꾼다.

    AI 답변 등을 복사하면서 ```c 같은 줄까지 함께 내는 학생이 있다. JPlag는 이런 제출을 파싱하지 못해
    비교에서 빼고, 남은 제출이 2개보다 적으면 그 칸 전체가 실패한다. JPlag에 넘기는 사본에만 적용하고
    DB의 원본은 그대로 둔다. 보고서의 줄 번호가 원본 제출과 같도록 줄 자체는 남긴다.

    컴파일 에러 제출을 비교에서 빼는 방식(A안)으로 바꾸려면 _source_bytes에서 이 함수를 빼고,
    judge/tasks/contest.py의 run_jplag에서 제출을 고르는 쿼리를 바꾼다.
    """
    return _MARKDOWN_FENCE_LINE_RE.sub('', source)


def _source_bytes(source):
    if isinstance(source, bytes):
        source = source.decode('utf-8', 'surrogateescape')
    return strip_markdown_fences(source or '').encode('utf-8', 'surrogateescape')


def _tail(output, lines=_LOG_TAIL_LINES):
    """JPlag 출력의 마지막 몇 줄. 진행 표시줄이 쓰는 \\r도 줄바꿈으로 본다."""
    if isinstance(output, bytes):  # TimeoutExpired는 text 모드여도 bytes를 담는다.
        output = output.decode('utf-8', 'replace')
    rows = [row.rstrip() for row in re.split(r'\r\n|\r|\n', output or '')]
    return '\n'.join([row for row in rows if row][-lines:])


def _skip_reasons(output):
    """JPlag가 비교에서 뺀 제출과 그 이유 (이름은 임시 폴더 이름, 즉 정리된 아이디)"""
    reasons = []
    parse_failed = sorted(set(_PARSE_FAILED_RE.findall(output)))
    if parse_failed:
        reasons.append('코드로 읽지 못한 제출: %s' % ', '.join(parse_failed))
    too_short = _TOO_SHORT_RE.findall(output)
    if too_short:
        names = sorted({name for name, _ in too_short})
        reasons.append('너무 짧은 제출(토큰 %s개 미만): %s' % (too_short[0][1], ', '.join(names)))
    return reasons


def _describe_failure(output, returncode):
    """JPlag가 0이 아닌 종료 코드로 끝났을 때 조교에게 보여줄 문장"""
    match = _NOT_ENOUGH_RE.search(output)
    if match:
        found = int(match.group(1))
        if found:
            message = 'JPlag가 비교할 수 있는 제출이 %d개뿐이라 표절 검사를 하지 못했습니다(2개 이상 필요).' % found
        else:
            message = 'JPlag가 비교할 수 있는 제출이 없어 표절 검사를 하지 못했습니다.'
        reasons = _skip_reasons(output)
        if reasons:
            message += ' ' + ' / '.join(reasons)
        return message

    message = 'JPlag가 실패했습니다(종료 코드 %d).' % returncode
    errors = _ERROR_LINE_RE.findall(output)
    if errors:
        message += ' ' + errors[-1].strip()
    return message


def _log_failure(where, submission_count, message, cmd, stdout, stderr):
    logger.warning('JPlag failed for %s (%d submissions): %s\ncommand: %s\n'
                   '--- JPlag stdout (last lines) ---\n%s\n--- JPlag stderr (last lines) ---\n%s',
                   where, submission_count, message, ' '.join(cmd), _tail(stdout), _tail(stderr, 10))


def _run_jplag(cmd, report_dir, where, submission_count):
    """JPlag를 실행한다. 보고서를 만들지 못하면 이유를 로그에 남기고 JplagError를 낸다."""
    timeout = getattr(settings, 'JPLAG_TIMEOUT', DEFAULT_JPLAG_TIMEOUT) or None
    try:
        completed = subprocess.run(cmd, capture_output=True, timeout=timeout, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired as e:
        message = 'JPlag가 %s초 안에 끝나지 않아 중단했습니다.' % timeout
        _log_failure(where, submission_count, message, cmd, e.stdout, e.stderr)
        raise JplagError(message, submission_count)

    if completed.returncode != 0:
        message = _describe_failure(completed.stdout or '', completed.returncode)
        _log_failure(where, submission_count, message, cmd, completed.stdout, completed.stderr)
        raise JplagError(message, submission_count)

    if not os.path.isfile(os.path.join(report_dir, REPORT_FILE_NAME)):
        message = 'JPlag가 끝났지만 보고서 파일을 만들지 않았습니다.'
        _log_failure(where, submission_count, message, cmd, completed.stdout, completed.stderr)
        raise JplagError(message, submission_count)

    # 보고서는 만들었지만 일부 제출을 조용히 뺀 경우도 기록한다.
    skipped = _SKIPPED_RE.search(completed.stdout or '')
    if skipped:
        logger.warning('JPlag skipped %s of %d submissions for %s. %s\n--- JPlag stdout (last lines) ---\n%s',
                       skipped.group(1), submission_count, where, ' / '.join(_skip_reasons(completed.stdout)),
                       _tail(completed.stdout))


def _safe_name(name):
    cleaned = _SAFE_NAME_RE.sub('_', name).strip('._')
    return cleaned or 'user'


def _is_inside(path, root):
    path = os.path.realpath(path)
    root = os.path.realpath(root)
    return os.path.commonpath((path, root)) == root


def _public_roots():
    # 웹 서버가 로그인 없이 내주는 폴더들
    roots = [entry[1] if isinstance(entry, (list, tuple)) else entry
             for entry in getattr(settings, 'STATICFILES_DIRS', [])]
    roots.append(getattr(settings, 'STATIC_ROOT', None))
    roots.append(getattr(settings, 'MEDIA_ROOT', None))
    return [root for root in roots if root]


def _get_report_root():
    report_root = getattr(settings, 'JPLAG_REPORT_ROOT', None) or os.path.join(settings.BASE_DIR, 'jplag_reports')
    # 보고서에는 학생 아이디와 제출 코드가 들어 있으므로 공개 폴더에 두지 않는다.
    for public_root in _public_roots():
        if _is_inside(report_root, public_root):
            raise ImproperlyConfigured('JPLAG_REPORT_ROOT must not be inside a public directory (%s): %s' %
                                       (public_root, report_root))
    return report_root


def _get_report_url(contest_key, problem_code, dmoj_lang):
    return reverse('contest_jplag_report', args=(contest_key, problem_code, dmoj_lang))


def _get_jplag_config():
    default_jar = os.path.join(settings.BASE_DIR, 'opt', 'jplag-6.3.0.jar')
    jar_path = getattr(settings, 'JPLAG_JAR_PATH', default_jar)
    java_path = getattr(settings, 'JPLAG_JAVA_PATH', None)

    report_root = _get_report_root()
    viewer_url_prefix = getattr(settings, 'JPLAG_VIEWER_URL_PREFIX', None)
    tmp_root = getattr(settings, 'JPLAG_TMP_ROOT', None)

    language_map = getattr(
        settings,
        'JPLAG_LANGUAGE_MAP',
        {
            'C': 'c',
            'C++': 'cpp',
            'Java': 'java',
            'Python': 'python3',
        },
    )
    extension_map = getattr(
        settings,
        'JPLAG_EXTENSION_MAP',
        {
            'C': 'c',
            'C++': 'cpp',
            'Java': 'java',
            'Python': 'py',
        },
    )
    extra_args = getattr(settings, 'JPLAG_EXTRA_ARGS', [])
    if isinstance(extra_args, str):
        extra_args = extra_args.split()

    return {
        'jar_path': jar_path,
        'java_path': java_path,
        'report_root': report_root,
        'viewer_url_prefix': viewer_url_prefix,
        'tmp_root': tmp_root,
        'language_map': language_map,
        'extension_map': extension_map,
        'extra_args': extra_args,
    }


def run_jplag_for_submissions(contest_key, problem_code, dmoj_lang, submissions):
    """한 문제·언어 조합의 제출을 JPlag로 비교하고 (보고서 주소, 학생 수)를 돌려준다.

    submissions는 (아이디, 코드) 목록이고 같은 아이디는 처음 것만 쓴다. 학생이 2명보다 적으면 JPlag를
    돌리지 않고 (None, 학생 수)를 돌려준다. JPlag가 보고서를 만들지 못하면 JplagError를, 설정이 잘못됐으면
    ImproperlyConfigured를 낸다.
    """
    config = _get_jplag_config()
    jar_path = config['jar_path']
    java_path = config['java_path']
    report_root = config['report_root']
    viewer_url_prefix = config['viewer_url_prefix']
    tmp_root = config['tmp_root']
    language_map = config['language_map']
    extension_map = config['extension_map']
    extra_args = config['extra_args']

    if java_path and not os.path.exists(java_path):
        raise ImproperlyConfigured('JPlag Java not found: %s' % java_path)
    if not os.path.exists(jar_path):
        raise ImproperlyConfigured('JPlag jar not found: %s' % jar_path)

    jplag_lang = language_map.get(dmoj_lang)
    if not jplag_lang:
        raise ImproperlyConfigured('No JPlag language mapping for %s' % dmoj_lang)

    ext = extension_map.get(dmoj_lang, 'txt')
    report_dir = os.path.join(report_root, contest_key, problem_code, dmoj_lang)
    # 예전 보고서는 이번 결과로 바뀌므로 먼저 지운다.
    shutil.rmtree(report_dir, ignore_errors=True)
    result_file = os.path.join(report_dir, 'results')

    users = set()
    if tmp_root:
        os.makedirs(tmp_root, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_root) as tmp_dir:
        for username, source in submissions:
            if username in users:
                continue
            users.add(username)

            user_dir = os.path.join(tmp_dir, _safe_name(username))
            os.makedirs(user_dir, exist_ok=True)
            file_path = os.path.join(user_dir, 'solution.%s' % ext)
            with open(file_path, 'wb') as handle:
                handle.write(_source_bytes(source))

        if len(users) < 2:
            return None, len(users)

        # JPlag는 보고서 폴더가 없으면 실패한다.
        os.makedirs(report_dir, exist_ok=True)
        cmd = [
            java_path or 'java',
            '-jar',
            jar_path,
            '-l',
            jplag_lang,
            '-r',
            result_file,
        ]
        cmd.extend(extra_args)
        cmd.append(tmp_dir)
        try:
            _run_jplag(cmd, report_dir, '%s/%s/%s' % (contest_key, problem_code, dmoj_lang), len(users))
        except JplagError:
            # 실패한 칸의 보고서 폴더는 남기지 않는다.
            shutil.rmtree(report_dir, ignore_errors=True)
            raise

    result_file_url = _get_report_url(contest_key, problem_code, dmoj_lang)
    if viewer_url_prefix:
        # 뷰어는 URLSearchParams로 file=을 읽으므로 'C++'의 '+'가 공백으로 풀리지 않게 인코딩한다.
        report_url = '%s?file=%s' % (viewer_url_prefix, quote(result_file_url, safe='/'))
    else:
        report_url = result_file_url
    return report_url, len(users)


def get_jplag_report_path(contest_key, problem_code, dmoj_lang):
    """보고서 파일의 실제 경로. report_root 밖을 가리키면 None을 돌려준다."""
    report_root = _get_report_root()
    try:
        path = os.path.realpath(os.path.join(report_root, contest_key, problem_code, dmoj_lang, REPORT_FILE_NAME))
    except ValueError:  # NUL 문자
        return None
    if not _is_inside(path, report_root):
        return None
    return path


def build_jplag_viewer_url(request, stored_url):
    if not stored_url or request is None:
        return stored_url

    parsed = urlparse(stored_url)
    file_url = None
    if parsed.query:
        for part in parsed.query.split('&'):
            if '=' not in part:
                continue
            key, value = part.split('=', 1)
            if key == 'file':
                # Preserve '+' in paths like C++, only decode %XX sequences.
                file_url = unquote(value)
                break

    if not file_url:
        file_url = stored_url

    legacy = _LEGACY_REPORT_PATH_RE.search(urlparse(file_url).path)
    if legacy:
        file_url = _get_report_url(*legacy.groups())

    if file_url and not urlparse(file_url).scheme:
        file_url = request.build_absolute_uri(file_url)

    viewer_base = getattr(settings, 'JPLAG_VIEWER_URL_PREFIX', '/static/jplag-viewer/')
    if not viewer_base.endswith('/'):
        viewer_base = viewer_base + '/'
    if not urlparse(viewer_base).scheme:
        viewer_base = request.build_absolute_uri(viewer_base)

    encoded_file_url = quote(file_url, safe=':/%?&=#')
    return '%s?file=%s' % (viewer_base, encoded_file_url)
