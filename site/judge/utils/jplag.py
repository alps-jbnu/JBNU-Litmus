import os
import posixpath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_SAFE_NAME_RE = re.compile(r'[^A-Za-z0-9_.-]+')


def _safe_name(name):
    cleaned = _SAFE_NAME_RE.sub('_', name).strip('._')
    return cleaned or 'user'


def _get_jplag_config():
    default_jar = os.path.join(settings.BASE_DIR, 'opt', 'jplag-6.3.0.jar')
    jar_path = getattr(settings, 'JPLAG_JAR_PATH', default_jar)
    java_path = getattr(settings, 'JPLAG_JAVA_PATH', None)

    report_root = getattr(settings, 'JPLAG_REPORT_ROOT', None)
    if not report_root:
        static_dirs = getattr(settings, 'STATICFILES_DIRS', [])
        if static_dirs:
            report_root = os.path.join(static_dirs[0], 'jplag_reports')
        else:
            report_root = os.path.join(settings.BASE_DIR, 'jplag_reports')

    report_url_prefix = getattr(settings, 'JPLAG_REPORT_URL_PREFIX', '/static/jplag_reports')
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
        'report_url_prefix': report_url_prefix,
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
    report_url_prefix = config['report_url_prefix']
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

    result_file_url = posixpath.join(
        report_url_prefix.rstrip('/'),
        contest_key,
        problem_code,
        dmoj_lang,
        'results.jplag',
    )
    if viewer_url_prefix:
        report_url = '%s?file=%s' % (viewer_url_prefix, result_file_url)
    else:
        report_url = posixpath.join(
            report_url_prefix.rstrip('/'),
            contest_key,
            problem_code,
            dmoj_lang,
            'index.html',
        )
    return report_url, len(users)


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

    if file_url and not urlparse(file_url).scheme:
        file_url = request.build_absolute_uri(file_url)

    viewer_base = getattr(settings, 'JPLAG_VIEWER_URL_PREFIX', '/static/jplag-viewer/')
    if not viewer_base.endswith('/'):
        viewer_base = viewer_base + '/'
    if not urlparse(viewer_base).scheme:
        viewer_base = request.build_absolute_uri(viewer_base)

    encoded_file_url = quote(file_url, safe=':/%?&=#')
    return '%s?file=%s' % (viewer_base, encoded_file_url)
