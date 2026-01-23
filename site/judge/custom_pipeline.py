# judge/social_auth/custom_pipeline.py
import re
import json
from operator import itemgetter
from django import forms
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User
from social_core.pipeline.partial import partial
from judge.models import Profile, Language, Department
from judge.models import Profile
import uuid

import logging

from social_core.exceptions import AuthException

def check_existing_user(backend, user, *args, **kwargs):
    """
    소셜 인증 파이프라인에서 사용자 존재 여부를 확인합니다.
    만약 사용자 객체(user)가 없다면, 메시지와 함께 인증을 중단합니다.

    리트머스 계정이 없고 키클락 로그인을 시도한 경우, 기존 파이프라인에서는 계정을 새로 만드는 부분이 있었음
    키클락 로그인 후 이 부분에서 계속 에러가 나서 여러 방법을 시도하다가
    그냥 최초 로그인 시 회원가입 후 로그인 가능하도록 함
    """
    if user is None:
        request = backend.strategy.request
        request.session.flush()
        return HttpResponseRedirect(reverse('registration_register'))
    return {}
