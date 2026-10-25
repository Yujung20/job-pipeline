# Job Auto-Collector 2기 — DB 설계 문서

> 상태: **확정 (2026-10-25)** — 변경 시 이 문서를 먼저 고친 뒤 코드를 고친다
> 대상: PostgreSQL 13 · 새 DB `jobs` (Airflow 메타데이터 DB `airflow`와 분리)

---

## 0. 한눈에 보기

### 2기 파이프라인 흐름

```
Gmail(JobNotification 라벨)
  → 알림 메일 읽기 → 공고 추출 → 중복 판단 → 직무·직급 분류
  → (가능하면) ATS 공개 API로 본문 보강 / 수동 붙여넣기
  → 레쥬메와 매칭 점수 → 공개 블로그(요약) + 비공개 페이지(상세)
```

### 표 6개와 연결 관계

```
alert_emails ──┐
               ├──> email_postings   (Jobright 점수는 여기에 저장)
postings ──────┘
   │  └─ duplicate_of ─> postings (다른 사이트의 같은 공고 → 원본)
   │
   └──> match_scores <── resume_versions

pipeline_runs ─> alert_emails, match_scores (어느 실행에서 생긴 기록인지)
```

| 표 | 한 줄 = | 역할 |
|---|---|---|
| `alert_emails` | 알림 메일 1통 | 받은 메일 기록, 같은 메일 재처리 방지 |
| `postings` | 고유한 공고 1건 | 공고 정보, 직무·직급 분류, 본문 |
| `email_postings` | 메일 ↔ 공고 연결 1건 | 어떤 메일에 어떤 공고가 있었는지, Jobright 점수 스냅샷 |
| `resume_versions` | 레쥬메 버전 1개 | 레쥬메 지문(해시)과 추출 텍스트 |
| `match_scores` | 공고 × 레쥬메 × 입력 내용 점수 1건 | 내 매칭 점수와 근거 |
| `pipeline_runs` | 파이프라인 실행 1회 | 실행 결과 모니터링 |

---

## 1. 설계 원칙

1. **한 가지 대상 = 표 하나.** 메일·공고·점수를 한 표에 섞으면 같은 공고가 메일 수만큼 복사되어 숫자가 틀어진다. (1기에서 로그 숫자와 DB 숫자가 약 33배 차이 났던 원인과 같은 종류의 문제)
2. **규칙은 가능한 한 DB가 직접 막는다.** 코드 실수가 있어도 잘못된 값이 들어가지 않도록 중복 금지(UNIQUE)·허용 값 목록(CHECK)·외래키를 건다. DB로 막을 수 없는 규칙은 §5에 "코드 규칙"으로 따로 적는다.
3. **지우지 않는다.** 표 사이의 연결은 `ON DELETE RESTRICT` — 다른 표가 가리키고 있는 줄은 삭제할 수 없다. 점수·메일 기록은 덮어쓰지 않고 새 줄로 쌓는다.
4. **시간은 모두 `TIMESTAMPTZ`(시간대 포함)로 저장한다.** 저장은 UTC, 화면 표시는 America/Toronto.
5. **공개/비공개를 칸 단위로 나눈다.** 공개 블로그를 만드는 코드는 §6의 공개 허용 칸만 명시적으로 골라 읽는다.
6. **원본 개인정보는 저장하지 않는다.** 메일 원본 HTML, 메일 속 추적 링크, 레쥬메 연락처 줄은 DB에 넣지 않는다.

---

## 2. 표 설계

표기: 🔑 기본키 · 🔗 외래키 · ⭐ 중복 금지 · "NULL 가능" = 비어 있어도 됨

### 2-1. `alert_emails` — 알림 메일 1통

