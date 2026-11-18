import os
import shutil
import subprocess
import tempfile
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone, translation
from django.utils.translation import gettext

from judge.models import Contest, ContestJplag, ContestParticipation, ContestSubmission, Language, Submission, \
    SubmissionSource
from judge.models.tests.util import create_contest_problem, create_problem, create_user
from judge.tasks import run_jplag
from judge.utils.jplag import JplagError, build_jplag_viewer_url, get_jplag_report_path, run_jplag_for_submissions, \
    strip_markdown_fences

# 485번 대회 12396번 C에서 운영 서버가 실제로 낸 출력과 같은 형식 (JPlag 6.3.0)
NOT_ENOUGH_OUTPUT = (
    '2026-11-18-09:44:23_425 [WARN] Submission - Failed to parse submission alice:\n'
    "failed to parse 'alice/solution.c'Lexical error at line 1, column 1.  Encountered: \"`\" (96), after : \"\"\n"
    '2026-11-18-09:44:23_457 [INFO] Scanner - Summary of all errors:\n'
    "2026-11-18-09:44:23_424 [ERROR] Scanner - Scanning Error in 'solution.c': Lexical error at line 1, column 1.\n"
    '2026-11-18-09:44:23_458 [INFO] CLI - Summary of all errors:\n'
    '2026-11-18-09:44:23_433 [ERROR] CLI - Not enough valid submissions! (found 1 valid submissions)\n'
)


def viewer_file_param(viewer_url):
    # 뷰어처럼 URLSearchParams 규칙('+'는 공백, %2B는 '+')으로 file= 값을 꺼낸다.
    return parse_qs(urlparse(viewer_url).query)['file'][0]


def fake_jplag(returncode=0, stdout='', stderr='', write_report=True, received=None):
    """subprocess.run 대신 쓴다. 성공하면 -r 경로에 보고서를 만들고, received에 JPlag가 받은 코드를 담는다."""
    def run(cmd, **kwargs):
        if received is not None:
            submission_dir = cmd[-1]
            for name in os.listdir(submission_dir):
                for file_name in os.listdir(os.path.join(submission_dir, name)):
                    with open(os.path.join(submission_dir, name, file_name), 'rb') as handle:
                        received[name] = handle.read()
        if returncode == 0 and write_report:
            with open(cmd[cmd.index('-r') + 1] + '.jplag', 'wb') as handle:
                handle.write(b'PK')
        if returncode and kwargs.get('check'):
            raise subprocess.CalledProcessError(returncode, cmd, stdout, stderr)
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


class FakeJarMixin:
    def setUp(self):
        super().setUp()
        jar = tempfile.NamedTemporaryFile(suffix='.jar')
        self.addCleanup(jar.close)
        override = override_settings(JPLAG_JAR_PATH=jar.name, JPLAG_JAVA_PATH=None, JPLAG_TMP_ROOT=None,
                                     JPLAG_VIEWER_URL_PREFIX='/static/jplag-viewer/', JPLAG_EXTRA_ARGS=[])
        override.enable()
        self.addCleanup(override.disable)


class ReportRootMixin:
    def setUp(self):
        super().setUp()
        self.report_root = tempfile.mkdtemp(prefix='jplag-test-')
        self.addCleanup(shutil.rmtree, self.report_root, ignore_errors=True)
        override = override_settings(JPLAG_REPORT_ROOT=self.report_root)
        override.enable()
        self.addCleanup(override.disable)

    def write_report(self, contest, problem, language):
        data = ('PK report %s/%s/%s' % (contest, problem, language)).encode()
        directory = os.path.join(self.report_root, contest, problem, language)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, 'results.jplag'), 'wb') as handle:
            handle.write(data)
        return data


