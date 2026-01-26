import itertools
import json
import os
from datetime import datetime
from operator import attrgetter, itemgetter

from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Permission, User
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetView, redirect_to_login
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db.models import Count, Max, Min
from django.db.models.functions import ExtractYear, TruncDate
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render, resolve_url, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView, TemplateView, View
from reversion import revisions

from judge.forms import CustomAuthenticationForm, DownloadDataForm, ProfileForm, newsletter_id, IdFindForm, CustomPasswordResetForm, EmailChangeForm, ResendActivationEmailForm
from judge.models import Profile, Submission, ContestParticipation
from judge.performance_points import get_pp_breakdown
from judge.ratings import rating_class, rating_progress
from judge.tasks import prepare_user_data
from judge.utils.celery import task_status_by_id, task_status_url_by_id
from judge.utils.problems import contest_completed_ids, user_completed_ids
from judge.utils.pwned import PwnedPasswordsValidator
from judge.utils.ranker import ranker
from judge.utils.subscription import Subscription
from judge.utils.unicode import utf8text
from judge.utils.views import DiggPaginatorMixin, QueryStringSortMixin, TitleMixin, add_file_response, generic_message
from judge.views.register import validate_password_method
from .contests import ContestRanking
from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.utils.translation import gettext_lazy as _

# 이메일 변경 관련 import
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from registration.models import RegistrationProfile
from django.db import IntegrityError


from judge.keycloak import keycloak_logout
import requests

__all__ = ['UserPage', 'UserAboutPage', 'UserProblemsPage', 'UserDownloadData', 'UserPrepareData',
           'users', 'edit_profile']


def remap_keys(iterable, mapping):
    return [dict((mapping.get(k, k), v) for k, v in item.items()) for item in iterable]



class UserMixin(object):
    model = Profile
    slug_field = 'user__username'
    slug_url_kwarg = 'user'
    context_object_name = 'user'

    def render_to_response(self, context, **response_kwargs):
        return super(UserMixin, self).render_to_response(context, **response_kwargs)


class UserPage(TitleMixin, UserMixin, DetailView):
    template_name = 'user/user-base.html'

    def get_object(self, queryset=None):
        if self.kwargs.get(self.slug_url_kwarg, None) is None:
            return self.request.profile
        return super(UserPage, self).get_object(queryset)

    def dispatch(self, request, *args, **kwargs):
        if self.kwargs.get(self.slug_url_kwarg, None) is None:
            if not self.request.user.is_authenticated:
                return redirect_to_login(self.request.get_full_path())
        try:
            return super(UserPage, self).dispatch(request, *args, **kwargs)
        except Http404:
            return generic_message(request, _('No such user'), _('No user handle "%s".') %
                                   self.kwargs.get(self.slug_url_kwarg, None))

    def get_title(self):
        return (_('My account') if self.request.user == self.object.user else
                _('User %s') % self.object.display_name)

    # TODO: the same code exists in problem.py, maybe move to problems.py?
    @cached_property
    def profile(self):
        if not self.request.user.is_authenticated:
            return None
        return self.request.profile

    @cached_property
    def in_contest(self):
        return self.profile is not None and self.profile.current_contest is not None

    def get_completed_problems(self):
        if self.in_contest:
            return contest_completed_ids(self.profile.current_contest)
        else:
            return user_completed_ids(self.profile) if self.profile is not None else ()

    def get_context_data(self, **kwargs):
        context = super(UserPage, self).get_context_data(**kwargs)

        context['hide_solved'] = int(self.hide_solved)
        # context['authored'] = self.object.authored_problems.filter(is_public=True, is_organization_private=False) \
        #                           .order_by('code')
        authored = self.object.authored_problems.filter(is_public=True)
        if not self.request.user.has_perm('judge.manage_contest_problem'):
            authored = authored.filter(is_contest_problem=False)
        context['authored'] = authored.order_by('code')
        rating = self.object.ratings.order_by('-contest__end_time')[:1]
        context['rating'] = rating[0] if rating else None

        context['rank'] = Profile.objects.filter(
            is_unlisted=False, performance_points__gt=self.object.performance_points,
        ).exclude(id=self.object.id).count() + 1

        if rating:
            context['rating_rank'] = Profile.objects.filter(
                is_unlisted=False, rating__gt=self.object.rating,
            ).count() + 1
        context.update(self.object.ratings.aggregate(min_rating=Min('rating'), max_rating=Max('rating'),
                                                     contests=Count('contest')))
        return context

    def get(self, request, *args, **kwargs):
        self.hide_solved = request.GET.get('hide_solved') == '1' if 'hide_solved' in request.GET else False
        return super(UserPage, self).get(request, *args, **kwargs)


