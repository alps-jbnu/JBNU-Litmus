import random
import string
from adminsortable2.admin import SortableInlineAdminMixin
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Q, TextField
from django.forms import ModelForm, ModelMultipleChoiceField
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, ngettext
from reversion.admin import VersionAdmin


#추가
import re
from django.shortcuts import render
from django.db import transaction
from django.http import JsonResponse
import json
from collections import defaultdict
from django.contrib.admin.filters import FieldListFilter
from operator import itemgetter


from django_ace import AceWidget
# from judge.models import Class, Contest, ContestProblem, ContestSubmission, Profile, Rating, Submission, Problem
from judge.models import Contest, ContestProblem, ContestSubmission, Profile, Rating, Submission, Problem
from judge.ratings import rate_contest
from judge.utils.views import NoBatchDeleteMixin
from judge.widgets import AdminHeavySelect2MultipleWidget, AdminHeavySelect2Widget, AdminMartorWidget, \
    AdminSelect2MultipleWidget, AdminSelect2Widget


class AdminHeavySelect2Widget(AdminHeavySelect2Widget):
    @property
    def is_hidden(self):
        return False


class ContestTagForm(ModelForm):
    contests = ModelMultipleChoiceField(
        label=_('Included contests'),
        queryset=Contest.objects.all(),
        required=False,
        widget=AdminHeavySelect2MultipleWidget(data_view='contest_select2'))


class ContestTagAdmin(admin.ModelAdmin):
    fields = ('name', 'color', 'description', 'contests')
    list_display = ('name', 'color')
    actions_on_top = True
    actions_on_bottom = True
    form = ContestTagForm
    formfield_overrides = {
        TextField: {'widget': AdminMartorWidget},
    }

    def save_model(self, request, obj, form, change):
        super(ContestTagAdmin, self).save_model(request, obj, form, change)
        obj.contests.set(form.cleaned_data['contests'])

    def get_form(self, request, obj=None, **kwargs):
        form = super(ContestTagAdmin, self).get_form(request, obj, **kwargs)
        if obj is not None:
            form.base_fields['contests'].initial = obj.contests.all()
        return form


class ContestProblemInlineForm(ModelForm):
    class Meta:
        widgets = {'problem': AdminHeavySelect2Widget(data_view='problem_select2')}


class ContestProblemInline(SortableInlineAdminMixin, admin.TabularInline):
    model = ContestProblem
    verbose_name = _('Problem')
    verbose_name_plural = _('Problems')
    fields = ('problem', 'points', 'partial',  'order',
              'rejudge_column')
    readonly_fields = ('rejudge_column',)
    form = ContestProblemInlineForm
    extra = 0
    
    def get_formset(self, request, obj, **kwargs):
        fs = super().get_formset(request, obj, **kwargs)
        fs.form.base_fields['problem'].widget.can_add_related = False
        fs.form.base_fields['problem'].widget.can_change_related = False
        fs.form.base_fields['problem'].widget.can_delete_related = False
        return fs
    
    def rejudge_column(self, obj):
        if obj.id is None:
            return ''
        return format_html('<a class="button rejudge-link" href="{0}">{1}</a>',
                           reverse('admin:judge_contest_rejudge', args=(obj.contest.id, obj.id)), _('Rejudge'))
    rejudge_column.short_description = ''


class ContestForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(ContestForm, self).__init__(*args, **kwargs)
        if 'rate_exclude' in self.fields:
            if self.instance and self.instance.id:
                self.fields['rate_exclude'].queryset = \
                    Profile.objects.filter(contest_history__contest=self.instance).distinct()
            else:
                self.fields['rate_exclude'].queryset = Profile.objects.none()
        #학과 관련 옵션 버튼은 비활성화
        self.fields['subject'].widget.can_add_related = False
        self.fields['subject'].widget.can_change_related = False
        self.fields['subject'].widget.can_delete_related = False
        # self.fields['banned_users'].widget.can_add_related = False
        # self.fields['view_contest_scoreboard'].widget.can_add_related = False
        
    def clean(self):
        cleaned_data = super(ContestForm, self).clean()
        # key값은 모델에 save될때, 자동으로 추가되므로 아무 값이나 넣어줘도 무관
        if 'key' not in cleaned_data:
            cleaned_data['key'] = self.instance.key
        return cleaned_data
        # cleaned_data['banned_users'].filter(current_contest__contest=self.instance).update(current_contest=None)

    class Meta:
        widgets = {
            'authors': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'curators': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'testers': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'spectators': AdminHeavySelect2MultipleWidget(data_view='profile_select2'),
            'private_contestants': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
                                                                   attrs={'style': 'width: 100%'}),
            # 'organizations': AdminHeavySelect2MultipleWidget(data_view='organization_select2'),
            # 'classes': AdminHeavySelect2MultipleWidget(data_view='class_select2'),
            # 'join_organizations': AdminHeavySelect2MultipleWidget(data_view='organization_select2'),
            'tags': AdminSelect2MultipleWidget,
            # 'banned_users': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
            #                                                 attrs={'style': 'width: 100%'}),
            'view_contest_scoreboard': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
                                                                       attrs={'style': 'width: 100%'}),
            'view_contest_submissions': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
                                                                        attrs={'style': 'width: 100%'}),
            'description': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('contest_preview')}),
        }


