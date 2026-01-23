#dev/service 인스턴스 settings.py를 다르게 하기 위해 settings.py를 block했습니다.
#이 파일을 참고하세요.

"""
Django settings for dmoj project.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import datetime
import os
import tempfile
import environ

from django.utils.translation import gettext_lazy as _
from django_jinja.builtins import DEFAULT_EXTENSIONS
from jinja2 import select_autoescape

from django.templatetags.static import static

def jinja2_globals():
    return {
        'static': static,  # Jinja2에서 Django의 static 기능을 사용할 수 있도록 추가
    }

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
env = environ.Env(DEBUG=(bool,False))
environ.Env.read_env(os.path.join(BASE_DIR,'.env'))

DJANGO_ADMIN_DIR = os.path.join(os.path.dirname(BASE_DIR), 'dmojsite/lib/python3.10/site-packages/wpadmin/templates')
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY는 .env 파일에서 환경 변수로 관리됩니다
# 환경 변수가 없을 경우 기본값 제공 (실제 운영에서는 반드시 .env에서 설정하세요)
SECRET_KEY = env('SECRET_KEY', default='your-secret-key-here-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = []

SITE_ID = 1
SITE_NAME = 'Litmus'
SITE_LONG_NAME = 'Litmus: Modern Online Judge'
SITE_ADMIN_EMAIL = 'litmus@jbnu.ac.kr'

DMOJ_REQUIRE_STAFF_2FA = True
# Display warnings that admins will not perform 2FA recovery.
DMOJ_2FA_HARDCORE = False

# Set to 1 to use HTTPS if request was made to https://
# Set to 2 to always use HTTPS for links
# Set to 0 to always use HTTP for links
DMOJ_SSL = 0

SECURE_SSL_REDIRECT = True

SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True    
SECURE_HSTS_PRELOAD = True  
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Refer to https://dmoj.ca/post/103-point-system-rework
DMOJ_PP_STEP = 0.95
DMOJ_PP_ENTRIES = 100
DMOJ_PP_BONUS_FUNCTION = lambda n: 300 * (1 - 0.997 ** n)  # noqa: E731

NODEJS = '/usr/bin/node'
EXIFTOOL = '/usr/bin/exiftool'
ACE_URL = '//cdnjs.cloudflare.com/ajax/libs/ace/1.1.3'
SELECT2_JS_URL = '//cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/js/select2.min.js'
SELECT2_CSS_URL = '//cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/css/select2.min.css'

DMOJ_CAMO_URL = None
DMOJ_CAMO_KEY = None
DMOJ_CAMO_HTTPS = False
DMOJ_CAMO_EXCLUDE = ()
DMOJ_PROBLEM_DATA_ROOT = env('DMOJ_PROBLEM_DATA_ROOT')
DMOJ_PROBLEM_MIN_TIME_LIMIT = 0  # seconds
DMOJ_PROBLEM_MAX_TIME_LIMIT = 60000  # seconds
DMOJ_PROBLEM_MIN_MEMORY_LIMIT = 0  # kilobytes
DMOJ_PROBLEM_MAX_MEMORY_LIMIT = 1048576000  # kilobytes
DMOJ_PROBLEM_MIN_PROBLEM_POINTS = 0
DMOJ_PROBLEM_MIN_USER_POINTS_VOTE = 10  # when voting on problem, minimum point value user can select
DMOJ_PROBLEM_MAX_USER_POINTS_VOTE = 500  # when voting on problem, maximum point value user can select
DMOJ_PROBLEM_HOT_PROBLEM_COUNT = 700
DMOJ_PROBLEM_STATEMENT_DISALLOWED_CHARACTERS = {'“', '”', '‘', '’', '−', 'ﬀ', 'ﬁ', 'ﬂ', 'ﬃ', 'ﬄ'}
DMOJ_RATING_COLORS = True
DMOJ_EMAIL_THROTTLING = (10, 60)
DMOJ_STATS_LANGUAGE_THRESHOLD = 100
DMOJ_SUBMISSIONS_REJUDGE_LIMIT = 100
# Maximum number of submissions a single user can queue without the `spam_submission` permission
DMOJ_SUBMISSION_LIMIT = 200
# Whether to allow users to view source code: 'all' | 'all-solved' | 'only-own'
DMOJ_SUBMISSION_SOURCE_VISIBILITY = 'all-solved'
DMOJ_BLOG_NEW_PROBLEM_COUNT = 7
DMOJ_TOTP_TOLERANCE_HALF_MINUTES = 10
DMOJ_SCRATCH_CODES_COUNT = 50
DMOJ_USER_MAX_ORGANIZATION_COUNT = 30
# Whether to allow users to download their data
DMOJ_USER_DATA_DOWNLOAD = False
DMOJ_USER_DATA_CACHE = ''
DMOJ_USER_DATA_DOWNLOAD_RATELIMIT = datetime.timedelta(days=1)
DMOJ_COMMENT_VOTE_HIDE_THRESHOLD = -5
DMOJ_COMMENT_REPLY_TIMEFRAME = datetime.timedelta(days=365)
DMOJ_PDF_PROBLEM_CACHE = ''
DMOJ_PDF_PROBLEM_TEMP_DIR = tempfile.gettempdir()
DMOJ_STATS_SUBMISSION_RESULT_COLORS = {
    'TLE': '#dc2626',
    'AC': '#94D95C',
    'WA': '#dc2626',
    'CE': '#525252',
    'ERR': '#dc2626',
}
DMOJ_API_PAGE_SIZE = 1000

DMOJ_PASSWORD_RESET_LIMIT_WINDOW = 3600
DMOJ_PASSWORD_RESET_LIMIT_COUNT = 10

MARKDOWN_STYLES = {}
MARKDOWN_DEFAULT_STYLE = {}

MATHOID_URL = False
MATHOID_GZIP = False
MATHOID_MML_CACHE = None
MATHOID_CSS_CACHE = 'default'
MATHOID_DEFAULT_TYPE = 'auto'
MATHOID_MML_CACHE_TTL = 864000
MATHOID_CACHE_ROOT = ''
MATHOID_CACHE_URL = False

TEXOID_GZIP = False
TEXOID_META_CACHE = 'default'
TEXOID_META_CACHE_TTL = 864000
DMOJ_NEWSLETTER_ID_ON_REGISTER = None

BAD_MAIL_PROVIDERS = ()
BAD_MAIL_PROVIDER_REGEX = ()
NOFOLLOW_EXCLUDED = set()

TIMEZONE_BG = None
TIMEZONE_MAP = None

TERMS_OF_SERVICE_URL = None
DEFAULT_USER_LANGUAGE = 'PY3'

PHANTOMJS = ''
PHANTOMJS_PDF_ZOOM = 0.75
PHANTOMJS_PDF_TIMEOUT = 5.0
PHANTOMJS_PAPER_SIZE = 'Letter'

SLIMERJS = ''
SLIMERJS_PDF_ZOOM = 0.75
SLIMERJS_FIREFOX_PATH = ''
SLIMERJS_PAPER_SIZE = 'Letter'

PUPPETEER_MODULE = '/usr/lib/node_modules/puppeteer'
PUPPETEER_PAPER_SIZE = 'Letter'

USE_SELENIUM = True
SELENIUM_CUSTOM_CHROME_PATH = '/usr/bin/chromium-browser'
SELENIUM_CHROMEDRIVER_PATH = '/usr/bin/chromedriver'

INLINE_JQUERY = True
INLINE_FONTAWESOME = True
JQUERY_JS = '//ajax.googleapis.com/ajax/libs/jquery/3.4.1/jquery.min.js'
FONTAWESOME_CSS = '//maxcdn.bootstrapcdn.com/font-awesome/4.3.0/css/font-awesome.min.css'
DMOJ_CANONICAL = ''

# Application definition

INSTALLED_APPS = ()

try:
    import wpadmin
except ImportError:
    pass
else:
    del wpadmin
    INSTALLED_APPS += ('wpadmin',)

    WPADMIN = {
        'admin': {
            'title': 'DMOJ Admin',
            'menu': {
                'top': 'wpadmin.menu.menus.BasicTopMenu',
                'left': 'wpadmin.menu.custom.CustomModelLeftMenuWithDashboard',
            },
            'custom_menu': [
                {
                    'model': 'judge.Problem',
                    'icon': 'fa-question-circle',
                    'children': [
                        'judge.ProblemGroup',
                        # 문제 유형 비활성화
                        # 'judge.ProblemType',
                        
                        # 라이선스 비활성화
                        # 'judge.License',
                        
                        # 문제 투표 관련 기능 비활성화
                        # 'judge.ProblemPointsVote',
                    ],
                },
                ('judge.Submission', 'fa-check-square-o'),
                {
                    'model': 'judge.Language',
                    'icon': 'fa-file-code-o',
                    'children': [
                        'judge.Judge',
                    ],
                },
                {
                    'model': 'judge.Contest',
                    'icon': 'fa-bar-chart',
                    'children': [
                        'judge.ContestParticipation',
                        'judge.ContestTag',
                    ],
                },
                ('judge.Ticket', 'fa-bell'),
                {
                    'model': 'auth.User',
                    'icon': 'fa-user',
                    'children': [
                        'judge.Profile',
                        'auth.Group',
                        # 'registration.RegistrationProfile',
                        'judge.Department',
                        'judge.Subject',
                    ],
                },
                {
                    'model': 'judge.Organization',
                    'icon': 'fa-users',
                    'children': [
                        'judge.OrganizationRequest',
                        'judge.Class',
                    ],
                },
                {
                    'model': 'sites.Site',
                    'icon': 'fa-bars',
                },
                ('judge.BlogPost', 'fa-rss-square'),
                {
                    'model': 'judge.Comment',
                    'icon': 'fa-comment-o',
                    'children': [
                        'judge.CommentLock',
                    ],
                },
                ('flatpages.FlatPage', 'fa-file-text-o'),
                ('judge.MiscConfig', 'fa-question-circle'),
            ],
            'dashboard': {
                'breadcrumbs': True,
            },
        },
    }

INSTALLED_APPS += (
    'django.contrib.admin',
    'judge',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.flatpages',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.redirects',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'registration',
    'mptt',
    'reversion',
    'django_social_share',
    'social_django',
    'compressor',
    'django_ace',
    'pagedown',
    'sortedm2m',
    'statici18n',
    'impersonate',
    'django_jinja',
    'martor',
    'adminsortable2',
)

MIDDLEWARE = (
    'django.middleware.security.SecurityMiddleware',
    'judge.middleware.NoCacheMiddleware',
    'judge.middleware.SimpleCSPMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    #'judge.middleware.KeycloakSSOMiddleware',
    'judge.middleware.DMOJLoginMiddleware',
    'judge.middleware.ShortCircuitMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'judge.middleware.APIMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'judge.user_log.LogUserAccessMiddleware',
    'judge.timezone.TimezoneMiddleware',
    'impersonate.middleware.ImpersonateMiddleware',
    'judge.middleware.DMOJImpersonationMiddleware',
    'judge.middleware.ContestMiddleware',
    'django.contrib.flatpages.middleware.FlatpageFallbackMiddleware',
    'judge.social_auth.SocialAuthExceptionMiddleware',
    'django.contrib.redirects.middleware.RedirectFallbackMiddleware',
)

IMPERSONATE_REQUIRE_SUPERUSER = True
IMPERSONATE_DISABLE_LOGGING = True

ACCOUNT_ACTIVATION_DAYS = 7

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'judge.utils.pwned.PwnedPasswordsValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

SILENCED_SYSTEM_CHECKS = ['urls.W002', 'fields.W342']

ROOT_URLCONF = 'dmoj.urls'
LOGIN_REDIRECT_URL = '/'
WSGI_APPLICATION = 'dmoj.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

TEMPLATES = [
    {
        'BACKEND': 'django_jinja.backend.Jinja2',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
        ],
        'APP_DIRS': False,
        'OPTIONS': {
            'match_extension': ('.html', '.txt'),
            'match_regex': '^(?!admin/)',
            'context_processors': [
                'django.template.context_processors.media',
                'django.template.context_processors.tz',
                'django.template.context_processors.i18n',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
                'judge.template_context.comet_location',
                'judge.template_context.get_resource',
                'judge.template_context.general_info',
                'judge.template_context.site',
                'judge.template_context.site_name',
                'judge.template_context.misc_config',
                'judge.template_context.math_setting',
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
            ],
            'autoescape': select_autoescape(['html', 'xml']),
            'trim_blocks': True,
            'lstrip_blocks': True,
            'translation_engine': 'judge.utils.safe_translations',
            'extensions': DEFAULT_EXTENSIONS + [
                'compressor.contrib.jinja2ext.CompressorExtension',
                'judge.jinja2.DMOJExtension',
                'judge.jinja2.spaceless.SpacelessExtension',
            ],
            'globals': jinja2_globals(),
        },
    },
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
        ],
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.media',
                'django.template.context_processors.tz',
                'django.template.context_processors.i18n',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

LANGUAGES = [
    ('ca', _('Catalan')),
    ('de', _('German')),
    ('el', _('Greek')),
    ('en', _('English')),
    ('es', _('Spanish')),
    ('fr', _('French')),
    ('hr', _('Croatian')),
    ('hu', _('Hungarian')),
    ('ja', _('Japanese')),
    ('ko', _('Korean')),
    ('pt', _('Brazilian Portuguese')),
    ('ro', _('Romanian')),
    ('ru', _('Russian')),
    ('sr-latn', _('Serbian (Latin)')),
    ('tr', _('Turkish')),
    ('vi', _('Vietnamese')),
    ('zh-hans', _('Simplified Chinese')),
    ('zh-hant', _('Traditional Chinese')),
]

BLEACH_USER_SAFE_TAGS = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'b', 'i', 'strong', 'em', 'tt', 'del', 'kbd', 's', 'abbr', 'cite', 'mark', 'q', 'samp', 'small',
    'u', 'var', 'wbr', 'dfn', 'ruby', 'rb', 'rp', 'rt', 'rtc', 'sub', 'sup', 'time', 'data',
    'p', 'br', 'pre', 'span', 'div', 'blockquote', 'code', 'hr',
    'ul', 'ol', 'li', 'dd', 'dl', 'dt', 'address', 'section', 'details', 'summary',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col', 'tfoot',
    'img', 'audio', 'video', 'source',
    'a',
    'style', 'noscript', 'center',
]

BLEACH_USER_SAFE_ATTRS = {
    '*': ['id', 'class', 'style'],
    'img': ['src', 'alt', 'title', 'width', 'height', 'data-src'],
    'a': ['href', 'alt', 'title'],
    'abbr': ['title'],
    'dfn': ['title'],
    'time': ['datetime'],
    'data': ['value'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
    'audio': ['autoplay', 'controls', 'crossorigin', 'muted', 'loop', 'preload', 'src'],
    'video': ['autoplay', 'controls', 'crossorigin', 'height', 'muted', 'loop', 'poster', 'preload', 'src', 'width'],
    'source': ['src', 'srcset', 'type'],
}

MARKDOWN_STAFF_EDITABLE_STYLE = {
    'safe_mode': False,
    'use_camo': True,
    'texoid': True,
    'math': True,
    'bleach': {
        'tags': BLEACH_USER_SAFE_TAGS,
        'attributes': BLEACH_USER_SAFE_ATTRS,
        'styles': True,
        'mathml': True,
    },
}

MARKDOWN_ADMIN_EDITABLE_STYLE = {
    'safe_mode': False,
    'use_camo': True,
    'texoid': True,
    'math': True,
}

MARKDOWN_DEFAULT_STYLE = {
    'safe_mode': True,
    'nofollow': True,
    'use_camo': True,
    'math': True,
}

MARKDOWN_USER_LARGE_STYLE = {
    'safe_mode': True,
    'nofollow': True,
    'use_camo': True,
    'math': True,
}

MARKDOWN_STYLES = {
    'default': MARKDOWN_DEFAULT_STYLE,
    'comment': MARKDOWN_DEFAULT_STYLE,
    'self-description': MARKDOWN_USER_LARGE_STYLE,
    'problem': MARKDOWN_STAFF_EDITABLE_STYLE,
    'problem-full': MARKDOWN_ADMIN_EDITABLE_STYLE,
    'contest': MARKDOWN_STAFF_EDITABLE_STYLE,
    'flatpage': MARKDOWN_ADMIN_EDITABLE_STYLE,
    'language': MARKDOWN_STAFF_EDITABLE_STYLE,
    'license': MARKDOWN_STAFF_EDITABLE_STYLE,
    'judge': MARKDOWN_STAFF_EDITABLE_STYLE,
    'blog': MARKDOWN_STAFF_EDITABLE_STYLE,
    'solution': MARKDOWN_STAFF_EDITABLE_STYLE,
    'contest_tag': MARKDOWN_STAFF_EDITABLE_STYLE,
    'organization-about': MARKDOWN_USER_LARGE_STYLE,
    'ticket': MARKDOWN_USER_LARGE_STYLE,
}

MARTOR_ENABLE_CONFIGS = {
    'imgur': 'true',
    'mention': 'true',
    'jquery': 'false',
    'living': 'false',
    'spellcheck': 'false',
    'hljs': 'false',
}
MARTOR_MARKDOWNIFY_URL = '/widgets/preview/default'
MARTOR_SEARCH_USERS_URL = '/widgets/martor/search-user'
MARTOR_UPLOAD_URL = '/widgets/martor/upload-image'
MARTOR_MARKDOWN_BASE_MENTION_URL = '/user/'

# Directory under MEDIA_ROOT to use to store image uploaded through martor.
MARTOR_UPLOAD_MEDIA_DIR = 'martor'
MARTOR_UPLOAD_SAFE_EXTS = {'.jpg', '.png', '.gif'}

# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    },
}

ENABLE_FTS = False

# Bridged configuration
BRIDGED_JUDGE_ADDRESS = [('localhost', 9999)]
BRIDGED_JUDGE_PROXIES = None
BRIDGED_DJANGO_ADDRESS = [('localhost', 9998)]
BRIDGED_DJANGO_CONNECT = None

# Event Server configuration
EVENT_DAEMON_USE = False
EVENT_DAEMON_POST = 'ws://localhost:9997/'
EVENT_DAEMON_GET = 'ws://localhost:9996/'
EVENT_DAEMON_POLL = '/channels/'
EVENT_DAEMON_KEY = None
EVENT_DAEMON_AMQP_EXCHANGE = 'dmoj-events'
EVENT_DAEMON_SUBMISSION_KEY = '6Sdmkx^%pk@GsifDfXcwX*Y7LRF%RGT8vmFpSxFBT$fwS7trc8raWfN#CSfQuKApx&$B#Gh2L7p%W!Ww'

# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

# Whatever you do, this better be one of the entries in `LANGUAGES`.
LANGUAGE_CODE = 'en'
TIME_ZONE = 'UTC'
DEFAULT_USER_TIME_ZONE = 'America/Toronto'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Cookies
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# 세션 만료 시간 설정
SESSION_COOKIE_AGE = 3600  # 1시간 (1시간 후 자동 로그아웃)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_MAX_AGE = None

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

SESSION_COOKIE_NAME = 'dmoj_sessionid'
CSRF_COOKIE_NAME = 'dmoj_csrftoken'

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

DMOJ_RESOURCES = os.path.join(BASE_DIR, 'resources')
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
)
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'resources'),
    "/home/ubuntu/dmojsite/static"
]
STATIC_URL = '/static/'

# Define a cache
CACHES = {}

# Authentication
AUTHENTICATION_BACKENDS = (
    'social_core.backends.google.GoogleOAuth2',
    'social_core.backends.facebook.FacebookOAuth2',
    'judge.social_auth.GitHubSecureEmailOAuth2',
    'django.contrib.auth.backends.ModelBackend',
    'social_core.backends.keycloak.KeycloakOAuth2',
)

DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

# 키클락 연동 #
SOCIAL_AUTH_KEYCLOAK_KEY = env("SOCIAL_AUTH_KEYCLOAK_KEY")
SOCIAL_AUTH_KEYCLOAK_SECRET = env("SOCIAL_AUTH_KEYCLOAK_SECRET")
SOCIAL_AUTH_KEYCLOAK_PUBLIC_KEY = env('SOCIAL_AUTH_KEYCLOAK_PUBLIC_KEY')
SOCIAL_AUTH_KEYCLOAK_DOMAIN = env("SOCIAL_AUTH_KEYCLOAK_DOMAIN")
SOCIAL_AUTH_KEYCLOAK_REALM = env("SOCIAL_AUTH_KEYCLOAK_REALM")
SOCIAL_AUTH_KEYCLOAK_ALGORITHM = env("SOCIAL_AUTH_KEYCLOAK_ALGORITHM")
SOCIAL_AUTH_KEYCLOAK_EXTRA_ARGUMENTS = env.json("SOCIAL_AUTH_KEYCLOAK_EXTRA_ARGUMENTS", default={})
SOCIAL_AUTH_JWT_AUDIENCE = env("SOCIAL_AUTH_JWT_AUDIENCE")
SOCIAL_AUTH_KEYCLOAK_ID_KEY = env('SOCIAL_AUTH_KEYCLOAK_ID_KEY')

SOCIAL_AUTH_KEYCLOAK_AUTHORIZATION_URL = 'https://{domain}/realms/{realm}/protocol/openid-connect/auth'.format(domain=SOCIAL_AUTH_KEYCLOAK_DOMAIN, realm=SOCIAL_AUTH_KEYCLOAK_REALM)
SOCIAL_AUTH_KEYCLOAK_ACCESS_TOKEN_URL = 'https://{domain}/realms/{realm}/protocol/openid-connect/token'.format(domain=SOCIAL_AUTH_KEYCLOAK_DOMAIN, realm=SOCIAL_AUTH_KEYCLOAK_REALM)
SOCIAL_AUTH_KEYCLOAK_USERINFO_URL = 'https://{domain}/realms/{realm}/protocol/openid-connect/userinfo'.format(domain=SOCIAL_AUTH_KEYCLOAK_DOMAIN, realm=SOCIAL_AUTH_KEYCLOAK_REALM)

SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'judge.social_auth.verify_email',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.social_auth.associate_by_email',
    # 최초 로그인 시 회원가입 하라는 메시지를 띄우는 파이프라인
    'judge.custom_pipeline.check_existing_user', 
    # 기존 파이프라인 - 기존 리트머스 계정이 없고 키클락 로그인 시도한 경우 인증 에러가 뜸
    # 'judge.social_auth.choose_username',
    #'social_core.pipeline.user.create_user',
    # 'judge.social_auth.make_profile',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'judge.keycloak.save_keycloak_tokens',
    'social_core.pipeline.user.user_details',
)

SOCIAL_AUTH_GITHUB_SECURE_SCOPE = ['user:email']
SOCIAL_AUTH_FACEBOOK_SCOPE = ['email']
SOCIAL_AUTH_SLUGIFY_USERNAMES = True
SOCIAL_AUTH_SLUGIFY_FUNCTION = 'judge.social_auth.slugify_username'

# MOSS_API_KEY = env('MOSS_API_KEY')

CELERY_WORKER_HIJACK_ROOT_LOGGER = False

WEBAUTHN_RP_ID = None

try:
    with open(os.path.join(os.path.dirname(__file__), 'local_settings.py')) as f:
        exec(f.read(), globals())
except IOError:
    pass


# Check settings are consistent
assert DMOJ_PROBLEM_MIN_USER_POINTS_VOTE >= DMOJ_PROBLEM_MIN_PROBLEM_POINTS

