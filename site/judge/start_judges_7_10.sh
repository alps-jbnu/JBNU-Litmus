#!/bin/bash

# 기존 tmux 세션 종료
tmux kill-session -t dmoj_judge_7_10 2>/dev/null || true

# 새로운 tmux 세션 생성
tmux new-session -d -s dmoj_judge_7_10

# 채점기(7-10)를 위한 창 분할 및 실행
for i in {7..10}; do
  judge_name="litmus-judge-$i"

  # 첫 번째 창 이후로는 새 창 생성
  if [ $i -gt 7 ]; then
    tmux new-window -t dmoj_judge_7_10
  fi

  # 창 이름 설정
  tmux rename-window -t dmoj_judge_7_10 "$judge_name"

  echo "Starting judge ($judge_name)..."
  tmux send-keys -t dmoj_judge_7_10 "cd /home/ubuntu/site/judge && /home/ubuntu/.local/bin/dmoj -c configs/$judge_name.yml localhost $judge_name" C-m
done

echo "채점기 7-10이 모두 시작되었습니다."
echo "채점기 7-10 세션: tmux attach -t dmoj_judge_7_10"
echo "상태 확인: https://litmus.jedutools.io/status/"