| 칸 | 타입 | 설명 |
|---|---|---|
| 🔑 `email_id` | BIGSERIAL | 메일 번호 |
| ⭐ `message_id` | TEXT | 메일 헤더의 Message-ID. 같은 메일 재처리 방지 |
| ⭐ `gmail_id` | TEXT | Gmail API 내부 ID. 메일 재조회용 |
| `site` | TEXT | `linkedin` / `indeed` / `glassdoor` / `jobright` |
| `subject` | TEXT | 메일 제목 |
| `received_at` | TIMESTAMPTZ | 수신 시각. 상대 날짜("1 day ago") 환산·환율 날짜의 기준 |
| `email_type` | TEXT | `job_alert` / `jobright_instant` / `jobright_digest` / `non_job` |
| `postings_found` | INTEGER | 이 메일에서 추출한 공고 수 (0 이상) |
| `parse_status` | TEXT | `success` / `failed` / `skipped` |
| `parse_error` | TEXT, NULL 가능 | 실패 이유 |
| 🔗 `run_id` | BIGINT → `pipeline_runs` | 이 메일을 읽은 실행 |
| `collected_at` | TIMESTAMPTZ | DB에 저장된 시각 (기본값: 지금) |

- `non_job` 메일(예: Glassdoor 커뮤니티 소식)도 기록은 남기고 `parse_status = 'skipped'`로 둔다. 다음 실행에서 같은 메일을 다시 판단하지 않기 위해서다.

### 2-2. `postings` — 고유한 공고 1건

| 칸 | 타입 | 설명 |
|---|---|---|
| 🔑 `posting_id` | BIGSERIAL | 공고 번호 |
| ⭐ `site` + `site_job_id` | TEXT + TEXT | 사이트 + 사이트 고유 공고번호 (1기의 URL 기준 중복 판단을 대체) |
| `title` / `company` / `location` | TEXT | 직무명 / 회사명 / 위치 (메일에 적힌 원문) |
| `work_mode` | TEXT | `onsite` / `hybrid` / `remote` / `unknown` |
| `job_url` | TEXT | 추적 파라미터를 제거한 공고 주소 |
| `posted_at_est` | TIMESTAMPTZ, NULL 가능 | 게시 시각 **추정값** (최초 수신 메일 기준으로 상대 날짜 환산) |
| **연봉** | | |
| `salary_text` | TEXT, NULL 가능 | 연봉 원문 그대로 |
| `salary_min` / `salary_max` | NUMERIC, NULL 가능 | 원래 통화 기준 숫자 |
| `salary_currency` | TEXT, NULL 가능 | 메일에 적힌 통화 기호 기준 (`USD`, `CAD`, `EUR` …) |
| `salary_period` | TEXT, NULL 가능 | `year` / `month` / `week` / `day` / `hour` (환산하지 않음) |
| `salary_min_cad` / `salary_max_cad` | NUMERIC, NULL 가능 | USD·CAD가 아닐 때만 CAD 환산값 |
| `fx_rate` | NUMERIC, NULL 가능 | 환산에 쓴 환율 (원래 통화 1 = CAD x) |
| `fx_rate_date` | DATE, NULL 가능 | 그 환율의 날짜 |
| **분류** | | |
| `role_category` | TEXT | `DE` / `BI` / `AE` / `DA` / `DS` / `ML` / `IT_SW` / `OTHER` |
| `priority` | TEXT | `P1` / `P2` / `EXCLUDED` |
| `seniority` | TEXT | `intern` / `entry` / `senior_plus` / `unknown`(직급 미확인) |
| `seniority_source` | TEXT | `title` / `description` / `none` |
| **본문** | | |
| `description` | TEXT, NULL 가능 | 공고 본문 |
| `description_source` | TEXT | `none` / `indeed_snippet` / `ats` / `manual` |
| `description_updated_at` | TIMESTAMPTZ, NULL 가능 | 본문이 마지막으로 바뀐 시각 |
| `ats_platform` | TEXT, NULL 가능 | `greenhouse` / `lever` / `ashby` |
| **중복** | | |
| `match_key` | TEXT | 정규화한 `회사|직무명|도시` (§4) — 중복 금지 아님 |
| 🔗 `duplicate_of` | BIGINT → `postings`, NULL 가능 | 다른 사이트의 같은 공고일 때 원본 공고 번호 |
| **기록** | | |
| `first_seen_at` / `last_seen_at` | TIMESTAMPTZ | 처음 / 마지막으로 메일에서 본 시각 |

### 2-3. `email_postings` — 메일 ↔ 공고 연결

