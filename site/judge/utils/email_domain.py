from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.utils.translation import gettext

# 회원가입과 관리자 이메일 변경 화면이 함께 쓰는 이메일 도메인 규칙.
# 전북대(is_jbnu=True) 소속은 목록의 도메인을 고르거나 직접 입력할 수 있고,
# 그 외(외부 학교) 소속은 g.jbedu.kr만 사용할 수 있다.
JBNU_EMAIL_DOMAIN = '@jbnu.ac.kr'
GMAIL_EMAIL_DOMAIN = '@gmail.com'
JBNU_EMAIL_DOMAIN_CHOICES = (JBNU_EMAIL_DOMAIN, GMAIL_EMAIL_DOMAIN)
EXTERNAL_SCHOOL_EMAIL_DOMAIN = '@g.jbedu.kr'

# 기본 EmailValidator는 localhost를 허용하므로 허용 목록을 비운다.
validate_school_email = EmailValidator(allowlist=[])


def can_choose_email_domain(school):
    return bool(school and school.is_jbnu)


def normalize_email_domain(email_domain):
    domain = (email_domain or '').strip().lstrip('@').lower()
    return '@' + domain if domain else ''


def build_school_email(school, email_local, email_domain):
    """학교 규칙에 맞춰 이메일 주소를 만들고 (이메일, 오류 목록)을 돌려준다."""
    if not email_local:
        return '', []

    domain = normalize_email_domain(email_domain)
    if can_choose_email_domain(school):
        if not domain:
            return '', [gettext('이메일 도메인을 선택하거나 입력해주세요.')]
    else:
        if domain and domain != EXTERNAL_SCHOOL_EMAIL_DOMAIN:
            return f'{email_local}{EXTERNAL_SCHOOL_EMAIL_DOMAIN}', [
                gettext('외부 학교는 %(domain)s 이메일만 사용 가능합니다.') % {
                    'domain': EXTERNAL_SCHOOL_EMAIL_DOMAIN,
                },
            ]
        domain = EXTERNAL_SCHOOL_EMAIL_DOMAIN

    email = f'{email_local}{domain}'
    try:
        validate_school_email(email)
    except ValidationError:
        return '', [gettext('올바른 이메일 주소를 입력해주세요.')]
    return email, []
