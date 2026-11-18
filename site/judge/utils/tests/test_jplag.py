import os
import shutil
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

from judge.models import Contest, ContestJplag
from judge.models.tests.util import create_contest_problem, create_problem, create_user
from judge.utils.jplag import build_jplag_viewer_url, get_jplag_report_path, run_jplag_for_submissions


def viewer_file_param(viewer_url):
    # 뷰어처럼 URLSearchParams 규칙('+'는 공백, %2B는 '+')으로 file= 값을 꺼낸다.
    return parse_qs(urlparse(viewer_url).query)['file'][0]


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

    @mock.patch('judge.utils.jplag.subprocess.run')
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
