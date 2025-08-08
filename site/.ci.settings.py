#####################################
######## CI/CD 테스트 환경 설정 ########
#####################################
# 이 파일은 GitHub Actions CI/CD 파이프라인에서 자동화된 테스트를 위한 설정입니다.
# .github/workflows/build.yml에서 이 파일을 dmoj/local_settings.py로 복사하여 사용합니다.
#
# 주의사항:
# - 이 설정은 GitHub Actions 러너의 임시 테스트 환경에서만 사용됩니다
# - 실제 운영 환경의 데이터베이스 설정과는 완전히 별개입니다
# - GitHub Actions MySQL 서비스의 기본 설정(root/root)을 사용합니다

COMPRESS_OUTPUT_DIR = 'cache'
STATICFILES_FINDERS += ('compressor.finders.CompressorFinder',)
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# 테스트 환경용 캐시 설정 (인메모리 캐시 사용)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'
    }
}

# 테스트 환경용 데이터베이스 설정
# GitHub Actions MySQL 서비스의 기본 설정을 사용합니다
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'dmoj',
        'USER': 'root',  # GitHub Actions MySQL 기본 사용자
        'PASSWORD': 'root',  # GitHub Actions MySQL 기본 비밀번호
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    },
}
