import json
from operator import attrgetter, itemgetter

from django.http import Http404
import pyotp
import webauthn
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm,PasswordResetForm
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.models import User
from django.db.models import Q
from django.forms import BooleanField, CharField, ChoiceField, Form, ModelForm, MultipleChoiceField
from django.urls import reverse_lazy
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _, ngettext_lazy

from django_ace import AceWidget
# from judge.models import Contest, Language, Organization, Problem, ProblemPointsVote, Profile, Submission, \
#     WebAuthnCredential
from judge.models import Contest, Language, Problem, ProblemPointsVote, Profile, Submission, \
    WebAuthnCredential
from judge.utils.subscription import newsletter_id
from judge.widgets import HeavyPreviewPageDownWidget, Select2MultipleWidget, Select2Widget

from django.contrib.auth.backends import get_user_model
from importlib import import_module
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from bleach import clean

User = get_user_model()

TOTP_CODE_LENGTH = 6

two_factor_validators_by_length = {
    TOTP_CODE_LENGTH: {
        'regex_validator': RegexValidator(
            f'^[0-9]{{{TOTP_CODE_LENGTH}}}$',
            format_lazy(ngettext_lazy('Two-factor authentication tokens must be {count} decimal digit.',
                                      'Two-factor authentication tokens must be {count} decimal digits.',
                                      TOTP_CODE_LENGTH), count=TOTP_CODE_LENGTH),
        ),
        'verify': lambda code, profile: not profile.check_totp_code(code),
        'err': _('Invalid two-factor authentication token.'),
    },
    16: {
        'regex_validator': RegexValidator('^[A-Z0-9]{16}$', _('Scratch codes must be 16 Base32 characters.')),
        'verify': lambda code, profile: code not in json.loads(profile.scratch_codes),
        'err': _('Invalid scratch code.'),
    },
}


class ProfileForm(ModelForm):
    if newsletter_id is not None:
        newsletter = forms.BooleanField(label=_('Subscribe to contest updates'), initial=False, required=False)
    test_site = forms.BooleanField(label=_('Enable experimental features'), initial=False, required=False)

    class Meta:
        model = Profile
        # fields = ['about', 'organizations', 'timezone', 'language', 'ace_theme', 'user_script']
        fields = ['about', 'timezone', 'language', 'ace_theme', 'user_script']
        widgets = {
            'user_script': AceWidget(theme='github'),
            'timezone': Select2Widget(attrs={'style': 'width:200px'}),
            'language': Select2Widget(attrs={'style': 'width:200px'}),
            'ace_theme': Select2Widget(attrs={'style': 'width:200px'}),
        }

        has_math_config = bool(settings.MATHOID_URL)
        if has_math_config:
            fields.append('math_engine')
            widgets['math_engine'] = Select2Widget(attrs={'style': 'width:200px'})

        if HeavyPreviewPageDownWidget is not None:
            widgets['about'] = HeavyPreviewPageDownWidget(
                preview=reverse_lazy('profile_preview'),
                attrs={'style': 'max-width:700px;min-width:700px;width:700px', 'data-max-chars': '1000'},
            )

    # 수정 전S
    # def clean_about(self):
    #     if 'about' in self.changed_data and not self.instance.has_any_solves:
    #         raise ValidationError(_('You must solve at least one problem before you can update your profile.'))
    #     return self.cleaned_data['about']

    # 수정 후
    def clean_about(self):
        if not True:
            raise ValidationError(_('You must solve at least one problem before you can update your profile.'))

        about = self.cleaned_data['about']
        if len(about) > 1000:
            raise ValidationError(_('자기소개는 1000자 이내로 작성해주세요.'))
        
        sanitized_about = clean(
            about,
            tags=settings.BLEACH_USER_SAFE_TAGS,
            attributes=settings.BLEACH_USER_SAFE_ATTRS,
            strip=True
        )
        
        return sanitized_about

    # def clean(self):
    #     organizations = self.cleaned_data.get('organizations') or []
    #     max_orgs = settings.DMOJ_USER_MAX_ORGANIZATION_COUNT

    #     if sum(org.is_open for org in organizations) > max_orgs:
    #         raise ValidationError(ngettext_lazy('You may not be part of more than {count} public organization.',
    #                                             'You may not be part of more than {count} public organizations.',
    #                                             max_orgs).format(count=max_orgs))

    #     return self.cleaned_data

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(ProfileForm, self).__init__(*args, **kwargs)
        # if not user.has_perm('judge.edit_all_organization'):
        #     self.fields['organizations'].queryset = Organization.objects.filter(
        #         Q(is_open=True) | Q(id__in=user.profile.organizations.all()),
        #     )
        # if not self.fields['organizations'].queryset:
        #     self.fields.pop('organizations')


