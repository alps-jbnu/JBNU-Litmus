from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from judge.forms import CustomAuthenticationForm
from judge.models import Profile
from judge.models.tests.util import CommonDataMixin


class LoginLockoutTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = cls.users['normal']
        cls.user.set_password('correct-password')
        cls.user.save(update_fields=['password'])
        cls.profile = cls.user.profile

    def make_form(self, password):
        return CustomAuthenticationForm(data={
            'username': self.user.username,
            'password': password,
        })

    def test_account_is_locked_after_five_failed_attempts(self):
        base_time = timezone.now()

        with patch('judge.models.profile.timezone.now', return_value=base_time):
            form = self.make_form('wrong-password')
            self.assertFalse(form.is_valid())
            self.assertEqual(form.login_failure_status_message, '현재 로그인 실패: 1/5회')
            self.assertEqual(form.errors['username'][0], '아이디 또는 비밀번호가 잘못되었습니다.')

            for _ in range(3):
                form = self.make_form('wrong-password')
                self.assertFalse(form.is_valid())

            self.profile.refresh_from_db()
            self.assertEqual(self.profile.failed_login_attempts, 4)
            self.assertIsNone(self.profile.login_locked_until)
            self.assertEqual(form.login_failure_status_message, '현재 로그인 실패: 4/5회')
            self.assertEqual(form.errors['username'][0], '아이디 또는 비밀번호가 잘못되었습니다.')

            form = self.make_form('wrong-password')
            self.assertFalse(form.is_valid())
            self.assertEqual(form.login_failure_status_message, '')
            self.assertEqual(form.errors['username'][0], '로그인 시도가 너무 많습니다. 10분 후 다시 시도해 주세요.')

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.failed_login_attempts, 0)
        self.assertEqual(self.profile.login_locked_until, base_time + timedelta(minutes=10))

        with patch('judge.models.profile.timezone.now', return_value=base_time + timedelta(minutes=1)):
            form = self.make_form('correct-password')
            self.assertFalse(form.is_valid())
            self.assertEqual(form.errors['username'][0], '로그인 시도가 너무 많습니다. 10분 후 다시 시도해 주세요.')

        with patch('judge.models.profile.timezone.now', return_value=base_time + timedelta(minutes=11)):
            form = self.make_form('correct-password')
            self.assertTrue(form.is_valid(), form.errors)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.failed_login_attempts, 0)
        self.assertIsNone(self.profile.login_locked_until)

    def test_login_page_renders_failure_status_between_error_and_inputs(self):
        response = self.client.post(reverse('auth_login'), data={
            'username': self.user.username,
            'password': 'wrong-password',
        })

        self.assertContains(response, '아이디 또는 비밀번호가 잘못되었습니다.')
        self.assertContains(response, '현재 로그인 실패: 1/5회')

        content = response.content.decode()
        error_index = content.index('아이디 또는 비밀번호가 잘못되었습니다.')
        status_index = content.index('현재 로그인 실패: 1/5회')
        username_input_index = content.index('name="username"')

        self.assertLess(error_index, status_index)
        self.assertLess(status_index, username_input_index)

    def test_login_failure_recreates_missing_profile_and_shows_counter(self):
        Profile.objects.filter(user=self.user).delete()

        form = self.make_form('wrong-password')
        self.assertFalse(form.is_valid())
        self.assertEqual(form.login_failure_status_message, '현재 로그인 실패: 1/5회')
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

    def test_missing_username_still_shows_failure_counter(self):
        response = self.client.post(reverse('auth_login'), data={
            'username': 'definitely_missing_user',
            'password': 'wrong-password',
        })

        self.assertContains(response, '아이디 또는 비밀번호가 잘못되었습니다.')
        self.assertContains(response, '현재 로그인 실패: 1/5회')
