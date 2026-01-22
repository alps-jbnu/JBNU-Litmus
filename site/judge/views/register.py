# coding=utf-8
import re
import json
from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import get_default_password_validators, validate_password
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.forms import ChoiceField, ModelChoiceField
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from registration.backends.default.views import (ActivationView as OldActivationView,
                                                 RegistrationView as OldRegistrationView)
from registration.forms import RegistrationForm
from sortedm2m.forms import SortedMultipleChoiceField

# from judge.models import Language, Organization, Profile, TIMEZONE
from judge.models import Language, Profile, Department, TIMEZONE

from judge.utils.recaptcha import ReCaptchaField, ReCaptchaWidget
from judge.utils.subscription import Subscription, newsletter_id
from judge.widgets import Select2MultipleWidget, Select2Widget



bad_mail_regex = list(map(re.compile, settings.BAD_MAIL_PROVIDER_REGEX))

@csrf_exempt
def validate_password_method(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            password = data.get('password', '')
            print(f"Received password for validation: {password}")  # 디버깅 메시지

            validators = get_default_password_validators()
            errors = []
            
            try:
                validate_password(password, password_validators=validators)
                return JsonResponse({'is_valid': True})
            except ValidationError as e:
                errors = [str(error) for error in e.messages]
                print(f"Validation errors: {errors}")  # 디버깅 메시지
                return JsonResponse({'errors': errors})
        except Exception as e:
            print(f"Unexpected error: {e}")  # 디버깅 메시지
            return JsonResponse({'errors': ['Internal Server Error']}, status=500)
    return JsonResponse({'errors': ['Invalid request method.']})


class CustomRegistrationForm(RegistrationForm):
    username = forms.RegexField(
        regex=r'^\d+$',
        max_length=9,
        label=_('Username'),
        error_messages={'invalid': '학번은 숫자만 입력해야 합니다.'},
        widget=forms.TextInput(attrs={'placeholder': _('학번 (아이디)')})
    )

    # 이름
    first_name = forms.CharField(
        max_length=30,
        label=_('first name'),
        # label=_('FirstName'),
        widget=forms.TextInput(attrs={'placeholder': '이름'})
    )

    # 이메일

    # 변경 전 
    # email = forms.EmailField(
    #     widget=forms.EmailInput(attrs={'placeholder': _('이메일')})
    # ) 

    ## 변경 후
    email_local = forms.CharField(
        max_length=64,
        widget=forms.TextInput(attrs={'placeholder': _('이메일'), 'class': 'email_local'}),
        validators=[
            RegexValidator(
                regex=r'^(?!.*\.\.)(?!\.)[a-zA-Z0-9._+-]+(?<!\.)$',
                message='영문자, 숫자, 그리고 일부 특수 문자(., -, _, +)만 사용할 수 있습니다. 마침표로 시작하거나 끝나는 것은 허용되지 않습니다.'
            )
        ],
        label=_('Email')
    )
    email_domain = forms.CharField(
        max_length=50,
        initial='@jbnu.ac.kr',
        widget=forms.HiddenInput(),
        required=False
    )
    email = forms.EmailField(
        widget=forms.HiddenInput(),  # 사용자에게 보이지 않는 숨겨진 필드
        required=False
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': _('비밀번호'), 'maxlength': '100', 'autocomplete': 'off'}),
        label=_('Password')
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': _('비밀번호 확인'), 'maxlength': '100', 'autocomplete': 'off'}),
        label=_('Password Confirmation')
    )
    ## html에서 쓰이지 않을 필드는 주석처리 필요
    # timezone = ChoiceField(label=_('Timezone'), choices=TIMEZONE,
    #                        widget=Select2Widget(attrs={'style': 'width:100%'}))
    language = ModelChoiceField(queryset=Language.objects.all(), label=_('Preferred language'), empty_label=None,
                                widget=Select2Widget(attrs={'style': 'width:100%', 'data-maximum-input-length': '50'}))
    department = ModelChoiceField(queryset=Department.objects.all(), label=_('학과 리스트'), empty_label=None,
                                widget=Select2Widget(attrs={'style': 'width:100%', 'data-maximum-input-length': '50'}))
    # organizations = SortedMultipleChoiceField(queryset=Organization.objects.filter(is_open=True),
    #                                           label=_('Organizations'), required=False,
    #                                           widget=Select2MultipleWidget(attrs={'style': 'width:100%'}))

    if newsletter_id is not None:
        newsletter = forms.BooleanField(label=_('Subscribe to newsletter?'), initial=True, required=False)

    if ReCaptchaField is not None:
        captcha = ReCaptchaField(widget=ReCaptchaWidget())

    # 변경 전
    # def clean_email(self):
    #     if User.objects.filter(email=self.cleaned_data['email']).exists():
    #         raise forms.ValidationError(gettext('The email address "%s" is already taken. Only one registration '
    #                                             'is allowed per address.') % self.cleaned_data['email'])
    #     if '@' in self.cleaned_data['email']:
    #         domain = self.cleaned_data['email'].split('@')[-1].lower()
    #         if (domain in settings.BAD_MAIL_PROVIDERS or
    #                 any(regex.match(domain) for regex in bad_mail_regex)):
    #             raise forms.ValidationError(gettext('Your email provider is not allowed due to history of abuse. '
    #                                                 'Please use a reputable email provider.'))
    #     return self.cleaned_data['email']

    # 변경 후
    # def clean_email_local(self):
    #     email_local = self.cleaned_data.get('email_local')
        
    def clean(self):
        cleaned_data = super().clean()
        email_local = cleaned_data.get('email_local')
        email_domain = cleaned_data.get('email_domain')

        # 이메일 주소 재구성
        email = f"{email_local}@jbnu.ac.kr"
        
        # email_domain이 올바른 도메인인지 확인
        if email_domain != "@jbnu.ac.kr":
            raise forms.ValidationError(gettext('유효하지 않은 이메일 도메인입니다. (jbnu.ac.kr의 도메인 필수)'), code='email')

        cleaned_data['email'] = email
        
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(gettext('해당 이메일은 이미 존재하는 이메일입니다.'), code='email')
        domain = email.split('@')[-1].lower()
        if (domain in settings.BAD_MAIL_PROVIDERS or
                any(regex.match(domain) for regex in bad_mail_regex)):
            raise forms.ValidationError(gettext('Your email provider is not allowed due to history of abuse. '
                                                'Please use a reputable email provider.'), code='email')
        
        return cleaned_data

    def clean_username(self):
        username = self.cleaned_data.get('username')
        
        if len(username) != 5 and len(username) != 9:
            raise forms.ValidationError('학번을 올바르게 입력해주세요.')
            
        if len(username) == 9:
            year_part = username[2:4]  # 예: 202320202 에서 '23' 추출
            try:
                year = int(year_part)
                if year < 15 or year > 26:
                    raise forms.ValidationError('15학번부터 26학번까지만 가입이 가능합니다.')
            except ValueError:
                raise forms.ValidationError('올바른 학번 형식이 아닙니다.')
                
        return username

    # def clean_organizations(self):
    #     organizations = self.cleaned_data.get('organizations') or []
    #     max_orgs = settings.DMOJ_USER_MAX_ORGANIZATION_COUNT
    #     if len(organizations) > max_orgs:
    #         raise forms.ValidationError(ngettext('You may not be part of more than {count} public organization.',
    #                                              'You may not be part of more than {count} public organizations.',
    #                                              max_orgs).format(count=max_orgs))
    #     return self.cleaned_data['organizations']


class RegistrationView(OldRegistrationView):
    title = _('Register')
    form_class = CustomRegistrationForm
    template_name = 'registration/registration_form.html'

    def get_context_data(self, **kwargs):
        if 'title' not in kwargs:
            kwargs['title'] = self.title
        tzmap = settings.TIMEZONE_MAP
        kwargs['TIMEZONE_MAP'] = tzmap or 'http://momentjs.com/static/img/world.png'
        kwargs['TIMEZONE_BG'] = settings.TIMEZONE_BG if tzmap else '#4E7CAD'
        kwargs['password_validators'] = get_default_password_validators()
        kwargs['tos_url'] = settings.TERMS_OF_SERVICE_URL
        kwargs['validate_password_url'] = reverse('validate_password')
        return super(RegistrationView, self).get_context_data(**kwargs)

    def register(self, form):
        # super().register(form) 사용하지 않고 직접 유저 생성
        cleaned_data = form.cleaned_data
        username = cleaned_data['username']
        password = cleaned_data['password1']
        email = cleaned_data['email']
        first_name = cleaned_data['first_name']

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name
        )
        user.is_active = True  # 메일 인증 없이 바로 활성화
        user.save()

        profile, _ = Profile.objects.get_or_create(user=user, defaults={
            'language': Language.get_default_language(),
        })
        profile.timezone = settings.DEFAULT_USER_TIME_ZONE
        profile.language = cleaned_data['language']
        profile.department = cleaned_data['department']
        profile.save()

        if newsletter_id is not None and cleaned_data['newsletter']:
            Subscription(user=user, newsletter_id=newsletter_id, subscribed=True).save()
        return user


    def get_initial(self, *args, **kwargs):
        initial = super(RegistrationView, self).get_initial(*args, **kwargs)
        initial['timezone'] = settings.DEFAULT_USER_TIME_ZONE
        initial['language'] = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
        return initial
     

class ActivationView(OldActivationView):
    title = _('Activation Key Invalid')
    template_name = 'registration/activate.html'

    def get_context_data(self, **kwargs):
        if 'title' not in kwargs:
            kwargs['title'] = self.title
        return super(ActivationView, self).get_context_data(**kwargs)


def social_auth_error(request):
    return render(request, 'generic-message.html', {
        'title': gettext('Authentication failure'),
        'message': request.GET.get('message'),
    })