class DownloadDataForm(Form):
    comment_download = BooleanField(required=False, label=_('Download comments?'))
    submission_download = BooleanField(required=False, label=_('Download submissions?'))
    submission_problem_glob = CharField(initial='*', label=_('Filter by problem code glob:'), max_length=100)
    submission_results = MultipleChoiceField(
        required=False,
        widget=Select2MultipleWidget(
            attrs={'style': 'width: 260px', 'data-placeholder': _('Leave empty to include all submissions')},
        ),
        choices=sorted(map(itemgetter(0, 0), Submission.RESULT)),
        label=_('Filter by result:'),
    )

    def clean(self):
        can_download = ('comment_download', 'submission_download')
        if not any(self.cleaned_data[v] for v in can_download):
            raise ValidationError(_('Please select at least one thing to download.'))
        return self.cleaned_data

    def clean_submission_problem_glob(self):
        if not self.cleaned_data['submission_download']:
            return '*'
        return self.cleaned_data['submission_problem_glob']

    def clean_submission_result(self):
        if not self.cleaned_data['submission_download']:
            return ()
        return self.cleaned_data['submission_result']


class ProblemSubmitForm(ModelForm):
    source = CharField(max_length=65536, widget=AceWidget(theme='twilight', no_ace_media=True))
    judge = ChoiceField(choices=(), widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, judge_choices=(), **kwargs):
        super(ProblemSubmitForm, self).__init__(*args, **kwargs)
        self.fields['language'].empty_label = None
        self.fields['language'].label_from_instance = attrgetter('display_name')
        self.fields['language'].queryset = Language.objects.filter(judges__online=True).distinct()

        if judge_choices:
            self.fields['judge'].widget = Select2Widget(
                attrs={'style': 'width: 150px', 'data-placeholder': _('Any judge')},
            )
            self.fields['judge'].choices = judge_choices

    class Meta:
        model = Submission
        fields = ['language']


# class EditOrganizationForm(ModelForm):
#     class Meta:
#         model = Organization
#         fields = ['about', 'logo_override_image', 'admins']
#         widgets = {'admins': Select2MultipleWidget(attrs={'style': 'width: 200px'})}
#         if HeavyPreviewPageDownWidget is not None:
#             widgets['about'] = HeavyPreviewPageDownWidget(preview=reverse_lazy('organization_preview'))

# 로그인 폼
class CustomAuthenticationForm(AuthenticationForm):
    error_messages = {
        'invalid_login': _(
            "아이디 또는 비밀번호가 잘못되었습니다."
        ),
        'inactive': _("인증이 완료되지 않은 계정입니다."),
    }

    def __init__(self, *args, **kwargs):
        super(CustomAuthenticationForm, self).__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'placeholder': _('아이디를 입력해 주세요'),
            'autocomplete': 'off'
        })
        self.fields['password'].widget.attrs.update({
            'placeholder': _('비밀번호를 입력해 주세요'),
            'autocomplete': 'off'
        })

        self.has_google_auth = self._has_social_auth('GOOGLE_OAUTH2')
        self.has_facebook_auth = self._has_social_auth('FACEBOOK')
        self.has_github_auth = self._has_social_auth('GITHUB_SECURE')

    def _has_social_auth(self, key):
        return (getattr(settings, 'SOCIAL_AUTH_%s_KEY' % key, None) and
                getattr(settings, 'SOCIAL_AUTH_%s_SECRET' % key, None))

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            for backend_path in settings.AUTHENTICATION_BACKENDS:
                backend = self._get_backend(backend_path)
                if backend:
                    user = self._try_login_with_backend(backend, username, password)
                    if user:
                        self.confirm_login_allowed(user)
                        user.backend = backend_path
                        self.user_cache = user
                        break
            else:
                self.add_error('username', self.error_messages['invalid_login'])

        return self.cleaned_data

    def _get_backend(self, backend_path):
        try:
            backend_module, backend_class = backend_path.rsplit('.', 1)
            module = import_module(backend_module)
            backend_cls = getattr(module, backend_class)
            return backend_cls()
        except (ImportError, AttributeError):
            return None

    def _try_login_with_backend(self, backend, username, password):
        try:
            user = backend.get_user(User.objects.get(username=username).pk)
            if user and user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
        return None

