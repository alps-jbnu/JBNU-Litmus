from types import SimpleNamespace

from django.test import SimpleTestCase

from judge.utils.email_domain import (
    EXTERNAL_SCHOOL_EMAIL_DOMAIN,
    GMAIL_EMAIL_DOMAIN,
    JBNU_EMAIL_DOMAIN,
    build_school_email,
)


class RegistrationEmailDomainTestCase(SimpleTestCase):
    def test_jbnu_school_uses_jbnu_domain(self):
        email, errors = build_school_email(
            SimpleNamespace(is_jbnu=True),
            '202400001',
            JBNU_EMAIL_DOMAIN,
        )

        self.assertEqual(email, '202400001@jbnu.ac.kr')
        self.assertEqual(errors, [])

    def test_jbnu_school_can_use_gmail_domain(self):
        email, errors = build_school_email(
            SimpleNamespace(is_jbnu=True),
            'student',
            GMAIL_EMAIL_DOMAIN,
        )

        self.assertEqual(email, 'student@gmail.com')
        self.assertEqual(errors, [])

    def test_jbnu_school_can_use_custom_domain(self):
        email, errors = build_school_email(
            SimpleNamespace(is_jbnu=True),
            'student',
            ' @Naver.COM ',
        )

        self.assertEqual(email, 'student@naver.com')
        self.assertEqual(errors, [])

    def test_jbnu_school_requires_domain(self):
        email, errors = build_school_email(
            SimpleNamespace(is_jbnu=True),
            'student',
            '',
        )

        self.assertEqual(email, '')
        self.assertEqual(errors, ['이메일 도메인을 선택하거나 입력해주세요.'])

    def test_jbnu_school_rejects_invalid_custom_domain(self):
        for domain in ('naver', '@localhost', 'naver..com', 'na ver.com', 'naver.com@evil.com'):
            with self.subTest(domain=domain):
                email, errors = build_school_email(
                    SimpleNamespace(is_jbnu=True),
                    'student',
                    domain,
                )

                self.assertEqual(email, '')
                self.assertEqual(errors, ['올바른 이메일 주소를 입력해주세요.'])

    def test_external_school_uses_jbedu_domain(self):
        email, errors = build_school_email(
            SimpleNamespace(is_jbnu=False),
            'student',
            EXTERNAL_SCHOOL_EMAIL_DOMAIN,
        )

        self.assertEqual(email, 'student@g.jbedu.kr')
        self.assertEqual(errors, [])

    def test_external_school_rejects_gmail_for_new_registration(self):
        email, errors = build_school_email(
            SimpleNamespace(is_jbnu=False),
            'student',
            '@gmail.com',
        )

        self.assertEqual(email, 'student@g.jbedu.kr')
        self.assertEqual(errors, ['외부 학교는 @g.jbedu.kr 이메일만 사용 가능합니다.'])

    def test_missing_domain_still_builds_expected_external_email(self):
        email, errors = build_school_email(
            SimpleNamespace(is_jbnu=False),
            'student',
            '',
        )

        self.assertEqual(email, 'student@g.jbedu.kr')
        self.assertEqual(errors, [])

    def test_missing_school_uses_external_rule(self):
        email, errors = build_school_email(None, 'student', '')

        self.assertEqual(email, 'student@g.jbedu.kr')
        self.assertEqual(errors, [])
