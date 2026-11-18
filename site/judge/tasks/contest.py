from celery import shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils.translation import gettext as _

from judge.models import Contest, ContestJplag, ContestParticipation, Submission
from judge.utils.celery import Progress
from judge.utils.jplag import JplagError, run_jplag_for_submissions

__all__ = ('rescore_contest', 'run_jplag')


@shared_task(bind=True)
def rescore_contest(self, contest_key):
    contest = Contest.objects.get(key=contest_key)
    participations = contest.users

    rescored = 0
    with Progress(self, participations.count(), stage=_('Recalculating contest scores')) as p:
        for participation in participations.iterator():
            participation.recompute_results()
            rescored += 1
            if rescored % 10 == 0:
                p.done = rescored
    return rescored


@shared_task(bind=True)
def run_jplag(self, contest_key):
    contest = Contest.objects.get(key=contest_key)
    problems = list(contest.problems.all())

    length = len(ContestJplag.LANG_MAPPING) * len(problems)
    jplag_results = []

    with Progress(self, length, stage=_('Running JPlag')) as p:
        for problem in problems:
            for dmoj_lang, jplag_lang in ContestJplag.LANG_MAPPING:
                result = ContestJplag(contest=contest, problem=problem, language=dmoj_lang)

                subs = list(Submission.objects.filter(
                    contest__participation__virtual__in=(ContestParticipation.LIVE, ContestParticipation.SPECTATE),
                    contest_object=contest,
                    problem=problem,
                    language__common_name=dmoj_lang,
                ).order_by('-points').values_list('user__user__username', 'source__source'))

                if subs:
                    try:
                        result.url, result.submission_count = run_jplag_for_submissions(
                            contest.key,
                            problem.code,
                            dmoj_lang,
                            subs,
                        )
                    except JplagError as e:
                        # 이 칸만 실패(학생은 있는데 url 없음)로 남기고 다음 조합으로 넘어간다. 이유는 judge.jplag 로그에 있다.
                        result.url = None
                        result.submission_count = e.submission_count

                jplag_results.append(result)
                p.did(1)

    # 예전 결과는 새 결과가 다 준비된 뒤에 바꾼다. 도중에 예외가 나면 예전 결과가 그대로 남는다.
    with transaction.atomic():
        ContestJplag.objects.filter(contest=contest).delete()
        ContestJplag.objects.bulk_create(jplag_results)

    return len(jplag_results)
