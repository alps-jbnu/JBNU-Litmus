from django.core.management.base import BaseCommand
from django.db.models import Count

from judge.models import Profile

MIDDLE_HIGH_SCHOOL_TYPES = ('highschool', 'middleschool')


class Command(BaseCommand):
    help = ('중/고등학생(school.school_type가 highschool 또는 middleschool인) 프로필 중 '
            '학번(student_number)이 등록되어 있는 프로필만 전부 NULL로 초기화합니다. '
            '대학생 등 그 외 프로필은 건드리지 않습니다.')

    def handle(self, *args, **options):
        queryset = Profile.objects.filter(
            school__school_type__in=MIDDLE_HIGH_SCHOOL_TYPES,
            student_number__isnull=False,
        )

        per_school = list(
            queryset.values('school__name').annotate(count=Count('id')).order_by('-count'),
        )

        total = queryset.update(student_number=None)

        self.stdout.write(self.style.SUCCESS('%d명의 학번이 초기화되었습니다.' % total))
        for row in per_school:
            self.stdout.write('- %s: %d명' % (row['school__name'], row['count']))
