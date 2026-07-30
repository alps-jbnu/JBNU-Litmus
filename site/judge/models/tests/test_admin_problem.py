from django.contrib import admin
from django.test import RequestFactory, TestCase

from judge.admin.problem import ProblemAdmin, ProblemCombinedInputFilter
from judge.models import Problem
from judge.models.tests.util import CommonDataMixin, create_problem


class ProblemAdminFilterTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.factory = RequestFactory()
        cls.problem_admin = ProblemAdmin(Problem, admin.site)
        cls.algorithm_problem = create_problem(code='alg001', group='algorithm')
        cls.contest_problem = create_problem(code='jbn001', group='JBNUPC')

    def build_filter(self, params=None):
        request = self.factory.get('/admin/judge/problem/', params or {})
        return ProblemCombinedInputFilter(
            Problem._meta.get_field('name'),
            request,
            request.GET.copy(),
            Problem,
            self.problem_admin,
            'name',
        ), request

    def test_problem_group_filter_returns_only_selected_group(self):
        filter_instance, request = self.build_filter({'problem_group': str(self.algorithm_problem.group_id)})

        queryset = filter_instance.queryset(request, Problem.objects.all())

        self.assertQuerySetEqual(
            queryset.order_by('code'),
            [self.algorithm_problem],
            transform=lambda problem: problem,
        )

    def test_problem_group_filter_ignores_unknown_group_value(self):
        filter_instance, request = self.build_filter({'problem_group': '999999'})

        queryset = filter_instance.queryset(request, Problem.objects.filter(
            id__in=[self.algorithm_problem.id, self.contest_problem.id]
        ))

        self.assertCountEqual(
            queryset.values_list('code', flat=True),
            [self.algorithm_problem.code, self.contest_problem.code],
        )

    def test_problem_group_choices_are_grouped_by_parent_path(self):
        create_problem(code='cpp001', group='교재별/C++ 프로그래밍/클래스 Part 1')
        create_problem(code='cpp002', group='교재별/C++ 프로그래밍/템플릿')

        filter_instance, _ = self.build_filter()
        ungrouped, grouped = filter_instance.grouped_group_lookups

        self.assertIn((str(self.algorithm_problem.group_id), 'algorithm'), ungrouped)
        self.assertIn(
            (
                '교재별 / C++ 프로그래밍',
                (
                    (str(Problem.objects.get(code='cpp001').group_id), '클래스 Part 1'),
                    (str(Problem.objects.get(code='cpp002').group_id), '템플릿'),
                ),
            ),
            grouped,
        )
