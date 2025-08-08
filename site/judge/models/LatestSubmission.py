from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# 유저 프로필, 문제, 콘테스트 모델을 import
from judge.models.problem import Problem, SubmissionSourceAccess
from judge.models.profile import Profile
from judge.models.runtime import Language
from django.contrib.auth.models import User


class LatestSubmission(models.Model):
    user = models.ForeignKey(User, verbose_name=_('user'), on_delete=models.CASCADE)
    problem = models.ForeignKey(Problem, verbose_name=_('problem'), on_delete=models.CASCADE)
    contest_object = models.ForeignKey('Contest', verbose_name=_('contest'), null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='+')
    score = models.FloatField(default=0.0) 
    source = models.TextField(verbose_name=_('source code'), max_length=65536)
    updated_at = models.DateTimeField(auto_now=True)
    language = models.ForeignKey(Language, verbose_name=_('submission language'), on_delete=models.CASCADE,default=10)

    class Meta:
        unique_together = ('user', 'problem', 'contest_object')
        verbose_name = 'Latest Submission'
        verbose_name_plural = 'Latest Submissions'

    def __str__(self):
        return f'LatestSubmission(user={self.user}, problem={self.problem}, contest={self.contest_object})'
    

