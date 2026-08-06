#!/bin/bash

# 기존 tmux 세션 종료
tmux kill-session -t dmoj_judge 2>/dev/null || true
tmux kill-session -t dmoj_judge_multi 2>/dev/null || true
tmux kill-session -t dmoj_judge_1_6 2>/dev/null || true

# 새로운 tmux 세션 생성
tmux new-session -d -s dmoj_judge_1_6

# 채점기 1~6 실행
for i in {1..6}; do
  if [ $i -eq 1 ]; then
    judge_name="litmus-judge"
  else
    judge_name="litmus-judge-$i"
  fi

  if [ $i -gt 1 ]; then
    tmux new-window -t dmoj_judge_1_6
  fi

  tmux rename-window -t dmoj_judge_1_6 "$judge_name"

  echo "Starting judge ($judge_name)..."
  tmux send-keys -t dmoj_judge_1_6 "cd /home/ubuntu/site/judge && /home/ubuntu/.local/bin/dmoj -c configs/$judge_name.yml localhost $judge_name" C-m
done

echo "채점기 1-6이 모두 시작되었습니다."
echo "채점기 1-6 세션: tmux attach -t dmoj_judge_1_6"
echo "상태 확인: https://litmus.jbnu.ac.kr/status/"