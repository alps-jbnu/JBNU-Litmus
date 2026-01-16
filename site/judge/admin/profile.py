from django.contrib import admin
from django.contrib.admin.filters import FieldListFilter
from django.forms import ModelForm
from django.http import HttpRequest
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from reversion.admin import VersionAdmin

from django_ace import AceWidget
from judge.models import Profile, WebAuthnCredential,Department
from judge.utils.views import NoBatchDeleteMixin
from judge.widgets import AdminMartorWidget, AdminSelect2Widget

class ProfileForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        if 'current_contest' in self.base_fields:
            # form.fields['current_contest'] does not exist when the user has only view permission on the model.
            self.fields['current_contest'].queryset = self.instance.contest_history.select_related('contest') \
                .only('contest__name', 'user_id', 'virtual')
            self.fields['current_contest'].label_from_instance = \
                lambda obj: '%s v%d' % (obj.contest.name, obj.virtual) if obj.virtual else obj.contest.name
            #학과 관련 옵션 버튼은 비활성화
            self.fields['department'].widget.can_add_related = False
            self.fields['department'].widget.can_change_related = False
            self.fields['department'].widget.can_delete_related = False

    class Meta:
        widgets = {
            'timezone': AdminSelect2Widget,
            'language': AdminSelect2Widget,
            'ace_theme': AdminSelect2Widget,
            'current_contest': AdminSelect2Widget,
            'about': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('profile_preview')}),
        }

class TimezoneFilter(admin.SimpleListFilter):
    title = _('timezone')
    parameter_name = 'timezone'

    def lookups(self, request, model_admin):
        return Profile.objects.values_list('timezone', 'timezone').distinct().order_by('timezone')

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        return queryset.filter(timezone=self.value())
    
class CombinedProfileFilter(FieldListFilter):
    title = ' '
    template = 'admin/input_filter/input_filter_profile.html'
    
    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.request = request
        self.params = params
        
        self.__timezone_lookups = tuple(
            Profile.objects.values_list('timezone', 'timezone')
            .distinct()
            .order_by('timezone')
        )
        self.__timezone_handles = {tz for tz, _ in self.__timezone_lookups}
        
        self.__department_lookups = tuple(
            Department.objects.values_list('id', 'name')
        )
        self.__department_handles = set(str(dep_id) for dep_id, _ in self.__department_lookups)
        
        
        self.filter_keys = ['username', 'email', 'department', 'timezone', 'IP']
    
    @property
    def timezone_lookups(self):
        return self.__timezone_lookups
    
    @property
    def department_lookups(self):
        print("🔥 department_lookups 호출됨")
        return self.__department_lookups
     

    def expected_parameters(self):
        return ['username', 'email', 'department', 'timezone', 'IP',]

    def choices(self, changelist):
        yield {
            'selected': False,
            'query_string': changelist.get_query_string(remove=self.expected_parameters()),
            'display': '초기화',
        }

    def queryset(self, request, queryset):
        username = request.GET.get('username')
        email=request.GET.get('email')
        department=request.GET.get('department')
        timezone=request.GET.get('timezone')
        ip=request.GET.get('IP')

        if username:
            queryset = queryset.filter(user__username__icontains=username)

        if email:
            queryset = queryset.filter(user__email__icontains=email)

        if department and department in self.__department_handles:
            queryset = queryset.filter(user__profile__department_id=department)

        if timezone and timezone in self.__timezone_handles:
            queryset = queryset.filter(user__profile__timezone=timezone)

        if ip:
            queryset = queryset.filter(ip__icontains=ip)

        return queryset


class WebAuthnInline(admin.TabularInline):
    model = WebAuthnCredential
    readonly_fields = ('cred_id', 'public_key', 'counter')
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False
    
from django import forms

class CustomActionForm(forms.Form):
    action = forms.ChoiceField(
        label="작업",   
        choices=[],           
        required=False,
    )
    select_across = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),   
        label=''
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['action'].choices.insert(0, ("", "작업을 선택하세요."))


class DepartmentAdmin(admin.ModelAdmin):
    fields = ('name',)
    list_display = ('id', 'name')
    form = ProfileForm
    action_form = CustomActionForm
    

    

class GroupAdmin(admin.ModelAdmin):
    fields = ('name',)
    list_display = ('id', 'name')
    action_form = CustomActionForm

    


class SubjectAdmin(admin.ModelAdmin):
    fields = ('name',)
    list_display = ('id', 'name')
    action_form = CustomActionForm
    

    

