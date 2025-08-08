import json
from calendar import Calendar, SUNDAY
from collections import defaultdict, namedtuple
from datetime import date, datetime, time, timedelta
from functools import partial
from itertools import chain
from operator import attrgetter, itemgetter

from django import forms
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist, PermissionDenied
from django.db import IntegrityError
from django.db.models import BooleanField, Case, Count, F, FloatField, IntegerField, Max, Min, Q, Sum, Value, When
from django.db.models.expressions import CombinedExpression
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse, HttpResponseForbidden, HttpResponseServerError
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.timezone import make_aware
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic import ListView, TemplateView
from django.views.generic.detail import DetailView, SingleObjectMixin, View
from django.views.generic.list import BaseListView
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from icalendar import Calendar as ICalendar, Event
from reversion import revisions

from judge import event_poster as event
from judge.comments import CommentedDetailView
from judge.forms import ContestCloneForm
from judge.models import Contest, ContestMoss, ContestParticipation, ContestProblem, ContestTag, ContestSubmission, \
    Problem, Profile, Submission, Subject
from judge.tasks import run_moss
from judge.utils.celery import redirect_to_task_status
from judge.utils.opengraph import generate_opengraph
from judge.utils.problems import _get_result_data
from judge.utils.ranker import ranker
from judge.utils.stats import get_bar_chart, get_pie_chart
from judge.utils.views import DiggPaginatorMixin, QueryStringSortMixin, SingleObjectFormView, TitleMixin, \
    generic_message
from judge.utils.problems import contest_attempted_ids, contest_completed_ids, hot_problems, user_attempted_ids, \
    user_completed_ids

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


__all__ = ['ContestList', 'ContestDetail', 'ContestRanking', 'ContestJoin', 'ContestLeave', 'ContestCalendar',
           'ContestClone', 'ContestStats', 'ContestMossView', 'ContestMossDelete', 'contest_ranking_ajax',
           'ContestParticipationList', 'ContestParticipationDisqualify', 'get_contest_ranking_list',
           'base_contest_ranking_list']

# JSON으로 대회 결과 출력
from openpyxl import Workbook
from io import BytesIO
import re

import logging


@require_POST
@csrf_exempt
def verify_contest_code(request, contest_key):
    data = json.loads(request.body)
    entered_code = data.get('code')
    user = request.user  # 로그인된 사용자
    profile = request.profile  # 사용자의 프로필

    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        return JsonResponse({'valid': False, 'error': 'Contest not found'})

    if contest.access_code != entered_code:
        return JsonResponse({'valid': False, 'error': 'Invalid access code'})

    # Check if the user is banned from the contest
    if not user.is_superuser and contest.banned_users.filter(id=profile.id).exists():
        return JsonResponse({'valid': False, 'error': 'You are banned from joining this contest'})

    # Determine if the user can participate or spectate
    SPECTATE = ContestParticipation.SPECTATE
    LIVE = ContestParticipation.LIVE

    if contest.ended:
        # Handle virtual participation after contest ended
        while True:
            virtual_id = max((ContestParticipation.objects.filter(contest=contest, user=profile)
                              .aggregate(virtual_id=Max('virtual'))['virtual_id'] or 0) + 1, 1)
            try:
                participation = ContestParticipation.objects.create(
                    contest=contest, user=profile, virtual=virtual_id,
                    real_start=timezone.now(),
                )
            except IntegrityError:
                continue
            else:
                break
    else:
        if contest.is_live_joinable_by(user):
            participation_type = LIVE
        elif contest.is_spectatable_by(user):
            participation_type = SPECTATE
        else:
            return JsonResponse({'valid': False, 'error': 'Cannot join this contest'})

        try:
            participation = ContestParticipation.objects.get(
                contest=contest, user=profile, virtual=participation_type,
            )
        except ContestParticipation.DoesNotExist:
            participation = ContestParticipation.objects.create(
                contest=contest, user=profile, virtual=participation_type,
                real_start=timezone.now(),
            )
        else:
            if participation.ended:
                participation = ContestParticipation.objects.get_or_create(
                    contest=contest, user=profile, virtual=SPECTATE,
                    defaults={'real_start': timezone.now()},
                )[0]

    profile.current_contest = participation
    profile.save()
    contest._updating_stats_only = True
    contest.update_user_count()

    return JsonResponse({'valid': True, 'redirect_url': reverse('contest_view', args=[contest.key])})

class ContestDetailJSON(View):
    def get(self, request, *args, **kwargs):
        contest_key = kwargs.get('contest')
        contest, exists = _find_contest(request, contest_key, private_check=False)
        if not exists:
            return JsonResponse({'error': 'Contest not found'}, status=404)

        contest_data = {
            'name': contest.name,
            'start_time': contest.start_time,
            'end_time': contest.end_time,
            'description': contest.description,
            'authors': [author.username for author in contest.authors.all()],
            'curators': [curator.username for curator in contest.curators.all()],
            'testers': [tester.username for tester in contest.testers.all()],
            'tags': [tag.name for tag in contest.tags.all()],
            'problems': [{
                'name': problem.problem.name,
                'order': problem.order,
                'points': problem.points
            } for problem in contest.contest_problems.select_related('problem')],
        }

        ranking_info = self.get_ranking_info(request, contest)
        contest_data['ranking'] = ranking_info

        return JsonResponse(contest_data, safe=False)

    def get_ranking_info(self, request, contest):
        if not contest.can_see_full_scoreboard(request.user):
            queryset = contest.users.filter(user=request.profile, virtual=ContestParticipation.LIVE)
            users, problems = get_contest_ranking_list(
                request, contest,
                ranking_list=partial(base_contest_ranking_list, queryset=queryset),
                ranker=lambda users, key: ((_('???'), user) for user in users),
            )
        else:
            users, problems = get_contest_ranking_list(request, contest)

        ranking_list = []
        for rank, user in users:
            ranking_list.append({
                'rank': rank,
                'username': user.username,
                'points': user.points,
                'cumtime': user.cumtime,
                'tiebreaker': user.tiebreaker,
                'problems': [
                    {
                        'name': problem.problem.name,
                        'order': problem.order,
                        'points': problem.points,
                        'status': user.problem_cells[problems.index(problem)],
                    }
                    for problem in problems
                ]
            })

        return ranking_list


