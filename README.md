# 🛰️ Job Auto-Collector — Automated Job Posting Pipeline

> Greenhouse·Lever·Ashby·Wanted 채용 공고 자동 수집·분석·게시 파이프라인  
> **(ENG) Automated Pipeline that Collects, Analyzes, and Publishes Job Postings from Greenhouse, Lever, Ashby, and Wanted**

---

## 📌 Project Summary

매일 정해진 시간에 Airflow DAG가 자동으로 실행되어,  
Greenhouse·Lever·Ashby의 공개 API와 Wanted의 내부 API를 통해 약 100개 기업의 채용 공고를 수집합니다.

수집된 공고는 PostgreSQL에 저장되고, Claude API가 각 공고를 분석하여  
직무 적합성, 기술 스택, 시니어리티 등의 정보를 추출합니다.

분석이 완료된 공고는 Jekyll 기반 GitHub Pages 블로그에 자동으로 게시되며,  
30일이 지난 공고는 자동으로 만료 처리됩니다.

로그인이 필요한 LinkedIn 등의 플랫폼은 기존에 사용하던 수동 도구(`analyze.js`)로 보완하여,  
공고 텍스트를 붙여넣으면 Claude API가 분석 후 동일한 블로그에 게시합니다.

---

**(ENG)**

Every day at a scheduled time, an Airflow DAG automatically runs to collect job postings  
from approximately 100 companies via the public APIs of Greenhouse, Lever, and Ashby,  
as well as Wanted's internal API.

Collected postings are stored in PostgreSQL, then analyzed by the Claude API  
to extract information such as role fit, tech stack, and seniority level.

Once analyzed, postings are automatically published to a Jekyll-based GitHub Pages blog,  
with postings older than 30 days automatically expired.

For platforms requiring login, such as LinkedIn, an existing manual tool (`analyze.js`)  
is used as a complement — pasted job text is analyzed by the Claude API  
and published to the same blog.

---

## 🛠 Skills