class CombinedContestFilter(FieldListFilter):
    title = ' '
    template = 'admin/input_filter/input_filter_contest.html'  # 템플릿 따로 필요
    
    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.request = request
        self.params = params
        
    def expected_parameters(self):
        return ['contest_name','is_public','is_assignment']
    
    def choices(self, changelist):
        yield {
            'selected': False,
            'query_string': changelist.get_query_string(remove=self.expected_parameters()),
            'display': '초기화',
        }

    def queryset(self, request, queryset):
        contest_name = request.GET.get('contest_name')
        is_public = request.GET.get('is_public')
        is_assignment = request.GET.get('is_assignment')

        if contest_name:
            queryset = queryset.filter(name__icontains=contest_name)

        if is_public in ['True', 'False']:
            queryset = queryset.filter(is_public=(is_public == 'True'))

        if is_assignment in ['True', 'False']:
            queryset = queryset.filter(is_assignment=(is_assignment == 'True'))

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


class ContestAdmin(VersionAdmin):
    fieldsets = (
        # (None, { 'classes':('collapse'),
        #     'fields': ('key', 'name' , 'authors', )}),
        ('기본', {'fields': ('key', 'name' , 'authors', 'subject' )}),
        (_('Settings'), {'fields': ('is_visible', 'is_practice',)}),
        (_('Scheduling'), {'fields': ('start_time', 'end_time')}),
        (_('Details'), {'fields': ('description', )}),
        # (_('Rating'), {'fields': ('is_rated', 'rate_all', )}),
        # (_('Access'), {'fields': ('access_code', 'organizations', 'classes',
        #                            'view_contest_submissions')}),
        (_('Access'), {'fields': ('access_code',
                                   'view_contest_submissions')}),
        # (_('Justice'), {'fields': ('banned_users',)}),
    )
    list_display = ('name', 'visibility_status', 'practice_status', 'rating_status', 'start_time_display', 'end_time_display', 'time_limit',
                    'user_count')
    search_fields = ('key', 'name')
    inlines = [ContestProblemInline]
    actions_on_top = True
    actions_on_bottom = True
    form = ContestForm
    change_list_template = 'admin/judge/contest/change_list.html'
    filter_horizontal = ['rate_exclude']
    date_hierarchy = 'start_time'
    list_filter = (
        ('id', CombinedContestFilter),
    )
    action_form = CustomActionForm

    
    
    # obj여부에 따라 달라지는 기능 구현
    def get_inlines(self, request, obj=None):
        """객체가 존재하지 않더라도 인라인을 표시."""
        return [ContestProblemInline]
    
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

    def get_actions(self, request):
        actions = super(ContestAdmin, self).get_actions(request)

        if request.user.has_perm('judge.change_contest_visibility') or \
                request.user.has_perm('judge.create_private_contest'):
            for action in ('make_visible', 'make_hidden'):
                actions[action] = self.get_action(action)

        if request.user.has_perm('judge.lock_contest'):
            for action in ('set_locked', 'set_unlocked'):
                actions[action] = self.get_action(action)

        return actions

    def get_queryset(self, request):
        queryset = Contest.objects.all()
        if request.user.has_perm('judge.edit_all_contest'):
            return queryset
        else:
            # return queryset.filter(Q(authors=request.profile) | Q(curators=request.profile)).distinct()
            # 문제 탭의 선택 삭제와 같은 오류 [커밋 13397fee35bbfdcaee6ee0190ea7b921676303bc 참고]
            return queryset.filter(Q(authors=request.profile) | Q(curators=request.profile))

    def get_readonly_fields(self, request, obj=None):
        readonly = []
        readonly += ['key']
        if not request.user.has_perm('judge.contest_rating'):
            readonly += ['is_rated', 'rate_all', 'rate_exclude']
        if not request.user.has_perm('judge.lock_contest'):
            readonly += ['locked_after']
        if not request.user.has_perm('judge.contest_access_code'):
            readonly += ['access_code']
        if not request.user.has_perm('judge.create_private_contest'):
            # readonly += ['private_contestants', 'organizations']
            readonly += ['private_contestants']
            if not request.user.has_perm('judge.change_contest_visibility'):
                readonly += ['is_visible']
        if not request.user.has_perm('judge.contest_problem_label'):
            readonly += ['problem_label_script']
        return readonly

    def save_model(self, request, obj, form, change):
        # `private_contestants` and `organizations` will not appear in `cleaned_data` if user cannot edit it
        form.cleaned_data['authors'] = Profile.objects.filter(user__username=request.user.username)
        if form.changed_data:
            if 'private_contestants' in form.changed_data:
                obj.is_private = bool(form.cleaned_data['private_contestants'])
            # if 'organizations' in form.changed_data or 'classes' in form.changed_data:
            #     obj.is_organization_private = bool(form.cleaned_data['organizations'] or form.cleaned_data['classes'])
            # if 'join_organizations' in form.cleaned_data:
            #     obj.limit_join_organizations = bool(form.cleaned_data['join_organizations'])

        # `is_visible` will not appear in `cleaned_data` if user cannot edit it
        if form.cleaned_data.get('is_visible') and not request.user.has_perm('judge.change_contest_visibility'):
            # if not obj.is_private and not obj.is_organization_private:
            #     raise PermissionDenied
            if not obj.is_private:
                raise PermissionDenied
            if not request.user.has_perm('judge.create_private_contest'):
                raise PermissionDenied

        super().save_model(request, obj, form, change)
        # We need this flag because `save_related` deals with the inlines, but does not know if we have already rescored
        self._rescored = False
        if form.changed_data and any(f in form.changed_data for f in ('format_config', 'format_name')):
            self._rescore(obj.key)
            self._rescored = True

        if form.changed_data and 'locked_after' in form.changed_data:
            self.set_locked_after(obj, form.cleaned_data['locked_after'])

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        
        # Only rescored if we did not already do so in `save_model`
        if not self._rescored and any(formset.has_changed() for formset in formsets):
            self._rescore(form.cleaned_data['key'])

    def has_change_permission(self, request, obj=None):
        if not request.user.has_perm('judge.edit_own_contest'):
            return False
        if obj is None:
            return True
        return obj.is_editable_by(request.user)

    def _rescore(self, contest_key):
        from judge.tasks import rescore_contest
        transaction.on_commit(rescore_contest.s(contest_key).delay)

    def make_visible(self, request, queryset):
        if not request.user.has_perm('judge.change_contest_visibility'):
            # queryset = queryset.filter(Q(is_private=True) | Q(is_organization_private=True))
            queryset = queryset.filter(Q(is_private=True))
        count = queryset.update(is_visible=True)
        self.message_user(request, ngettext('%d contest successfully marked as visible.',
                                            '%d contests successfully marked as visible.',
                                            count) % count)
    make_visible.short_description = _('Mark contests as visible')

    def make_hidden(self, request, queryset):
        if not request.user.has_perm('judge.change_contest_visibility'):
            # queryset = queryset.filter(Q(is_private=True) | Q(is_organization_private=True))
            queryset = queryset.filter(Q(is_private=True))
        count = queryset.update(is_visible=True)
        self.message_user(request, ngettext('%d contest successfully marked as hidden.',
                                            '%d contests successfully marked as hidden.',
                                            count) % count)
    make_hidden.short_description = _('Mark contests as hidden')

    def set_locked(self, request, queryset):
        for row in queryset:
            self.set_locked_after(row, timezone.now())
        count = queryset.count()
        self.message_user(request, ngettext('%d contest successfully locked.',
                                            '%d contests successfully locked.',
                                            count) % count)
    set_locked.short_description = _('Lock contest submissions')

    def set_unlocked(self, request, queryset):
        for row in queryset:
            self.set_locked_after(row, None)
        count = queryset.count()
        self.message_user(request, ngettext('%d contest successfully unlocked.',
                                            '%d contests successfully unlocked.',
                                            count) % count)
    set_unlocked.short_description = _('Unlock contest submissions')

    def set_locked_after(self, contest, locked_after):
        with transaction.atomic():
            contest.locked_after = locked_after
            contest.save()
            Submission.objects.filter(contest_object=contest,
                                      contest__participation__virtual=0).update(locked_after=locked_after)

    def get_urls(self):
        return [
            path('rate/all/', self.rate_all_view, name='judge_contest_rate_all'),
            path('<int:id>/rate/', self.rate_view, name='judge_contest_rate'),
            path('<int:contest_id>/judge/<int:problem_id>/', self.rejudge_view, name='judge_contest_rejudge'),
            ##인라인 업데이트를 위한 url경로 하나 생성
            ##test 문제 매니저
            path('problem_manager/<int:contest_id>/', self.problem_manager_view , name='problem_manager'),
            #path('problem_manager/<int:contest_id>/<path:path>/', self.problem_manager_view , name='problem_manager'),
            path(
                'update-inline/<int:contest_id>/',
                self.admin_site.admin_view(self.update_inline_view),
                name='update_contest_inline',
            ),
        ] + super(ContestAdmin, self).get_urls()
    
    ##Json객체에 모든 파일 정보를 담아 템플릿에 전달하는 파일 매니저 코드
    def problem_manager_view(self, request, contest_id):
        if request.method == 'GET' and request.user.is_staff == True:        
            #자신이 만든 문제만 필터링    
            # problems = Problem.objects.filter(authors__user=request.user).distinct().select_related('group')
            problems = Problem.objects.distinct().select_related('group')

            #현재 대회 페이지에 대한 인라인 문제들 목록 가져오기
            contest_problems = ContestProblem.objects.filter(contest_id=contest_id).all()
            contest_problems_ids = list(contest_problems.values_list('problem_id', flat=True))
            
            # ContestProblem과 Problem이 일치하는 Problem만 필터링
            matching_problems = problems.filter(id__in=contest_problems_ids)
            # 없는 키값에 접근하려 하는 경우, False반환하도록 설정
            matching_problem_ids = defaultdict(lambda: False, {problem.id: True for problem in matching_problems})
            
            # 문제를 담을 파일 트리
            user_problems = {"name": "root", "is_dir": True, "children": []}
            for problem in problems:
                ##그룹 경로에 따라, 파일 트리 구성    
                #파일 경로 + 파일 이름을 가진 경로로 생성
                group_name = problem.group.full_name if problem.group else "기타"
                names = re.sub(r'/+', '/', f"{group_name}/{problem.name}").strip("/").split("/")
                current_level = user_problems["children"]
                
                for i, part in enumerate(names):
                    existing_node = next((node for node in current_level if node["name"] == part), None)

                    if existing_node and existing_node.get('is_dir', False):
                        current_level = existing_node["children"]
                    else:
                        new_node = {"name": part, "is_dir": i < len(names) - 1}
                        if i == len(names) - 1:
                            # 마지막 노드 (문제 파일)
                            new_node["name"] = problem.name
                            new_node["id"] = problem.id
                            new_node["selected"] = matching_problem_ids[problem.id]
                            new_node["is_dir"] = False
                        else:
                            # 디렉토리 노드
                            new_node["children"] = []
                            new_node["is_dir"] = True
                            
                        current_level.append(new_node)
                        if new_node.get("is_dir", False):
                            current_level = new_node["children"]
            
            context = {
                'problems': json.dumps(user_problems),
                'contest_id': contest_id,
            }
            
            template_name = 'admin/judge/contest/problem_tree_manager.html' 
            return render(request, template_name, context)
        
        # 요청이 GET이 아니거나, 사용자가 staff가 아닌 경우 적절한 응답 반환
        return HttpResponse("Unauthorized or invalid Get request", status=401)
    
    
    def update_inline_view(self, request,contest_id):
        if request.method == 'POST' and request.user.is_staff == True:
            selected_items = json.loads(request.POST.get('selected_items', '{}'))
            # selected_items = request.POST.get('selected_items')
            # return JsonResponse({'message': f"정상적으로 받음 {selected_items}"})
            # problem objects (in mariadb)
            inline_objects = ContestProblem.objects.filter(contest_id=contest_id).all()
            
            # 인라인 항목에 있는 문제와 select_item에 대해서 체크 상태를 비교하여, False로 바뀐 항목만 삭제
            # 이미 처리한 문제에 대한 id를 담아 놓기
            for inline_object in inline_objects:
                problem_id = str(inline_object.problem.id)
                if problem_id in selected_items: 
                    if selected_items[problem_id] == False:
                        inline_object.delete()
                    #이미 처리한 문제는 False처리
                    selected_items[problem_id] = False
            
            query = Q()
            for key,value in selected_items.items():
                if value == True:
                    query |= Q(id=key)
            
            if query:
                # problems = Problem.objects.filter(Q(authors__user=request.user) & (query)).distinct().select_related('group')
                problems = Problem.objects.filter((query)).distinct().select_related('group')
            else:
                problems = Problem.objects.none()

            
            contest_problems = []
            for idx,problem in enumerate(problems):
                contest_problem = ContestProblem(
                    problem=problem,
                    contest_id=contest_id,
                    order = idx
                )
                contest_problems.append(contest_problem)

            # 트랜잭션을 사용하여 한 번에 저장
            with transaction.atomic():
                ContestProblem.objects.bulk_create(contest_problems)
            
            return JsonResponse({'message': f"정상적으로 받음 {selected_items}"})
        # 요청이 POST가 아니거나, 사용자가 staff가 아닌 경우 적절한 응답 반환
        return HttpResponse("Unauthorized or invalid Post request", status=401)

    def rejudge_view(self, request, contest_id, problem_id):
        queryset = ContestSubmission.objects.filter(problem_id=problem_id).select_related('submission')
        for model in queryset:
            model.submission.judge(rejudge=True, rejudge_user=request.user)

        self.message_user(request, ngettext('%d submission was successfully scheduled for rejudging.',
                                            '%d submissions were successfully scheduled for rejudging.',
                                            len(queryset)) % len(queryset))
        return HttpResponseRedirect(reverse('admin:judge_contest_change', args=(contest_id,)))

    def rate_all_view(self, request):
        if not request.user.has_perm('judge.contest_rating'):
            raise PermissionDenied()
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('TRUNCATE TABLE `%s`' % Rating._meta.db_table)
            Profile.objects.update(rating=None)
            for contest in Contest.objects.filter(is_rated=True, end_time__lte=timezone.now()).order_by('end_time'):
                rate_contest(contest)
        return HttpResponseRedirect(reverse('admin:judge_contest_changelist'))

    def rate_view(self, request, id):
        if not request.user.has_perm('judge.contest_rating'):
            raise PermissionDenied()
        contest = get_object_or_404(Contest, id=id)
        if not contest.is_rated or not contest.ended:
            raise Http404()
        with transaction.atomic():
            contest.rate()
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('admin:judge_contest_changelist')))

    def get_form(self, request, obj=None, **kwargs):
        form = super(ContestAdmin, self).get_form(request, obj, **kwargs)
        if 'problem_label_script' in form.base_fields:
            # form.base_fields['problem_label_script'] does not exist when the user has only view permission
            # on the model.
            form.base_fields['problem_label_script'].widget = AceWidget('lua', request.profile.ace_theme)

        #랜덤 접근코드 생성
        if obj == None:
            rand_str = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))
            form.base_fields['access_code'].initial = rand_str
        
        perms = ('edit_own_contest', 'edit_all_contest')
        # form.base_fields['curators'].queryset = Profile.objects.filter(
        #     Q(user__is_superuser=True) |
        #     Q(user__groups__permissions__codename__in=perms) |
        #     Q(user__user_permissions__codename__in=perms),
        # ).distinct()

        # form.base_fields['classes'].queryset = Class.get_visible_classes(request.user)
        return form

    def visibility_status(self, obj):
        """
        관리자 페이지에서 공개/비공개 상태를 pill 스타일로 표시
        기존 X/V 이미지로 제공되던 정보를 공개/비공개 텍스트로 띄우기 위한 함수입니다.
        """
        if obj.is_visible:
            return format_html('<span class="pill pill-success">공개</span>')
        else:
            return format_html('<span class="pill pill-danger">비공개</span>')
    
    visibility_status.short_description = _('공개')

    def practice_status(self, obj):
        """관리자 페이지에서 과제/대회 상태를 pill 스타일로 표시"""
        if obj.is_practice:
            return format_html('<span class="pill pill-warning">과제</span>')
        else:
            return format_html('<span class="pill pill-info">대회</span>')
    
    practice_status.short_description = _('과제/대회')

    def rating_status(self, obj):
        """관리자 페이지에서 대회 순위 유무를 pill 스타일로 표시"""
        if obj.is_rated:
            return format_html('<span class="pill pill-success">있음</span>')
        else:
            return format_html('<span class="pill pill-neutral">없음</span>')
    
    rating_status.short_description = _('대회 순위')

    def start_time_display(self, obj):
        """시작 시간을 한국 형식으로 표시"""
        if obj.start_time:
            return obj.start_time.strftime('%Y. %m. %d. %H:%M')
        return '-'
    
    start_time_display.admin_order_field = 'start_time'
    start_time_display.short_description = _('시작 시각')

    def end_time_display(self, obj):
        """종료 시간을 한국 형식으로 표시"""
        if obj.end_time:
            return obj.end_time.strftime('%Y. %m. %d. %H:%M')
        return '-'
    
    end_time_display.admin_order_field = 'end_time'
    end_time_display.short_description = _('종료 시각')