class ContestDetailExcelDownload(View):
    def get(self, request, *args, **kwargs):
        try:
            contest_key = kwargs.get('contest')
            contest, exists = _find_contest(request, contest_key, private_check=False)
            if not exists:
                raise Http404("Contest not found")

            # 권한 검증 로직 추가
            if not contest.can_see_full_scoreboard(request.user):
                raise PermissionDenied("You don't have permission to download contest results.")

            # 권한이 있는 사용자만 엑셀 다운로드 가능
            if not (request.user.is_staff or contest.is_editable_by(request.user) or 
                    request.user.has_perm('judge.see_private_contest')):
                raise PermissionDenied("You don't have permission to download contest results.")

            contest_data = {
                'name': contest.name,
                'start_time': contest.start_time,
                'end_time': contest.end_time,
                'description': contest.description,
                'authors': [author.username for author in contest.authors.all()],
                'curators': [curator.username for curator in contest.curators.all()],
                'testers': [tester.username for tester in contest.testers.all()],
                'tags': [tag.name for tag in contest.tags.all()],
                'problems': [{
                    'name': problem.problem.name,
                    'order': problem.order,
                    'points': problem.points
                } for problem in contest.contest_problems.select_related('problem')],
            }

            ranking_info = self.get_ranking_info(request, contest)
            contest_data['ranking'] = ranking_info

            # 엑셀 파일 생성
            wb = Workbook()
            ws = wb.active
            ws.title = "Contest Details"

            # 문제 이름을 열 헤더로 설정
            headers = ["Rank", "Username", "First Name"] + [problem['name'] for problem in contest_data['problems']] + ["Total Points"]
            ws.append(headers)

            # 데이터 작성
            for user in contest_data['ranking']:
                rank = user['rank']
                username = user['username']
                first_name = user['first_name']  # first_name 추가
                problems_points = [0.0] * len(contest_data['problems'])
                for problem in user['problems']:
                    problem_index = next((index for (index, d) in enumerate(contest_data['problems']) if d["name"] == problem['name']), None)
                    # status에서 점수를 추출
                    point = self.extract_point_from_status(problem['status'])
                    problems_points[problem_index] = point
                total_points = user['points']
                ws.append([rank, username, first_name] + problems_points + [total_points])

            # 엑셀 파일을 BytesIO에 저장
            output = BytesIO()
            wb.save(output)
            output.seek(0)

            # 응답 설정
            response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename={contest.name}_details.xlsx'

            return response
        
        except Exception as e:
            return HttpResponseServerError(f"An error occurred: {str(e)}")

    def extract_point_from_status(self, status):
        # status에서 점수를 추출하는 정규식
        match = re.search(r'>(\d+(?:\.\d+)?)<div', status)
        if match:
            return float(match.group(1))
        return 0.0

    def get_ranking_info(self, request, contest):
        if not contest.can_see_full_scoreboard(request.user):
            queryset = contest.users.filter(user=request.profile, virtual=ContestParticipation.LIVE)
            users, problems = get_contest_ranking_list(
                request, contest,
                ranking_list=partial(base_contest_ranking_list, queryset=queryset),
                ranker=lambda users, key: ((_('???'), user) for user in users),
            )
        else:
            users, problems = get_contest_ranking_list(request, contest)

        ranking_list = []
        for rank, user in users:
            ranking_list.append({
                'rank': rank,
                'username': user.username,
                'first_name': user.user.first_name if hasattr(user, 'user') else '',  # first_name 추가
                'points': user.points,
                'cumtime': user.cumtime,
                'tiebreaker': user.tiebreaker,
                'problems': [
                    {
                        'name': problem.problem.name,
                        'order': problem.order,
                        'points': problem.points,
                        'status': user.problem_cells[problems.index(problem)],
                    }
                    for problem in problems
                ]
            })

        return ranking_list
        

def _find_contest(request, key, private_check=True):
    try:
        contest = Contest.objects.get(key=key)
        if private_check and not contest.is_accessible_by(request.user):
            raise ObjectDoesNotExist()
    except ObjectDoesNotExist:
        return generic_message(request, _('No such contest'),
                               _('Could not find a contest with the key "%s".') % key, status=404), False
    return contest, True


class ContestListMixin(object):
    def get(self, request, *args, **kwargs):
        self.subject_ids = None
        
        if 'subject_id' in request.GET:
            try:
                self.subject_ids = list(map(int, request.GET.getlist('subject_id')))
            except ValueError:
                pass
            
        return super(ContestListMixin, self).get(request, *args, **kwargs)
    def get_queryset(self):
        queryset = Contest.get_visible_contests(self.request.user)
        
        querys = Q()
        
        if self.subject_ids is not None:
            for id in self.subject_ids:
                querys |= Q(subject = id)
            
            queryset = queryset.filter(querys)
            
        return queryset
        