class NoAutoCompleteCharField(forms.CharField):
    def widget_attrs(self, widget):
        attrs = super(NoAutoCompleteCharField, self).widget_attrs(widget)
        attrs['autocomplete'] = 'off'
        return attrs


class TOTPForm(Form):
    TOLERANCE = settings.DMOJ_TOTP_TOLERANCE_HALF_MINUTES

    totp_or_scratch_code = NoAutoCompleteCharField(required=False)

    def __init__(self, *args, **kwargs):
        self.profile = kwargs.pop('profile')
        super().__init__(*args, **kwargs)

    def clean(self):
        totp_or_scratch_code = self.cleaned_data.get('totp_or_scratch_code')
        try:
            validator = two_factor_validators_by_length[len(totp_or_scratch_code)]
        except KeyError:
            raise ValidationError(_('Invalid code length.'))
        validator['regex_validator'](totp_or_scratch_code)
        if validator['verify'](totp_or_scratch_code, self.profile):
            raise ValidationError(validator['err'])


class TOTPEnableForm(TOTPForm):
    def __init__(self, *args, **kwargs):
        self.totp_key = kwargs.pop('totp_key')
        super().__init__(*args, **kwargs)

    def clean(self):
        totp_validate = two_factor_validators_by_length[TOTP_CODE_LENGTH]
        code = self.cleaned_data.get('totp_or_scratch_code')
        totp_validate['regex_validator'](code)
        if not pyotp.TOTP(self.totp_key).verify(code, valid_window=settings.DMOJ_TOTP_TOLERANCE_HALF_MINUTES):
            raise ValidationError(totp_validate['err'])


class TwoFactorLoginForm(TOTPForm):
    webauthn_response = forms.CharField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        self.webauthn_challenge = kwargs.pop('webauthn_challenge')
        self.webauthn_origin = kwargs.pop('webauthn_origin')
        super().__init__(*args, **kwargs)

    def clean(self):
        totp_or_scratch_code = self.cleaned_data.get('totp_or_scratch_code')
        if self.profile.is_webauthn_enabled and self.cleaned_data.get('webauthn_response'):
            if len(self.cleaned_data['webauthn_response']) > 65536:
                raise ValidationError(_('Invalid WebAuthn response.'))

            if not self.webauthn_challenge:
                raise ValidationError(_('No WebAuthn challenge issued.'))

            response = json.loads(self.cleaned_data['webauthn_response'])
            try:
                credential = self.profile.webauthn_credentials.get(cred_id=response.get('id', ''))
            except WebAuthnCredential.DoesNotExist:
                raise ValidationError(_('Invalid WebAuthn credential ID.'))

            user = credential.webauthn_user
            # Work around a useless check in the webauthn package.
            user.credential_id = credential.cred_id
            assertion = webauthn.WebAuthnAssertionResponse(
                webauthn_user=user,
                assertion_response=response.get('response'),
                challenge=self.webauthn_challenge,
                origin=self.webauthn_origin,
                uv_required=False,
            )

            try:
                sign_count = assertion.verify()
            except Exception as e:
                raise ValidationError(str(e))

            credential.counter = sign_count
            credential.save(update_fields=['counter'])
        elif totp_or_scratch_code:
            if self.profile.is_totp_enabled and self.profile.check_totp_code(totp_or_scratch_code):
                return
            elif self.profile.scratch_codes and totp_or_scratch_code in json.loads(self.profile.scratch_codes):
                scratch_codes = json.loads(self.profile.scratch_codes)
                scratch_codes.remove(totp_or_scratch_code)
                self.profile.scratch_codes = json.dumps(scratch_codes)
                self.profile.save(update_fields=['scratch_codes'])
                return
            elif self.profile.is_totp_enabled:
                raise ValidationError(_('Invalid two-factor authentication token or scratch code.'))
            else:
                raise ValidationError(_('Invalid scratch code.'))
        else:
            raise ValidationError(_('Must specify either totp_token or webauthn_response.'))