# class CustomLoginView(LoginView):
#     template_name = 'registration/login.html'
#     extra_context = {'title': gettext_lazy('Login')}
#     authentication_form = CustomAuthenticationForm
#     redirect_authenticated_user = True

#     def form_valid(self, form):
#         password = form.cleaned_data['password']
#         validator = PwnedPasswordsValidator()
#         try:
#             validator.validate(password)
#         except ValidationError:
#             self.request.session['password_pwned'] = True
#         else:
#             self.request.session['password_pwned'] = False
#         return super().form_valid(form)

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    extra_context = {'title': gettext_lazy('Login')}
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        password = form.cleaned_data['password']
        validator = PwnedPasswordsValidator()
        try:
            validator.validate(password)
        except ValidationError:
            self.request.session['password_pwned'] = True
        else:
            self.request.session['password_pwned'] = False
        return super().form_valid(form)

# 관리자 로그인 추가 
class AdminLoginView(LoginView):
    template_name = 'registration/login-admin.html'
    extra_context = {'title': gettext_lazy('Login')}
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True
    def form_valid(self, form):
        password = form.cleaned_data['password']
        validator = PwnedPasswordsValidator()
        try:
            validator.validate(password)
        except ValidationError:
            self.request.session['password_pwned'] = True
        else:
            self.request.session['password_pwned'] = False
        return super().form_valid(form)

class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'

    def form_valid(self, form):
        self.request.session['password_pwned'] = False
        return super().form_valid(form)
    def get_context_data(self, **kwargs):
        kwargs['validate_password_url'] = reverse('validate_password')
        return super(CustomPasswordChangeView, self).get_context_data(**kwargs)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class UserAboutPage(UserPage):
    template_name = 'user/user-about.html'

    def get_context_data(self, **kwargs):
        context = super(UserAboutPage, self).get_context_data(**kwargs)
        context['active_tab'] = 'info'
        ratings = context['ratings'] = self.object.ratings.order_by('-contest__end_time').select_related('contest') \
            .defer('contest__description')
        context['rating_data'] = mark_safe(json.dumps([{
            'label': rating.contest.name,
            'rating': rating.rating,
            'ranking': rating.rank,
            'link': '%s#!%s' % (reverse('contest_ranking', args=(rating.contest.key,)), self.object.user.username),
            'timestamp': (rating.contest.end_time - EPOCH).total_seconds() * 1000,
            'date': date_format(timezone.localtime(rating.contest.end_time), _('M j, Y, G:i')),
            'class': rating_class(rating.rating),
            'height': '%.3fem' % rating_progress(rating.rating),
        } for rating in ratings]))

        submissions = (
            self.object.submission_set
            .annotate(date_only=TruncDate('date'))
            .values('date_only').annotate(cnt=Count('id'))
        )

        context['submission_data'] = mark_safe(json.dumps({
            date_counts['date_only'].isoformat(): date_counts['cnt'] for date_counts in submissions
        }))
        context['submission_metadata'] = mark_safe(json.dumps({
            'min_year': (
                self.object.submission_set
                .annotate(year_only=ExtractYear('date'))
                .aggregate(min_year=Min('year_only'))['min_year']
            ),
        }))
        return context