class ContestList(QueryStringSortMixin, DiggPaginatorMixin, TitleMixin, ContestListMixin, ListView):
    model = Contest
    paginate_by = 20
    template_name = 'contest/list.html'
    title = gettext_lazy(_('대회'))
    title_info = '진행 중 / 진행 예정 대회 목록'
    context_object_name = 'past_contests'
    all_sorts = frozenset(('name', 'user_count', 'start_time'))
    default_desc = frozenset(('name', 'user_count'))
    default_sort = '-start_time'

    @cached_property
    def _now(self):
        return timezone.now()

    def _get_queryset(self):
        return super().get_queryset().prefetch_related(
            'tags',
            'authors',
            'curators',
            'testers',
            'spectators',
        )

    def get_queryset(self):
        return self._get_queryset().order_by(self.order, 'key').filter(end_time__lt=self._now)

    def get_context_data(self, **kwargs):
        context = super(ContestList, self).get_context_data(**kwargs)
        spectate, present, active, future = [], [], [], []
        finished = set()
        
        is_practice_view = self.kwargs.get('is_practice')
        
        for contest in self._get_queryset().exclude(end_time__lt=self._now):
            if contest.is_practice != is_practice_view:
                continue
            if contest.start_time > self._now:
                future.append(contest)
            else:
                present.append(contest)

        if self.request.user.is_authenticated:
            for participation in (
                ContestParticipation.objects.filter(virtual__in=[0], user=self.request.profile, contest_id__in=present)
                .select_related('contest')
                .prefetch_related('contest__authors', 'contest__curators', 'contest__testers', 'contest__spectators')
                .annotate(key=F('contest__key'))
            ):
                if participation.ended:
                    finished.add(participation.contest.key)
                else:
                    active.append(participation)
                    present.remove(participation.contest)

        for contest in present:
            if contest.is_spectatable_by(self.request.user):
                spectate.append(contest)
                
        present = list(set(present) - set(spectate))
        
        active.sort(key=attrgetter('end_time', 'key'))
        present.sort(key=attrgetter('end_time', 'key'))
        spectate.sort(key=attrgetter('end_time', 'key'))
        future.sort(key=attrgetter('start_time'))
            
        context['title_info'] = self.title_info
        context['active_participations'] = active
        context['current_contests'] = present
        context['spectate_contests'] = spectate
        context['future_contests'] = future
        context['finished_contests'] = finished
        context['now'] = self._now
        context['first_page_href'] = '.'
        context['page_suffix'] = '#past-contests'
        context['is_practice'] = 0
        
        subjects = Subject.objects.all()
        context['subjects'] = subjects
        
        if is_practice_view:
            context['title'] = gettext_lazy(_('과제'))
            context['title_info'] = '진행 중 / 진행 예정 과제 목록'
            context['is_practice'] = 1
        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        
        return context

    # ContestJoin의 기능 추가

    def post(self, request, *args, **kwargs):
        contest_key = request.POST.get('contest_key')
        access_code = request.POST.get('access_code')
        if contest_key:
            self.object = get_object_or_404(Contest, key=contest_key)
            try:
                return self.join_contest(request, access_code)
            except ContestAccessDenied:
                if access_code:
                    return self.ask_for_access_code(ContestAccessCodeForm(request.POST))
                else:
                    return HttpResponseRedirect(request.path)
        return super().post(request, *args, **kwargs)

    def join_contest(self, request, access_code=None):
        contest = self.object

        if not contest.started and not (self.is_editor or self.is_tester):
            return generic_message(request, _('Contest not ongoing'),
                                   _('"%s" is not currently ongoing.') % contest.name)

        profile = request.profile

        if not request.user.is_superuser and contest.banned_users.filter(id=profile.id).exists():
            return generic_message(request, _('Banned from joining'),
                                   _('You have been declared persona non grata for this contest. '
                                     'You are permanently barred from joining this contest.'))

        requires_access_code = (not self.can_edit and contest.access_code and access_code != contest.access_code)
        if contest.ended:
            if requires_access_code:
                raise ContestAccessDenied()

            while True:
                virtual_id = max((ContestParticipation.objects.filter(contest=contest, user=profile)
                                  .aggregate(virtual_id=Max('virtual'))['virtual_id'] or 0) + 1, 1)
                try:
                    participation = ContestParticipation.objects.create(
                        contest=contest, user=profile, virtual=virtual_id,
                        real_start=timezone.now(),
                    )
                except IntegrityError:
                    pass
                else:
                    break
        else:
            SPECTATE = ContestParticipation.SPECTATE
            LIVE = ContestParticipation.LIVE

            if contest.is_live_joinable_by(request.user):
                participation_type = LIVE
            elif contest.is_spectatable_by(request.user):
                participation_type = SPECTATE
            else:
                return generic_message(request, _('Cannot enter'),
                                       _('You are not able to join this contest.'))
            try:
                participation = ContestParticipation.objects.get(
                    contest=contest, user=profile, virtual=participation_type,
                )
            except ContestParticipation.DoesNotExist:
                if requires_access_code:
                    raise ContestAccessDenied()

                participation = ContestParticipation.objects.create(
                    contest=contest, user=profile, virtual=participation_type,
                    real_start=timezone.now(),
                )
            else:
                if participation.ended:
                    participation = ContestParticipation.objects.get_or_create(
                        contest=contest, user=profile, virtual=SPECTATE,
                        defaults={'real_start': timezone.now()},
                    )[0]

        profile.current_contest = participation
        profile.save()
        contest._updating_stats_only = True
        contest.update_user_count()
        return HttpResponseRedirect(reverse('contest_view', args=[contest.key]))

    def ask_for_access_code(self, form=None):
        contest = self.object
        wrong_code = False
        if form:
            if form.is_valid():
                if form.cleaned_data['access_code'] == contest.access_code:
                    return self.join_contest(self.request, form.cleaned_data['access_code'])
                wrong_code = True
        else:
            form = ContestAccessCodeForm()
        return render(self.request, 'contest/access_code.html', {
            'form': form, 'wrong_code': wrong_code,
            'title': _('Enter access code for "%s"') % contest.name,
        })


class ContestPastList(ContestList):
    template_name = 'contest/pastlist.html'
    title = gettext_lazy(_('대회'))
    title_info = '종료된 대회 목록'
    context_object_name = 'past_contests'
    
    def dispatch(self, request, *args, **kwargs):
        self.is_practice_view = kwargs.get('is_practice')
        if self.is_practice_view not in [0, 1]:
            raise Http404(self.is_practice_view)
        self.is_practice_view = bool(self.is_practice_view)

        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_practice'] = 1 if self.is_practice_view else 0
        spectate, last_other, last_own = [], [], []

        is_practice_view = self.kwargs.get('is_practice')

        for contest in self._get_queryset():
            if contest.is_practice != is_practice_view:
                continue
            if contest.end_time > self._now:
                last_other.append(contest)
            else:
                spectate.append(contest)

        for contest in spectate:
            if contest.is_spectatable_by(self.request.user):
                last_own.append(contest)
                
        spectate = list(set(spectate) - set(last_own))
        last_own.sort(key=attrgetter('end_time', 'key'),reverse=True)
        spectate.sort(key=attrgetter('end_time', 'key'),reverse=True)

        # 페이지네이션
        own_page_number = self.request.GET.get('own_page', 1)
        other_page_number = self.request.GET.get('other_page', 1)
        own_per_page = 15
        other_per_page = 15

        paginated_own = Paginator(last_own, own_per_page)
        paginated_other = Paginator(spectate, other_per_page)

        # 요청한 페이지 번호 가져오기
        own_page_number = self.request.GET.get('own_page', 1)
        other_page_number = self.request.GET.get('other_page', 1)

        past_own_contests = paginated_own.get_page(own_page_number)
        past_other_contests = paginated_other.get_page(other_page_number)

        context['past_own_contests'] = past_own_contests
        context['past_other_contests'] = past_other_contests

        subjects = Subject.objects.all()
        context['subjects'] = subjects
        
        if self.is_practice_view:
            context['title'] = '과제'
            context['title_info'] = '종료된 과제 목록'

        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        return context
    
    def get_queryset(self):
        return self._get_queryset().order_by(self.order, 'key').filter(end_time__lt=self._now, is_practice=self.is_practice_view)

