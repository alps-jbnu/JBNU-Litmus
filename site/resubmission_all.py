#!/usr/bin/env python3

# ✅ Django 설정을 가장 먼저 초기화
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dmoj.settings")

import django
django.setup()

# 이후에야 models 등을 import!
from django.utils import timezone
from datetime import timedelta
from judge.models import Submission

def resubmit_recent_submissions(days=14):
    now = timezone.now()
    recent_time = now - timedelta(days=days)

    # submissions = Submission.objects.filter(date__gte=recent_time)
    submissions = Submission.objects.filter(date__gte=recent_time)
    total = submissions.count()

    print(f"최근 {days}일 내 제출 {total}건을 다시 재출(재채점)합니다.")

    for i, submission in enumerate(submissions, 1):
        submission.judge()

        if i % 10 == 0 or i == total:
            print(f"{i}/{total} 처리됨")

    print(f"총 {total}건 재출 완료!")

if __name__ == "__main__":
    resubmit_recent_submissions(52)

