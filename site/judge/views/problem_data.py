import json
import mimetypes
import os
import re
import pickle
from itertools import chain
from zipfile import BadZipfile, ZipFile
from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.forms import BaseModelFormSet, HiddenInput, ModelForm, NumberInput, Select, formset_factory
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import DetailView

from judge.highlight_code import highlight_code
from judge.models import Problem, ProblemData, ProblemTestCase, Submission, problem_data_storage
from judge.utils.problem_data import ProblemDataCompiler
from judge.utils.unicode import utf8text
from judge.utils.views import TitleMixin, add_file_response
from judge.views.problem import ProblemMixin

mimetypes.init()
mimetypes.add_type('application/x-yaml', '.yml')


def checker_args_cleaner(self):
    data = self.cleaned_data['checker_args']
    if not data or data.isspace():
        return ''
    try:
        if not isinstance(json.loads(data), dict):
            raise ValidationError(_('Checker arguments must be a JSON object.'))
    except ValueError:
        raise ValidationError(_('Checker arguments is invalid JSON.'))
    return data


class ProblemDataForm(ModelForm):
    class Meta:
        model = ProblemData
        fields = ['zipfile', 'generator', 'unicode', 'nobigmath', 'output_limit', 'output_prefix',
                  'checker', 'checker_args']
        widgets = {
            'checker_args': HiddenInput,
        }
        

    # def clean_zipfile(self):
    #     # if hasattr(self, 'zip_valid') and not self.zip_valid:
    #     #     raise ValidationError(_('Your zip file is invalid!'))
    #     # return self.cleaned_data['zipfile']
    #     zipfile = self.cleaned_data.get('zipfile')
        
    #     if not zipfile:
    #         return zipfile
    #     try:
    #         ## 확장자 앞 prefix가 쌍으로 같으면 반환
    #         with ZipFile(zipfile) as z:
    #             file_list = z.namelist()
    #             test_cases = ProblemDataCompiler._extract_extention_zip(file_list)

    #             if not test_cases:
    #                 raise ValidationError("zip 파일에 유효한 테스트케이스 쌍이 없습니다.")
                
    #         # 지정된 확장자만 필터링 업로드
    #         # with ZipFile(zipfile) as z:
    #         #     file_list = z.namelist()
    #         #     in_files = [f for f in file_list if f.endswith(('.in', '.bin'))]
    #         #     out_files = [f for f in file_list if f.endswith('.out')]
    #         #     a_files = [f for f in file_list if f.endswith('.a')]

    #         #     test_cases = []

    #         #     # .in/.out 쌍
    #         #     if len(in_files) == len(out_files) and len(in_files) > 0:
    #         #         test_cases.extend(zip(in_files, out_files))
    #         #     else:
    #         #         # .a와 확장자 없는 쌍
    #         #         for a_file in a_files:
    #         #             base = a_file[:-2]  # remove ".a"
    #         #             if base in file_list:
    #         #                 test_cases.append((base, a_file))

    #         #     if not test_cases:
    #         #         raise forms.ValidationError("ZIP 파일에 유효한 테스트케이스 쌍(.in/.out 또는 .a)이 없습니다.")

    #     except BadZipfile:
    #         raise forms.ValidationError("잘못된 ZIP 파일입니다.")
        
    #     return zipfile
    def clean_zipfile(self):
        if hasattr(self, 'zip_valid') and not self.zip_valid:
            raise ValidationError(_('Your zip file is invalid!'))
        return self.cleaned_data['zipfile']




    clean_checker_args = checker_args_cleaner
    


class ProblemCaseForm(ModelForm):
    clean_checker_args = checker_args_cleaner

    class Meta:
        model = ProblemTestCase
        fields = ('order', 'type', 'input_file', 'output_file', 'points',
                  'is_pretest', 'output_limit', 'output_prefix', 'checker', 'checker_args', 'generator_args')
        widgets = {
            'generator_args': HiddenInput,
            'type': Select(attrs={'style': 'width: 100%'}),
            'points': NumberInput(attrs={'style': 'width: 4em'}),
            'output_prefix': NumberInput(attrs={'style': 'width: 4.5em'}),
            'output_limit': NumberInput(attrs={'style': 'width: 6em'}),
            'checker_args': HiddenInput,
        }


