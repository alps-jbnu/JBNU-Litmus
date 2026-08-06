"""
Django-ace originally from https://github.com/bradleyayers/django-ace.
"""

from django import forms
from django.forms.utils import flatatt
from django.utils.safestring import mark_safe


# 에디터 테마는 사이트 테마(라이트/다크)를 따라간다. 두 값 모두 마크업으로 내보내고
# 최종 선택은 widget.js 가 <html data-theme> 를 보고 한다.
# 서버에서 고르지 않는 이유는 '시스템 기본값(auto)' 때문이다. auto 는 브라우저의
# prefers-color-scheme 으로만 판정되므로 서버가 알 수 없고, 서버에서 고르면
# auto 사용자에게 항상 라이트 테마가 나가 버린다.
DEFAULT_LIGHT_THEME = 'github'
DEFAULT_DARK_THEME = 'twilight'


class AceWidget(forms.Textarea):
    def __init__(self, mode=None, theme=None, wordwrap=False, width='100%', height='300px',
                 no_ace_media=False, dark_theme=None, *args, **kwargs):
        self.mode = mode
        self.theme = theme or DEFAULT_LIGHT_THEME
        self.dark_theme = dark_theme or DEFAULT_DARK_THEME
        self.wordwrap = wordwrap
        self.width = width
        self.height = height
        self.ace_media = not no_ace_media
        super(AceWidget, self).__init__(*args, **kwargs)

    @property
    def media(self):
        # Self-hosted so that Ace's runtime-injected <script> tags for modes,
        # themes and workers stay same-origin and satisfy `script-src 'self'`.
        js = ['vendor/ace/1.1.3/ace.js'] if self.ace_media else []
        js.append('django_ace/widget.js')
        css = {
            'screen': ['django_ace/widget.css'],
        }
        return forms.Media(js=js, css=css)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}

        ace_attrs = {
            'class': 'django-ace-widget loading',
            'style': 'width:%s; height:%s' % (self.width, self.height),
            'id': 'ace_%s' % name,
        }
        if self.mode:
            ace_attrs['data-mode'] = self.mode
        if self.theme:
            ace_attrs['data-theme'] = self.theme
        if self.dark_theme:
            ace_attrs['data-theme-dark'] = self.dark_theme
        if self.wordwrap:
            ace_attrs['data-wordwrap'] = 'true'

        attrs.update(style='width: 100%; min-width: 100%; max-width: 100%; resize: none')
        textarea = super(AceWidget, self).render(name, value, attrs)

        html = '<div%s><div></div></div>%s' % (flatatt(ace_attrs), textarea)

        # add toolbar
        html = ('<div class="django-ace-editor"><div style="width: 100%%" class="django-ace-toolbar">'
                '<a href="./" class="django-ace-max_min"></a></div>%s</div>') % html

        return mark_safe(html)
