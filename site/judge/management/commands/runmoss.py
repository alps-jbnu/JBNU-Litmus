# from django.conf import settings
# from django.core.management.base import BaseCommand

# from judge.models import Contest, ContestJplag, ContestParticipation, Submission
# from judge.utils.jplag import run_jplag_for_submissions


# class Command(BaseCommand):
#     help = 'Checks for duplicate code using MOSS'

#     def add_arguments(self, parser):
#         parser.add_argument('contest', help='the id of the contest')

#     def handle(self, *args, **options):
#         moss_api_key = settings.MOSS_API_KEY
#         if moss_api_key is None:
#             print('No MOSS API Key supplied')
#             return
#         contest = options['contest']

#         for problem in Contest.objects.get(key=contest).problems.order_by('code'):
#             print('========== %s / %s ==========' % (problem.code, problem.name))
#             for dmoj_lang, _ in ContestJplag.LANG_MAPPING:
#                 print('%s: ' % dmoj_lang, end=' ')
#                 subs = list(Submission.objects.filter(
#                     contest__participation__virtual__in=(ContestParticipation.LIVE, ContestParticipation.SPECTATE),
#                     contest__participation__contest__key=contest,
#                     result='AC', problem__id=problem.id,
#                     language__common_name=dmoj_lang,
#                 ).values_list('user__user__username', 'source__source'))
#                 if not subs:
#                     print('<no submissions>')
#                     continue

#                 report_url, submission_count = run_jplag_for_submissions(
#                     contest,
#                     problem.code,
#                     dmoj_lang,
#                     subs,
#                 )
#                 print('(%d): %s' % (submission_count, report_url))
