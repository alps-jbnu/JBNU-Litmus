import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

_SAFE_NAME_RE = re.compile(r'[^A-Za-z0-9_.-]+')

# 예전 코드는 보고서를 정적 폴더에 두고 .../jplag_reports/<대회>/<문제>/<언어>/results.jplag 주소를 저장했다.
# 이런 행은 DB를 고치지 않고, 보여줄 때 권한 확인 뷰(contest_jplag_report) 주소로 바꾼다.
_LEGACY_REPORT_PATH_RE = re.compile(r'/jplag_reports/([^/]+)/([^/]+)/([^/]+)/results\.jplag$')

REPORT_FILE_NAME = 'results.jplag'


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
    shutil.rmtree(report_dir, ignore_errors=True)
    os.makedirs(report_dir, exist_ok=True)
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

            if isinstance(source, bytes):
                data = source
            else:
                data = (source or '').encode('utf-8')
            with open(file_path, 'wb') as handle:
                handle.write(data)

        if not users:
            return None, 0
        if len(users) < 2:
            return None, len(users)

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
        subprocess.run(cmd, check=True, capture_output=True, text=True)

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