class ProblemCloneForm(Form):
    code = CharField(max_length=20, validators=[RegexValidator('^[a-z0-9]+$', _('Problem code must be ^[a-z0-9]+$'))])

    def clean_code(self):
        code = self.cleaned_data['code']
        if Problem.objects.filter(code=code).exists():
            raise ValidationError(_('Problem with code already exists.'))
        return code


class ContestCloneForm(Form):
    name = CharField(max_length=100)

    def clean_name(self):
        name = self.cleaned_data['name']
        # if Contest.objects.filter(name=name).exists():
        #     raise ValidationError(_('Contest with key already exists.'))
        return name


class ProblemPointsVoteForm(ModelForm):
    note = CharField(max_length=8192, required=False)

    class Meta:
        model = ProblemPointsVote
        fields = ['points', 'note']
        
#아이디 찾기 관련 폼
class IdFindForm(forms.Form):
    email_local = forms.CharField(
        label="이메일",
        widget=forms.TextInput(attrs={
            'class': 'email_local',
            'placeholder': _('이메일')}),
        max_length=254
    )
    # email = forms.EmailField(label="Email", max_length=254)

#비밀번호 리셋 관련 폼    
UserModel = get_user_model()
class CustomPasswordResetForm(PasswordResetForm):
    email_local = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': _('이메일'), 'class': 'email_local'}),
        label=_('Email')
    )
    email_domain = forms.CharField(
        max_length=50,
        initial='@jbnu.ac.kr',
        widget=forms.HiddenInput(),
        required=False
    )
    email = forms.EmailField(
        initial = '',
        widget=forms.HiddenInput(),  # 사용자에게 보이지 않는 숨겨진 필드
        required=False
    )
    
    username = forms.RegexField(
        regex=r'^\w+$',
        max_length=30,
        label=_('Username'),
        error_messages={'invalid': _('A username must contain letters, numbers, or underscores.')},
        widget=forms.TextInput(attrs={'placeholder': _('아이디')})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        email_local = cleaned_data.get('email_local')
        email_domain = cleaned_data.get('email_domain')

        # 이메일 주소 재구성
        email = f"{email_local}@jbnu.ac.kr"
        
        # email_domain이 올바른 도메인인지 확인
        if email_domain != "@jbnu.ac.kr":
            raise forms.ValidationError(gettext('Invalid email domain. Please use the provided domain.'))

        #해당 계정의 이메일 또는 사용자가 존재하는지 확인
        users = self.get_users(email)
        is_match_username = False
        for user in users:
            if user.get_username() == cleaned_data['username']: 
                is_match_username = True
                
        if not is_match_username:
            raise forms.ValidationError(_('입력하신 아이디 또는 이메일에 해당하는 사용자가 없습니다.'))
        else:
            cleaned_data['email'] = email
        
        return cleaned_data

# 이메일 변경 관련 폼
class EmailChangeForm(forms.Form):
    error_messages = {
        'invalid_login': "아이디 또는 비밀번호가 잘못되었습니다.",
        'active_user': "이미 인증이 완료된 계정입니다.",
        'exists_email': "이미 사용하고 있는 이메일입니다.",
    }

    email_local = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': _('이메일'), 'class': 'email_local'}),
        label=_('Email')
    )
    email_domain = forms.CharField(
        max_length=50,
        initial='@jbnu.ac.kr',
        widget=forms.HiddenInput(),
        required=False
    )
    email = forms.EmailField(
        initial = '',
        widget=forms.HiddenInput(),  
        required=False
    )
    
    username = forms.RegexField(
        regex=r'^\w+$',
        max_length=30,
        label=_('Username'),
        error_messages={'invalid': _('A username must contain letters, numbers, or underscores.')},
        widget=forms.TextInput(attrs={'placeholder': _('아이디')})
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': _('비밀번호')}),
        label=_('Password')
    )

    def clean(self):
        cleaned_data = super().clean()
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        email_local = self.cleaned_data.get('email_local')
        email_domain = cleaned_data.get('email_domain')

        # 이메일 주소 재구성
        email = f"{email_local}@jbnu.ac.kr"
        
        # email_domain이 올바른 도메인인지 확인
        if email_domain != "@jbnu.ac.kr":
            raise forms.ValidationError(_('유효하지 않은 이메일 도메인입니다. (jbnu.ac.kr의 도메인 필수)'), code='email')

        if username is not None and password:
            for backend_path in settings.AUTHENTICATION_BACKENDS:
                backend = self._get_backend(backend_path)
                if backend:
                    user = self._try_login_with_backend(backend, username, password)
                    if user:
                        if user.is_active:  # 계정이 이미 활성화 된 경우
                            raise forms.ValidationError(_('이미 활성화된 계정입니다.'), code='active_user')
                        else:
                            break
            else:  # 아이디, 비밀번호에 맞는 계정이 존재하지 않는 경우
                raise forms.ValidationError(_('아이디 또는 비밀번호가 잘못되었습니다.'), code='invalid_login')

        if User.objects.filter(email=email).exists():  # 이미 존재하는 이메일의 경우
            raise forms.ValidationError(_('이미 존재하는 이메일입니다.'), code='exists_email')

        return self.cleaned_data

        
    def _get_backend(self, backend_path):
        try:
            backend_module, backend_class = backend_path.rsplit('.', 1)
            module = import_module(backend_module)
            backend_cls = getattr(module, backend_class)
            return backend_cls()
        except (ImportError, AttributeError):
            return None

    def _try_login_with_backend(self, backend, username, password):
        try:
            user = backend.get_user(User.objects.get(username=username).pk)
            if user and user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
        return None