| 칸 | 타입 | 설명 |
|---|---|---|
| 🔑🔗 `email_id` | BIGINT → `alert_emails` | |
| 🔑🔗 `posting_id` | BIGINT → `postings` | |
| `position_in_email` | SMALLINT | 메일 안에서 몇 번째 공고인지 (1부터) |
| `is_sponsored` | BOOLEAN | Indeed 광고(pagead) 공고 여부 |
| `jobright_score` | SMALLINT, NULL 가능 | 이 메일에 찍힌 Jobright 점수 (0~100), 수신 시점 스냅샷 |

- 기본키는 (`email_id`, `posting_id`) 두 칸 조합. 같은 메일에 같은 공고가 두 번 나오면 처음 위치만 기록한다.

### 2-4. `resume_versions` — 레쥬메 버전

| 칸 | 타입 | 설명 |
|---|---|---|
| 🔑 `resume_version_id` | BIGSERIAL | 레쥬메 버전 번호 |
| ⭐ `file_hash` | TEXT | 레쥬메 PDF의 SHA-256 지문. 내용이 바뀌면 새 버전 |
| `resume_text` | TEXT | 연락처 줄을 제거한 추출 텍스트 (비공개) |
| `first_seen_at` | TIMESTAMPTZ | 이 버전을 처음 발견한 시각 |

- 레쥬메 파일 자체는 저장소 밖 고정 경로에 둔다. DB에는 파일이 아니라 지문과 텍스트만 저장한다.

### 2-5. `match_scores` — 매칭 점수

| 칸 | 타입 | 설명 |
|---|---|---|
| 🔑 `score_id` | BIGSERIAL | 점수 기록 번호 |
| 🔗 `posting_id` | BIGINT → `postings` | 점수를 매긴 공고 (원본 공고만) |
| 🔗 `resume_version_id` | BIGINT → `resume_versions` | 사용한 레쥬메 |
| ⭐ `input_hash` | TEXT | Claude에 보낸 **공고 입력 내용**의 SHA-256 지문 (§3-3) |
| `score_basis` | TEXT | `metadata_only`(메일 정보만) / `with_description`(본문 포함) |
| `score` | SMALLINT | 0~100 (경력직 감점 반영 후 최종 점수) |
| `evidence` | JSONB | 비공개 상세 근거 (구조는 §3-4) |
| `summary` | TEXT | 공개용 짧은 근거 |
| `model` | TEXT | 점수를 매긴 Claude 모델 이름 |
| `scored_at` | TIMESTAMPTZ | 점수 시각 |
| 🔗 `run_id` | BIGINT → `pipeline_runs`, NULL 가능 | 점수를 매긴 실행 |

- 중복 금지는 (`posting_id`, `resume_version_id`, `input_hash`) 세 칸 조합.
- 1기의 `analyzed` 칸은 없앤다. 이 표에 줄이 있으면 점수를 매긴 것이다.

### 2-6. `pipeline_runs` — 실행 기록

| 칸 | 타입 | 설명 |
|---|---|---|
| 🔑 `run_id` | BIGSERIAL | 실행 번호 |
| `airflow_run_id` | TEXT, NULL 가능 | Airflow의 실행 ID (Airflow 화면과 대조용) |
| `started_at` / `finished_at` | TIMESTAMPTZ | 시작 / 종료 시각 |
| `status` | TEXT | `running` / `success` / `partial` / `failed` — **실제 결과로 기록** |
| `emails_read` | INTEGER | 새로 읽은 메일 수 |
| `emails_skipped` | INTEGER | 공고가 아니어서 건너뛴 메일 수 |
| `emails_failed` | INTEGER | 해석에 실패한 메일 수 |
| `postings_found` | INTEGER | 메일에서 찾은 공고 수 (중복 포함) |
| `new_postings` | INTEGER | `postings`에 새로 저장된 공고 수 |
| `duplicates` | INTEGER | 같은 사이트에서 이미 저장돼 있던 공고 수 |
| `cross_site_duplicates` | INTEGER | 새로 저장됐지만 다른 사이트 공고와 같다고 판단된 수 (`new_postings`의 일부) |
| `excluded` | INTEGER | 직무 필터에서 `EXCLUDED`로 분류된 수 |
| `ats_enriched` | INTEGER | ATS 공개 API로 본문을 보강한 수 |
| `scored` | INTEGER | 점수를 매긴 수 |
| 🔗 `resume_version_id` | BIGINT → `resume_versions`, NULL 가능 | 이번 실행에 사용한 레쥬메 |
| `error_message` | TEXT, NULL 가능 | 실패 이유 |

