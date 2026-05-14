from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import connection
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy, ngettext

from judge.contest_format.default import DefaultContestFormat
from judge.contest_format.registry import register_contest_format
from judge.timezone import from_database_time
from judge.utils.timedelta import nice_repr


@register_contest_format('icpc')
class ICPCContestFormat(DefaultContestFormat):
    name = gettext_lazy('대회용')
    config_defaults = {'penalty': 10}
    config_validators = {'penalty': lambda x: x >= 0}
    """
        penalty: Number of penalty minutes each incorrect submission adds. Defaults to 20.
    """

    @classmethod
    def validate(cls, config):
        if config is None:
            return

        if not isinstance(config, dict):
            raise ValidationError('ICPC-styled contest expects no config or dict as config')

        for key, value in config.items():
            if key not in cls.config_defaults:
                raise ValidationError('unknown config key "%s"' % key)
            if not isinstance(value, type(cls.config_defaults[key])):
                raise ValidationError('invalid type for config key "%s"' % key)
            if not cls.config_validators[key](value):
                raise ValidationError('invalid value "%s" for config key "%s"' % (value, key))

    def __init__(self, contest, config):
        self.config = self.config_defaults.copy()
        self.config.update(config or {})
        self.contest = contest

    def update_participation(self, participation):
        cumtime = 0
        last = 0
        penalty = 0
        score = 0
        format_data = {}

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT MAX(cs.points) as `points`, (
                    SELECT MIN(csub.date)
                        FROM judge_contestsubmission ccs LEFT OUTER JOIN
                             judge_submission csub ON (csub.id = ccs.submission_id)
                        WHERE ccs.problem_id = cp.id AND ccs.participation_id = %s AND ccs.points = MAX(cs.points)
                ) AS `time`, cp.id AS `prob`, cp.points AS `max_possible`
                FROM judge_contestproblem cp INNER JOIN
                     judge_contestsubmission cs ON (cs.problem_id = cp.id AND cs.participation_id = %s) LEFT OUTER JOIN
                     judge_submission sub ON (sub.id = cs.submission_id)
                GROUP BY cp.id
            """, (participation.id, participation.id))

            for points, time, prob, max_possible in cursor.fetchall():
                time = from_database_time(time)
                dt = (time - participation.start).total_seconds()

                # Only full score counts as solved; partial scores are treated as 0
                if points < max_possible:
                    points = 0

                # Count total attempts (excluding IE/CE)
                subs = participation.submissions.exclude(submission__result__isnull=True) \
                                                .exclude(submission__result__in=['IE', 'CE']) \
                                                .filter(problem_id=prob)
                total_attempts = subs.count()

                # Compute penalty
                if self.config['penalty']:
                    if points:
                        prev = subs.filter(submission__date__lte=time).count() - 1
                        penalty += prev * self.config['penalty'] * 60
                    else:
                        prev = subs.count()
                else:
                    prev = 0

                if points:
                    cumtime += dt
                    last = max(last, dt)

                format_data[str(prob)] = {'time': dt, 'points': points, 'penalty': prev, 'attempts': total_attempts}
                score += points

        participation.cumtime = cumtime + penalty
        participation.score = round(score, self.contest.points_precision)
        participation.tiebreaker = cumtime  # sum of solve times (exclude penalty); asc -> earlier wins on tie
        participation.format_data = format_data
        participation.save()

    def display_user_problem(self, participation, contest_problem):
        format_data = (participation.format_data or {}).get(str(contest_problem.id))
        if format_data:
            url = reverse('contest_user_submissions',
                          args=[self.contest.key, participation.user.user.username, contest_problem.problem.code])

            if format_data['points']:
                # Solved: display time = first-solve time + accumulated penalty
                total_seconds = format_data['time'] + format_data['penalty'] * self.config['penalty'] * 60
                return format_html(
                    '<td class="{state}"><a href="{url}">{points}'
                    '<div class="solving-time">{time}</div></a></td>',
                    state=(('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                           self.best_solution_state(format_data['points'], contest_problem.points)),
                    url=url,
                    points=floatformat(format_data['points']),
                    time=nice_repr(timedelta(seconds=total_seconds), 'noday'),
                )
            else:
                return format_html('<td class="failed-score"><a href="{url}">-</a></td>', url=url)
        else:
            return mark_safe('<td></td>')

    def get_label_for_problem(self, index):
        return str(index + 1)

    def get_short_form_display(self):
        yield _('The maximum score submission for each problem will be used.')

        penalty = self.config['penalty']
        if penalty:
            yield ngettext(
                'Each submission before the first maximum score submission will incur a **penalty of %d minute**.',
                'Each submission before the first maximum score submission will incur a **penalty of %d minutes**.',
                penalty,
            ) % penalty

        yield _('Ties will be broken by the sum of the last score altering submission time on problems with a non-zero '
                'score, followed by the time of the last score altering submission.')