class UserProblemsPage(UserPage):
    template_name = 'user/user-problems.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            from judge.utils.views import generic_message
            return generic_message(request, '접근 권한 없음',
                                 '해결한 문제 정보는 관리자만 확인할 수 있습니다.', status=403)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(UserProblemsPage, self).get_context_data(**kwargs)
        context['active_tab'] = 'problems'

        # result = Submission.objects.filter(user=self.object, points__gt=0, problem__is_public=True,
        #                                    problem__is_organization_private=False) \
        result = Submission.objects.filter(user=self.object, points__gt=0, problem__is_public=True) \
            .exclude(problem__in=self.get_completed_problems() if self.hide_solved else []) \
            .values('problem__id', 'problem__code', 'problem__name', 'problem__points', 'problem__group__full_name') \
            .distinct().annotate(points=Max('points')).order_by('problem__group__full_name', 'problem__code')

        def process_group(group, problems_iter):
            problems = list(problems_iter)
            points = sum(map(itemgetter('points'), problems))
            return {'name': group, 'problems': problems, 'points': points}

        context['best_submissions'] = [
            process_group(group, problems) for group, problems in itertools.groupby(
                remap_keys(result, {
                    'problem__code': 'code', 'problem__name': 'name', 'problem__points': 'total',
                    'problem__group__full_name': 'group',
                }), itemgetter('group'))
        ]
        breakdown, has_more = get_pp_breakdown(self.object, start=0, end=10)
        context['pp_breakdown'] = breakdown
        context['pp_has_more'] = has_more

        return context


class UserPerformancePointsAjax(UserProblemsPage):
    template_name = 'user/pp-table-body.html'

    def get_context_data(self, **kwargs):
        context = super(UserPerformancePointsAjax, self).get_context_data(**kwargs)
        try:
            start = int(self.request.GET.get('start', 0))
            end = int(self.request.GET.get('end', settings.DMOJ_PP_ENTRIES))
            if start < 0 or end < 0 or start > end:
                raise ValueError
        except ValueError:
            start, end = 0, 100
        breakdown, self.has_more = get_pp_breakdown(self.object, start=start, end=end)
        context['pp_breakdown'] = breakdown
        return context

    def get(self, request, *args, **kwargs):
        httpresp = super(UserPerformancePointsAjax, self).get(request, *args, **kwargs)
        httpresp.render()

        return JsonResponse({
            'results': utf8text(httpresp.content),
            'has_more': self.has_more,
        })


class UserDataMixin:
    @cached_property
    def data_path(self):
        return os.path.join(settings.DMOJ_USER_DATA_CACHE, '%s.zip' % self.request.profile.id)

    def dispatch(self, request, *args, **kwargs):
        if not settings.DMOJ_USER_DATA_DOWNLOAD or self.request.profile.mute:
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


class UserPrepareData(LoginRequiredMixin, UserDataMixin, TitleMixin, FormView):
    template_name = 'user/prepare-data.html'
    form_class = DownloadDataForm

    @cached_property
    def _now(self):
        return timezone.now()

    @cached_property
    def can_prepare_data(self):
        return (
            self.request.profile.data_last_downloaded is None or
            self.request.profile.data_last_downloaded + settings.DMOJ_USER_DATA_DOWNLOAD_RATELIMIT < self._now or
            not os.path.exists(self.data_path)
        )

    @cached_property
    def data_cache_key(self):
        return 'celery_status_id:user_data_download_%s' % self.request.profile.id

    @cached_property
    def in_progress_url(self):
        status_id = cache.get(self.data_cache_key)
        status = task_status_by_id(status_id).status if status_id else None
        return (
            self.build_task_url(status_id)
            if status in ('PENDING', 'PROGRESS', 'STARTED')
            else None
        )

    def build_task_url(self, status_id):
        return task_status_url_by_id(
            status_id, message=_('Preparing your data...'), redirect=reverse('user_prepare_data'),
        )

    def get_title(self):
        return _('Download your data')

    def form_valid(self, form):
        self.request.profile.data_last_downloaded = self._now
        self.request.profile.save()
        status = prepare_user_data.delay(self.request.profile.id, json.dumps(form.cleaned_data))
        cache.set(self.data_cache_key, status.id)
        return HttpResponseRedirect(self.build_task_url(status.id))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_prepare_data'] = self.can_prepare_data
        context['can_download_data'] = os.path.exists(self.data_path)
        context['in_progress_url'] = self.in_progress_url
        context['ratelimit'] = settings.DMOJ_USER_DATA_DOWNLOAD_RATELIMIT

        if not self.can_prepare_data:
            context['time_until_can_prepare'] = (
                settings.DMOJ_USER_DATA_DOWNLOAD_RATELIMIT - (self._now - self.request.profile.data_last_downloaded)
            )
        return context

    def post(self, request, *args, **kwargs):
        if not self.can_prepare_data or self.in_progress_url is not None:
            raise PermissionDenied()
        return super().post(request, *args, **kwargs)