- 숫자 검산식: `postings_found = new_postings + duplicates` — 실행이 끝난 줄(`status ≠ running`)에서는 DB가 이 식을 검사한다.
- 실행 시작 시 `running`으로 한 줄을 만들고, 끝날 때 결과로 갱신한다. 컨테이너 강제 종료 등으로 `running`이 계속 남은 줄은 "비정상 종료"로 본다 (1기의 좀비 태스크와 같은 상황).

---

## 3. 핵심 규칙

### 3-1. 직무·직급 분류

| 우선순위 | 직무 |
|---|---|
| `P1` | DE, BI, AE, 데이터 분석(DA), Data Scientist(DS) — 인턴 포함 |
| `P2` | IT·SW 직무, ML Engineer — 인턴 포함 |
| `EXCLUDED` | 그 외 무관 직무, Coordinator 직무 — **저장하되 점수를 매기지 않고 화면에 표시하지 않음** |

| 직급 | 판단 |
|---|---|
| `intern` / `entry` | 대상 직급 (Junior·입문 관련 모든 직급, 인턴) |
| `senior_plus` | Senior·Staff·Lead·Principal 등 — 수집하되 점수에서 감점 |
| `unknown` | 제목과 본문 모두로 판단 불가 — 후보로 남김 |

- 판단 순서: 제목 → (본문이 있으면) 본문 속 직급 추측 단어 → 둘 다 없으면 `unknown`.
- 지역: GTA + 캐나다 전역 원격. 그 외 지역 공고는 `EXCLUDED`.

### 3-2. 연봉 통화

- 통화는 **메일에 적힌 통화 기호**로 판단한다.
- `USD`, `CAD` → 그대로 둔다 (`salary_*_cad`, `fx_rate` 모두 NULL).
- 그 외 통화 → CAD로 환산하고 `fx_rate`, `fx_rate_date`를 함께 저장한다.
- 환율 날짜 = 이 공고를 처음 담고 있던 메일의 수신일. 그날 환율이 없으면(주말·공휴일) **직전 영업일** 환율을 쓴다.
- 환율 출처: Bank of Canada 공식 환율 (연결 방식은 4~5단계에서 확인).
- 시급·월급은 연봉으로 환산하지 않는다.

### 3-3. 점수를 언제 다시 매기는가

`input_hash`는 Claude에 보낸 공고 입력(제목·회사·위치·직급 정보·본문)의 지문이다.

| 상황 | 결과 |
|---|---|
| 같은 공고 + 같은 레쥬메 + 같은 입력 | 다시 매기지 않음 (DB가 중복으로 거부) |
| 본문이 새로 생김 (수동 붙여넣기 / ATS 보강) | 입력이 바뀌었으므로 **새 줄 추가**, 이전 점수는 유지 |
| 붙여넣은 본문을 고쳐서 다시 붙여넣음 | 입력이 바뀌었으므로 새 줄 추가 |
| 레쥬메가 바뀜 | **기존 공고는 다시 매기지 않음.** 새로 들어온 공고만 새 레쥬메로 매김 |
| 다른 사이트의 중복 공고 | 점수를 매기지 않음. 원본 점수를 보여줌 |
| `EXCLUDED` 공고 | 점수를 매기지 않음 |

- 레쥬메 변경 후 기존 공고에 본문이 새로 붙은 경우: 그 시점의 **현재 레쥬메**로 본문 점수를 매긴다. ("본문이 생기면 다시 점수" 규칙이 우선)

**대표 점수** (목록 화면에 보여줄 점수 하나):
1. `with_description` 점수가 있으면 그중 가장 최근 것
2. 없으면 `metadata_only` 점수 중 가장 최근 것
3. 중복 공고는 원본의 대표 점수를 따른다

→ DB 뷰(`v_representative_scores`)로 만들어 화면 코드가 같은 규칙을 쓰게 한다.

### 3-4. `evidence` JSONB 구조