class JplagReportPathTest(ReportRootMixin, SimpleTestCase):
    def test_report_path_inside_root(self):
        root = os.path.realpath(self.report_root)
        self.assertEqual(get_jplag_report_path('468', '10674', 'C++'),
                         os.path.join(root, '468', '10674', 'C++', 'results.jplag'))

    def test_path_outside_root_is_none(self):
        for parts in (('..', '..', '..'), ('468', '..', '..'), ('/etc', 'x', 'y'), ('468', '10674', 'a\0b')):
            with self.subTest(parts=parts):
                self.assertIsNone(get_jplag_report_path(*parts))

    def test_symlink_outside_root_is_none(self):
        outside = tempfile.mkdtemp(prefix='jplag-outside-')
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        os.makedirs(os.path.join(self.report_root, '468', '10674'))
        os.symlink(outside, os.path.join(self.report_root, '468', '10674', 'Python'))
        self.assertIsNone(get_jplag_report_path('468', '10674', 'Python'))

    def test_default_report_root(self):
        with override_settings(JPLAG_REPORT_ROOT=None):
            self.assertEqual(get_jplag_report_path('468', '10674', 'Python'),
                             os.path.join(os.path.realpath(settings.BASE_DIR), 'jplag_reports',
                                          '468', '10674', 'Python', 'results.jplag'))

    def test_report_root_in_public_directory_is_refused(self):
        public = tempfile.mkdtemp(prefix='jplag-public-')
        self.addCleanup(shutil.rmtree, public, ignore_errors=True)
        report_root = os.path.join(public, 'static', 'jplag_reports')
        for public_setting in ({'STATICFILES_DIRS': [public]}, {'STATIC_ROOT': public}):
            with self.subTest(public_setting=public_setting), \
                    override_settings(JPLAG_REPORT_ROOT=report_root, **public_setting):
                with self.assertRaises(ImproperlyConfigured):
                    get_jplag_report_path('468', '10674', 'Python')


