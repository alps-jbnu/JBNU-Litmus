import base64
import hashlib
import json
import traceback
from datetime import datetime
from operator import attrgetter
from zipfile import BadZipfile, ZipFile

from adminsortable2.admin import SortableInlineAdminMixin
from cryptography.fernet import Fernet
from reversion.admin import VersionAdmin

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection, transaction
#Problem Code 처리를 위한 import
from django.db.models import IntegerField
from django.db.models.deletion import Collector
from django.db.models.functions import Cast
from django.forms import BaseInlineFormSet, HiddenInput, ModelForm, NumberInput, Select
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import path, reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.template.response import TemplateResponse
from django.utils.translation import gettext, gettext_lazy as _, ngettext

from judge.models import (Judge, Language, LanguageLimit, Problem, ProblemClarification, 
                         ProblemData, ProblemPointsVote, ProblemTestCase, 
                         ProblemTranslation, Profile, Solution)
from judge.utils.views import NoBatchDeleteMixin
#TestCase 처리를 위한 import
from judge.views.problem_data import *
from judge.widgets import (AdminHeavySelect2MultipleWidget, AdminMartorWidget, 
                          AdminSelect2MultipleWidget, AdminSelect2Widget, 
                          CheckboxSelectMultipleWithSelectAll)
from judge.widgets.select2 import AdminHeavySelect2Widget
from django.contrib.admin.filters import FieldListFilter