class UserDownloadData(LoginRequiredMixin, UserDataMixin, View):
    def get(self, request, *args, **kwargs):
        if not os.path.exists(self.data_path):
            raise Http404()

        response = HttpResponse()

        if hasattr(settings, 'DMOJ_USER_DATA_INTERNAL'):
            url_path = '%s/%s.zip' % (settings.DMOJ_USER_DATA_INTERNAL, self.request.profile.id)
        else:
            url_path = None
        add_file_response(request, response, url_path, self.data_path)

        response['Content-Type'] = 'application/zip'
        response['Content-Disposition'] = 'attachment; filename=%s-data.zip' % self.request.user.username
        return response


@login_required
def edit_profile(request):
    if request.profile.mute:
        raise Http404()
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.profile, user=request.user)
        if form.is_valid():
            with revisions.create_revision(atomic=True):
                form.save()
                revisions.set_user(request.user)
                revisions.set_comment(_('Updated on site'))

            if newsletter_id is not None:
                try:
                    subscription = Subscription.objects.get(user=request.user, newsletter_id=newsletter_id)
                except Subscription.DoesNotExist:
                    if form.cleaned_data['newsletter']:
                        Subscription(user=request.user, newsletter_id=newsletter_id, subscribed=True).save()
                else:
                    if subscription.subscribed != form.cleaned_data['newsletter']:
                        subscription.update(('unsubscribe', 'subscribe')[form.cleaned_data['newsletter']])

            perm = Permission.objects.get(codename='test_site', content_type=ContentType.objects.get_for_model(Profile))
            if form.cleaned_data['test_site']:
                request.user.user_permissions.add(perm)
            else:
                request.user.user_permissions.remove(perm)

            return HttpResponseRedirect(request.path)
    else:
        form = ProfileForm(instance=request.profile, user=request.user)
        if newsletter_id is not None:
            try:
                subscription = Subscription.objects.get(user=request.user, newsletter_id=newsletter_id)
            except Subscription.DoesNotExist:
                form.fields['newsletter'].initial = False
            else:
                form.fields['newsletter'].initial = subscription.subscribed
        form.fields['test_site'].initial = request.user.has_perm('judge.test_site')

    tzmap = settings.TIMEZONE_MAP
    return render(request, 'user/edit-profile.html', {
        'require_staff_2fa': settings.DMOJ_REQUIRE_STAFF_2FA,
        'form': form, 'title': _('Edit profile'), 'profile': request.profile,
        'can_download_data': bool(settings.DMOJ_USER_DATA_DOWNLOAD),
        'has_math_config': bool(settings.MATHOID_URL),
        'ignore_user_script': True,
        'TIMEZONE_MAP': tzmap or 'http://momentjs.com/static/img/world.png',
        'TIMEZONE_BG': settings.TIMEZONE_BG if tzmap else '#4E7CAD',
    })


@require_POST
@login_required
def generate_api_token(request):
    profile = request.profile
    with revisions.create_revision(atomic=True):
        revisions.set_user(request.user)
        revisions.set_comment(_('Generated API token for user'))
        return JsonResponse({'data': {'token': profile.generate_api_token()}})


@require_POST
@login_required
def remove_api_token(request):
    profile = request.profile
    with revisions.create_revision(atomic=True):
        profile.api_token = None
        profile.save()
        revisions.set_user(request.user)
        revisions.set_comment(_('Removed API token for user'))
    return JsonResponse({})


@require_POST
@login_required
def generate_scratch_codes(request):
    profile = request.profile
    with revisions.create_revision(atomic=True):
        revisions.set_user(request.user)
        revisions.set_comment(_('Generated scratch codes for user'))
    return JsonResponse({'data': {'codes': profile.generate_scratch_codes()}})