class JplagViewerUrlTest(ReportRootMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.request = RequestFactory().get('/')

    def assertViewerOpens(self, viewer_url, contest, problem, language):
        self.assertTrue(viewer_url.startswith('http://testserver/static/jplag-viewer/?file='), viewer_url)
        file_url = viewer_file_param(viewer_url)
        self.assertEqual(file_url,
                         'http://testserver/jplag-report/%s/%s/%s/results.jplag' % (contest, problem, language))
        match = resolve(urlparse(file_url).path)
        self.assertEqual(match.url_name, 'contest_jplag_report')
        self.assertEqual(match.kwargs, {'contest': contest, 'problem': problem, 'language': language})

    def test_legacy_static_url_is_rewritten(self):
        for language in ('Python', 'C++'):
            with self.subTest(language=language):
                stored = '/static/jplag-viewer/?file=/static/jplag_reports/468/10674/%s/results.jplag' % language
                viewer_url = build_jplag_viewer_url(self.request, stored)
                self.assertNotIn('jplag_reports', viewer_url)
                self.assertViewerOpens(viewer_url, '468', '10674', language)

    @mock.patch('judge.utils.jplag.subprocess.run', side_effect=fake_jplag())
    def test_new_report_url(self, run):
        jar = tempfile.NamedTemporaryFile(suffix='.jar')
        self.addCleanup(jar.close)
        with override_settings(JPLAG_JAR_PATH=jar.name, JPLAG_JAVA_PATH=None, JPLAG_TMP_ROOT=None,
                               JPLAG_VIEWER_URL_PREFIX='/static/jplag-viewer/'):
            stored, count = run_jplag_for_submissions('468', '10674', 'C++', [('alice', 'a'), ('bob', 'b')])

        self.assertEqual(count, 2)
        self.assertEqual(stored, '/static/jplag-viewer/?file=/jplag-report/468/10674/C%2B%2B/results.jplag')
        command = run.call_args[0][0]
        self.assertEqual(command[command.index('-r') + 1],
                         os.path.join(self.report_root, '468', '10674', 'C++', 'results'))
        self.assertViewerOpens(build_jplag_viewer_url(self.request, stored), '468', '10674', 'C++')


class ContestJplagReportTest(ReportRootMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.editor = create_user(username='jplag_editor', user_permissions=('jplag_contest', 'edit_own_contest'))
        cls.other_editor = create_user(username='jplag_other', user_permissions=('jplag_contest', 'edit_own_contest'))
        cls.editor_without_jplag = create_user(username='jplag_noperm', user_permissions=('edit_own_contest',))
        cls.normal = create_user(username='jplag_normal')
        cls.superuser = create_user(username='jplag_superuser', is_superuser=True, is_staff=True)

        # Contest.save()가 key를 str(id)로 바꿔 한 번 더 저장하므로 objects.create()(force_insert)를 쓰지 않는다.
        # 공개 대회로 만들어, 다른 대회 편집자를 막는 것이 access_check가 아니라 편집 권한 확인임을 보인다.
        now = timezone.now()
        cls.contest = Contest(name='jplagtest', description='', is_visible=True,
                              start_time=now - timedelta(days=1), end_time=now + timedelta(days=1))
        cls.contest.save()
        cls.contest.authors.set([cls.editor.profile, cls.editor_without_jplag.profile])
        cls.key = cls.contest.key
        problem = create_problem(code='jplagprob')
        create_contest_problem(contest=cls.contest, problem=problem)

        viewer = '/static/jplag-viewer/?file='
        for language, url, count in (
            ('Python', viewer + '/jplag-report/%s/jplagprob/Python/results.jplag' % cls.key, 3),
            ('C++', viewer + '/static/jplag_reports/%s/jplagprob/C++/results.jplag' % cls.key, 3),  # 예전 형식
            ('C', None, 1),
            ('Java', None, 0),
        ):
            ContestJplag.objects.create(contest=cls.contest, problem=problem, language=language,
                                        url=url, submission_count=count)

    def setUp(self):
        super().setUp()
        self.reports = {language: self.write_report(self.key, 'jplagprob', language)
                        for language in ('Python', 'C++', 'C')}

    def report_url(self, language, contest=None):
        return reverse('contest_jplag_report', args=(contest or self.key, 'jplagprob', language))

    def assertReport(self, path, language):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), self.reports[language])
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        response.close()

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.report_url('Python'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith(settings.LOGIN_URL))

    def test_user_without_jplag_permission_is_forbidden(self):
        for user in (self.normal, self.editor_without_jplag):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.report_url('Python')).status_code, 403)

    def test_jplag_user_who_cannot_edit_contest(self):
        self.client.force_login(self.other_editor)
        self.assertEqual(self.client.get(self.report_url('Python')).status_code, 403)

        response = self.client.get(reverse('contest_jplag', args=(self.key,)))
        self.assertEqual(response.status_code, 200)
        with translation.override(settings.LANGUAGE_CODE):
            self.assertContains(response, gettext('No such contest'))
        self.assertNotContains(response, 'jplag-report')

        self.client.post(reverse('contest_jplag_delete', args=(self.key,)))
        self.assertEqual(ContestJplag.objects.filter(contest=self.contest).count(), 4)

    def test_editor_gets_report(self):
        for user in (self.editor, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertReport(self.report_url('Python'), 'Python')

    def test_cpp_report(self):
        self.client.force_login(self.editor)
        for path in (self.report_url('C++'), '/jplag-report/%s/jplagprob/C%%2B%%2B/results.jplag' % self.key):
            with self.subTest(path=path):
                self.assertReport(path, 'C++')

    def test_missing_report_is_404(self):
        self.client.force_login(self.editor)
        for path in (
            self.report_url('C'),  # 파일은 있지만 결과 행에 url이 없다 (제출자 1명)
            self.report_url('Java'),
            self.report_url('Kotlin'),
            self.report_url('Python', contest='nosuchcontest'),
            self.report_url('..'),
            '/jplag-report/../../etc/results.jplag',
            '/jplag-report/%s/jplagprob/..%%2F..%%2FC/results.jplag' % self.key,
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_jplag_page_links_to_report_view(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse('contest_jplag', args=(self.key,)))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '/static/jplag_reports/')
        for language in ('Python', 'C%2B%2B'):
            self.assertContains(response, 'file=http://testserver/jplag-report/%s/jplagprob/%s/results.jplag' %
                                (self.key, language))


class StripMarkdownFencesTest(SimpleTestCase):
    def test_fence_lines_become_empty(self):
        source = '```c\n#include <stdio.h>\nint main() {}\n```\n'
        stripped = strip_markdown_fences(source)
        self.assertEqual(stripped, '\n#include <stdio.h>\nint main() {}\n\n')
        self.assertEqual(stripped.count('\n'), source.count('\n'))  # 보고서의 줄 번호가 원본과 같다

    def test_only_lines_starting_with_fence(self):
        for source, expected in (
            ('  ```python\nprint(1)\n\t```', '\nprint(1)\n'),
            ('```c\r\nint x;\r\n```\r\n', '\nint x;\r\n\n'),
            ('printf("```");\n', 'printf("```");\n'),
            ('int x; // ```\n', 'int x; // ```\n'),
            ('~~~c\nint x;\n~~~\n', '~~~c\nint x;\n~~~\n'),
            ('', ''),
        ):
            with self.subTest(source=source):
                self.assertEqual(strip_markdown_fences(source), expected)


class JplagRunTest(FakeJarMixin, ReportRootMixin, SimpleTestCase):
    submissions = [('alice', '```c\nint main(void) { return 0; }\n```\n'), ('bob', 'int main(void) { return 0; }\n')]

    def setUp(self):
        super().setUp()
        # 예전 실행에서 남은 보고서. 실패하면 이것도 남지 않아야 한다.
        self.write_report('485', '12396', 'C')
        self.report_dir = os.path.join(self.report_root, '485', '12396', 'C')

    def run_jplag(self, run, submissions=None):
        with mock.patch('judge.utils.jplag.subprocess.run', side_effect=run) as mocked:
            result = run_jplag_for_submissions('485', '12396', 'C', submissions or self.submissions)
        return result, mocked

    def assertJplagError(self, run, message, submissions=None):
        with self.assertLogs('judge.jplag', 'WARNING') as logs, self.assertRaises(JplagError) as raised:
            self.run_jplag(run, submissions)
        self.assertEqual(str(raised.exception), message)
        self.assertFalse(os.path.exists(self.report_dir))
        self.assertIn('485/12396/C', logs.output[0])
        return raised.exception, logs.output[0]

    def test_not_enough_valid_submissions(self):
        error, log = self.assertJplagError(
            fake_jplag(1, NOT_ENOUGH_OUTPUT, 'stderr text'),
            'JPlag가 비교할 수 있는 제출이 1개뿐이라 표절 검사를 하지 못했습니다(2개 이상 필요). 코드로 읽지 못한 제출: alice',
        )
        self.assertEqual(error.submission_count, 2)
        # 로그에는 JPlag 출력의 끝부분이 남는다.
        self.assertIn('Not enough valid submissions! (found 1 valid submissions)', log)
        self.assertIn('stderr text', log)

    def test_no_valid_submissions(self):
        output = NOT_ENOUGH_OUTPUT.replace('found 1', 'found 0') + (
            '2026-11-18-09:44:23_421 [ERROR] Submission - Submission bob contains 6 tokens, '
            'which is below the minimum match length 12!\n')
        self.assertJplagError(
            fake_jplag(1, output),
            'JPlag가 비교할 수 있는 제출이 없어 표절 검사를 하지 못했습니다. '
            '코드로 읽지 못한 제출: alice / 너무 짧은 제출(토큰 12개 미만): bob',
        )

    def test_other_failure(self):
        output = '2026-11-18-09:44:17_108 [ERROR] CLI - The output file (/x/results.jplag) cannot be written to.\n'
        self.assertJplagError(
            fake_jplag(1, output),
            'JPlag가 실패했습니다(종료 코드 1). The output file (/x/results.jplag) cannot be written to.',
        )

    def test_timeout(self):
        def run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs['timeout'], output=b'partial output', stderr=b'')

        with override_settings(JPLAG_TIMEOUT=5):
            error, log = self.assertJplagError(run, 'JPlag가 5초 안에 끝나지 않아 중단했습니다.')
        self.assertEqual(error.submission_count, 2)
        self.assertIn('partial output', log)

    def test_timeout_setting(self):
        for value, expected in ((5, 5), (None, None), (0, None)):
            with self.subTest(value=value), override_settings(JPLAG_TIMEOUT=value):
                _, run = self.run_jplag(fake_jplag())
                self.assertEqual(run.call_args.kwargs['timeout'], expected)
        with override_settings():
            del settings.JPLAG_TIMEOUT  # 설정이 없으면 기본값
            _, run = self.run_jplag(fake_jplag())
            self.assertEqual(run.call_args.kwargs['timeout'], 600)

    def test_missing_report_file(self):
        self.assertJplagError(fake_jplag(0, write_report=False), 'JPlag가 끝났지만 보고서 파일을 만들지 않았습니다.')

    def test_skipped_submissions_are_logged(self):
        output = (
            '2026-11-18-09:44:56_337 [WARN] Submission - Failed to parse submission carol:\n'
            '2026-11-18-09:44:56_718 [WARN] JPlag - 1 submissions were skipped (see errors above): [carol]\n'
        )
        with self.assertLogs('judge.jplag', 'WARNING') as logs:
            (url, count), _ = self.run_jplag(fake_jplag(0, output),
                                             self.submissions + [('carol', '`not code`')])
        self.assertEqual(count, 3)
        self.assertTrue(url)
        self.assertIn('skipped 1 of 3 submissions for 485/12396/C', logs.output[0])
        self.assertIn('코드로 읽지 못한 제출: carol', logs.output[0])

    def test_markdown_fences_are_stripped_before_jplag(self):
        received = {}
        submissions = [('alice', '```c\nint main(void) { return 0; }\n```\n'),
                       ('bob', b'  ```cpp\nint main(void) { return 1; }\n```')]
        (url, count), _ = self.run_jplag(fake_jplag(received=received), submissions)
        self.assertEqual(count, 2)
        self.assertEqual(received, {'alice': b'\nint main(void) { return 0; }\n\n',
                                    'bob': b'\nint main(void) { return 1; }\n'})

    def test_single_student_does_not_run_jplag(self):
        (url, count), run = self.run_jplag(fake_jplag(), [('alice', 'a'), ('alice', 'b')])
        self.assertEqual((url, count), (None, 1))
        run.assert_not_called()
        self.assertFalse(os.path.exists(self.report_dir))