class ProblemForm(ModelForm):
    change_message = forms.CharField(max_length=256, label=_('Edit reason'), required=False)
    encryption_key = forms.CharField(
        required=False, 
        widget=forms.PasswordInput(attrs={
            'class': 'encryption-key-input',
            'maxlength': 50,
            'minlength': 4,
            'autocomplete': 'off'
        }),
        label=_('암호화 키'),
        min_length=4,
        max_length=50,
        help_text=_('암호화 키는 4-50자 사이여야 합니다.')
    )
    
    def __init__(self, *args, **kwargs):
        super(ProblemForm, self).__init__(*args, **kwargs)
        self.fields['authors'].widget.can_add_related = False
        self.fields['testers'].widget.can_add_related = False
        self.fields['change_message'].widget.attrs.update({
            'placeholder': gettext('Describe the changes you made (optional)'),
        })

        # 새 문제 생성 시 is_public을 False(비공개)로 설정
        if not self.instance.pk:  # 새 문제인 경우
            self.initial['is_public'] = False
        
        # description을 선택적 필드로 설정
        self.fields['description'].required = False
        
        # 암호화된 문제인 경우 '복호화 키'로 라벨 변경
        if self.instance and self.instance.pk:
            if self.instance.is_encrypted:
                self.fields['encryption_key'].label = _('복호화 키')
                self.fields['encryption_key'].help_text = _('암호화된 문제를 편집하려면 올바른 복호화 키를 입력하세요.')
                self.fields['description'].widget.attrs['placeholder'] = '(암호화된 내용)'
    
    def clean(self):
        cleaned_data = super().clean()
        is_encrypted = cleaned_data.get('is_encrypted', False)
        encryption_key = cleaned_data.get('encryption_key', '')
        
        # 현재 암호화 상태
        was_encrypted = False
        if self.instance and self.instance.pk:
            # 데이터베이스에서 직접 암호화 상태 확인
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT is_encrypted FROM judge_problem WHERE id = %s", [self.instance.pk])
                    row = cursor.fetchone()
                    if row:
                        was_encrypted = bool(row[0])
            except Exception as e:
                # 오류 발생 시 인스턴스 값 사용
                was_encrypted = self.instance.is_encrypted
        
        # 암호화 활성화 검증
        if is_encrypted and not was_encrypted:
            if not encryption_key:
                raise forms.ValidationError('암호화가 활성화된 경우 암호화 키를 입력해야 합니다.')
            if len(encryption_key) < 4:
                raise forms.ValidationError('암호화 키는 최소 4자 이상이어야 합니다.')
            
            # 암호화 키 복잡성 검증
            if len(encryption_key) > 50:
                raise forms.ValidationError('암호화 키는 최대 50자까지 허용됩니다.')
        
        # 이미 암호화된 문제를 암호화 해제하려는 경우
        elif was_encrypted and not is_encrypted:
            if not encryption_key:
                raise forms.ValidationError('암호화된 문제를 복호화하려면 복호화 키를 입력해야 합니다.')
            
            # 키 해시 검증
            try:
                input_hash = hashlib.sha256(encryption_key.encode('utf-8')).hexdigest()
                db_hash = self.instance.encryption_key_hash or ''
                
                if not db_hash or input_hash != db_hash:
                    raise forms.ValidationError('잘못된 복호화 키입니다. 정확한 복호화 키를 입력하세요.')
            except forms.ValidationError:
                raise
            except Exception as e:
                raise forms.ValidationError(f'복호화 키 검증 중 오류가 발생했습니다: {e}')
        
        # 암호화 상태에서 복호화 키를 입력했을 때
        elif was_encrypted and is_encrypted and encryption_key:
            # 암호화 유지 상태에서 키 입력 처리: 키가 변경되면 안됨
            try:
                input_hash = hashlib.sha256(encryption_key.encode('utf-8')).hexdigest()
                db_hash = self.instance.encryption_key_hash or ''
                
                if input_hash != db_hash:
                    raise forms.ValidationError(
                        '암호화된 상태를 유지하면서 키를 변경할 수 없습니다. 암호화를 해제하려면 먼저 암호화 체크박스를 해제하세요.'
                    )
            except forms.ValidationError:
                raise
            except Exception as e:
                raise forms.ValidationError('복호화 키 검증 중 오류가 발생했습니다.')
        
        return cleaned_data

    def save(self, commit=True):
        # 기본 필드들을 처리하되 DB에는 아직 저장하지 않음
        instance = super(ProblemForm, self).save(commit=False)
        
        # DB에서 현재 is_encrypted 상태를 직접 확인
        real_is_encrypted = False
        if instance.pk:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT is_encrypted, encryption_key_hash FROM judge_problem WHERE id = %s", [instance.pk])
                    row = cursor.fetchone()
                    if row:
                        real_is_encrypted = bool(row[0])
            except Exception:
                pass
        
        is_encrypted = self.cleaned_data.get('is_encrypted', False)
        was_encrypted = real_is_encrypted  # 인스턴스 값 대신 DB 값 사용
        encryption_key = self.cleaned_data.get('encryption_key', '')
        
        try:
            if is_encrypted and not was_encrypted and encryption_key:
                # 암호화 처리
                instance._encryption_key = encryption_key
                
            elif was_encrypted and not is_encrypted and encryption_key:
                # 복호화 처리
                if instance.encrypted_description:
                    # 직접 복호화 시도
                    try:
                        # 복호화 시도
                        from judge.utils.encryption import decrypt_text
                        try:
                            decrypted_text = decrypt_text(instance.encrypted_description, encryption_key)
                            
                            # SQL 인젝션 방지: 파라미터화된 쿼리 사용
                            if instance.pk:
                                with connection.cursor() as cursor:
                                    cursor.execute(
                                        """
                                        UPDATE judge_problem 
                                        SET description = %s, 
                                            encrypted_description = NULL, 
                                            encryption_key_hash = NULL, 
                                            is_encrypted = %s
                                        WHERE id = %s
                                        """,
                                        [decrypted_text, False, instance.pk]
                                    )
                                
                                # 인스턴스에도 복호화된 내용 설정
                                instance.description = decrypted_text
                                instance.encrypted_description = None
                                instance.encryption_key_hash = None
                                instance.is_encrypted = False
                                
                                # 추가 저장 방지
                                if commit:
                                    # M2M 관계만 저장
                                    self.save_m2m()
                                    
                                    # 저장 완료 플래그
                                    instance._directly_updated = True
                                    return instance
                        except ValidationError as ve:
                            raise forms.ValidationError(f'복호화 실패: {ve}')
                                
                    except Exception as e:
                        raise forms.ValidationError(f'복호화 중 오류가 발생했습니다: {e}')
            
            # 암호화 유지 상태에서 키 입력 검증 (버그 수정)
            elif was_encrypted and is_encrypted and encryption_key:
                # clean 메서드에서 이미 검증됨 - 추가 조치 필요 없음
                pass
        except Exception as e:
            raise
        
        # 일반 저장 (복호화가 직접 업데이트되지 않은 경우)
        if commit and not hasattr(instance, '_directly_updated'):
            instance.save()
            self.save_m2m()
        
        return instance

    class Meta:
        widgets = {
            'authors': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%; display: none;'}),
            # 'curators': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
            'testers': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
            'banned_users': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
                                                           attrs={'style': 'width: 100%'}),
            # 'organizations': AdminHeavySelect2MultipleWidget(data_view='organization_select2', attrs={'style': 'width: 100%'}),
            'types': AdminSelect2MultipleWidget,
            'group': AdminSelect2Widget,
            'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('problem_preview')}),
            'allowed_languages': CheckboxSelectMultipleWithSelectAll(),
        }
 
 
