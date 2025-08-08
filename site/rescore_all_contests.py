#!/usr/bin/env python
# 모든 활성 대회와 최근 종료된 대회의 점수를 재계산하는 스크립트

import os
import time
from datetime import timedelta

# Django 설정 모듈 지정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dmoj.settings")

# Django 설정을 로드하기 전에 로깅 설정을 제거
import sys
from importlib import import_module

# Django 설정 모듈 가져오기
settings_module = import_module(os.environ["DJANGO_SETTINGS_MODULE"])

# LOGGING 설정 제거
if hasattr(settings_module, 'LOGGING'):
    delattr(settings_module, 'LOGGING')

# Django 설정 로드
import django
django.setup()

from django.utils import timezone
from judge.models import Contest, ContestParticipation

def rescore_contest(contest):
    """
    특정 대회의 모든 참가자 점수를 재계산합니다.
    """
    print(f"\n===== 대회 '{contest.name}' (키: {contest.key}) 점수 재계산 시작 =====")
    start_time = time.time()
    
    participations = ContestParticipation.objects.filter(contest=contest)
    total = participations.count()
    print(f"총 {total}명의 참가자 점수를 재계산합니다.")
    
    # 점수가 변경된 참가자 수 추적
    changed_count = 0
    
    for i, participation in enumerate(participations, 1):
        old_score = participation.score
        
        # 결과 재계산
        participation.recompute_results()
        
        # 점수가 변경되었는지 확인
        if old_score != participation.score:
            print(f"참가자 {participation.user.username}: {old_score} -> {participation.score}")
            changed_count += 1
        
        if i % 10 == 0 or i == total:
            print(f"진행 상황: {i}/{total} ({i/total*100:.1f}%)")
    
    elapsed_time = time.time() - start_time
    print(f"대회 '{contest.name}' 점수 재계산 완료. 소요 시간: {elapsed_time:.2f}초")
    print(f"변경된 참가자 수: {changed_count}/{total}")
    return changed_count

def main():
    print("=== 대회 점수 재계산 시작 ===")
    start_time = time.time()
    
    # 활성 대회와 최근 종료된 대회(2주 이내) 가져오기
    now = timezone.now()
    recent_time = now - timedelta(days=90)
    
    contests = Contest.objects.filter(
        end_time__gte=recent_time
    ).order_by('-end_time')
    
    print(f"총 {contests.count()}개의 대회를 재계산합니다.")
    
    total_changed = 0
    for contest in contests:
        changed = rescore_contest(contest)
        total_changed += changed
    
    elapsed_time = time.time() - start_time
    print(f"\n=== 모든 대회 점수 재계산 완료. 총 소요 시간: {elapsed_time:.2f}초 ===")
    print(f"총 변경된 참가자 수: {total_changed}")

if __name__ == "__main__":
    main()
