# Job Auto-Collector — Claude 작업 지침

**한 줄 설명**: Gmail 채용 알림 메일을 수집·분류하고 레쥬메와 매칭 점수를 매겨 공개 블로그에 요약을 올리는 파이프라인.

설계 기준 문서: `docs/db-design.md` — 설계와 다르게 구현해야 할 상황이 생기면 반드시 먼저 사용자에게 물어볼 것.

---

## 절대 규칙 — 반드시 실행 전에 사용자에게 물어볼 것

- `git push` (태그 push 포함), `git commit`
- 파일·폴더 삭제, DB 삭제/DROP/DELETE, `docker compose down -v`
- `.env`, `credentials.json`, `token.json`, `Resume.pdf`, `*.eml` 의 **내용**을 출력하거나 읽는 행동
  - `.env`는 변수 **이름**만 확인할 것. 값은 절대 출력하지 말 것

---

## 비밀 파일 위치

비밀 파일(`.env`, `credentials.json`, `token.json`, 레쥬메, DB 백업)은 저장소 **밖** `/mnt/d/project/secrets/job-pipeline/` 에 보관한다.
저장소 안으로 복사하지 않는다.

---

## Docker 실행 환경

`docker compose`는 이 **Ubuntu(WSL) 환경에서만** 실행한다. Windows PowerShell에서 직접 실행하지 않는다.

---

## 줄바꿈 규칙

파일은 **LF 줄바꿈**으로 저장한다. 저장소는 Windows 드라이브(D:, exFAT)에 있으며, Windows 편집기로 저장하면 CRLF로 바뀔 수 있으니 커밋 전에 `git ls-files --eol` 로 확인한다.

---

## 1기 DAG 자동 실행 주의

2기 DAG로 교체(6단계)하기 전까지 **1기 DAG는 매일 오전 7시(토론토 시간, `schedule_interval="0 7 * * *"`)에 자동 실행**된다.
Docker를 켜 두면 매일 실행되고, 꺼져 있다가 켜면 놓친 가장 최근 실행이 바로 한 번 돌 수 있다.
그래서 작업이 끝나면 반드시 사용자에게 `docker compose down` 실행 여부를 알려줄 것.

---

## 금지 행동

- 금지: 웹 스크래핑, LinkedIn 페이지 자동 조회, 여러 사이트 공고를 모아 제공하는 서드파티 중개 채용 API
- 허용: 회사가 쓰는 채용 시스템의 공식 공개 API(Greenhouse, Lever, Ashby) — `docs/db-design.md` 의 본문 보강 ②단계에서만 사용
- 공개 블로그(`yujung20.github.io`)에는 아래 내용을 절대 내보내지 않는다:
  - 공고 원문 전체
  - 레쥬메 텍스트
  - 점수 상세 근거(`evidence`)

---

## 커밋 메시지 형식

Conventional Commits 형식을 따른다.

```
<타입>: <한 줄 요약>

예시:
chore: add db design doc
feat: add alert_emails table schema
fix: correct salary_currency check constraint
```

타입: `feat` (새 기능), `fix` (버그 수정), `chore` (빌드·설정), `docs` (문서), `refactor` (리팩터), `test` (테스트)

---

## 설명 방식

나(사용자)는 비전공자다. **무엇을 왜 하는지** 쉬운 한국어로 설명할 것.
전문 용어를 쓸 때는 한 줄 이내로 쉽게 풀어줄 것.
