from django.conf import settings
from django.core.management.base import BaseCommand

from judge.models import Contest, ContestJplag, ContestParticipation, Submission
from judge.utils.jplag import run_jplag_for_submissions


class Command(BaseCommand):
    help = 'Checks for duplicate code using JPlag'

    def add_arguments(self, parser):
        parser.add_argument('contest', help='the id of the contest')

    def handle(self, *args, **options):
        contest = options['contest']

        for problem in Contest.objects.get(key=contest).problems.order_by('code'):
            self.stdout.write('========== %s / %s ==========' % (problem.code, problem.name))
            for dmoj_lang, _ in ContestJplag.LANG_MAPPING:
                self.stdout.write('%s: ' % dmoj_lang, ending=' ')
                subs = list(Submission.objects.filter(
                    contest__participation__virtual__in=(ContestParticipation.LIVE, ContestParticipation.SPECTATE),
                    contest__participation__contest__key=contest,
                    result='AC', problem__id=problem.id,
                    language__common_name=dmoj_lang,
                ).values_list('user__user__username', 'source__source'))
                if not subs:
                    self.stdout.write('<no submissions>')
                    continue

                report_url, submission_count = run_jplag_for_submissions(
                    contest,
                    problem.code,
                    dmoj_lang,
                    subs,
                )
                self.stdout.write('(%d): %s' % (submission_count, report_url))