class ContestParticipationForm(ModelForm):
    class Meta:
        widgets = {
            'contest': AdminSelect2Widget(),
            'user': AdminHeavySelect2Widget(data_view='profile_select2'),
        }

class CombinedContestParticipationFilter(FieldListFilter):
    title = ' '
    template = 'admin/input_filter/input_filter_contest_participation.html'  # 템플릿 따로 필요
    
    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.request = request
        self.params = params
        
    def expected_parameters(self):
        return ['contest_name','user_name']
    
    def choices(self, changelist):
        yield {
            'selected': False,
            'query_string': changelist.get_query_string(remove=self.expected_parameters()),
            'display': '초기화',
        }

    def queryset(self, request, queryset):
        contest_name = request.GET.get('contest_name')
        user_name=request.GET.get('user_name')

        if contest_name:
            queryset = queryset.filter(contest__name__icontains=contest_name)

        if user_name:
            queryset=queryset.filter(user__user__username__icontains=user_name)
        
        return queryset

class ContestParticipationAdmin(admin.ModelAdmin):
    fields = ('contest', 'user', 'real_start', 'virtual', 'is_disqualified')
    list_display = ('contest', 'username', 'show_virtual', 'real_start_display', 'score', 'cumtime', 'tiebreaker')
    actions = ['recalculate_results']
    actions_on_bottom = actions_on_top = True
    search_fields = ('contest__key', 'contest__name', 'user__user__username')
    form = ContestParticipationForm
    date_hierarchy = 'real_start'
    list_filter=[('id',CombinedContestParticipationFilter)]
    action_form = CustomActionForm

    

    def get_queryset(self, request):
        return super(ContestParticipationAdmin, self).get_queryset(request).only(
            'contest__name', 'contest__format_name', 'contest__format_config',
            'user__user__username', 'real_start', 'score', 'cumtime', 'tiebreaker', 'virtual',
        )

    def real_start_display(self, obj):
        """시작 시간을 한국 형식으로 표시"""
        if obj.real_start:
            return obj.real_start.strftime('%Y. %m. %d. %H:%M')
        return '-'
    
    real_start_display.admin_order_field = 'real_start'
    real_start_display.short_description = _('시작 시각')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.changed_data and 'is_disqualified' in form.changed_data:
            obj.set_disqualified(obj.is_disqualified)

    def recalculate_results(self, request, queryset):
        count = 0
        for participation in queryset:
            participation.recompute_results()
            count += 1
        self.message_user(request, ngettext('%d participation recalculated.',
                                            '%d participations recalculated.',
                                            count) % count)
    recalculate_results.short_description = _('Recalculate results')

    def username(self, obj):
        return obj.user.username
    username.short_description = _('username')
    username.admin_order_field = 'user__user__username'

    def show_virtual(self, obj):
        return obj.virtual or '-'
    show_virtual.short_description = _('virtual')
    show_virtual.admin_order_field = 'virtual'