```json
{
  "items": [
    {
      "resume_part": "레쥬메의 해당 부분 (짧게)",
      "posting_requirement": "공고의 요구사항 (본문이 없으면 직무명·회사 정보)",
      "result": "match | partial | missing"
    }
  ],
  "adjustments": [
    { "reason": "senior_role", "delta": -20 }
  ]
}
```

- `adjustments`에 감점 이유를 남겨, 경력직 감점이 점수에 얼마나 반영됐는지 화면에서 보이게 한다. (감점 폭은 5단계에서 결정)
- `metadata_only` 점수의 근거는 얕을 수밖에 없다. 화면에 "본문 없이 매긴 점수" 표시를 함께 둔다.

---

## 4. 다른 사이트의 같은 공고 판단

1. **정규화** 후 `match_key = 회사|직무명|도시` 생성
   - 회사: 소문자, 기호 제거, `inc` · `ltd` · `corp` · `llc` · `co` · `limited` · `corporation` 꼬리 제거
   - 직무명: 소문자, 기호 제거, 제목 속 지역·근무형태 표기 제거, 약어는 **지우지 않고 풀기** (`sr` → `senior`, `jr` → `junior`)
   - 위치: 도시 이름만, 원격은 `remote`
2. **30일 제한**: 원본의 `first_seen_at`으로부터 30일 안에 **다른 사이트**에서 발견된 경우만 같은 공고로 본다.
3. **원본** = 가장 먼저 발견된 공고. 나중 공고의 `duplicate_of`에 원본 번호를 적는다.
4. 원본을 가리키는 공고만 허용한다 (중복의 중복을 가리키지 않음 → 사슬 방지).
5. 중복 공고 쪽에서 본문을 확보하면 원본에 본문을 옮기고, 원본 기준으로 본문 점수를 매긴다.
6. 화면에는 카드 한 장으로 합치고 출처 사이트와 각 링크를 함께 표시한다.

**알려진 한계**
- 같은 회사·같은 도시·같은 직무명으로 여러 자리를 뽑으면 잘못 합쳐질 수 있다 → `duplicate_of`를 비우면 풀린다.
- 단어 순서가 다르면("Analyst, Data") 못 알아본다 → 점수를 두 번 매기는 정도의 손해.
- 정규화 규칙을 바꾸면 기존 `match_key`를 모두 다시 계산한다.
- 실제 데이터로 7단계(테스트)에서 다듬는다.

---

## 5. DB로 막을 수 없어 코드가 지켜야 하는 규칙

| 규칙 | 이유 |
|---|---|
| `EXCLUDED` 공고와 중복 공고에는 점수를 매기지 않는다 | 다른 표의 값에 따라 달라지는 규칙이라 CHECK로 표현 불가 |
| `jobright_score`는 Jobright 메일에서만 채운다 | 사이트 정보가 `alert_emails`에 있음 |
| `duplicate_of`는 원본(자기 자신이 중복이 아닌 공고)만 가리킨다 | 표 안의 다른 줄을 봐야 함 |
| Claude에 레쥬메를 보내기 전 연락처 줄 제거 | 개인정보 보호 |
| 공개 블로그 생성 코드는 §6의 공개 칸만 명시적으로 선택 (`SELECT *` 금지) | 실수로 비공개 칸이 공개되는 것 방지 |

---

## 6. 공개 / 비공개 구분 (A 방식)

| 공개 블로그 (`yujung20.github.io`) | 비공개 페이지 (내 컴퓨터 전용) |
|---|---|
| 직무명, 회사, 위치, 근무형태 | 공개 항목 전부 |
| 연봉 원문 / 숫자 | `postings.description` (공고 원문) |
| 직무 분류, 우선순위, 직급 | `match_scores.evidence` (상세 근거) |
| 대표 점수 (그대로 또는 높음/중간/낮음 — 8단계에서 결정) | `resume_versions.resume_text` |
| `match_scores.summary` | Jobright 점수 비교 |
| 출처 사이트와 공고 링크 | 점수 변화 이력 |

- **공고 원문은 공개하지 않는다.** 특히 LinkedIn 등에서 직접 붙여넣은 본문을 공개 블로그에 다시 올리면 해당 사이트 약관에 걸릴 수 있다.

---

## 7. 보안·운영