class UserList(QueryStringSortMixin, DiggPaginatorMixin, TitleMixin, ListView):
    model = Profile
    title = gettext_lazy('사용자')
    title_info = '모든 사용자의 정보'
    context_object_name = 'users'
    template_name = 'user/list.html'
    paginate_by = 20 #페이징 기준 정하는 변수
    all_sorts = frozenset(('points', 'problem_count', 'rating', 'performance_points'))
    default_desc = all_sorts
    default_sort = '-performance_points'

    def get_queryset(self):
        # return (Profile.objects.filter(is_unlisted=False).order_by(self.order).select_related('user')
        #         .only('display_rank', 'user__username', 'points', 'rating', 'performance_points',
        #               'problem_count'))
        queryset = Profile.objects.filter(is_unlisted=False).select_related('user').order_by('-performance_points')

        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(user__username__icontains=search)

        return queryset.only('display_rank', 'user__username', 'points', 'rating', 'performance_points', 'problem_count')

    def get_context_data(self, **kwargs):
        context = super(UserList, self).get_context_data(**kwargs)
        context['title_info'] = self.title_info
        context['users'] = ranker(
            context['users'],
            key=attrgetter('performance_points', 'problem_count'),
            rank=self.paginate_by * (context['page_obj'].number - 1),
        )
        context['first_page_href'] = '.'
        context.update(self.get_sort_context())
        context.update(self.get_sort_paginate_context())
        return context


user_list_view = UserList.as_view()


class FixedContestRanking(ContestRanking):
    contest = None

    def get_object(self, queryset=None):
        return self.contest


def users(request):
    if request.user.is_authenticated:
        return user_list_view(request)
    #     participation = request.profile.current_contest
    #     if participation is not None:
    #         contest = participation.contest
    #         return FixedContestRanking.as_view(contest=contest)(request, contest=contest.key)
    # 로그인 되지 않은 경우, 로그인 화면 뷰
    return HttpResponseRedirect(reverse('auth_login'))

def user_ranking_redirect(request):
    try:
        username = request.GET['handle']
    except KeyError:
        raise Http404()
    user = get_object_or_404(Profile, user__username=username)
    rank = Profile.objects.filter(is_unlisted=False, performance_points__gt=user.performance_points).count()
    rank += Profile.objects.filter(
        is_unlisted=False, performance_points__exact=user.performance_points, id__lt=user.id,
    ).count()
    page = rank // UserList.paginate_by
    return HttpResponseRedirect('%s%s#!%s' % (reverse('user_list'), '?page=%d' % (page + 1) if page else '', username))


class UserLogoutView(TemplateView):
    template_name = 'registration/logout.html'
    title = gettext_lazy('You have been successfully logged out.')

    def post(self, request, *args, **kwargs):
        # Django 세션에서 refresh_token 가져오기
        refresh_token = request.session.get("keycloak_refresh_token")

        # Keycloak 로그아웃 실행
        if refresh_token:
            logout_success = keycloak_logout(refresh_token)
        
        # Django 세션 삭제
        request.session.flush()
        auth_logout(request)

        return redirect(reverse('home'))



class CustomPasswordResetView(PasswordResetView):
    template_name = 'registration/password_reset.html'
    html_email_template_name = 'registration/password_reset_email.html'
    email_template_name = 'registration/password_reset_email.txt'
    extra_email_context = {'site_admin_email': settings.SITE_ADMIN_EMAIL}
    form_class = CustomPasswordResetForm # 사용자 정의 폼 지정

    def post(self, request, *args, **kwargs):
        try:
            key = f'pwreset!{request.META["REMOTE_ADDR"]}'
            cache.add(key, 0, timeout=settings.DMOJ_PASSWORD_RESET_LIMIT_WINDOW)
            if cache.incr(key) > settings.DMOJ_PASSWORD_RESET_LIMIT_COUNT:
                return HttpResponse(_('You have sent too many password reset requests. Please try again later.'),
                                    content_type='text/plain', status=429)
            return super().post(request, *args, **kwargs)
        except ValidationError:
            return HttpResponse(_('입력하신 이메일 또는 아이디에 해당하는 사용자가 없습니다.'),
                                    content_type='text/plain', status=444)