class ProfileAdmin(NoBatchDeleteMixin, VersionAdmin):
    # fields = ('user', 'display_rank', 'about', 'organizations', 'timezone', 'language', 'ace_theme',
    #           'math_engine', 'last_access', 'ip', 'mute', 'is_unlisted', 'is_banned_from_problem_voting',
    #           'username_display_override', 'notes', 'is_totp_enabled', 'user_script', 'current_contest')
    fields = ('user', 'display_rank', 'about', 'timezone', 'language', 'ace_theme', 'department',
              'math_engine', 'last_access', 'ip', 'mute', 'is_unlisted', 'is_banned_from_problem_voting',
              'username_display_override', 'notes', 'is_totp_enabled', 'user_script', 'current_contest')
    readonly_fields = ('user',)
    list_display = ('admin_user_admin', 'email', 'department', 'staff_status', 'active_status', 'timezone_full',
                    'date_joined_display', 'last_access_display', 'ip', 'show_public')
    ordering = ('user__username',)
    search_fields = ('user__username', 'ip', 'user__email')
    # 커스텀 필터만 사용 - Django 기본 필터들 제거
    list_filter = [
        ('id', CombinedProfileFilter),
    ]
    actions = ('recalculate_points',)
    actions_on_top = True
    actions_on_bottom = True
    form = ProfileForm
    inlines = [WebAuthnInline]
    action_form = CustomActionForm
    

    
    

    def get_queryset(self, request):
        return super(ProfileAdmin, self).get_queryset(request).select_related('user')

    def get_fields(self, request, obj=None):
        if request.user.has_perm('judge.totp'):
            fields = list(self.fields)
            fields.insert(fields.index('is_totp_enabled') + 1, 'totp_key')
            fields.insert(fields.index('totp_key') + 1, 'scratch_codes')
            return tuple(fields)
        else:
            return self.fields

    def get_readonly_fields(self, request, obj=None):
        fields = self.readonly_fields
        if not request.user.has_perm('judge.totp'):
            fields += ('is_totp_enabled',)
        return fields

    def show_public(self, obj):
        return format_html('<a href="{0}" style="white-space:nowrap;">{1}</a>',
                           obj.get_absolute_url(), gettext('View on site'))
    show_public.short_description = ''

    def admin_user_admin(self, obj):
        return obj.username
    admin_user_admin.admin_order_field = 'user__username'
    admin_user_admin.short_description = _('User')

    def email(self, obj):
        return obj.user.email
    email.admin_order_field = 'user__email'
    email.short_description = _('Email')

    def timezone_full(self, obj):
        return obj.timezone
    timezone_full.admin_order_field = 'timezone'
    timezone_full.short_description = _('Timezone')

    def date_joined(self, obj):
        return obj.user.date_joined
    date_joined.admin_order_field = 'user__date_joined'
    date_joined.short_description = _('date joined')

    def staff_status(self, obj):
        """관리자 페이지에서 스태프 권한 유무를 pill 스타일로 표시"""
        if obj.user.is_staff:
            return format_html('<span class="pill pill-success">있음</span>')
        else:
            return format_html('<span class="pill pill-neutral">없음</span>')
    
    staff_status.admin_order_field = 'user__is_staff'
    staff_status.short_description = _('스태프 권한')

    def active_status(self, obj):
        """관리자 페이지에서 사용자 활성화 상태를 pill 스타일로 표시"""
        if obj.user.is_active:
            return format_html('<span class="pill pill-success">활성</span>')
        else:
            return format_html('<span class="pill pill-danger">비활성</span>')
    
    active_status.admin_order_field = 'user__is_active'
    active_status.short_description = _('활성 상태')

    def date_joined_display(self, obj):
        """가입 시간을 한국 형식으로 표시"""
        if obj.user.date_joined:
            return obj.user.date_joined.strftime('%Y. %m. %d. %H:%M')
        return '-'
    
    date_joined_display.admin_order_field = 'user__date_joined'
    date_joined_display.short_description = _('가입 시간')

    def last_access_display(self, obj):
        """마지막 접속을 한국 형식으로 표시"""
        if obj.last_access:
            return obj.last_access.strftime('%Y. %m. %d. %H:%M')
        return '-'
    
    last_access_display.admin_order_field = 'last_access'
    last_access_display.short_description = _('마지막 접속')

    def recalculate_points(self, request, queryset):
        count = 0
        for profile in queryset:
            profile.calculate_points()
            count += 1
        self.message_user(request, ngettext('%d user had scores recalculated.',
                                            '%d users had scores recalculated.',
                                            count) % count)
    recalculate_points.short_description = _('Recalculate scores')

    def get_form(self, request, obj=None, **kwargs):
        form = super(ProfileAdmin, self).get_form(request, obj, **kwargs)
        if 'user_script' in form.base_fields:
            # form.base_fields['user_script'] does not exist when the user has only view permission on the model.
            form.base_fields['user_script'].widget = AceWidget('javascript', request.profile.ace_theme)
        return form