from django.db.models import Q

class ProblemCombinedInputFilter(FieldListFilter):
    title=' '
    template = 'admin/input_filter/input_filter_problem.html'  # 커스텀 템플릿

    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.request = request
        self.params = params

        self.available_usernames = list(
            Profile.objects
            .filter(authored_problems__isnull=False)
            .values_list('user__username', flat=True)
            .distinct()
        )

    def expected_parameters(self):
        # 여러 필드를 필터하므로 각 필드 이름을 명시
        return ['is_public', 'encryption_status', 'authors', 'name','code']

    def choices(self, changelist):
        yield {
            'selected': False,
            'query_string': changelist.get_query_string(remove=self.expected_parameters()),
            'display': '초기화',
        }

    def queryset(self, request, queryset):
        is_public = request.GET.get('is_public')
        encryption_status = request.GET.get('encryption_status')
        authors = request.GET.get('authors')
        name = request.GET.get('name')
        code = request.GET.get('code')

        if is_public in ['True', 'False']:
            queryset = queryset.filter(is_public=(is_public == 'True'))

        if encryption_status == 'encrypted':
            queryset = queryset.filter(is_encrypted=True)
        elif encryption_status == 'not_encrypted':
            queryset = queryset.filter(is_encrypted=False)

        if authors:
            queryset = queryset.filter(authors__user__username__icontains=authors)

        if code:
            queryset = queryset.filter(code__icontains=code)
            
        if name:
            queryset = queryset.filter(name__icontains=name)

            
        return queryset


class LanguageLimitInlineForm(ModelForm):
    class Meta:
        widgets = {'language': AdminSelect2Widget}


class LanguageLimitInline(admin.TabularInline):
    model = LanguageLimit
    fields = ('language', 'time_limit', 'memory_limit')
    form = LanguageLimitInlineForm
    extra = 0


class ProblemClarificationForm(ModelForm):
    class Meta:
        widgets = {'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('comment_preview')})}


class ProblemClarificationInline(admin.StackedInline):
    model = ProblemClarification
    fields = ('description',)
    form = ProblemClarificationForm
    extra = 0


class ProblemSolutionForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(ProblemSolutionForm, self).__init__(*args, **kwargs)
        self.fields['authors'].widget.can_add_related = False

    class Meta:
        widgets = {
            'authors': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
            'content': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('solution_preview')}),
        }


class ProblemSolutionInline(admin.StackedInline):
    model = Solution
    fields = ('is_public', 'publish_on', 'authors', 'content')
    form = ProblemSolutionForm
    extra = 0