# 활성화 메일 재전송 폼
class ResendActivationEmailForm(forms.Form):
    error_messages = {
        'invalid_login': "아이디 또는 비밀번호가 잘못되었습니다.",
        'active_user': "이미 인증이 완료된 계정입니다.",
    }
    
    username = forms.RegexField(
        regex=r'^\w+$',
        max_length=30,
        label=_('Username'),
        error_messages={'invalid': _('A username must contain letters, numbers, or underscores.')},
        widget=forms.TextInput(attrs={'placeholder': _('아이디')})
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': _('비밀번호')}),
        label=_('Password')
    )

    def clean(self):
        cleaned_data = super().clean()
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            for backend_path in settings.AUTHENTICATION_BACKENDS:
                backend = self._get_backend(backend_path)
                if backend:
                    user = self._try_login_with_backend(backend, username, password)
                    if user:
                        if user.is_active:  # 계정이 이미 활성화 된 경우
                            raise forms.ValidationError(_('이미 활성화된 계정입니다.'), code='active_user')
                        else:
                            break
            else:  # 아이디, 비밀번호에 맞는 계정이 존재하지 않는 경우
                raise forms.ValidationError(_('아이디 또는 비밀번호가 잘못되었습니다.'), code='invalid_login')

        return self.cleaned_data

    def _get_backend(self, backend_path):
        try:
            backend_module, backend_class = backend_path.rsplit('.', 1)
            module = import_module(backend_module)
            backend_cls = getattr(module, backend_class)
            return backend_cls()
        except (ImportError, AttributeError):
            return None

    def _try_login_with_backend(self, backend, username, password):
        try:
            user = backend.get_user(User.objects.get(username=username).pk)
            if user and user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
        return None