- DB 접속 정보(사용자·비밀번호)는 `.env`에 두고 코드에 적지 않는다. (1기 `db.py`의 비밀번호 하드코딩 개선)
- 2기 전용 DB 사용자를 만들어 `jobs` DB에만 접근하게 한다.
- `credentials.json`, `token.json`, 레쥬메 파일, DB 백업 파일은 모두 저장소 밖에 보관하고 `.gitignore`에 등록한다.
- Claude 모델 이름은 설정값(`.env`)으로 두고, 실제 사용한 이름을 `match_scores.model`에 기록한다.
- DB 세션 시간대는 UTC로 고정한다.

---

## 8. 1기 데이터 아카이브

### 절차 (4단계 첫 작업)

1. Git 태그로 1기 시점 표시 — 파이프라인 저장소와 블로그 저장소 **둘 다**
2. `pg_dump`로 1기 표 2개 백업 파일 생성 (저장소 밖 보관)
3. `jobs` DB에 스키마 `archive_v1` 생성 후 `job_postings`, `pipeline_runs` 복사
4. 줄 수 확인: `job_postings` **1,821**, `pipeline_runs` **164**
5. `airflow` DB의 원래 표는 바로 지우지 않는다. 2기가 안정적으로 돌아간 뒤 삭제 여부 결정

- 아카이브 데이터는 **수정하지 않는다** (시간대 변환 포함). 이력서에 쓴 1기 확정 수치의 근거이기 때문이다.
- 1기 분석 결과(키워드·요약·필수 조건·추천 대상)는 DB가 아니라 블로그 저장소 `_posts/*.md`에만 있으며, Git으로 보존된다.
- 블로그의 1기 공고 글과 통계 페이지는 "1기 아카이브"로 고정한다.

### 1기 데이터 해석 시 주의

| 칸 | 실제 의미 |
|---|---|
| `job_postings.posted_at` | 공고 게시일이 **아니라** 블로그 글 생성 시각 |
| `job_postings.analyzed` | TRUE여도 블로그에 같은 회사+직무 글이 이미 있어 **분석 없이 건너뛴** 경우가 포함됨. 본문 50자 미만 공고는 FALSE로 남아 매 실행마다 재시도됨 |
| `job_postings.collected_at` 등 | `TIMESTAMP`(시간대 없음). 컨테이너 기본 시간대 기준으로 추정되나 확인되지 않음 |
| 중복 기준 | DB는 URL, 블로그는 회사+직무명 앞 40자 — 기준이 두 가지였음 |
| `pipeline_runs.status` | 실제 결과와 무관하게 `"success"`로 고정 기록됨 |

---

## 9. 테이블 생성 SQL (초안)

> 4단계에서 실행 전 다시 검토한다. PostgreSQL 13 기준.