**Pipeline / Orchestration**

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Apache Airflow](https://img.shields.io/badge/Apache_Airflow-017CEE?style=flat-square&logo=apacheairflow&logoColor=white)

**AI / Analysis**

![Anthropic](https://img.shields.io/badge/Claude_API-D97757?style=flat-square&logo=anthropic&logoColor=white)

**Data**

![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)

**Infra / Deploy**

![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

**Blog / Frontend**

![Jekyll](https://img.shields.io/badge/Jekyll-CC0000?style=flat-square&logo=jekyll&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-222222?style=flat-square&logo=githubpages&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=black)

**Manual Track**

![Node.js](https://img.shields.io/badge/Node.js-339933?style=flat-square&logo=node.js&logoColor=white)

---

## 🔄 System Architecture

```
[Manual]                                    [Automated]
채용 공고 텍스트 복사                       Airflow DAG (매일 9:00 AM KST)
   │                                            │
   ▼                                            ▼
node analyze.js 실행                  ┌─────────────────────────────┐
   │                                  │      수집 (Collectors)         │
   │                                  │  Greenhouse / Lever / Ashby   │
   │                                  │  (공개 API)                    │
   │                                  │  Wanted (내부 API)             │
   │                                  │  ~100개 기업 대상                │
   │                                  └───────────────┬───────────────┘
   │                                                  ▼
   │                                        PostgreSQL (job_postings)
   │                                                  │
   ▼                                                  ▼
┌──────────────────┐                      ┌──────────────────────┐
│  Claude API 분석    │                    │  Claude API 분석        │
│  (analyze.js 내부)  │                    │  (analyzer.py 내부)     │
└─────────┬────────────┘                  └───────────┬─────────────┘
          │                                            │
          ▼                                            ▼
   Markdown 생성                              Markdown 생성
          │                                            │
          └───────────────────┬────────────────────────┘
                               ▼
                  GitHub Pages 블로그 게시
                  (Jekyll · 30일 후 자동 만료)
```

---

**(ENG)**

```
[Manual]                                    [Automated]
Copy job posting text                  Airflow DAG (daily, 9:00 AM KST)
   │                                            │
   ▼                                            ▼
Run node analyze.js                  ┌─────────────────────────────┐
   │                                  │      Collectors               │
   │                                  │  Greenhouse / Lever / Ashby   │
   │                                  │  (public APIs)                │
   │                                  │  Wanted (internal API)        │
   │                                  │  ~100 companies                │
   │                                  └───────────────┬───────────────┘
   │                                                  ▼
   │                                        PostgreSQL (job_postings)
   │                                                  │
   ▼                                                  ▼
┌──────────────────┐                      ┌──────────────────────┐
│  Claude API analysis │                  │  Claude API analysis   │
│  (inside analyze.js) │                  │  (inside analyzer.py)  │
└─────────┬────────────┘                  └───────────┬─────────────┘
          │                                            │
          ▼                                            ▼
   Generate Markdown                          Generate Markdown
          │                                            │
          └───────────────────┬────────────────────────┘
                               ▼
                  Publish to GitHub Pages blog
                  (Jekyll · auto-expires after 30 days)
```

---

## ✨ Main Features

### ⏰ Airflow DAG 자동 스케줄링

- 매일 **9:00 AM KST** (`0 0 * * *` UTC)에 DAG가 자동으로 트리거되어 별도 개입 없이 파이프라인이 실행됨
- `catchup=False` 설정으로 과거 미실행 구간을 한꺼번에 몰아서 실행하지 않도록 방지
- 작업 실패 시 **2회 재시도, 10분 간격**으로 재실행
- `execution_timeout`은 오래 걸리는 작업(`collect_jobs`, `analyze_jobs`)에만 적용하여, 무한 대기로 인한 파이프라인 전체 정지를 방지

**(ENG)**  
The DAG is automatically triggered every day at 9:00 AM KST without manual intervention. `catchup=False` prevents backfilling missed runs, and failed tasks retry twice with a 10-minute delay. `execution_timeout` is applied only to long-running tasks (`collect_jobs`, `analyze_jobs`) to avoid stalling the entire pipeline on a single hang.

---

### 🔍 다중 플랫폼 수집기 — 공개 API + 비공개 API 역공학

약 100개 기업을 대상으로, 플랫폼별로 서로 다른 수집 전략을 사용합니다.

**공개 API 기반 (Greenhouse / Lever / Ashby)**

- Greenhouse·Lever는 채용 정보를 제공하는 공식 공개 API를 그대로 사용
- Ashby는 기업마다 고유한 **slug 기반 네이밍 규칙**을 사용하여, 이를 별도로 파싱하는 처리가 필요했음
- Greenhouse 응답의 HTML 인코딩된 본문은 `html.unescape()`로 디코딩한 뒤 태그를 제거하여 정제

**비공개 API 역공학 (Wanted)**

원티드는 공식 공개 API를 제공하지 않아, 웹사이트 요청을 분석해 내부 API 엔드포인트(`https://www.wanted.co.kr/api/v4/jobs`)를 직접 찾아냈습니다.  
`country=kr` 파라미터가 없으면 응답이 비정상적이라는 점을 확인했고,  
`is_data_role()` 함수로 데이터 직군 여부를 먼저 필터링한 뒤에만 상세 정보 API를 호출하여 불필요한 요청을 최소화했습니다.

플랫폼별 실제 신규 공고 저장 비율을 SQL로 확인한 결과, **Wanted가 266건(53.8%)으로 가장 높은 수집률**을 보였고, 그 다음으로 **Greenhouse가 206건(41.7%)**으로 이어졌습니다.

**(ENG)**  
Across ~100 companies, each platform required a different collection strategy. Greenhouse and Lever use official public APIs, while Ashby required parsing company-specific slug-based naming conventions. Greenhouse's HTML-encoded content is decoded via `html.unescape()` before tag stripping. Wanted has no public API, so its internal endpoint (`https://www.wanted.co.kr/api/v4/jobs`) was discovered through request analysis; a `country=kr` parameter is required, and `is_data_role()` filtering is applied before detail API calls to minimize unnecessary requests. A SQL-based check of actual storage rates by platform confirmed Wanted led with 266 postings (53.8%), followed by Greenhouse with 206 postings (41.7%).

---

### 🤖 Claude API 기반 공고 분석

수집된 공고 원문을 Claude API에 전달하여, 다음 4가지 항목을 추출합니다.

- **핵심 키워드**: 공고 원문에서 자주 등장하거나 중요한 키워드 5~10개 선별
- **공고 요약**: 원문 전체를 짧게 요약
- **필수 지원 조건**: 채용 공고에 명시된 자격 요건 정리
- **추천 대상**: 어떤 배경/역량을 가진 사람에게 적합한 공고인지 제안

분석 결과는 `원문 → 핵심 키워드 → 공고 요약 → 필수 지원 조건 → 추천 대상` 순서로 마크다운 파일에 자동 기록되며, 핵심 키워드는 `Python` `SQL`처럼 코드 태그 스타일로 표시됩니다.

**(ENG)**  
Each collected job posting is sent to the Claude API to extract four structured fields: core keywords (5–10 frequently appearing or important terms), a summary, key requirements, and a recommendation of who the role would suit. The output is recorded in the order: original text → keywords → summary → requirements → recommended candidates, with keywords rendered as inline code tags (e.g. `Python` `SQL`).

---

## 📈 Data Insights — SQL 기반 운영 데이터 분석

파이프라인 운영 초기 데이터를 `pipeline_runs`와 `job_postings` 두 테이블을 SQL로 직접 분석하여 다음과 같은 인사이트를 도출했습니다.

**1. 측정 지표의 정합성 검증**

`pipeline_runs.jobs_saved`는 "회사명+제목 기준, 그날 실행 내 신규 식별 개수"(매일 리셋)이고, `job_postings`의 실제 행 수는 "url 기준 DB 전체 영구 저장 개수"로, 서로 다른 것을 측정하는 지표임을 확인했습니다. 이에 따라 단순히 "저장률 89.7%"로 해석하기보다, "수집 시도 중 신규 식별률"로 정확히 재정의했습니다.

**2. 플랫폼별 실제 신규 공고 저장 비율**

Wanted가 266건(53.8%)으로 가장 높았고, Greenhouse가 206건(41.7%)으로 이어져, 두 플랫폼이 전체 신규 공고 수집의 약 95%를 차지함을 확인했습니다.

**3. 요일별 등록 패턴**

화요일에 신규 공고 등록이 가장 활발했고, 주말에는 등록이 급감하는 패턴을 확인했습니다. 일요일에 `job_postings`에 행이 없는 것은 버그가 아니라, 그날 신규 공고가 0건이라 `GROUP BY` 자체에 행이 잡히지 않은 정상적인 현상임을 직접 검증했습니다.

> 📝 위 요일별 패턴은 운영 초기 데이터를 기준으로 한 잠정적 관찰이며, 데이터가 누적될수록 더 정교하게 검증·보완될 예정입니다.

**요약**

> 파이프라인 운영 데이터 분석 결과, Wanted(53.8%)와 Greenhouse(41.7%)가 신규 공고 수집의 약 95%를 차지했으며, 화요일에 신규 공고 등록이 가장 활발하고 주말에는 거의 등록이 없는 패턴을 확인함.

**(ENG)**  
Using SQL on the `pipeline_runs` and `job_postings` tables from early operational data, three key insights were found: (1) the metric `jobs_saved` measures daily new-identification within a run, not the same thing as permanent storage count in `job_postings` — so "89.7% save rate" actually means "new-identification rate among collection attempts"; (2) Wanted (53.8%) and Greenhouse (41.7%) together account for roughly 95% of newly stored postings; (3) Tuesdays showed the highest posting activity, with activity dropping sharply on weekends — confirmed that the missing Sunday row wasn't a bug, but a `GROUP BY` artifact of zero new postings that day. These weekday patterns are early observations and will be validated further as more data accumulates.

---

## 💡 Why We Built This

채용 공고를 매일 직접 찾아보는 대신, 이 과정 자체를 자동화하면서 동시에  
**Airflow, Docker, Claude API를 실전에서 다뤄볼 기회**로 만들고자 했습니다.

당장 필요한 도구가 없으면 직접 만들어서 쓴다는 생각으로 시작한 프로젝트입니다.  
매일 실제로 사용하는 구직 도구로 운영하면서, 그 과정에서 마주치는 실제 문제  
(컨테이너 환경, Git 자동화, API 제약 등)를 하나씩 직접 해결해나갔습니다.

**(ENG)**  
Instead of manually browsing job postings every day, this project automates the process —  
while also serving as a hands-on opportunity to work with **Airflow, Docker, and the Claude API**  
in a real-world setting.

The project started from a simple idea: if the tool you need doesn't exist, build it yourself.  
It runs daily as an actual job-search tool, and along the way, real operational problems  
(container environments, Git automation, API constraints, and more) were solved one by one.

---

## 📂 Project Structure

```text
job-pipeline/
├── airflow/
│   ├── dags/
│   │   └── job_pipeline_dag.py      # DAG 정의 (스케줄링·태스크 흐름)
│   ├── scripts/
│   │   ├── collectors.py            # 플랫폼별 수집기
│   │   ├── db.py                    # PostgreSQL 연동 및 로그 기록
│   │   └── analyzer.py              # Claude API 분석 및 포스트 생성
│   ├── docker-compose.yml
│   ├── Dockerfile                   # git 사전 설치된 커스텀 이미지
│   └── .env                         # ANTHROPIC_API_KEY, AIRFLOW_UID 등
└── analyze.js                       # 수동 트랙 (LinkedIn 등 로그인 필요 사이트용)
```

---

## 🧑‍💻 What I Learned

- Airflow DAG를 활용한 스케줄링 및 태스크 단위 타임아웃/재시도 설계
- 공개 API와 비공개(내부) API를 모두 다루는 다중 플랫폼 수집기 설계
- Wanted 같은 비공개 API의 엔드포인트를 요청 분석을 통해 직접 역공학으로 찾아내는 경험
- Docker 컨테이너 환경에서 Git 인증/권한 문제를 진단하고, 커스텀 Dockerfile로 근본적으로 해결하는 방법
- Windows + WSL2 + Docker 환경에서 발생하는 볼륨 마운트·파일 권한 이슈 디버깅
- Claude API를 활용해 비정형 텍스트(채용 공고)에서 구조화된 정보(키워드·요약·조건·추천 대상)를 추출하는 프롬프트 설계
- SQL을 활용해 운영 데이터를 직접 분석하고, 지표 간 정합성을 검증하는 경험
- 자동화 파이프라인과 기존 수동 도구를 함께 운영하며 점진적으로 전환하는 실무적 접근

**(ENG)**
- Designing Airflow DAG scheduling with per-task timeouts and retry logic
- Building a multi-platform collector that handles both public and private (internal) APIs
- Reverse-engineering an undocumented internal API endpoint (Wanted) through request analysis
- Diagnosing Git authentication/permission issues inside Docker containers and resolving them at the root with a custom Dockerfile
- Debugging volume mount and file permission issues across Windows + WSL2 + Docker
- Designing prompts for the Claude API to extract structured information (keywords, summary, requirements, recommended candidates) from unstructured job posting text
- Performing SQL-based analysis of operational data and validating consistency between metrics
- Taking a practical approach to running an automated pipeline alongside an existing manual tool during gradual transition