class ProblemCaseFormSet(formset_factory(ProblemCaseForm, formset=BaseModelFormSet, extra=1, max_num=1,
                                         can_delete=True)):
    model = ProblemTestCase

    def __init__(self, *args, **kwargs):
        self.valid_files = kwargs.pop('valid_files', None)
        super(ProblemCaseFormSet, self).__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        form = super(ProblemCaseFormSet, self)._construct_form(i, **kwargs)
        form.valid_files = self.valid_files
        return form


class ProblemManagerMixin(LoginRequiredMixin, ProblemMixin, DetailView):
    def get_object(self, queryset=None):
        problem = super(ProblemManagerMixin, self).get_object(queryset)
        if problem.is_manually_managed:
            raise Http404()
        if self.request.user.is_superuser or problem.is_editable_by(self.request.user):
            return problem
        raise Http404()


class ProblemSubmissionDiff(TitleMixin, ProblemMixin, DetailView):
    template_name = 'problem/submission-diff.html'

    def get_title(self):
        return _('Comparing submissions for {0}').format(self.object.name)

    def get_content_title(self):
        return mark_safe(escape(_('Comparing submissions for {0}')).format(
            format_html('<a href="{1}">{0}</a>', self.object.name, reverse('problem_detail', args=[self.object.code])),
        ))

    def get_object(self, queryset=None):
        problem = super(ProblemSubmissionDiff, self).get_object(queryset)
        if self.request.user.is_superuser or problem.is_editable_by(self.request.user):
            return problem
        raise Http404()

    def get_context_data(self, **kwargs):
        context = super(ProblemSubmissionDiff, self).get_context_data(**kwargs)
        try:
            ids = self.request.GET.getlist('id')
            subs = Submission.objects.filter(id__in=ids)
        except ValueError:
            raise Http404
        if not subs:
            raise Http404

        context['submissions'] = subs

        # If we have associated data we can do better than just guess
        data = ProblemTestCase.objects.filter(dataset=self.object, type='C')
        if data:
            num_cases = data.count()
        else:
            num_cases = subs.first().test_cases.count()
        context['num_cases'] = num_cases
        return context


