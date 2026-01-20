from django.contrib import admin
from django.contrib.auth.models import User, AbstractUser, Group
from django.contrib.auth.admin import UserAdmin as OldUserAdmin
from django.contrib.admin.filters import FieldListFilter
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from judge.models import Profile

class Users(AbstractUser):
    
    class Meta(AbstractUser.Meta):
        swappable = 'AUTH_USER_MODEL'

class UserCombinedInputFilter(FieldListFilter):
    title = ' '
    template = 'admin/input_filter/input_filter_user.html'
    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.request = request
        self.params = params
        
        # 그룹 목록 가져오기
        self.__group_lookups = tuple(Group.objects.values_list('id', 'name'))
        self.__group_handles = set(str(group_id) for group_id, _ in self.__group_lookups)

        self.filter_keys = ['username', 'email', 'first_name', 'is_active', 'is_staff', 'is_superuser', 'groups']

    @property
    def group_lookups(self):
        return self.__group_lookups

    def expected_parameters(self):
        return ['username', 'email', 'first_name', 'is_active', 'is_staff', 'is_superuser', 'groups']

    def choices(self, changelist):
        yield {
            'selected': False,
            'query_string': changelist.get_query_string(remove=self.expected_parameters()),
            'display': '초기화',
        }
    def queryset(self, request, queryset):
        username = request.GET.get('username')
        email = request.GET.get('email')
        first_name = request.GET.get('first_name')
        is_active = request.GET.get('is_active')
        is_staff = request.GET.get('is_staff')
        is_superuser = request.GET.get('is_superuser')
        groups = request.GET.get('groups')

        if username:
            queryset = queryset.filter(username__icontains=username)
        
        if email:
            queryset = queryset.filter(email__icontains=email)
            
        if first_name:
            queryset = queryset.filter(first_name__icontains=first_name)

        if is_active in ['True', 'False']:
            queryset = queryset.filter(is_active=(is_active == 'True'))

        if is_staff in ['True', 'False']:
            queryset = queryset.filter(is_staff=(is_staff == 'True'))

        if is_superuser in ['True', 'False']:
            queryset = queryset.filter(is_superuser=(is_superuser == 'True'))

        if groups and groups in self.__group_handles:
            queryset = queryset.filter(groups__id=groups)

        return queryset
    
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


class UserAdmin(OldUserAdmin):
    search_fields = ('username', 'email', 'first_name', 'last_name')
    list_display = ('username', 'email', 'first_name', 'staff_status', 'active_status', 'date_joined_display')
    list_filter = (
        ('username', UserCombinedInputFilter),
    )
    action_form = CustomActionForm

    def staff_status(self, obj):
        """관리자 페이지에서 스태프 권한 유무를 pill 스타일로 표시"""
        if obj.is_staff:
            return format_html('<span class="pill pill-success">있음</span>')
        return format_html('<span class="pill pill-neutral">없음</span>')
    
    staff_status.admin_order_field = 'is_staff'
    staff_status.short_description = _('스태프 권한')

    def active_status(self, obj):
        if obj.is_active:
            return format_html('<span class="pill pill-success">활성</span>')
        return format_html('<span class="pill pill-danger">비활성</span>')
    
    active_status.admin_order_field = 'is_active'
    active_status.short_description = _('활성 상태')

    def date_joined_display(self, obj):
        if obj.date_joined:
            return obj.date_joined.strftime('%Y. %m. %d. %H:%M')
        return '-'
    
    date_joined_display.admin_order_field = 'date_joined'
    date_joined_display.short_description = _('가입 시간')
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            Profile.objects.create(user=obj)
