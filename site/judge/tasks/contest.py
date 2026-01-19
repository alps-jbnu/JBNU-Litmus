from celery import shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext as _

from judge.models import Contest, ContestJplag, ContestParticipation, Submission
from judge.utils.celery import Progress
from judge.utils.jplag import run_jplag_for_submissions

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
    ContestJplag.objects.filter(contest=contest).delete()

    length = len(ContestJplag.LANG_MAPPING) * contest.problems.count()
    jplag_results = []

    with Progress(self, length, stage=_('Running JPlag')) as p:
        for problem in contest.problems.all():
            for dmoj_lang, jplag_lang in ContestJplag.LANG_MAPPING:
                result = ContestJplag(contest=contest, problem=problem, language=dmoj_lang)

                subs = list(Submission.objects.filter(
                    contest__participation__virtual__in=(ContestParticipation.LIVE, ContestParticipation.SPECTATE),
                    contest_object=contest,
                    problem=problem,
                    language__common_name=dmoj_lang,
                ).order_by('-points').values_list('user__user__username', 'source__source'))

                if subs:
                    result.url, result.submission_count = run_jplag_for_submissions(
                        contest.key,
                        problem.code,
                        dmoj_lang,
                        subs,
                    )

                jplag_results.append(result)
                p.did(1)

    ContestJplag.objects.bulk_create(jplag_results)

    return len(jplag_results)