# 아이디 찾기 클래스
class IdFindView(FormView):
    template_name = 'registration/id_find.html'
    form_class = IdFindForm
    success_url = reverse_lazy('id_find_complete')
    email_context = settings.SITE_ADMIN_EMAIL
    title = _('아이디 찾기')
    fixed_domain = '@jbnu.ac.kr'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        return context
    
    def form_valid(self, form):
        email_local = form.cleaned_data['email_local']
        email = f"{email_local}{self.fixed_domain}"
        try:
            user = Profile.objects.get(user__email=email)
        except Profile.DoesNotExist:
            form.add_error('email_local', _('해당 정보로 등록된 사용자가 없습니다.'))
            return self.form_invalid(form)
        
        send_mail(
            subject=_('Litmus 아이디 찾기'),
            message=_('아이디: %s' % user.user.username),
            from_email=self.email_context,
            recipient_list=[email],
            fail_silently=False,
        )

        return super().form_valid(form)

#id/pw 찾기 오류 클래스
class IdpwFindErrorView(TemplateView):
    template_name='registration/idpw_find_error.html'
    
    
# 아이디 찾기 완료 클래스
class IdFindCompleteView(TemplateView):
    template_name = 'registration/id_find_complete.html'
    title = _('아이디 찾기 완료')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['login_url'] = resolve_url(settings.LOGIN_URL)
        context['title'] = self.title
        return context

# 이메일 변경 클래스 (활성화가 되지 않은 계정)   
User = get_user_model()
class EmailChangeView(FormView):
    title = _('이메일 변경')
    form_class = EmailChangeForm
    template_name = 'registration/email_change.html'  
    success_url = reverse_lazy('email_change_complete')
    fixed_domain = '@jbnu.ac.kr'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        return context

    def form_valid(self, form):
        username = form.cleaned_data['username']
        email_local = form.cleaned_data['email_local']
        new_email = f"{email_local}{self.fixed_domain}"

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            form.add_error('username', _('아이디 또는 비밀번호가 잘못되었습니다.'))
            return self.form_invalid(form)

        # 이메일을 새로 설정하고 계정을 바로 활성화
        user.email = new_email
        user.is_active = True
        user.save() # 유저 데이터 저장

        # 이미 프로필이 있는지 확인
        registration_profile, created = RegistrationProfile.objects.get_or_create(user=user)
        registration_profile.activated = True
        registration_profile.save()

        return super().form_valid(form)

# 이메일 변경 완료 클래스 (활성화가 되지 않은 계정)  
class EmailChangeCompleteView(TemplateView):
    template_name = 'registration/email_change_complete.html'
    title = _('이메일 변경 완료')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        return context

# 활성화 메일 재전송 클래스
class ResendActivationEmailView(FormView):
    title = _('활성화 메일 재전송')
    form_class = ResendActivationEmailForm
    template_name = 'registration/resend_activation_email.html'  
    success_url = reverse_lazy('resend_activation_email_complete')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        return context

    def form_valid(self, form):
        try:
            username = form.cleaned_data['username']
            user = User.objects.get(username=username)

            # 이미 프로필이 있는지 확인
            profile, created = RegistrationProfile.objects.get_or_create(user=user)

            # 활성화 키를 새로 생성
            profile.create_new_activation_key(save=True)

            # 활성화 메일 재전송 대신 바로 활성화
            profile.activated = True
            profile.save()

        except User.DoesNotExist:
            form.add_error('username', _('아이디 또는 비밀번호가 잘못되었습니다.'))
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error(None, _('계정 활성화 정보 생성 중 문제가 발생했습니다. 다시 시도해주세요.'))
            return self.form_invalid(form)

        return super().form_valid(form)


# 활성화 메일 재전송 완료 클래스
class ResendActivationEmailCompleteView(TemplateView):
    template_name = 'registration/resend_activation_email_complete.html'
    title = _('이메일 재전송 완료')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        return context


# 사용자 과제/대회 목록 뷰
class UserContestView(TitleMixin, DetailView):
    model = Profile
    context_object_name = 'user'
    template_name = 'user/user-contests.html'
    slug_field = 'user__username'
    slug_url_kwarg = 'user'

    def get_title(self):
        return _('%(username)s님의 과제/대회') % {'username': self.object.username}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'contests'
        
        # 사용자가 참가한 대회 목록 가져오기 (실제 참가만, LIVE=0)
        participations = ContestParticipation.objects.filter(
            user=self.object,
            virtual=ContestParticipation.LIVE
        ).select_related('contest').order_by('-contest__end_time')
        
        context['participations'] = participations
        return context