```sql
-- 시간대 고정
SET TIME ZONE 'UTC';

CREATE TABLE pipeline_runs (
    run_id                BIGSERIAL PRIMARY KEY,
    airflow_run_id        TEXT,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at           TIMESTAMPTZ,
    status                TEXT NOT NULL DEFAULT 'running'
                          CHECK (status IN ('running','success','partial','failed')),
    emails_read           INTEGER NOT NULL DEFAULT 0 CHECK (emails_read >= 0),
    emails_skipped        INTEGER NOT NULL DEFAULT 0 CHECK (emails_skipped >= 0),
    emails_failed         INTEGER NOT NULL DEFAULT 0 CHECK (emails_failed >= 0),
    postings_found        INTEGER NOT NULL DEFAULT 0 CHECK (postings_found >= 0),
    new_postings          INTEGER NOT NULL DEFAULT 0 CHECK (new_postings >= 0),
    duplicates            INTEGER NOT NULL DEFAULT 0 CHECK (duplicates >= 0),
    cross_site_duplicates INTEGER NOT NULL DEFAULT 0 CHECK (cross_site_duplicates >= 0),
    excluded              INTEGER NOT NULL DEFAULT 0 CHECK (excluded >= 0),
    ats_enriched          INTEGER NOT NULL DEFAULT 0 CHECK (ats_enriched >= 0),
    scored                INTEGER NOT NULL DEFAULT 0 CHECK (scored >= 0),
    resume_version_id     BIGINT,  -- FK는 resume_versions 생성 후 추가
    error_message         TEXT,
    CHECK (status = 'running' OR postings_found = new_postings + duplicates),
    CHECK (cross_site_duplicates <= new_postings),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE resume_versions (
    resume_version_id BIGSERIAL PRIMARY KEY,
    file_hash         TEXT NOT NULL UNIQUE,
    resume_text       TEXT NOT NULL,
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE pipeline_runs
    ADD FOREIGN KEY (resume_version_id)
    REFERENCES resume_versions (resume_version_id) ON DELETE RESTRICT;

CREATE TABLE alert_emails (
    email_id       BIGSERIAL PRIMARY KEY,
    message_id     TEXT NOT NULL UNIQUE,
    gmail_id       TEXT NOT NULL UNIQUE,
    site           TEXT NOT NULL
                   CHECK (site IN ('linkedin','indeed','glassdoor','jobright')),
    subject        TEXT,
    received_at    TIMESTAMPTZ NOT NULL,
    email_type     TEXT NOT NULL
                   CHECK (email_type IN ('job_alert','jobright_instant','jobright_digest','non_job')),
    postings_found INTEGER NOT NULL DEFAULT 0 CHECK (postings_found >= 0),
    parse_status   TEXT NOT NULL
                   CHECK (parse_status IN ('success','failed','skipped')),
    parse_error    TEXT,
    run_id         BIGINT NOT NULL REFERENCES pipeline_runs (run_id) ON DELETE RESTRICT,
    collected_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (parse_status <> 'failed' OR parse_error IS NOT NULL)
);

CREATE TABLE postings (
    posting_id             BIGSERIAL PRIMARY KEY,
    site                   TEXT NOT NULL
                           CHECK (site IN ('linkedin','indeed','glassdoor','jobright')),
    site_job_id            TEXT NOT NULL,
    title                  TEXT NOT NULL,
    company                TEXT NOT NULL,
    location               TEXT,
    work_mode              TEXT NOT NULL DEFAULT 'unknown'
                           CHECK (work_mode IN ('onsite','hybrid','remote','unknown')),
    job_url                TEXT,
    posted_at_est          TIMESTAMPTZ,
    salary_text            TEXT,
    salary_min             NUMERIC CHECK (salary_min >= 0),
    salary_max             NUMERIC CHECK (salary_max >= 0),
    salary_currency        TEXT,
    salary_period          TEXT
                           CHECK (salary_period IN ('year','month','week','day','hour')),
    salary_min_cad         NUMERIC CHECK (salary_min_cad >= 0),
    salary_max_cad         NUMERIC CHECK (salary_max_cad >= 0),
    fx_rate                NUMERIC CHECK (fx_rate > 0),
    fx_rate_date           DATE,
    role_category          TEXT NOT NULL
                           CHECK (role_category IN ('DE','BI','AE','DA','DS','ML','IT_SW','OTHER')),
    priority               TEXT NOT NULL
                           CHECK (priority IN ('P1','P2','EXCLUDED')),
    seniority              TEXT NOT NULL DEFAULT 'unknown'
                           CHECK (seniority IN ('intern','entry','senior_plus','unknown')),
    seniority_source       TEXT NOT NULL DEFAULT 'none'
                           CHECK (seniority_source IN ('title','description','none')),
    description            TEXT,
    description_source     TEXT NOT NULL DEFAULT 'none'
                           CHECK (description_source IN ('none','indeed_snippet','ats','manual')),
    description_updated_at TIMESTAMPTZ,
    ats_platform           TEXT
                           CHECK (ats_platform IN ('greenhouse','lever','ashby')),
    match_key              TEXT NOT NULL,
    duplicate_of           BIGINT REFERENCES postings (posting_id) ON DELETE RESTRICT,
    first_seen_at          TIMESTAMPTZ NOT NULL,
    last_seen_at           TIMESTAMPTZ NOT NULL,
    UNIQUE (site, site_job_id),
    -- 본문 유무와 출처 표시가 서로 맞아야 함
    CHECK ((description IS NULL) = (description_source = 'none')),
    -- 연봉 범위가 뒤집히지 않아야 함
    CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max),
    -- 환율은 USD·CAD가 아닐 때만, 환율과 날짜는 항상 함께
    CHECK (fx_rate IS NULL OR salary_currency NOT IN ('USD','CAD')),
    CHECK ((fx_rate IS NULL) = (fx_rate_date IS NULL)),
    CHECK ((salary_min_cad IS NULL AND salary_max_cad IS NULL) OR fx_rate IS NOT NULL),
    -- 자기 자신을 원본으로 가리키지 않음
    CHECK (duplicate_of IS NULL OR duplicate_of <> posting_id),
    CHECK (last_seen_at >= first_seen_at)
);

CREATE INDEX idx_postings_match_key ON postings (match_key);
CREATE INDEX idx_postings_priority  ON postings (priority);

CREATE TABLE email_postings (
    email_id          BIGINT NOT NULL REFERENCES alert_emails (email_id) ON DELETE RESTRICT,
    posting_id        BIGINT NOT NULL REFERENCES postings (posting_id) ON DELETE RESTRICT,
    position_in_email SMALLINT NOT NULL CHECK (position_in_email >= 1),
    is_sponsored      BOOLEAN NOT NULL DEFAULT FALSE,
    jobright_score    SMALLINT CHECK (jobright_score BETWEEN 0 AND 100),
    PRIMARY KEY (email_id, posting_id)
);

CREATE INDEX idx_email_postings_posting ON email_postings (posting_id);

CREATE TABLE match_scores (
    score_id          BIGSERIAL PRIMARY KEY,
    posting_id        BIGINT NOT NULL REFERENCES postings (posting_id) ON DELETE RESTRICT,
    resume_version_id BIGINT NOT NULL REFERENCES resume_versions (resume_version_id) ON DELETE RESTRICT,
    input_hash        TEXT NOT NULL,
    score_basis       TEXT NOT NULL
                      CHECK (score_basis IN ('metadata_only','with_description')),
    score             SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 100),
    evidence          JSONB NOT NULL,
    summary           TEXT NOT NULL,
    model             TEXT NOT NULL,
    scored_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id            BIGINT REFERENCES pipeline_runs (run_id) ON DELETE RESTRICT,
    UNIQUE (posting_id, resume_version_id, input_hash)
);

CREATE INDEX idx_match_scores_posting ON match_scores (posting_id);

-- 대표 점수: 본문 기준 최신 점수 우선, 없으면 메일 정보 기준 최신 점수
-- 중복 공고는 원본의 점수를 따름
CREATE VIEW v_representative_scores AS
SELECT p.posting_id,
       COALESCE(p.duplicate_of, p.posting_id) AS scored_posting_id,
       s.score_id, s.score, s.score_basis, s.summary, s.scored_at
FROM postings p
LEFT JOIN LATERAL (
    SELECT ms.*
    FROM match_scores ms
    WHERE ms.posting_id = COALESCE(p.duplicate_of, p.posting_id)
    ORDER BY (ms.score_basis = 'with_description') DESC, ms.scored_at DESC
    LIMIT 1
) s ON TRUE
WHERE p.priority <> 'EXCLUDED';
```

