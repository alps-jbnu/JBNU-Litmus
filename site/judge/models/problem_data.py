import errno
import os

from django.db import models, transaction  
from django.utils.translation import gettext_lazy as _

from judge.utils.problem_data import ProblemDataStorage

from zipfile import ZipFile, BadZipFile

__all__ = ['problem_data_storage', 'problem_directory_file', 'ProblemData', 'ProblemTestCase', 'CHECKERS']

problem_data_storage = ProblemDataStorage()


def _problem_directory_file(code, filename):
    return os.path.join(code, os.path.basename(filename))


def problem_directory_file(data, filename):
    return _problem_directory_file(data.problem.code, filename)


CHECKERS = (
    ('standard', _('Standard')),
    ('floats', _('Floats')),
    ('floatsabs', _('Floats (absolute)')),
    ('floatsrel', _('Floats (relative)')),
    ('rstripped', _('Non-trailing spaces')),
    ('sorted', _('Unordered')),
    ('identical', _('Byte identical')),
    ('linecount', _('Line-by-line')),
)


class ProblemData(models.Model):
    problem = models.OneToOneField('Problem', verbose_name=_('problem'), related_name='data_files',
                                   on_delete=models.CASCADE)
    zipfile = models.FileField(verbose_name=_('data zip file'), storage=problem_data_storage, null=True, blank=True,
                               upload_to=problem_directory_file)
    generator = models.FileField(verbose_name=_('generator file'), storage=problem_data_storage, null=True, blank=True,
                                 upload_to=problem_directory_file)
    output_prefix = models.IntegerField(verbose_name=_('output prefix length'), blank=True, null=True)
    output_limit = models.IntegerField(verbose_name=_('output limit length'), blank=True, null=True)
    feedback = models.TextField(verbose_name=_('init.yml generation feedback'), blank=True)
    checker = models.CharField(max_length=10, verbose_name=_('checker'), choices=CHECKERS, blank=True)
    unicode = models.BooleanField(verbose_name=_('enable unicode'), null=True, blank=True)
    nobigmath = models.BooleanField(verbose_name=_('disable bigInteger / bigDecimal'), null=True, blank=True)
    checker_args = models.TextField(verbose_name=_('checker arguments'), blank=True,
                                    help_text=_('Checker arguments as a JSON object.'))

    __original_zipfile = None

    def __init__(self, *args, **kwargs):
        super(ProblemData, self).__init__(*args, **kwargs)
        self.__original_zipfile = self.zipfile

    def save(self, *args, **kwargs):
        # 파일이 저장된 후에 `_process_zipfile` 호출
        is_new_file = self.zipfile != self.__original_zipfile
        super(ProblemData, self).save(*args, **kwargs)
        if is_new_file and self.zipfile:
            try:
                self._process_zipfile()
            except Exception as e:
                return ValueError("{e}")

    def _find_root_dir(self, file_list):
        """
        Find the common root directory of .in and .out files.
        """
        dirs = {os.path.dirname(f) for f in file_list}
        common_prefix = os.path.commonpath(dirs)
        return common_prefix if common_prefix else ''

    def _process_zipfile(self):
        """
        ZIP 파일 처리 후 테스트 케이스 생성
        지원하는 파일 형식:
        1. .in 및 .out 파일 쌍
        2. 확장자 없는 파일 및 .a 확장자 파일 쌍
        """
        try:
            # 문제 코드 기반으로 경로 재구성
            problem_code = self.problem.code
            zip_path = os.path.join('/home/ubuntu/problems', problem_code, os.path.basename(self.zipfile.path))
            
            with ZipFile(zip_path) as zfile:
                file_list = zfile.namelist()
                test_cases = []
                
                # 케이스 1: .in과 .out 파일 쌍 찾기
                input_files_in = sorted([f for f in file_list if f.endswith('.in')])
                output_files_out = sorted([f for f in file_list if f.endswith('.out')])
                
                if len(input_files_in) == len(output_files_out) and len(input_files_in) > 0:
                    # .in 및 .out 파일 형식이 올바르게 짝지어진 경우
                    for input_file, output_file in zip(input_files_in, output_files_out):
                        test_cases.append((input_file, output_file))
                
                # 케이스 2: 확장자 없는 파일과 .a 확장자 파일 쌍 찾기
                # 1. 먼저 .a 확장자 파일 목록 가져오기
                a_files = sorted([f for f in file_list if f.endswith('.a')])
                
                # 2. 각 .a 파일에 대해 해당되는 확장자 없는 입력 파일 찾기
                for a_file in a_files:
                    base_name = os.path.splitext(a_file)[0]  # .a 확장자 제거
                    
                    # 정확히 같은 이름의 파일이 존재하는지 확인
                    if base_name in file_list:
                        # 이미 .in/.out 쌍으로 추가된 것은 제외
                        if not any(base_name == input_file for input_file, _ in test_cases):
                            test_cases.append((base_name, a_file))
                
                if not test_cases:
                    raise ValueError("No valid test case pairs found in the ZIP file.")
                
                # 기존 테스트 케이스 삭제
                self.problem.cases.all().delete()
                
                # 새로운 테스트 케이스 생성
                with transaction.atomic():
                    for idx, (input_file, output_file) in enumerate(test_cases, start=1):
                        ProblemTestCase.objects.create(
                            dataset=self.problem,
                            order=idx,
                            type='C',
                            input_file=input_file,
                            output_file=output_file,
                            points=1,  # 기본 점수
                        )
        except BadZipFile:
            raise ValueError("Invalid ZIP file.")
        except Exception as e:
            raise ValueError(f"Error processing ZIP file: {e}")


    def has_yml(self):
        return problem_data_storage.exists(f"{self.problem.code}/init.yml")

    def _update_code(self, original, new):
        try:
            problem_data_storage.rename(original, new)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
        if self.zipfile:
            self.zipfile.name = problem_directory_file(new, self.zipfile.name)
        if self.generator:
            self.generator.name = problem_directory_file(new, self.generator.name)
        self.save()
    _update_code.alters_data = True

class ProblemTestCase(models.Model):
    dataset = models.ForeignKey('Problem', verbose_name=_('problem data set'), related_name='cases',
                                on_delete=models.CASCADE)
    order = models.IntegerField(verbose_name=_('case position'))
    type = models.CharField(max_length=1, verbose_name=_('case type'),
                            choices=(('C', _('Normal case')),
                                     ('S', _('Batch start')),
                                     ('E', _('Batch end'))),
                            default='C')
    input_file = models.CharField(max_length=100, verbose_name=_('input file name'), blank=True)
    output_file = models.CharField(max_length=100, verbose_name=_('output file name'), blank=True)
    generator_args = models.TextField(verbose_name=_('generator arguments'), blank=True)
    points = models.IntegerField(verbose_name=_('point value'), blank=True, null=True, default=1)
    is_pretest = models.BooleanField(verbose_name=_('case is pretest?'),default=False)
    output_prefix = models.IntegerField(verbose_name=_('output prefix length'), blank=True, null=True)
    output_limit = models.IntegerField(verbose_name=_('output limit length'), blank=True, null=True)
    checker = models.CharField(max_length=10, verbose_name=_('checker'), choices=CHECKERS, blank=True)
    checker_args = models.TextField(verbose_name=_('checker arguments'), blank=True,
                                    help_text=_('Checker arguments as a JSON object.'))

    def __str__(self):
        return ''
    
    class Meta:
        ordering = ['order']