class ProblemDataView(TitleMixin, ProblemManagerMixin):
    template_name = 'problem/data.html'
    title = '테스트케이스 관리'

    # def get_title(self):
    #     return _('Editing data for {0}').format(self.object.name)

    # def get_content_title(self):
    #     return mark_safe(escape(_('Editing data for %s')) % (
    #         format_html('<a href="{1}">{0}</a>', self.object.name,
    #                     reverse('problem_detail', args=[self.object.code]))))

    def get_data_form(self, post=False):
        return ProblemDataForm(data=self.request.POST if post else None, prefix='problem-data',
                               files=self.request.FILES if post else None,
                               instance=ProblemData.objects.get_or_create(problem=self.object)[0],
                               label_suffix='')

    def get_case_formset(self, files, post=False):
        return ProblemCaseFormSet(data=self.request.POST if post else None, prefix='cases', valid_files=files,
                                  queryset=ProblemTestCase.objects.filter(dataset_id=self.object.pk).order_by('order'))

    def get_valid_files(self, data, post=False):
        try:
            if post and 'problem-data-zipfile-clear' in self.request.POST:
                return []
            elif post and 'problem-data-zipfile' in self.request.FILES:
                return ZipFile(self.request.FILES['problem-data-zipfile']).namelist()
            elif data.zipfile:
                return ZipFile(data.zipfile.path).namelist()
        except BadZipfile:
            return []
        return []

    def get_context_data(self, **kwargs):
        context = super(ProblemDataView, self).get_context_data(**kwargs)
        context['title_info'] = self.object.name + '에 대한 테스트케이스 관리'
        context['title'] = self.title
        if 'data_form' not in context:
            aa = context['data_form'] = self.get_data_form()
            valid_files = context['valid_files'] = self.get_valid_files(context['data_form'].instance)
            context['data_form'].zip_valid = valid_files is not False
            context['cases_formset'] = self.get_case_formset(valid_files)
        context['valid_files_json'] = mark_safe(json.dumps(context['valid_files']))
        context['valid_files'] = set(context['valid_files'])
        context['all_case_forms'] = chain(context['cases_formset'], [context['cases_formset'].empty_form])
        return context

    def post(self, request, *args, **kwargs):
        self.object = problem = self.get_object()
        data_form = self.get_data_form(post=True)
        valid_files = self.get_valid_files(data_form.instance, post=True)
        data_form.zip_valid = valid_files is not False
        cases_formset = self.get_case_formset(valid_files, post=True)
        cases_formset = self.__parse_dict__(cases_formset, valid_files=valid_files)
        data_form = self.__parse_dict__(data_form, valid_files=valid_files)
        if data_form.is_valid() and cases_formset.is_valid():
            data = data_form.save()
            for case in cases_formset.save(commit=False):
                case.dataset_id = problem.id
                case.save()
            for case in cases_formset.deleted_objects:
                case.delete()
            ProblemDataCompiler.generate(problem, data, problem.cases.order_by('order'), valid_files)

            return HttpResponseRedirect(request.get_full_path())
        return self.render_to_response(self.get_context_data(data_form=data_form, cases_formset=cases_formset,
                                                             valid_files=valid_files))

    put = post


    def __parse_dict__(self, _dict, valid_files=None):
        if valid_files is None:
            return _dict

        _data = _dict.data.copy()
        test_in_files = [value for key, value in _data.items() if key.startswith('cases-') and key.endswith('-input_file') and key.find('__') < 0]
        test_out_files = [value for key, value in _data.items() if key.startswith('cases-') and key.endswith('-output_file') and key.find('__') < 0]

        if len(test_in_files) != len(test_out_files):
            return _dict

        if len(test_in_files) != 1:
            return _dict

        if test_in_files[0] != test_out_files[0]:
            return _dict

        prefix = test_in_files[0]
        in_files = self.sort_files([
            f for f in valid_files if re.match(rf'{re.escape(prefix)}.*\d{{1,4}}\.in$', f)
        ])

        out_files = self.sort_files([
            f for f in valid_files if re.match(rf'{re.escape(prefix)}.*\d{{1,4}}\.out$', f)
        ])

        in_files = [str(f) for f in in_files]
        out_files = [str(f) for f in out_files]

        results = dict()
        for i in range(len(in_files)):
            results[f'cases-{i}-id'] = _data['cases-0-id']
            results[f'cases-{i}-order'] = _data['cases-0-order']
            results[f'cases-{i}-type'] = _data['cases-0-type']
            results[f'cases-{i}-input_file'] = in_files[i]
            results[f'cases-{i}-output_file'] = out_files[i]
            results[f'cases-{i}-points'] = _data['cases-0-points']
            results[f'cases-{i}-output_prefix'] = _data['cases-0-output_prefix']
            results[f'cases-{i}-output_limit'] = _data['cases-0-output_limit']
            results[f'cases-{i}-checker'] = _data['cases-0-checker']
            results[f'cases-{i}-checker_args'] = _data['cases-0-checker_args']
            results[f'cases-{i}-generator_args'] = _data['cases-0-generator_args']

        for k, v in results.items():
            _data.__setitem__(k, v)
        _data.__setitem__('cases-TOTAL_FORMS', len(in_files))

        _dict.data = _data


        return _dict


    def check_root_dir(self, path: str):
        return \
                path.endswith('/') and \
            not path.endswith('.in') and \
            not path.endswith('.out')


    def sort_files(self, file_list):
        def extract_number(filename):
            match = re.search(r'(\d+)(?:\.[^.]+)?$', filename)
            if match:
                return int(match.group(1))
            return 0

        # 추출된 숫자를 기준으로 정렬합니다.
        return list(sorted(file_list, key=extract_number))



    
