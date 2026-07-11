from types import SimpleNamespace

from django.test import SimpleTestCase

from judge.views.register import (
    EXTERNAL_SCHOOL_EMAIL_DOMAIN,
    JBNU_EMAIL_DOMAIN,
    _build_registration_email,
)


class RegistrationEmailDomainTestCase(SimpleTestCase):
    def test_jbnu_school_uses_jbnu_domain(self):
        email, errors = _build_registration_email(
            SimpleNamespace(is_jbnu=True),
            '202400001',
            JBNU_EMAIL_DOMAIN,
        )

        self.assertEqual(email, '202400001@jbnu.ac.kr')
        self.assertEqual(errors, [])

    def test_external_school_uses_jbedu_domain(self):
        email, errors = _build_registration_email(
            SimpleNamespace(is_jbnu=False),
            'student',
            EXTERNAL_SCHOOL_EMAIL_DOMAIN,
        )

        self.assertEqual(email, 'student@g.jbedu.kr')
        self.assertEqual(errors, [])

    def test_external_school_rejects_gmail_for_new_registration(self):
        email, errors = _build_registration_email(
            SimpleNamespace(is_jbnu=False),
            'student',
            '@gmail.com',
        )

        self.assertEqual(email, 'student@g.jbedu.kr')
        self.assertEqual(errors, ['외부 학교는 @g.jbedu.kr 이메일만 사용 가능합니다.'])

    def test_missing_domain_still_builds_expected_external_email(self):
        email, errors = _build_registration_email(
            SimpleNamespace(is_jbnu=False),
            'student',
            '',
        )

        self.assertEqual(email, 'student@g.jbedu.kr')
        self.assertEqual(errors, [])
