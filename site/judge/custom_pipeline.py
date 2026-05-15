# judge/custom_pipeline.py
from django.http import HttpResponseRedirect
from django.urls import reverse


def assign_school_on_keycloak_login(backend, details, user, *args, **kwargs):
    """
    Keycloak 인증 후 school 처리.
    - 리트머스 계정 없음(user=None) → 회원가입 리다이렉트
    - 이메일 미인증(is_active=False) → 로그인 페이지로 리다이렉트 (안내 메시지 포함)
    - @jbnu.ac.kr → is_jbnu=True인 School 자동 할당 (school이 아직 없는 경우만)
    - @gmail.com → school은 가입 시 이미 설정됨, 파이프라인에서 변경하지 않음
    """
    if user is None:
        request = backend.strategy.request
        request.session.flush()
        return HttpResponseRedirect(reverse('registration_register'))

    if not user.is_active:
        request = backend.strategy.request
        request.session.flush()
        return HttpResponseRedirect(reverse('activation_required'))

    email = details.get('email', '')
    domain = email.split('@')[-1].lower() if '@' in email else ''

    if domain == 'jbnu.ac.kr' and user.profile.school is None:
        try:
            from judge.models.profile import School
            jbnu_school = School.objects.get(is_jbnu=True, is_active=True)
            user.profile.school = jbnu_school
            user.profile.save(update_fields=['school'])
        except School.DoesNotExist:
            pass

    return {}
