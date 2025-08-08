from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import Max
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy

from judge.contest_format.base import BaseContestFormat
from judge.contest_format.registry import register_contest_format
from judge.utils.timedelta import nice_repr


@register_contest_format('default')
class DefaultContestFormat(BaseContestFormat):
    name = gettext_lazy('Default')

    @classmethod
    def validate(cls, config):
        if config is not None and (not isinstance(config, dict) or config):
            raise ValidationError('default contest expects no config or empty dict as config')

    def __init__(self, contest, config):
        super(DefaultContestFormat, self).__init__(contest, config)

    def update_participation(self, participation):
        cumtime = 0
        points = 0
        format_data = {}

        # SQL과 연결하여 각 문제별 제출 정보를 가져옴
        from django.db import connection
        from judge.timezone import from_database_time
        import logging
        
        # debug 로그 설정 - 파일 쓰기 오류를 방지하기 위해 안전하게 처리
        logger = logging.getLogger('contest_time_debug')
        logger.setLevel(logging.DEBUG)
        
        try:
            # 로그 핸들러 추가
            import os
            handler = logging.FileHandler('/tmp/contest_debug.log')
            handler.setLevel(logging.DEBUG)
            logger.addHandler(handler)
        except Exception as e:
            # 로그 파일 생성 실패 시 무시 (권한 문제 등)
            pass
            
        try:
            with connection.cursor() as cursor:
                # 모든 문제 가져오기 (contest_problem 테이블에서)
                cursor.execute("""
                    SELECT cp.id 
                    FROM judge_contestproblem cp
                    WHERE cp.contest_id = %s
                    ORDER BY cp.id
                """, [participation.contest_id])
                
                all_problems = cursor.fetchall()
                logger.debug(f'All problems: {all_problems}')
                
                # 각 문제에 대한 점수와 시도 횟수 초기화
                for prob_id, in all_problems:
                    format_data[str(prob_id)] = {'time': 0, 'points': 0, 'attempts': 0}
                
                # 각 문제별 시도 횟수 가져오기
                cursor.execute("""
                    SELECT cs.problem_id, COUNT(cs.id) as attempts
                    FROM judge_contestsubmission cs
                    WHERE cs.participation_id = %s
                    GROUP BY cs.problem_id
                """, [participation.id])
                
                attempts = cursor.fetchall()
                for prob_id, attempt_count in attempts:
                    if str(prob_id) in format_data:
                        format_data[str(prob_id)]['attempts'] = attempt_count
                
                # 각 문제별 최대 점수 가져오기 (동일 문제에 대해 최고 점수만 사용)
                cursor.execute("""
                    SELECT cp.id, MAX(cs.points) as max_points, MIN(sub.date) as first_ac_time
                    FROM judge_contestproblem cp
                    LEFT JOIN judge_contestsubmission cs ON (cs.problem_id = cp.id AND cs.participation_id = %s AND cs.points > 0)
                    LEFT JOIN judge_submission sub ON (sub.id = cs.submission_id)
                    WHERE cp.contest_id = %s
                    GROUP BY cp.id
                """, [participation.id, participation.contest_id])
        
                max_scores = cursor.fetchall()
                logger.debug(f'Max scores by problem: {max_scores}')
        
                # 총점 초기화 - 이 부분이 중요합니다!
                points = 0
        
                # 문제별 최대 점수에 대한 정보 업데이트
                for prob_id, max_points, first_time in max_scores:
                    if str(prob_id) in format_data:
                        # 점수가 없는 경우 처리
                        if max_points is None:
                            format_data[str(prob_id)]['points'] = 0
                            format_data[str(prob_id)]['time'] = 0
                            continue
                    
                        first_time = from_database_time(first_time)
                        dt = (first_time - participation.start).total_seconds()
                
                        format_data[str(prob_id)]['points'] = max_points
                        format_data[str(prob_id)]['time'] = dt
                
                        # 총점에 추가 (최대 점수만 더함)
                        points += max_points
                        logger.debug(f'Problem ID: {prob_id}, Points: {max_points}, Time: {dt}, Total points so far: {points}')
                
                logger.debug(f'Final format_data: {format_data}')
                logger.debug(f'Final total points: {points}')
                
                # 로그 핸들러 제거
                try:
                    logger.removeHandler(handler)
                    handler.close()
                except Exception as e:
                    pass
        except Exception as e:
            # DB 연결 오류 또는 기타 예외 발생 시 로그에 기록
            logger.error(f'Error updating participation: {e}')
            
            # 로그 핸들러 제거
            try:
                logger.removeHandler(handler)
                handler.close()
            except Exception as e:
                pass
        
        # problem_first_solved가 초기화되지 않았으면 초기화
        if not hasattr(participation, 'problem_first_solved') or participation.problem_first_solved is None:
            participation.problem_first_solved = {}
        
        try:
            # 각 문제별 첫 정답 제출 시간 가져오기
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT cs.problem_id, MIN(sub.date) as first_ac_time
                    FROM judge_contestsubmission cs
                    JOIN judge_submission sub ON (sub.id = cs.submission_id)
                    WHERE cs.participation_id = %s AND cs.points > 0
                    GROUP BY cs.problem_id
                """, [participation.id])
                
                first_submissions = cursor.fetchall()
                
                # 각 문제별 첫 정답 제출 시간 기록
                for prob_id, first_time in first_submissions:
                    dt = (from_database_time(first_time) - participation.start).total_seconds()
                    participation.problem_first_solved[str(prob_id)] = dt
        except Exception as e:
            logger.error(f'Error getting first submission times: {e}')
        
        # 점수가 있는 문제들의 시간만 합산
        for prob_id_str, prob_data in format_data.items():
            if prob_data['points'] > 0 and prob_id_str in participation.problem_first_solved:
                cumtime += participation.problem_first_solved[prob_id_str]
        
                    
        logger.debug(f'Final Score: {points}, Cumtime: {cumtime}')
        logger.debug(f'Format data: {format_data}')
        logger.debug(f'problem_first_solved: {participation.problem_first_solved if hasattr(participation, "problem_first_solved") else "not exists"}')
        
        participation.cumtime = max(cumtime, 0)
        participation.score = round(points, self.contest.points_precision)
        participation.tiebreaker = 0
        participation.format_data = format_data
        participation.save()

    def display_user_problem(self, participation, contest_problem):
        import logging
        logger = logging.getLogger('contest_time_debug')
        
        # 해당 문제에 대한 제출 이력 가져오기
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as attempts, MAX(cs.points) as max_points
                FROM judge_contestsubmission cs
                WHERE cs.participation_id = %s AND cs.problem_id = %s
            """, [participation.id, contest_problem.id])
            attempts, max_points = cursor.fetchone() or (0, 0)
        
        format_data = (participation.format_data or {}).get(str(contest_problem.id))
        logger.debug(f'display_user_problem - problem_id: {contest_problem.id}, format_data: {format_data}, attempts: {attempts}, max_points: {max_points}')
        
        # 제출이 있는지 확인
        has_submissions = attempts > 0
        
        if format_data and format_data.get('points', 0) > 0:
            # 정답 제출인 경우
            logger.debug(f'Correct submission: points={format_data.get("points", 0)}, time={format_data.get("time", 0)}')
            return format_html(
                '<td class="{state}"><a href="{url}">{points}<div class="solving-time">{time}</div></a></td>',
                state=(('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                       self.best_solution_state(format_data['points'], contest_problem.points)),
                url=reverse('contest_user_submissions',
                            args=[self.contest.key, participation.user.user.username, contest_problem.problem.code]),
                points=floatformat(format_data['points']),
                time=nice_repr(timedelta(seconds=format_data.get('time', 0)), 'noday'),
            )
        elif has_submissions:
            # 오답 제출인 경우
            logger.debug(f'Wrong submission: attempts={attempts}')
            return format_html(
                '<td class="failed-score"><a href="{url}">{points}<div class="solving-time">{attempts} 시도</div></a></td>',
                url=reverse('contest_user_submissions',
                            args=[self.contest.key, participation.user.user.username, contest_problem.problem.code]),
                points='0',
                attempts=attempts,
            )
        else:
            # 제출이 없는 경우
            logger.debug('No submissions')
            return mark_safe('<td></td>')

    def display_participation_result(self, participation):
        return format_html(
            # '<td class="user-points"><a href="{url}">{points}<div class="solving-time">{cumtime}</div></a></td>',
            '<td class="user-points">{points}<div class="solving-time">{cumtime}</div></a></td>',
            # url=reverse('contest_all_user_submissions',
            #             args=[self.contest.key, participation.user.user.username]),
            points=floatformat(participation.score, -self.contest.points_precision),
            cumtime=nice_repr(timedelta(seconds=participation.cumtime), 'noday'),
        )

    def get_problem_breakdown(self, participation, contest_problems):
        return [(participation.format_data or {}).get(str(contest_problem.id)) for contest_problem in contest_problems]

    def get_label_for_problem(self, index):
        return str(index + 1)

    def get_short_form_display(self):
        yield _('The maximum score submission for each problem will be used.')
        yield _('Ties will be broken by the sum of the last submission time on problems with a non-zero score.')
