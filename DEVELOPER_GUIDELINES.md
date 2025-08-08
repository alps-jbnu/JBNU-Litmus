# 개발자 가이드라인

이 문서는 프로젝트에서 작업하는 개발자를 위한 중요한 가이드라인과 절차를 설명합니다.

## 커밋 메시지 작성 규칙

1. **형식**: 다음 형식으로 커밋 메시지를 작성해주세요:
   ```
   category: 간단한 설명 (50자 이내)

   필요한 경우 더 자세한 설명을 추가하세요. 72자에서 줄바꿈을 해주세요.
   ```

2. **카테고리**:
   - `feat`: 새로운 기능 추가
   - `fix`: 버그 수정
   - `docs`: 문서 변경
   - `style`: 코드 스타일 변경 (포맷팅, 들여쓰기 등)
   - `refactor`: 코드 리팩토링
   - `test`: 테스트 추가 또는 수정
   - `perf`: 성능 개선
   - `chore`: 빌드 프로세스 또는 보조 도구 변경

3. **가이드라인**:
   - 명령형 현재 시제를 사용하세요 (예: "추가" (O), "추가했음" (X))
   - 제목 끝에 마침표를 붙이지 마세요
   - 제목의 첫 글자는 대문자로 작성하세요
   - 제목과 본문 사이에 빈 줄을 넣으세요
   - 본문에는 '무엇을' 그리고 '왜' 변경했는지 설명하고, '어떻게'는 생략하세요

## 가상환경 활성화

개발 작업을 시작하기 전에 항상 가상환경을 활성화해야 합니다:

```bash
. dmojsite/bin/activate
```

## 사이트 재시작 방법

사이트의 각 서비스를 재시작하려면 다음 명령어를 사용하세요:

```bash
sudo supervisorctl restart all     # 모든 서비스 재시작
sudo supervisorctl restart bridged  # bridge 서비스만 재시작
sudo supervisorctl restart site     # 사이트 서비스만 재시작
sudo supervisorctl restart celery   # celery 서비스만 재시작
```

## 서버 재시작 방법

웹 서버(nginx)를 재시작하려면 다음 명령어를 사용하세요:

```bash
sudo service nginx restart
```

## 데이터베이스 접속 방법

MySQL 데이터베이스에 접속하려면 다음 명령어를 사용하세요:

```bash
mysql -u dmoj -p -h 127.0.0.1
use dmoj;  
```

## 채점기(Judge) 관리 방법

### 채점기 구성

JBNU-Litmus 시스템은 `/home/ubuntu/site/judge/configs/` 디렉토리에 있는 YAML 설정 파일을 통해 채점기를 구성합니다:

- `litmus-judge.yml`: 기본 채점기(1번)
- `litmus-judge-2.yml` ~ `litmus-judge-20.yml`: 추가 채점기(2-20번)

각 채점기는 독립적으로 실행되며, tmux 세션을 통해 관리됩니다.

### 단일 채점기 실행 방법

#### 방법 1: 직접 실행 (포그라운드)

터미널에서 직접 채점기를 실행합니다. 이 방법은 터미널을 차지하고, 종료 시 Ctrl+C를 사용합니다:

```bash
cd /home/ubuntu/site/judge
/home/ubuntu/.local/bin/dmoj -c configs/litmus-judge.yml localhost litmus-judge
```

#### 방법 2: tmux를 사용한 백그라운드 실행

채점기를 백그라운드에서 실행하고 나중에 로그를 확인할 수 있습니다:

```bash
# 특정 채점기를 실행할 새로운 tmux 세션 생성
tmux new-session -d -s my_judge "cd /home/ubuntu/site/judge && /home/ubuntu/.local/bin/dmoj -c configs/litmus-judge-5.yml localhost litmus-judge-5"

# 세션에 접속하여 로그 확인
tmux attach -t my_judge

# 세션에서 빠져나오기 (채점기는 계속 실행): Ctrl+b 누른 후 d 누르기

# 나중에 종료할 때
tmux kill-session -t my_judge
```

### 여러 채점기 일괄 실행 방법

#### 제공된 스크립트 사용

JBNU-Litmus 시스템은 여러 채점기를 일괄적으로 실행하기 위한 두 가지 스크립트를 제공합니다:

1. 채점기 1-10번 실행:
   ```bash
   /home/ubuntu/site/judge/start_judges_1_10.sh
   ```

2. 채점기 11-20번 실행:
   ```bash
   /home/ubuntu/site/judge/start_judges_11_20.sh
   ```

#### 스크립트 작동 방식

스크립트는 다음과 같은 작업을 수행합니다:

1. 기존 tmux 세션을 종료합니다.
2. 새로운 tmux 세션을 생성합니다.
3. 각 채점기에 대해:
   - 새 tmux 창을 생성합니다.
   - 채점기 실행 명령어를 전송합니다.
4. 채점기가 모두 시작되었음을 알립니다.

#### 세션 관리

스크립트 실행 후 tmux 세션에 접속하여 채점기 상태를 확인할 수 있습니다:

```bash
# 채점기 1-10 확인
tmux attach -t dmoj_judge_1_10

# 채점기 11-20 확인
tmux attach -t dmoj_judge_11_20

# 세션에서 빠져나오기: Ctrl+b 누른 후 d 누르기
```

#### 채점기 관리 명령어

```bash
# tmux 세션 목록 확인
tmux ls

# 특정 세션 종료
tmux kill-session -t 세션이름

# 모든 채점기 세션 종료
tmux kill-session -t dmoj_judge_1_10
tmux kill-session -t dmoj_judge_11_20
```

#### 상태 확인

채점기 상태는 다음 URL에서 확인 가능합니다:
```
https://litmus.jbnu.ac.kr/status/
```