---

## 10. 다음 단계로 넘기는 결정 사항

### 실행 일정 (확정, 6단계에서 적용)

- 월~금 오후 7시 (America/Toronto) — `schedule_interval="0 19 * * 1-5"`, `pendulum`으로 서머타임 처리
- 메일이 도착할 때 바로 실행되는 방식이 아니라, **정해진 시간에 그동안 쌓인 메일을 한꺼번에 읽는** 방식
- 금요일 실행 후 주말에 온 메일은 월요일 실행에서 함께 처리

| 항목 | 결정 시점 |
|---|---|
| 메일을 어디부터 읽을지 (마지막 성공 실행 이후가 기본안) | 4단계 |
| 수동 붙여넣기 방법 (폴더에 텍스트 파일 등) | 4~5단계 |
| 경력직 감점 폭, 점수 기준 | 5단계 |
| Bank of Canada 환율 연결 방식 | 4~5단계 |
| `airflow`에서 `jobs` DB 접속 설정 | 4·6단계 |
| 공개 화면의 점수 표시 방식 (숫자 / 높음·중간·낮음) | 8단계 |
| `stats.json` 생성 방식 확인 (`rebuild-stats.js`) | 8단계 |
| `airflow` DB의 1기 원본 표 삭제 여부 | 2기 안정화 후 |