def create_language(key, common_name, extension):
    return Language.objects.get_or_create(key=key, defaults={
        'name': key, 'common_name': common_name, 'ace': 'text', 'pygments': 'text', 'extension': extension,
    })[0]


class RunJplagTaskTest(FakeJarMixin, ReportRootMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        now = timezone.now()
        cls.contest = Contest(name='jplagtask', description='', start_time=now - timedelta(days=1),
                              end_time=now + timedelta(days=1))
        cls.contest.save()
        cls.key = cls.contest.key
        c, cpp = create_language('TC', 'C', 'c'), create_language('TCPP', 'C++', 'cpp')

        problems = {}
        for order, code in enumerate(('taskprob1', 'taskprob2'), 1):
            problems[code] = create_contest_problem(contest=cls.contest, problem=create_problem(code=code),
                                                    order=order)
        participations = {}
        for username in ('alice', 'bob', 'carol'):
            participations[username] = ContestParticipation.objects.create(
                contest=cls.contest, user=create_user(username='task_' + username).profile)

        def submit(username, code, language, points):
            participation = participations[username]
            # 채점이 끝난 제출(status='D')은 LatestSubmission 시그널이 language 기본값 10(없는 언어)으로 행을 만든다.
            # run_jplag는 status를 보지 않으므로 기본값(QU)으로 둔다.
            submission = Submission.objects.create(user=participation.user, problem=problems[code].problem,
                                                   language=language, points=points, result='AC')
            SubmissionSource.objects.create(submission=submission, source='%s %s' % (username, code))
            ContestSubmission.objects.create(submission=submission, problem=problems[code],
                                             participation=participation, points=points)

        submit('alice', 'taskprob1', c, 0)  # 이 칸은 JPlag가 실패한다
        submit('bob', 'taskprob1', c, 100)
        submit('alice', 'taskprob1', cpp, 100)
        submit('carol', 'taskprob1', cpp, 50)
        submit('alice', 'taskprob2', c, 100)
        submit('bob', 'taskprob2', c, 100)
        submit('carol', 'taskprob2', c, 100)

        # 지난번 실행 결과
        ContestJplag.objects.create(contest=cls.contest, problem=problems['taskprob1'].problem, language='Java',
                                    url='/old', submission_count=5)

    def results(self):
        return {(row.problem.code, row.language): (row.url, row.submission_count)
                for row in ContestJplag.objects.filter(contest=self.contest).select_related('problem')}

    def test_failed_combination_does_not_stop_the_others(self):
        def run(cmd, **kwargs):
            if '/taskprob1/C/' in cmd[cmd.index('-r') + 1]:
                return fake_jplag(1, NOT_ENOUGH_OUTPUT)(cmd, **kwargs)
            return fake_jplag()(cmd, **kwargs)

        with mock.patch('judge.utils.jplag.subprocess.run', side_effect=run) as mocked, \
                mock.patch('judge.tasks.contest.Progress'), self.assertLogs('judge.jplag', 'WARNING'):
            self.assertEqual(run_jplag(self.key), 8)

        self.assertEqual(mocked.call_count, 3)
        report = '/static/jplag-viewer/?file=/jplag-report/%s/%%s/results.jplag' % self.key
        self.assertEqual(self.results(), {
            ('taskprob1', 'C'): (None, 2),  # 실패한 칸: 학생 수는 남기고 url은 없다
            ('taskprob1', 'C++'): (report % 'taskprob1/C%2B%2B', 2),
            ('taskprob1', 'Java'): (None, 0),
            ('taskprob1', 'Python'): (None, 0),
            ('taskprob2', 'C'): (report % 'taskprob2/C', 3),
            ('taskprob2', 'C++'): (None, 0),
            ('taskprob2', 'Java'): (None, 0),
            ('taskprob2', 'Python'): (None, 0),
        })
        self.assertFalse(os.path.exists(os.path.join(self.report_root, self.key, 'taskprob1', 'C')))
        self.assertTrue(os.path.isfile(os.path.join(self.report_root, self.key, 'taskprob2', 'C', 'results.jplag')))

    def test_unexpected_error_keeps_previous_results(self):
        with mock.patch('judge.tasks.contest.run_jplag_for_submissions',
                        side_effect=ImproperlyConfigured('JPlag jar not found')), \
                mock.patch('judge.tasks.contest.Progress'), self.assertRaises(ImproperlyConfigured):
            run_jplag(self.key)
        self.assertEqual(self.results(), {('taskprob1', 'Java'): ('/old', 5)})


@override_settings(ROOT_URLCONF='judge.utils.tests.practice_jplag_urls')
class JplagFailedCellTest(TestCase):
    FAILED_TOOLTIP = 'data-tooltip="코드로 읽을 수 없거나 너무 짧은 제출이 섞여 있는 등의 이유로 표절 검사를 하지 못했습니다."'
    SINGLE_TOOLTIP = 'data-tooltip="제출자가 2명 이상일 때만 표절 검사가 가능합니다."'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.editor = create_user(username='cell_editor', user_permissions=('jplag_contest', 'edit_own_contest'))
        cls.other_editor = create_user(username='cell_other', user_permissions=('jplag_contest', 'edit_own_contest'))
        cls.normal = create_user(username='cell_normal')

        now = timezone.now()
        cls.contest = Contest(name='jplagcell', description='', is_visible=True,
                              start_time=now - timedelta(days=1), end_time=now + timedelta(days=1))
        cls.contest.save()
        cls.contest.authors.set([cls.editor.profile])
        cls.key = cls.contest.key
        problem = create_problem(code='cellprob')
        create_contest_problem(contest=cls.contest, problem=problem)

        report = '/static/jplag-viewer/?file=/jplag-report/%s/cellprob/C%%2B%%2B/results.jplag' % cls.key
        for language, url, count in (
            ('C', None, 2),  # JPlag 실패
            ('C++', report, 3),
            ('Java', None, 1),
            ('Python', None, 0),
        ):
            ContestJplag.objects.create(contest=cls.contest, problem=problem, language=language,
                                        url=url, submission_count=count)

    def assertOnlyFailedCellMarked(self, response):
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(content.count(self.FAILED_TOOLTIP), 1)
        self.assertEqual(content.count('(검사 실패)'), 1)
        self.assertEqual(content.count(self.SINGLE_TOOLTIP), 1)
        self.assertEqual(content.count('/jplag-report/%s/cellprob/' % self.key), 1)
        self.assertNotIn('href="None"', content)

    def test_contest_page_marks_failed_cell(self):
        self.client.force_login(self.editor)
        self.assertOnlyFailedCellMarked(self.client.get(reverse('contest_jplag', args=(self.key,))))

    def test_practice_page_marks_failed_cell(self):
        self.client.force_login(self.editor)
        self.assertOnlyFailedCellMarked(self.client.get(reverse('practice_jplag', args=(self.key,))))

    def test_practice_page_requires_jplag_permission(self):
        self.client.force_login(self.normal)
        self.assertEqual(self.client.get(reverse('practice_jplag', args=(self.key,))).status_code, 403)

    @mock.patch('judge.views.practices.run_jplag')
    def test_practice_page_requires_contest_edit_permission(self, task):
        self.client.force_login(self.other_editor)
        response = self.client.get(reverse('practice_jplag', args=(self.key,)))
        self.assertEqual(response.status_code, 200)
        with translation.override(settings.LANGUAGE_CODE):
            self.assertContains(response, gettext('No such practice'))
        self.assertNotContains(response, 'jplag-report')

        self.client.post(reverse('practice_jplag', args=(self.key,)))
        task.delay.assert_not_called()
        self.client.post(reverse('practice_jplag_delete', args=(self.key,)))
        self.assertEqual(ContestJplag.objects.filter(contest=self.contest).count(), 4)