# class ContestSpectateList(ContestList):
#     template_name = 'contest/spectatelist.html'
#     title = '대회'
#     title_info = ''


class PrivateContestError(Exception):
    # def __init__(self, name, is_private, is_organization_private, orgs, classes):
    #     self.name = name
    #     self.is_private = is_private
    #     self.is_organization_private = is_organization_private
    #     self.orgs = orgs
    #     self.classes = classes
    def __init__(self, name, is_private):
        self.name = name
        self.is_private = is_private


class ContestMixin(object):
    context_object_name = 'contest'
    model = Contest
    slug_field = 'key'
    slug_url_kwarg = 'contest'

    def is_user_in_contest(self, user):
        """
        현재 사용자가 현재 대회에 참가하고 있는지 확인합니다.
        """
        if not user.is_authenticated:
            return False  
        
        if hasattr(self, 'object') and isinstance(self.object, Contest):
            return self.object.is_in_contest(user)
        return False

    def get_completed_problems(self):
        if not self.request.user.is_authenticated:
            return ()  

        if self.is_user_in_contest(self.request.user):
            return contest_completed_ids(self.request.user.profile.current_contest)
        
        return user_completed_ids(self.request.user.profile) if hasattr(self.request.user, 'profile') else ()

    def get_attempted_problems(self):
        if not self.request.user.is_authenticated:
            return ()
        
        if self.is_user_in_contest(self.request.user):
            return contest_attempted_ids(self.request.user.profile.current_contest)
        
        return user_attempted_ids(self.request.user.profile) if hasattr(self.request.user, 'profile') else ()


    @cached_property
    def is_editor(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.profile.id in self.object.editor_ids

    @cached_property
    def is_tester(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.profile.id in self.object.tester_ids

    @cached_property
    def is_spectator(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.profile.id in self.object.spectator_ids

    @cached_property
    def can_edit(self):
        return self.object.is_editable_by(self.request.user)

    def get_context_data(self, **kwargs):

        context = super(ContestMixin, self).get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            try:
                context['live_participation'] = (
                    self.request.profile.contest_history.get(
                        contest=self.object,
                        virtual=ContestParticipation.LIVE,
                    )
                )
            except ContestParticipation.DoesNotExist:
                context['live_participation'] = None
                context['has_joined'] = False
            else:
                context['has_joined'] = True
        else:
            context['live_participation'] = None
            context['has_joined'] = False

        context['now'] = timezone.now()
        context['is_editor'] = self.is_editor
        context['is_tester'] = self.is_tester
        context['is_spectator'] = self.is_spectator
        context['can_edit'] = self.can_edit

        if not self.object.og_image or not self.object.summary:
            metadata = generate_opengraph('generated-meta-contest:%d' % self.object.id,
                                          self.object.description, 'contest')
        context['meta_description'] = self.object.summary or metadata[0]
        context['og_image'] = self.object.og_image or metadata[1]
        context['has_moss_api_key'] = settings.MOSS_API_KEY is not None
        context['logo_override_image'] = self.object.logo_override_image
        # if not context['logo_override_image'] and self.object.organizations.count() == 1:
        #     context['logo_override_image'] = self.object.organizations.first().logo_override_image

        return context

    def get_object(self, queryset=None):
        contest = super(ContestMixin, self).get_object(queryset)
        contest.update_user_count()
        profile = self.request.profile
        if (profile is not None and
                ContestParticipation.objects.filter(id=profile.current_contest_id, contest_id=contest.id).exists()):
            return contest

        try:
            contest.access_check(self.request.user)
        except Contest.PrivateContest:
            # raise PrivateContestError(contest.name, contest.is_private, contest.is_organization_private,
            #                           contest.organizations.all(), contest.classes.all())
            raise PrivateContestError(contest.name, contest.is_private)
        except Contest.Inaccessible:
            raise Http404()
        else:
            return contest

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(ContestMixin, self).dispatch(request, *args, **kwargs)
        except Http404:
            key = kwargs.get(self.slug_url_kwarg, None)
            if key:
                return generic_message(request, _('No such contest'),
                                       _('Could not find a contest with the key "%s".') % key)
            else:
                return generic_message(request, _('No such contest'),
                                       _('Could not find such contest.'))
        except PrivateContestError as e:
            return render(request, 'contest/private.html', {
                'error': e, 'title': _('Access to contest "%s" denied') % e.name,
            }, status=403)

## 해당 믹스인은 유저의 현재 참가중인 대회라면, 자동으로 해당 대회에 재참가하도록 만드는 기능
class ContestAutoJoinMixin(object):
    def dispatch(self, request, *args, **kwargs):
        try:
            contest = self.get_object()
        except Contest.DoesNotExist:
            raise Http404()
        
        #종료된 대회라면, 모의 참여를 직접 하기때문에, 자동 참여 기능 비활성화 
        if request.user.is_authenticated and not contest.ended:
            participation = contest.users.filter(
                virtual=ContestParticipation.LIVE, 
                user=request.user.profile
            ).first()
            # 참가자이면서 현재 대회 상태가 해당 대회가 아닌 경우가 참여중인 대회
            if participation and (request.user.profile.current_contest is None or request.user.profile.current_contest.contest != contest):
                request.user.profile.current_contest = participation
                request.user.profile.save()
                request.participation = participation #현재 request에 참가자 정보 갱신

        return super(ContestAutoJoinMixin, self).dispatch(request, *args, **kwargs)
        
        

from django.db.models import Count, Q, BooleanField, Case, When, F, Sum
from django.db.models.functions import Coalesce

class ContestDetail(ContestMixin, TitleMixin, ContestAutoJoinMixin, CommentedDetailView):
    template_name = 'contest/contest.html'

    def get_comment_page(self):
        return 'c:%s' % self.object.key

    def get_title(self):
        return self.object.name

    def get_context_data(self, **kwargs):
        context = super(ContestDetail, self).get_context_data(**kwargs)
        contest = self.object
        problems = list(contest.contest_problems.all())

        context['completed_problem_ids'] = self.get_completed_problems()
        context['attempted_problems'] = self.get_attempted_problems()

        context['is_participation'] = ContestParticipation.objects.filter(
            virtual=0, user=self.request.profile, contest_id=self.object.id
        ).exists()

        contest_problems = Problem.objects.filter(contests__contest=self.object) \
            .order_by('contests__order').defer('description') \
            .annotate(
                has_public_editorial=Case(
                    When(solution__is_public=True, solution__publish_on__lte=timezone.now(), then=True),
                    default=False,
                    output_field=BooleanField(),
                )
            )

        problem_stats = (
            Submission.objects.filter(contest_object_id=self.object.id)
            .values('problem_id')
            .annotate(
                total_submissions=Count('id'),
                ac_submissions=Count('id', filter=Q(result='AC')),
                correct_users=Count('user_id', filter=Q(result='AC'), distinct=True),
            )
        )

        stats_map = {stat['problem_id']: stat for stat in problem_stats}

        for problem in contest_problems:
            stats = stats_map.get(problem.id, {
                'total_submissions': 0,
                'ac_submissions': 0,
                'correct_users': 0,
            })
            problem.total_submissions = stats['total_submissions'] # 특정 대회의 특정 문제에 대한 총 제출 갯수
            problem.ac_submissions = stats['ac_submissions'] # 특정 대회의 특정 문제에 대한 정답 제출 갯수
            problem.correct_users = stats['correct_users'] # 특정 대회의 특정 문제에 대한 맞힌 사람 수
            problem.correct_rate = (
                (stats['ac_submissions'] / stats['total_submissions'] * 100)
                if stats['total_submissions'] > 0 else 0
            )
        
        # 현재 contest_problems 리스트는 contestproblem 모델이 아닌 problem 모델에서 문제를 가져옴. (problems 리스트가 contestproblem 모델델)
        # 각 대회별 문제의 포인트(점수)가 반영되지 않고, 해당 문제의 포인트가 반영되어 이걸 바꿔주는 코드
        contest_points_map = { cp.problem.id: cp.points for cp in problems }
        for problem in contest_problems:
            if problem.id in contest_points_map:
                problem.points = contest_points_map[problem.id]

        context['contest_problems'] = contest_problems

        context['metadata'] = {
            'has_public_editorials': any(
                problem.is_public and problem.has_public_editorial for problem in contest_problems
            ),
        }
        context['metadata'].update(
            **self.object.contest_problems
            .annotate(
                partials_enabled=F('partial').bitand(F('problem__partial')),
                pretests_enabled=F('is_pretested').bitand(F('contest__run_pretests_only')),
            )
            .aggregate(
                has_partials=Sum('partials_enabled'),
                has_pretests=Sum('pretests_enabled'),
                has_submission_cap=Sum('max_submissions'),
                problem_count=Count('id'),
            ),
        )

        return context


class ContestClone(ContestMixin, PermissionRequiredMixin, TitleMixin, SingleObjectFormView):
    title = gettext_lazy('Clone Contest')
    template_name = 'contest/clone.html'
    form_class = ContestCloneForm
    permission_required = 'judge.clone_contest'

    def form_valid(self, form):
        contest = self.object

        tags = contest.tags.all()
        # organizations = contest.organizations.all()
        private_contestants = contest.private_contestants.all()
        view_contest_scoreboard = contest.view_contest_scoreboard.all()
        # contest_problems = contest.contest_problems.all()
        contest_problems = list(contest.contest_problems.all())
        old_key = contest.key

        contest.pk = None
        contest.is_visible = False
        contest.user_count = 0
        contest.locked_after = None
        contest.name = form.cleaned_data['name']
        contest.key = 'NoKey'
        with revisions.create_revision(atomic=True):
            contest.save()
            contest.tags.set(tags)
            # contest.organizations.set(organizations)
            contest.private_contestants.set(private_contestants)
            contest.view_contest_scoreboard.set(view_contest_scoreboard)
            contest.authors.add(self.request.profile)

            for problem in contest_problems:
                problem.contest = contest
                problem.pk = None
            
            ContestProblem.objects.bulk_create(contest_problems)

            revisions.set_user(self.request.user)
            revisions.set_comment(_('Cloned contest from %s') % old_key)

        return HttpResponseRedirect(reverse('admin:judge_contest_change', args=(contest.id,)))


class ContestAccessDenied(Exception):
    pass


class ContestAccessCodeForm(forms.Form):
    access_code = forms.CharField(max_length=255)

    def __init__(self, *args, **kwargs):
        super(ContestAccessCodeForm, self).__init__(*args, **kwargs)
        self.fields['access_code'].widget.attrs.update({'autocomplete': 'off'})


class ContestJoin(LoginRequiredMixin, ContestMixin, SingleObjectMixin, View):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.ask_for_access_code()

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            return self.join_contest(request)
        except ContestAccessDenied:
            if request.POST.get('access_code'):
                return self.ask_for_access_code(ContestAccessCodeForm(request.POST))
            else:
                return HttpResponseRedirect(request.path)

    def join_contest(self, request, access_code=None):
        contest = self.object

        if not contest.started and not (self.is_editor or self.is_tester):
            return generic_message(request, _('Contest not ongoing'),
                                   _('"%s" is not currently ongoing.') % contest.name)

        profile = request.profile

        if not request.user.is_superuser and contest.banned_users.filter(id=profile.id).exists():
            return generic_message(request, _('Banned from joining'),
                                   _('You have been declared persona non grata for this contest. '
                                     'You are permanently barred from joining this contest.'))

        requires_access_code = (not self.can_edit and contest.access_code and access_code != contest.access_code)
        if contest.ended:
            if requires_access_code:
                raise ContestAccessDenied()

            while True:
                virtual_id = max((ContestParticipation.objects.filter(contest=contest, user=profile)
                                  .aggregate(virtual_id=Max('virtual'))['virtual_id'] or 0) + 1, 1)
                try:
                    participation = ContestParticipation.objects.create(
                        contest=contest, user=profile, virtual=virtual_id,
                        real_start=timezone.now(),
                    )
                # There is obviously a race condition here, so we keep trying until we win the race.
                except IntegrityError:
                    pass
                else:
                    break
        else:
            SPECTATE = ContestParticipation.SPECTATE
            LIVE = ContestParticipation.LIVE

            if contest.is_live_joinable_by(request.user):
                participation_type = LIVE
            elif contest.is_spectatable_by(request.user):
                participation_type = SPECTATE
            else:
                return generic_message(request, _('Cannot enter'),
                                       _('You are not able to join this contest.'))
            try:
                participation = ContestParticipation.objects.get(
                    contest=contest, user=profile, virtual=participation_type,
                )
            except ContestParticipation.DoesNotExist:
                if requires_access_code:
                    raise ContestAccessDenied()

                participation = ContestParticipation.objects.create(
                    contest=contest, user=profile, virtual=participation_type,
                    real_start=timezone.now(),
                )
            else:
                if participation.ended:
                    participation = ContestParticipation.objects.get_or_create(
                        contest=contest, user=profile, virtual=SPECTATE,
                        defaults={'real_start': timezone.now()},
                    )[0]

        profile.current_contest = participation
        profile.save()
        contest._updating_stats_only = True
        contest.update_user_count()
        return HttpResponseRedirect(reverse('contest_view', args=[contest.key]))

    def ask_for_access_code(self, form=None):
        contest = self.object
        wrong_code = False
        if form:
            if form.is_valid():
                if form.cleaned_data['access_code'] == contest.access_code:
                    return self.join_contest(self.request, form.cleaned_data['access_code'])
                wrong_code = True
        else:
            form = ContestAccessCodeForm()
        return render(self.request, 'contest/access_code.html', {
            'form': form, 'wrong_code': wrong_code,
            'title': _('Enter access code for "%s"') % contest.name,
        })


class ContestLeave(LoginRequiredMixin, ContestMixin, SingleObjectMixin, View):
    def post(self, request, *args, **kwargs):
        contest = self.get_object()

        profile = request.profile
        if profile.current_contest is None or profile.current_contest.contest_id != contest.id:
            return generic_message(request, _('No such contest'),
                                   _('You are not in contest "%s".') % contest.key, 404)

        profile.remove_contest()
        is_practice = 1 if contest.is_practice else 0
        return HttpResponseRedirect(reverse('contest_list', args=(is_practice,)))


ContestDay = namedtuple('ContestDay', 'date is_pad is_today starts ends oneday')


class ContestCalendar(TitleMixin, ContestListMixin, TemplateView):
    firstweekday = SUNDAY
    template_name = 'contest/calendar.html'

    def get(self, request, *args, **kwargs):
        try:
            self.year = int(kwargs['year'])
            self.month = int(kwargs['month'])
        except (KeyError, ValueError):
            raise ImproperlyConfigured('ContestCalendar requires integer year and month')
        self.today = timezone.now().date()
        return self.render()

    def render(self):
        context = self.get_context_data()
        return self.render_to_response(context)

    def get_contest_data(self, start, end):
        end += timedelta(days=1)
        contests = self.get_queryset().filter(Q(start_time__gte=start, start_time__lt=end) |
                                              Q(end_time__gte=start, end_time__lt=end))
        starts, ends, oneday = (defaultdict(list) for i in range(3))
        for contest in contests:
            start_date = timezone.localtime(contest.start_time).date()
            end_date = timezone.localtime(contest.end_time - timedelta(seconds=1)).date()
            if start_date == end_date:
                oneday[start_date].append(contest)
            else:
                starts[start_date].append(contest)
                ends[end_date].append(contest)
        return starts, ends, oneday

    def get_table(self):
        calendar = Calendar(self.firstweekday).monthdatescalendar(self.year, self.month)
        starts, ends, oneday = self.get_contest_data(make_aware(datetime.combine(calendar[0][0], time.min)),
                                                     make_aware(datetime.combine(calendar[-1][-1], time.min)))
        return [[ContestDay(
            date=date, is_pad=date.month != self.month,
            is_today=date == self.today, starts=starts[date], ends=ends[date], oneday=oneday[date],
        ) for date in week] for week in calendar]

    def get_context_data(self, **kwargs):
        context = super(ContestCalendar, self).get_context_data(**kwargs)

        try:
            month = date(self.year, self.month, 1)
        except ValueError:
            raise Http404()
        else:
            context['title'] = _('Contests in %(month)s') % {'month': date_filter(month, _('F Y'))}

        dates = Contest.objects.aggregate(min=Min('start_time'), max=Max('end_time'))
        min_month = (self.today.year, self.today.month)
        if dates['min'] is not None:
            min_month = dates['min'].year, dates['min'].month
        max_month = (self.today.year, self.today.month)
        if dates['max'] is not None:
            max_month = max((dates['max'].year, dates['max'].month), (self.today.year, self.today.month))

        month = (self.year, self.month)
        if month < min_month or month > max_month:
            # 404 is valid because it merely declares the lack of existence, without any reason
            raise Http404()

        context['now'] = timezone.now()
        context['calendar'] = self.get_table()
        context['curr_month'] = date(self.year, self.month, 1)

        if month > min_month:
            context['prev_month'] = date(self.year - (self.month == 1), 12 if self.month == 1 else self.month - 1, 1)
        else:
            context['prev_month'] = None

        if month < max_month:
            context['next_month'] = date(self.year + (self.month == 12), 1 if self.month == 12 else self.month + 1, 1)
        else:
            context['next_month'] = None
        return context


class ContestICal(TitleMixin, ContestListMixin, BaseListView):
    def generate_ical(self):
        cal = ICalendar()
        cal.add('prodid', '-//DMOJ//NONSGML Contests Calendar//')
        cal.add('version', '2.0')

        now = timezone.now().astimezone(timezone.utc)
        domain = self.request.get_host()
        for contest in self.get_queryset():
            event = Event()
            event.add('uid', f'contest-{contest.key}@{domain}')
            event.add('summary', contest.name)
            event.add('location', self.request.build_absolute_uri(contest.get_absolute_url()))
            event.add('dtstart', contest.start_time.astimezone(timezone.utc))
            event.add('dtend', contest.end_time.astimezone(timezone.utc))
            event.add('dtstamp', now)
            cal.add_component(event)
        return cal.to_ical()

    def render_to_response(self, context, **kwargs):
        return HttpResponse(self.generate_ical(), content_type='text/calendar')


class ContestStats(TitleMixin, ContestMixin, DetailView):
    template_name = 'contest/stats.html'

    def get_title(self):
        return _('%s Statistics') % self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not (self.object.ended or self.can_edit):
            raise Http404()

        queryset = Submission.objects.filter(contest_object=self.object)

        ac_count = Count(Case(When(result='AC', then=Value(1)), output_field=IntegerField()))
        ac_rate = CombinedExpression(ac_count / Count('problem'), '*', Value(100.0), output_field=FloatField())

        status_count_queryset = list(
            queryset.values('problem__code', 'result').annotate(count=Count('result'))
                    .values_list('problem__code', 'result', 'count'),
        )
        labels, codes = [], []
        contest_problems = self.object.contest_problems.order_by('order').values_list('problem__name', 'problem__code')
        if contest_problems:
            labels, codes = zip(*contest_problems)
        num_problems = len(labels)
        status_counts = [[] for i in range(num_problems)]
        for problem_code, result, count in status_count_queryset:
            if problem_code in codes:
                status_counts[codes.index(problem_code)].append((result, count))

        result_data = defaultdict(partial(list, [0] * num_problems))
        for i in range(num_problems):
            for category in _get_result_data(defaultdict(int, status_counts[i]))['categories']:
                result_data[category['code']][i] = category['count']

        stats = {
            'problem_status_count': {
                'labels': labels,
                'datasets': [
                    {
                        'label': name,
                        'backgroundColor': settings.DMOJ_STATS_SUBMISSION_RESULT_COLORS[name],
                        'data': data,
                    }
                    for name, data in result_data.items()
                ],
            },
            'problem_ac_rate': get_bar_chart(
                queryset.values('contest__problem__order', 'problem__name').annotate(ac_rate=ac_rate)
                        .order_by('contest__problem__order').values_list('problem__name', 'ac_rate'),
            ),
            'language_count': get_pie_chart(
                queryset.values('language__name').annotate(count=Count('language__name'))
                        .filter(count__gt=0).order_by('-count').values_list('language__name', 'count'),
            ),
            'language_ac_rate': get_bar_chart(
                queryset.values('language__name').annotate(ac_rate=ac_rate)
                        .filter(ac_rate__gt=0).values_list('language__name', 'ac_rate'),
            ),
        }

        context['stats'] = mark_safe(json.dumps(stats))

        return context


ContestRankingProfile = namedtuple(
    'ContestRankingProfile',
    # 'id user css_class username points cumtime tiebreaker organization participation '
    'id user css_class username points cumtime tiebreaker participation '
    'participation_rating problem_cells result_cell display_name',
)

BestSolutionData = namedtuple('BestSolutionData', 'code points time state is_pretested')


def make_contest_ranking_profile(contest, participation, contest_problems):
    def display_user_problem(contest_problem):
        # When the contest format is changed, `format_data` might be invalid.
        # This will cause `display_user_problem` to error, so we display '???' instead.
        try:
            return contest.format.display_user_problem(participation, contest_problem)
        except (KeyError, TypeError, ValueError):
            return mark_safe('<td>???</td>')

    user = participation.user
    return ContestRankingProfile(
        id=user.id,
        user=user.user,
        css_class=user.css_class,
        username=user.username,
        points=participation.score,
        cumtime=participation.cumtime,
        tiebreaker=participation.tiebreaker,
        # organization=user.organization,
        participation_rating=participation.rating.rating if hasattr(participation, 'rating') else None,
        problem_cells=[display_user_problem(contest_problem) for contest_problem in contest_problems],
        result_cell=contest.format.display_participation_result(participation),
        participation=participation,
        display_name=user.display_name,
    )


def base_contest_ranking_list(contest, problems, queryset):
    # return [make_contest_ranking_profile(contest, participation, problems) for participation in
    #         queryset.select_related('user__user', 'rating').defer('user__about', 'user__organizations__about')]
    return [make_contest_ranking_profile(contest, participation, problems) for participation in
            queryset.select_related('user__user', 'rating').defer('user__about')]


def contest_ranking_list(contest, problems):
    return base_contest_ranking_list(contest, problems, contest.users.filter(virtual=0)
                                    #  .prefetch_related('user__organizations')
                                    .order_by('is_disqualified', '-score', 'cumtime', 'tiebreaker'))


def get_contest_ranking_list(request, contest, participation=None, ranking_list=contest_ranking_list,
                             show_current_virtual=True, ranker=ranker):
    problems = list(contest.contest_problems.select_related('problem').defer('problem__description').order_by('order'))

    users = ranker(ranking_list(contest, problems), key=attrgetter('points', 'cumtime', 'tiebreaker'))

    if show_current_virtual:
        if participation is None and request.user.is_authenticated:
            participation = request.profile.current_contest
            if participation is None or participation.contest_id != contest.id:
                participation = None
        if participation is not None and participation.virtual:
            users = chain([('-', make_contest_ranking_profile(contest, participation, problems))], users)
    return users, problems


def contest_ranking_ajax(request, contest, participation=None):
    contest, exists = _find_contest(request, contest)
    if not exists:
        return HttpResponseBadRequest('Invalid contest', content_type='text/plain')

    if not contest.can_see_full_scoreboard(request.user):
        raise Http404()

    users, problems = get_contest_ranking_list(request, contest, participation)
    return render(request, 'contest/ranking-table.html', {
        'users': users,
        'problems': problems,
        'contest': contest,
        'has_rating': contest.ratings.exists(),
    })


class ContestRankingBase(ContestMixin, TitleMixin, DetailView):
    template_name = 'contest/ranking.html'
    tab = None

    def get_title(self):
        raise NotImplementedError()

    def get_content_title(self):
        return self.object.name

    def get_ranking_list(self):
        raise NotImplementedError()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.object.can_see_own_scoreboard(self.request.user):
            raise Http404()

        users, problems = self.get_ranking_list()
        context['users'] = users
        context['problems'] = problems
        context['last_msg'] = event.last()
        context['tab'] = self.tab
        return context


class ContestRanking(ContestRankingBase):
    tab = 'ranking'

    def get_title(self):
        return _('%s Rankings') % self.object.name

    def get_ranking_list(self):
        if not self.object.can_see_full_scoreboard(self.request.user):
            queryset = self.object.users.filter(user=self.request.profile, virtual=ContestParticipation.LIVE)
            return get_contest_ranking_list(
                self.request, self.object,
                ranking_list=partial(base_contest_ranking_list, queryset=queryset),
                ranker=lambda users, key: ((_('???'), user) for user in users),
            )

        return get_contest_ranking_list(self.request, self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['has_rating'] = self.object.ratings.exists()
        context['is_participation'] = ContestParticipation.objects.filter(virtual=0, user=self.request.profile, contest_id=self.object.id).exists()
        return context


class ContestParticipationList(LoginRequiredMixin, ContestRankingBase):
    tab = 'participation'

    def get_title(self):
        if self.profile == self.request.profile:
            return _('Your participation in %(contest)s') % {'contest': self.object.name}
        return _("%(user)s's participation in %(contest)s") % {
            'user': self.profile.username, 'contest': self.object.name,
        }

    def get_ranking_list(self):
        if not self.object.can_see_full_scoreboard(self.request.user) and self.profile != self.request.profile:
            raise Http404()

        queryset = self.object.users.filter(user=self.profile, virtual__gte=0).order_by('-virtual')
        live_link = format_html('<a href="{2}#!{1}">{0}</a>', _('Live'), self.profile.username,
                                reverse('contest_ranking', args=[self.object.key]))

        return get_contest_ranking_list(
            self.request, self.object, show_current_virtual=False,
            ranking_list=partial(base_contest_ranking_list, queryset=queryset),
            ranker=lambda users, key: ((user.participation.virtual or live_link, user) for user in users))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['has_rating'] = False
        context['now'] = timezone.now()
        context['rank_header'] = _('Participation')
        return context

    def get(self, request, *args, **kwargs):
        if 'user' in kwargs:
            self.profile = get_object_or_404(Profile, user__username=kwargs['user'])
        else:
            self.profile = self.request.profile
        return super().get(request, *args, **kwargs)


class ContestParticipationDisqualify(ContestMixin, SingleObjectMixin, View):
    def get_object(self, queryset=None):
        contest = super().get_object(queryset)
        if not contest.is_editable_by(self.request.user):
            raise Http404()
        return contest

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        try:
            participation = self.object.users.get(pk=request.POST.get('participation'))
        except ObjectDoesNotExist:
            pass
        else:
            participation.set_disqualified(not participation.is_disqualified)
        return HttpResponseRedirect(reverse('contest_ranking', args=(self.object.key,)))


class ContestMossMixin(ContestMixin, PermissionRequiredMixin):
    permission_required = 'judge.moss_contest'

    def get_object(self, queryset=None):
        contest = super().get_object(queryset)
        if settings.MOSS_API_KEY is None or not contest.is_editable_by(self.request.user):
            raise Http404()
        return contest


class ContestMossView(ContestMossMixin, TitleMixin, DetailView):
    template_name = 'contest/moss.html'

    def get_title(self):
        return _('%s MOSS Results') % self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        problems = list(map(attrgetter('problem'), self.object.contest_problems.order_by('order')
                                                              .select_related('problem')))
        languages = list(map(itemgetter(0), ContestMoss.LANG_MAPPING))

        results = ContestMoss.objects.filter(contest=self.object)
        moss_results = defaultdict(list)
        for result in results:
            moss_results[result.problem].append(result)

        for result_list in moss_results.values():
            result_list.sort(key=lambda x: languages.index(x.language))

        context['languages'] = languages
        context['has_results'] = results.exists()
        context['moss_results'] = [(problem, moss_results[problem]) for problem in problems]

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        status = run_moss.delay(self.object.key)
        return redirect_to_task_status(
            status, message=_('Running MOSS for %s...') % (self.object.name,),
            redirect=reverse('contest_moss', args=(self.object.key,)),
        )


class ContestMossDelete(ContestMossMixin, SingleObjectMixin, View):
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        ContestMoss.objects.filter(contest=self.object).delete()
        return HttpResponseRedirect(reverse('contest_moss', args=(self.object.key,)))


class ContestTagDetailAjax(DetailView):
    model = ContestTag
    slug_field = slug_url_kwarg = 'name'
    context_object_name = 'tag'
    template_name = 'contest/tag-ajax.html'


class ContestTagDetail(TitleMixin, ContestTagDetailAjax):
    template_name = 'contest/tag.html'

    def get_title(self):
        return _('Contest tag: %s') % self.object.name
    
    
from judge.models.LatestSubmission import LatestSubmission
import zipfile
import io
from django.utils.encoding import iri_to_uri

class ContestDetailCodeDownload(View):
    def get(self, request, *args, **kwargs):
        try:
            contest_key = kwargs.get('contest')  # URL에서 contest key 받기
            contest, exists = _find_contest(request, contest_key, private_check=False)

            if not exists:
                raise Http404("Contest not found")

            submissions = LatestSubmission.objects.filter(contest_object=contest).select_related('user', 'problem', 'user__profile')

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for sub in submissions:
                    try:
                        profile = sub.user.profile
                        first_name = f"{profile.username}_{profile.first_name()}"
                        first_name = re.sub(r'[^a-zA-Z0-9가-힣_]', '_', first_name or 'unknown')
                    except Profile.DoesNotExist:
                        first_name = 'no_profile'

                    problem_name = re.sub(r'[^a-zA-Z0-9가-힣_]', '_', sub.problem.name)
                    file_extension=sub.language.extension
                    filename = f'{first_name}/{problem_name}.{file_extension}'

                    source = sub.source or ""
                    zip_file.writestr(filename, source)

            buffer.seek(0)
            response = HttpResponse(buffer.read(), content_type='application/zip')
            safe_name = re.sub(r'[^\w가-힣]', '_', contest.name or '').strip('_')

            if not safe_name:
                safe_name = 'contest'

            quoted_filename = iri_to_uri(f'{safe_name}_codes.zip')

            response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quoted_filename}"
            
            return response

        except Exception as e:
            return HttpResponseServerError(f"An error occurred: {str(e)}")
