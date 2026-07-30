from django.test import TestCase

from judge.forms import ProfileForm
from judge.models import Language
from judge.models.tests.util import CommonDataMixin


class ProfileAboutFormTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = cls.users['normal']
        cls.profile = cls.user.profile
        cls.language = Language.objects.get(pk=cls.profile.language_id)

    def make_form(self, about):
        return ProfileForm(
            data={
                'about': about,
                'timezone': self.profile.timezone,
                'language': self.language.pk,
                'ace_theme': self.profile.ace_theme,
                'site_theme': self.profile.site_theme,
                'user_script': self.profile.user_script,
                'math_engine': self.profile.math_engine,
                'test_site': '',
            },
            instance=self.profile,
            user=self.user,
        )

    def test_clean_about_strips_script_tag(self):
        form = self.make_form('<script>alert(1)</script>hello')

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['about'], 'alert(1)hello')

    def test_clean_about_strips_style_tag(self):
        form = self.make_form('<style>body{color:red}</style>hello')

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['about'], 'body{color:red}hello')
