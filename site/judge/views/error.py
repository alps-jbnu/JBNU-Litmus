import traceback

from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import Resolver404
from django.utils.translation import gettext as _


BOT_USER_AGENT_MARKERS = (
    'bot',
    'crawler',
    'spider',
    'slurp',
    'baiduspider',
    'yandex',
    'duckduckbot',
)

LIGHTWEIGHT_404_PREFIXES = (
    '/api/',
    '/static/',
    '/media/',
)

LIGHTWEIGHT_404_PATHS = (
    '/favicon.ico',
    '/robots.txt',
    '/sitemap.xml',
    '/manifest.json',
)


def error(request, context, status):
    context = dict(context)
    context.update({
        'csp_nonce': getattr(request, 'csp_nonce', ''),
        'language_code': getattr(request, 'LANGUAGE_CODE', 'ko'),
        'show_traceback': getattr(getattr(request, 'user', None), 'is_superuser', False),
    })
    content = render_to_string('error.html', context=context)
    return HttpResponse(content, status=status, content_type='text/html; charset=utf-8')


def _accepts_html_page(request):
    accept = request.META.get('HTTP_ACCEPT', '')
    if not accept:
        return False

    accepted_types = [item.split(';', 1)[0].strip().lower() for item in accept.split(',')]
    return 'text/html' in accepted_types or 'application/xhtml+xml' in accepted_types


def _is_json_or_ajax_request(request):
    if request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
        return True

    accept = request.META.get('HTTP_ACCEPT', '').lower()
    return 'application/json' in accept or '+json' in accept


def _is_bot_request(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    return any(marker in user_agent for marker in BOT_USER_AGENT_MARKERS)


def _is_lightweight_404_path(request):
    path = request.path_info or request.path
    return path in LIGHTWEIGHT_404_PATHS or path.startswith(LIGHTWEIGHT_404_PREFIXES)


def _should_render_browser_404_redirect(request, exception):
    return (
        isinstance(exception, Resolver404) and
        _accepts_html_page(request) and
        not _is_json_or_ajax_request(request) and
        not _is_bot_request(request) and
        not _is_lightweight_404_path(request)
    )


def _should_render_browser_404_message(request):
    return (
        _accepts_html_page(request) and
        not _is_json_or_ajax_request(request) and
        not _is_bot_request(request) and
        not _is_lightweight_404_path(request)
    )


def error404(request, exception=None):
    if _should_render_browser_404_message(request):
        should_redirect_home = _should_render_browser_404_redirect(request, exception)
        content = render_to_string('404-redirect-home.html', {
            'auto_redirect_home': should_redirect_home,
            'csp_nonce': getattr(request, 'csp_nonce', ''),
            'language_code': getattr(request, 'LANGUAGE_CODE', 'ko'),
            'title': _('Page not found'),
            'message': (
                _('You will be redirected to the home page shortly.')
                if should_redirect_home else
                _('The requested page or result does not exist.')
            ),
        })
        return HttpResponseNotFound(content, content_type='text/html; charset=utf-8')

    return HttpResponseNotFound('Not Found\n', content_type='text/plain; charset=utf-8')


def error403(request, exception=None):
    return error(request, {
        'id': 'unauthorized_access',
        'description': _('no permission for %s') % request.path,
        'code': 403,
    }, 403)


def error500(request):
    return error(request, {
        'id': 'invalid_state',
        'description': _('corrupt page %s') % request.path,
        'traceback': traceback.format_exc(),
        'code': 500,
    }, 500)
