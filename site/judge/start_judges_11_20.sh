#!/bin/bash

# 기존 tmux 세션 종료
tmux kill-session -t dmoj_judge_11_20 2>/dev/null || true

# 새로운 tmux 세션 생성
tmux new-session -d -s dmoj_judge_11_20

# 각 추가 채점기(11-20)를 위한 창 분할 및 실행
for i in {11..20}; do
  judge_name="litmus-judge-$i"
  
  # 첫 번째 창 이후로는 새 창 생성
  if [ $i -gt 11 ]; then
    tmux new-window -t dmoj_judge_11_20
  fi
  
  # 창 이름 설정
  tmux rename-window -t dmoj_judge_11_20 "$judge_name"
  
  # 채점기 실행 명령어 - 수정된 경로 사용
  echo "Starting new judge ($judge_name)..."
  tmux send-keys -t dmoj_judge_11_20 "cd /home/ubuntu/site/judge && /home/ubuntu/.local/bin/dmoj -c configs/$judge_name.yml localhost $judge_name" C-m
done

echo "채점기 11-20이 모두 시작되었습니다."
echo "채점기 11-20 세션: tmux attach -t dmoj_judge_11_20"
echo "상태 확인: https://litmus.jbnu.ac.kr/status/"