class ProblemTranslationForm(ModelForm):
    class Meta:
        widgets = {'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('problem_preview')})}


class ProblemTranslationInline(admin.StackedInline):
    model = ProblemTranslation
    fields = ('language', 'name', 'description')
    form = ProblemTranslationForm
    extra = 0

    def has_permission_full_markup(self, request, obj=None):
        if not obj:
            return True
        return request.user.has_perm('judge.problem_full_markup') or not obj.is_full_markup

    has_add_permission = has_change_permission = has_delete_permission = has_permission_full_markup


## 테스트케이스 인라인 관련 클래스
class TestCaseInlineForm(forms.ModelForm):
    class Meta:
        model = ProblemTestCase
        fields = '__all__'
        widgets = {
            'generator_args': HiddenInput(),
            'input_file': Select(attrs={'style': 'width: 100%'}),
            'output_file': Select(attrs={'style': 'width: 100%'}),
            'type': Select(attrs={'style': 'width: 100%'}),
            'points': NumberInput(attrs={'style': 'width: 4em'}),
            'output_prefix': NumberInput(attrs={'style': 'width: 4.5em'}),
            'output_limit': NumberInput(attrs={'style': 'width: 6em'}),
            'checker_args': HiddenInput(),
        }

class TestCaseInlineFormset(BaseInlineFormSet):
    def save(self, commit=True):
        instances = super().save(commit=False)
        
        # 삭제된 객체들 처리
        if self.deleted_objects:
            for obj in self.deleted_objects:
                obj.delete()
        
        saved_instances = []
        for instance in instances:
            instance.save()
            saved_instances.append(instance)
            
        # init.yml 생성/업데이트
        try:
            problem = self.instance
            if hasattr(problem, 'data_files'):
                problem_data = problem.data_files
                
                from judge.utils.problem_data import ProblemDataCompiler
                files = []
                if problem_data.zipfile:
                    try:
                        with ZipFile(problem_data.zipfile.path) as zf:
                            files = zf.namelist()
                    except Exception as e:
                        print(f"Error reading zipfile: {e}")
                
                ProblemDataCompiler.generate(
                    problem=problem,
                    data=problem_data,
                    cases=problem.cases.all(),
                    files=files
                )
        except Exception as e:
            print(f"Error generating init.yml: {e}")
            
        return saved_instances

    def add_fields(self, form, index):
        super().add_fields(form, index)
        
        if self.instance and self.instance.pk:
            input_files = self.get_files(self.instance)
            form.fields['input_file'].widget.choices = input_files
            form.fields['output_file'].widget.choices = input_files

    def get_files(self, obj):
        if obj and obj.pk:
            problem_data = ProblemData.objects.filter(problem=obj).first()
            if problem_data and problem_data.zipfile:
                try:
                    with ZipFile(problem_data.zipfile.path) as zf:
                        choices = [(name, name) for name in zf.namelist()]
                        return choices
                except BadZipfile:
                    pass
        return []


class TestCaseInline(SortableInlineAdminMixin, admin.TabularInline):
    model = ProblemTestCase
    form = TestCaseInlineForm
    formset = TestCaseInlineFormset
    fields = ('order', 'type', 'input_file', 'output_file', 'points')
    extra = 0
    
    def has_add_permission(self, request, obj=None):
        if obj is None or not hasattr(obj, 'data_files') or not obj.data_files.zipfile:
            return False
        return True
        
class ProblemDataInline(admin.TabularInline):
    model = ProblemData
    fields = ['zipfile', 'generator', 'unicode', 'nobigmath']
    form = ProblemDataForm

class ProblemEncryptionFilter(admin.SimpleListFilter):
    title = '암호화 상태'  # 필터 제목
    parameter_name = 'encryption_status'  # URL 파라미터 이름

    def lookups(self, request, model_admin):
        return [
            ('encrypted', '암호화된 문제만'),
            ('not_encrypted', '암호화되지 않은 문제만'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'encrypted':
            return queryset.filter(is_encrypted=True)
        if self.value() == 'not_encrypted':
            return queryset.filter(is_encrypted=False)
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

class ProblemAdmin(VersionAdmin):
    fieldsets = (
        ('문제 설정', {
            'fields': (
                'code', 'name', 'date', 'authors', 'testers',
                ('is_encrypted', 'encryption_key'), 
                'is_public',
                'is_contest_problem',
                'description', 
            ),
        }),
        # (_('Social Media'), {'classes': ('collapse',), 'fields': ('og_image', 'summary')}),
        (_('Taxonomy'), {'fields': ('group',)}),
        (_('Points'), {'fields': ('points', )}),
        (_('Limits'), {'fields': ('time_limit', ('memory_limit','memory_limit_1','memory_unit'),'allowed_languages',)}),
        # (_('Language'), {'fields': ('allowed_languages',)}),
        # (_('Justice'), {'fields': ('banned_users',)}),
        # (_('History'), {'fields': ('change_message',)}),
    )
    list_display = ['code', 'name', 'show_authors', 'points', 'public_status', 'encryption_status', 'show_public']
    list_display_links = None
    ordering = ['code']
    search_fields = ('code', 'name', 'authors__user__username', 'curators__user__username')
    inlines = [LanguageLimitInline, ProblemDataInline, TestCaseInline, ProblemSolutionInline, ProblemClarificationInline] # [LanguageLimitInline, ProblemClarificationInline, ProblemSolutionInline, ProblemTranslationInline]
    list_max_show_all = 1000
    actions_on_top = True
    actions_on_bottom = True
    list_filter = [
        ('name', ProblemCombinedInputFilter)              
    ]
    form = ProblemForm
    date_hierarchy = 'date'
    change_list_template = 'admin/judge/problem/change_list.html'
    action_form = CustomActionForm

    

    def get_actions(self, request):
        actions = super(ProblemAdmin, self).get_actions(request)

        if request.user.has_perm('judge.change_public_visibility'):
            func, name, desc = self.get_action('make_public')
            actions[name] = (func, name, desc)

            func, name, desc = self.get_action('make_private')
            actions[name] = (func, name, desc)

        func, name, desc = self.get_action('update_publish_date')
        actions[name] = (func, name, desc)

        return actions

    def get_list_display(self, request):
        def code_link(obj):
            if obj.is_editable_by(request.user):
                url = reverse('admin:judge_problem_change', args=[obj.pk])
                return format_html('<a href="{}">{}</a>', url, obj.code)
            return obj.code

        code_link.short_description = _('code')
        code_link.admin_order_field = 'code'
        return (
            code_link,
            'name',
            'show_authors',
            'points',
            'public_status',
            'encryption_status',
            'show_public',
        )

    def get_readonly_fields(self, request, obj=None):
        fields = self.readonly_fields
        fields += ('code',)
        if not request.user.has_perm('judge.change_public_visibility'):
            fields += ('is_public',)
        if not request.user.has_perm('judge.manage_contest_problem'):
            fields += ('is_contest_problem',)
        if not request.user.has_perm('judge.change_manually_managed'):
            fields += ('is_manually_managed',)
        if not request.user.has_perm('judge.problem_full_markup'):
            fields += ('is_full_markup',)
            if obj and obj.is_full_markup:
                fields += ('description',)
        return fields

    def get_fieldsets(self, request, obj=None):
        fieldsets = super(ProblemAdmin, self).get_fieldsets(request, obj)
        if request.user.has_perm('judge.manage_contest_problem'):
            return fieldsets

        filtered = []
        for name, options in fieldsets:
            fields = options.get('fields', ())
            if isinstance(fields, (list, tuple)):
                new_fields = []
                for field in fields:
                    if field == 'is_contest_problem':
                        continue
                    if isinstance(field, (list, tuple)):
                        new_fields.append(tuple(f for f in field if f != 'is_contest_problem'))
                    else:
                        new_fields.append(field)
                options = dict(options)
                options['fields'] = tuple(new_fields)
            filtered.append((name, options))
        return tuple(filtered)

    # obj여부에 따라 달라지는 기능 구현
    def get_inlines(self, request, obj=None):
        """객체가 존재하는 경우에만 인라인을 표시하도록 설정."""
        if obj: 
            return super().get_inlines(request, obj)
        return []
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if object_id is None:
            extra_context['show_save_and_continue'] = True
            extra_context['show_save'] = False
            extra_context['show_delete'] = False
            extra_context['show_save_and_add_another'] = False
        else:
            extra_context['show_save_and_continue'] = True
            extra_context['show_save'] = True
            extra_context['show_delete'] = True
            extra_context['show_save_and_add_another'] = True

        return super().changeform_view(request, object_id, form_url, extra_context=extra_context)
    
    def show_authors(self, obj):
        return ', '.join(map(attrgetter('user.username'), obj.authors.all()))

    show_authors.short_description = _('Authors')

    def public_status(self, obj):
        """
        관리자 페이지에서 공개/비공개 상태를 pill 스타일로 표시
        기존 X/V 이미지로 제공되던 정보를 공개/비공개 텍스트로 띄우기 위한 함수입니다.
        관련 함수는 모두 같은 이유로 작성되었습니다.
        """
        if obj.is_public:
            return format_html('<span class="pill pill-success">공개</span>')
        else:
            return format_html('<span class="pill pill-danger">비공개</span>')
    
    public_status.short_description = _('공개')

    def encryption_status(self, obj):
        """관리자 페이지에서 암호화/비암호화 상태를 pill 스타일로 표시"""
        if obj.is_encrypted:
            return format_html('<span class="pill pill-warning">암호화</span>')
        else:
            return format_html('<span class="pill pill-neutral">비암호화</span>')
    
    encryption_status.short_description = _('암호화')

    def show_public(self, obj):
        return format_html('<a href="{1}">{0}</a>', gettext('View on site'), obj.get_absolute_url())

    show_public.short_description = '문제 바로가기'

    def _rescore(self, request, problem_id):
        from judge.tasks import rescore_problem
        transaction.on_commit(rescore_problem.s(problem_id).delay)

    def update_publish_date(self, request, queryset):
        count = queryset.update(date=timezone.now())
        self.message_user(request, ngettext("%d problem's publish date successfully updated.",
                                            "%d problems' publish date successfully updated.",
                                            count) % count)

    update_publish_date.short_description = _('Set publish date to now')

    def make_public(self, request, queryset):
        count = queryset.update(is_public=True)
        for problem_id in queryset.values_list('id', flat=True):
            self._rescore(request, problem_id)
        self.message_user(request, ngettext('%d problem successfully marked as public.',
                                            '%d problems successfully marked as public.',
                                            count) % count)

    make_public.short_description = _('Mark problems as public')

    def make_private(self, request, queryset):
        count = queryset.update(is_public=False)
        for problem_id in queryset.values_list('id', flat=True):
            self._rescore(request, problem_id)
        self.message_user(request, ngettext('%d problem successfully marked as private.',
                                            '%d problems successfully marked as private.',
                                            count) % count)

    make_private.short_description = _('Mark problems as private')

    def get_queryset(self, request):
        if request.user.has_perm('judge.view_all_problem') or request.user.has_perm('judge.edit_all_problem'):
            queryset = Problem.objects.all()
        else:
            queryset = Problem.get_editable_problems(request.user)

        if not request.user.has_perm('judge.manage_contest_problem'):
            queryset = queryset.filter(is_contest_problem=False)

        return queryset.prefetch_related('authors__user')

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return request.user.has_perm('judge.view_all_problem') or request.user.has_perm('judge.edit_own_problem')
        return obj.is_editable_by(request.user)

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return request.user.has_perm('judge.edit_own_problem')
        return obj.is_editable_by(request.user)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if object_id is not None and not self.has_change_permission(request):
            context = dict(
                self.admin_site.each_context(request),
                opts=self.model._meta,
                title=_('Permission denied'),
                message=_('해당 문제를 수정할 권한이 없습니다.'),
            )
            return TemplateResponse(
                request,
                'admin/judge/problem/permission_denied.html',
                context,
                status=200,
            )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == 'allowed_languages':
            kwargs['widget'] = CheckboxSelectMultipleWithSelectAll()
        
        return super(ProblemAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)

    def get_form(self, request, *args, **kwargs):
        form = super(ProblemAdmin, self).get_form(request,*args, **kwargs)
        form.base_fields['authors'].queryset = Profile.objects.filter(user__username=request.user.username)
        form.base_fields['allowed_languages'].initial = Language.objects.all()
        if not request.user.has_perm('judge.manage_contest_problem'):
            form.base_fields.pop('is_contest_problem', None)
        return form

    def save_model(self, request, obj, form, change):
        # `organizations` will not appear in `cleaned_data` if user cannot edit it
        form.cleaned_data['authors'] = Profile.objects.filter(user__username=request.user.username)
        # form.cleaned_data['allowed_languages'] = Language
        
        # if form.changed_data and 'organizations' in form.changed_data:
        #     obj.is_organization_private = bool(form.cleaned_data['organizations'])
            
        memory_limit_1 = form.cleaned_data.get('memory_limit_1')
        memory_unit = form.cleaned_data.get('memory_unit')
        if memory_unit == 'MB':
            obj.memory_limit = memory_limit_1 * 1024
        else:
            obj.memory_limit = memory_limit_1
        
        #코드 자동 생성
        if obj.code == 'default':
            last_problem = Problem.objects.annotate(
                numeric_value=Cast('code', IntegerField())
            ).order_by('-numeric_value').first()
            if last_problem:
                obj.code = str(int(last_problem.code) + 1)
            else:
                obj.code = str(10000) #10000번부터 문제 시작          
        
        super(ProblemAdmin, self).save_model(request, obj, form, change)
        if (
            form.changed_data and
            # any(f in form.changed_data for f in ('is_public', 'organizations', 'points', 'partial'))
            any(f in form.changed_data for f in ('is_public', 'points', 'partial'))
        ):
            self._rescore(request, obj.id)
            
    def get_urls(self):
        return [
            path('preview/<int:problem_id>', self.preview , name='testcase_preview'),
        ] + super(ProblemAdmin, self).get_urls()
        
    def preview(self,request,problem_id):
        if request.method == 'GET' and request.user.is_staff == True:        
            problem_data = ProblemData.objects.filter(problem=problem_id).first()

            context = {'json':json.dumps({})}
            error_messages = []

            if problem_data is not None:
                zip_path = problem_data.zipfile
                testcases = ProblemTestCase.objects.filter(dataset=problem_id)
                dic = {'testcases':[]}
                try:
                    with ZipFile(zip_path) as zip:
                        for idx, testcase in enumerate(testcases):
                            dic['testcases'].append({
                                    "inputFileName": '',
                                    "inputFileBody": '',
                                    "outputFileName": '',
                                    "outputFileBody": '',
                            })
                            try:
                                with zip.open(testcase.input_file) as file: 
                                    content = file.read()
                                    try:
                                        decoded = content.decode('utf-8')
                                    except UnicodeDecodeError:
                                        decoded = None
                                    dic['testcases'][idx]['inputFileName'] = testcase.input_file
                                    dic['testcases'][idx]['inputFileBody'] = decoded
                            except KeyError:
                                error_messages.append("지원하지 않는 input 파일 형식입니다.")
                            try:
                                with zip.open(testcase.output_file) as file: 
                                    dic['testcases'][idx]['outputFileName'] = testcase.output_file
                                    dic['testcases'][idx]['outputFileBody'] = file.read().decode('utf-8')
                            except KeyError:
                                error_messages.append("지원하지 않는 output 파일 형식입니다.")
                    context = {'json':json.dumps(dic)}
                except FileNotFoundError:
                    error_messages.append("ZIP 파일이 존재하지 않습니다.")
                except BadZipfile:
                    error_messages.append("ZIP 파일이 손상되었거나 열 수 없습니다.")
                except Exception as e:
                    error_messages.append(f"알 수 없는 오류가 발생했습니다: {str(e)}")
                context['errors'] = error_messages
            return render(request,'problem/testcase_preview.html',context)
            
            # 요청이 GET이 아니거나, 사용자가 staff가 아닌 경우 적절한 응답 반환
        return HttpResponse("Unauthorized or invalid Get request", status=401)

    def construct_change_message(self, request, form, *args, **kwargs):
        if form.cleaned_data.get('change_message'):
            return form.cleaned_data['change_message']
        return super(ProblemAdmin, self).construct_change_message(request, form, *args, **kwargs)


class ProblemPointsVoteAdmin(admin.ModelAdmin):
    list_display = ('points', 'voter', 'linked_problem', 'vote_time')
    search_fields = ('voter__user__username', 'problem__code', 'problem__name')
    readonly_fields = ('voter', 'problem', 'vote_time')
    action_form = CustomActionForm

    

    def get_queryset(self, request):
        return ProblemPointsVote.objects.filter(problem__in=Problem.get_editable_problems(request.user))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return request.user.has_perm('judge.edit_own_problem')
        return obj.problem.is_editable_by(request.user)

    def lookup_allowed(self, key, value):
        return super().lookup_allowed(key, value) or key in ('problem__code',)

    def linked_problem(self, obj):
        link = reverse('problem_detail', args=[obj.problem.code])
        return format_html('<a href="{0}">{1}</a>', link, obj.problem.name)
    linked_problem.short_description = _('problem')
    linked_problem.admin_order_field = 'problem__name'