class TestCasePreView(TitleMixin,View):
    def get(self, request, *args, **kwargs):
        problem_code = self.kwargs.get('problem')
        problem = Problem.objects.filter(code=problem_code).first()

        if not problem:
            raise Http404("존재하지 않는 문제입니다.")
        if not problem.is_accessible_by(request.user):
            raise Http404()
        if request.user.has_perm('judge.view_testcase') or problem.is_editable_by(request.user):
            return self.post(request, *args, **kwargs)
        raise Http404()

    def post(self, request, *args, **kwargs):
        problem_code = self.kwargs.get('problem')  
        problem = Problem.objects.filter(code=problem_code).first()
        if not problem:
            raise Http404("존재하지 않는 문제입니다.")
        if not problem.is_accessible_by(request.user):
            raise Http404()
        if not (request.user.has_perm('judge.view_testcase') or problem.is_editable_by(request.user)):
            raise Http404()
        if problem:
            problem_id = problem.id
        else:
            problem_id = None
        problem_data = ProblemData.objects.filter(problem_id=problem_id).first()
        context = {'json':json.dumps({})}
        error_messages = []

        if problem_data is not None:
            zip_path = problem_data.zipfile
            dataset_id = problem_id
            testcases = ProblemTestCase.objects.filter(dataset__id=dataset_id)
            dic = {'testcases':[]}
            try:
                with ZipFile(zip_path) as zip:
                    for idx, testcase in enumerate(testcases):
                        dic['testcases'].append({
                                "inputFileName": '',
                                "inputFileBody": '',
                                "outputFileName": '',
                                "outputFileBody": '',
                        })
                        try:
                            with zip.open(testcase.input_file) as file: 
                                content = file.read()
                                try:
                                    decoded = content.decode('utf-8')
                                except UnicodeDecodeError:
                                    decoded = None
                                dic['testcases'][idx]['inputFileName'] = testcase.input_file
                                dic['testcases'][idx]['inputFileBody'] = decoded
                        except KeyError:
                            error_messages.append("지원하지 않는 input 파일 형식입니다.")
                        try:
                            with zip.open(testcase.output_file) as file: 
                                dic['testcases'][idx]['outputFileName'] = testcase.output_file
                                dic['testcases'][idx]['outputFileBody'] = file.read().decode('utf-8')
                        except KeyError:
                            error_messages.append("지원하지 않는 output 파일 형식입니다.")
                context = {'json': json.dumps(dic), 'errors': error_messages}
            except FileNotFoundError:
                error_messages.append("ZIP 파일이 존재하지 않습니다.")
            except BadZipfile:
                error_messages.append("ZIP 파일이 손상되었거나 열 수 없습니다.")
            except Exception as e:
                error_messages.append(f"알 수 없는 오류가 발생했습니다: {str(e)}")
            context['errors'] = error_messages
            
        return render(request,'problem/testcase_preview.html',context)
        
@login_required
def problem_data_file(request, problem, path):
    object = get_object_or_404(Problem, code=problem)
    if not object.is_editable_by(request.user):
        raise Http404()

    problem_dir = problem_data_storage.path(problem)
    if os.path.commonpath((problem_data_storage.path(os.path.join(problem, path)), problem_dir)) != problem_dir:
        raise Http404()

    response = HttpResponse()

    if hasattr(settings, 'DMOJ_PROBLEM_DATA_INTERNAL'):
        url_path = '%s/%s/%s' % (settings.DMOJ_PROBLEM_DATA_INTERNAL, problem, path)
    else:
        url_path = None

    try:
        add_file_response(request, response, url_path, os.path.join(problem, path), problem_data_storage)
    except IOError:
        raise Http404()

    response['Content-Type'] = 'application/octet-stream'
    return response


@login_required
def problem_init_view(request, problem):
    problem = get_object_or_404(Problem, code=problem)
    if not problem.is_editable_by(request.user):
        raise Http404()

    try:
        with problem_data_storage.open(os.path.join(problem.code, 'init.yml'), 'rb') as f:
            data = utf8text(f.read()).rstrip('\n')

    except IOError:
        raise Http404()

    return render(request, 'problem/yaml.html', {
        'raw_source': data, 'highlighted_source': highlight_code(data, 'yaml'),
        'title': _('Generated init.yml for %s') % problem.name,
        'content_title': mark_safe(escape(_('Generated init.yml for %s')) % (
            format_html('<a href="{1}">{0}</a>', problem.name,
                        reverse('problem_detail', args=[problem.code])))),
    })
