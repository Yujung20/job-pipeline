import requests
import time
import re
import html
from datetime import datetime
from db import log_pipeline_run

DATA_KEYWORDS = [
    # 데이터 직군 (영어)
    "data engineer", "data scientist", "data analyst",
    "data architect", "data platform", "data infrastructure",
    "data product", "data governance", "data steward",
    "analytics engineer", "business intelligence", "bi engineer",
    "etl", "dataops",

    # AI/ML 직군 (영어)
    "machine learning", "ml engineer", "mlops", "llmops",
    "ai engineer", "ai agent", "ai software", "ai product",
    "ai consultant", "ai solution", "ai researcher",
    "llm", "rag", "nlp", "computer vision",
    "deep learning", "foundation model", "large language model",
    "generative ai", "gen ai", "prompt engineer",

    # 연구/분석 직군 (영어)
    "research engineer", "research scientist",
    "quantitative analyst", "quant",
    "knowledge graph",

    # 백엔드 (AI 팀 포함 목적)
    "backend engineer",

    # 데이터 라벨링/어노테이션
    "data labeling", "data annotation", "annotation",

    # 통계
    "statistician", "statistical",

    # 한국어 직군명
    "데이터", "머신러닝", "인공지능", "딥러닝",
    "ai 엔지니어", "ai 연구", "ai 기획", "ai 서비스",
    "ai 강사", "ai 교육", "ai 컨설턴트", "ai 솔루션",
    "데이터 라벨링", "어노테이션", "통계 분석",

    # ML (오탐 방지 위해 앞뒤 공백)
    " ml ",
]


# ── 원티드 검색 키워드 ──────────────────────────────────────────
WANTED_KEYWORDS = [
    "AI", "LLM", "머신러닝", "데이터", "data", "ML", "Machine Learning", "RAG"
]

# ── Greenhouse / Lever 회사 리스트 ─────────────────────────────
COMPANIES = [
    # 🤖 AI 스타트업/스케일업
    "openai", "anthropic", "cohere", "mistral", "perplexity",
    "character-ai", "glean", "scaleai", "harvey", "codeium",
    "abridge", "writer", "runway", "elevenlabs", "synthesia",
    "lumaai", "huggingface", "deepmind", "bytedance", "tiktok",
    # 🛠️ 개발자 도구 / MLOps
    "wandb", "databricks", "astronomer", "cloudflare", "digitalocean",
    "notion", "canva", "atlassian",
    # 📊 데이터 인프라 중견
    "snowflake", "confluent", "mongodb", "elastic", "redis",
    "cockroachlabs", "fivetran", "dbtlabs", "starburst", "singlestore",
    # 🌏 아시아 스케일업
    "coupang", "grab", "shopee", "sea", "rakuten",
    "booking", "agoda", "expedia",
    # 🏢 기타 유망 중견
    "hubspot", "stripe", "block", "shopify",
]

# ── Ashby 전용 회사 리스트 (슬러그 대소문자 주의) ──────────────
ASHBY_COMPANIES = [
    "OpenAI", "Anthropic", "Figma", "Linear", "Cursor",
    "Vercel", "Perplexity", "Notion", "Ramp", "Brex",
    "scale-ai", "Reddit", "Shopify", "Plaid", "Airtable",
    "Retool", "Supabase", "PostHog", "Replit", "Mercury",
    "Cohere", "Zapier", "Harvey", "Render", "Docker",
    "Benchling", "WorkOS", "Confluent", "Airwallex", "Crusoe"
]


def is_data_role(title: str, description: str = "") -> bool:
    """공고 제목/설명이 데이터 직군인지 확인"""
    text = (title + " " + description).lower()
    return any(keyword in text for keyword in DATA_KEYWORDS)


def slugify(name: str) -> str:
    """회사 이름을 슬러그 형태로 변환 (공백 제거, 소문자)"""
    return re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ', '-'))


# ── Greenhouse ─────────────────────────────────────────────────
def fetch_greenhouse(company_slug: str) -> list:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return []

        jobs = res.json().get("jobs", [])
        result = []
        for job in jobs:
            title = job.get("title", "")
            if is_data_role(title):

                # ── 상세 API 호출해서 description 가져오기 ──
                job_id = job.get("id")
                description = ""
                if job_id:
                    detail_url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs/{job_id}"
                    try:
                        detail_res = requests.get(detail_url, timeout=10)
                        if detail_res.status_code == 200:
                            detail = detail_res.json()
                            raw = detail.get("content", "")
                            raw = html.unescape(raw)
                            description = re.sub(r'<[^>]+>', ' ', raw)
                            description = re.sub(r'\s+', ' ', description).strip()[:1000]
                    except Exception:
                        pass
                    time.sleep(0.2)

                result.append({
                    "source": "greenhouse",
                    "company": company_slug,
                    "title": title,
                    "url": job.get("absolute_url", ""),
                    "location": job.get("location", {}).get("name", ""),
                    "updated_at": job.get("updated_at", ""),
                    "description": description
                })
        return result

    except Exception as e:
        print(f"[Greenhouse] {company_slug} 오류: {e}")
        return []


# ── Lever ──────────────────────────────────────────────────────
def fetch_lever(company_slug: str) -> list:
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return []

        jobs = res.json()
        if not isinstance(jobs, list):
            return []

        result = []
        for job in jobs:
            title = job.get("text", "")
            if is_data_role(title):
                result.append({
                    "source": "lever",
                    "company": company_slug,
                    "title": title,
                    "url": job.get("hostedUrl", ""),
                    "location": job.get("categories", {}).get("location", ""),
                    "updated_at": str(job.get("createdAt", "")),
                    "description": job.get("descriptionPlain", "")[:500]
                })
        return result

    except Exception as e:
        print(f"[Lever] {company_slug} 오류: {e}")
        return []


# ── Ashby ──────────────────────────────────────────────────────
def fetch_ashby(company_slug: str) -> list:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return []

        jobs = res.json().get("jobPostings", [])
        result = []
        for job in jobs:
            title = job.get("title", "")
            if is_data_role(title):
                result.append({
                    "source": "ashby",
                    "company": company_slug,
                    "title": title,
                    "url": job.get("jobUrl", ""),
                    "location": job.get("location", ""),
                    "updated_at": job.get("publishedAt", ""),
                    "description": job.get("descriptionPlain", "")[:500]
                })
        return result

    except Exception as e:
        print(f"[Ashby] {company_slug} 오류: {e}")
        return []


# ── Wanted ─────────────────────────────────────────────────────
def fetch_wanted() -> list:
    result = []
    seen_ids = set()

    for keyword in WANTED_KEYWORDS:
        url = f"https://www.wanted.co.kr/api/v4/jobs?query={keyword}&country=kr&limit=50&offset=0"
        try:
            res = requests.get(url, timeout=10, headers={"Accept": "application/json"})
            if res.status_code != 200:
                continue

            jobs = res.json().get("data", [])
            for job in jobs:
                job_id = job.get("id")

                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                if not is_data_role(job.get("position", "")):
                    continue

                detail_url = f"https://www.wanted.co.kr/api/v4/jobs/{job_id}"
                try:
                    detail_res = requests.get(detail_url, timeout=10, headers={"Accept": "application/json"})
                    if detail_res.status_code != 200:
                        continue
                    detail = detail_res.json().get("job", {})
                    d = detail.get("detail", {})

                    description = "\n\n".join(filter(None, [
                        d.get("intro", ""),
                        d.get("main_tasks", ""),
                        d.get("requirements", ""),
                        d.get("preferred_points", ""),
                        d.get("benefits", "")
                    ]))[:1000]

                except Exception:
                    description = ""

                result.append({
                    "source": "wanted",
                    "company": job.get("company", {}).get("name", ""),
                    "title": job.get("position", ""),
                    "url": f"https://www.wanted.co.kr/wd/{job_id}",
                    "location": job.get("address", {}).get("location", ""),
                    "updated_at": job.get("due_time", ""),
                    "description": description
                })

                time.sleep(2)

        except Exception as e:
            print(f"[Wanted] '{keyword}' 키워드 오류: {e}")

        time.sleep(2)

    print(f"[Wanted] 총 {len(result)}개 공고 수집")
    return result


# ── 전체 수집 실행 ──────────────────────────────────────────────
def collect_all_jobs(run_id: str = None) -> list:
    all_jobs = []
    seen = set()

    fetch_fns = [
        ("greenhouse", fetch_greenhouse),
        ("lever", fetch_lever),
        ("ashby", fetch_ashby),
    ]

    for source_name, fetch_fn in fetch_fns:
        started_at = datetime.now()
        companies_tried = 0
        jobs_found = 0
        jobs_saved = 0
        jobs_skipped = 0
        jobs_failed = 0

        # ✅ 변경: Ashby는 전용 리스트, 나머지는 기존 COMPANIES 사용
        company_list = ASHBY_COMPANIES if source_name == "ashby" else COMPANIES

        for company in company_list:
            companies_tried += 1
            try:
                jobs = fetch_fn(company)
                jobs_found += len(jobs)

                for job in jobs:
                    key = f"{job['company']}_{job['title']}"
                    if key not in seen:
                        seen.add(key)
                        all_jobs.append(job)
                        jobs_saved += 1
                    else:
                        jobs_skipped += 1

            except Exception as e:
                jobs_failed += 1
                print(f"[{source_name}] {company} 오류: {e}")

            time.sleep(0.3)

        finished_at = datetime.now()
        duration = (finished_at - started_at).total_seconds()

        log_pipeline_run({
            "run_id": run_id,
            "source": source_name,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration,
            "companies_tried": companies_tried,
            "jobs_found": jobs_found,
            "jobs_saved": jobs_saved,
            "jobs_skipped": jobs_skipped,
            "jobs_failed": jobs_failed,
            "status": "success",
            "error_message": None
        })

        print(f"[{source_name}] 시도 {companies_tried}개 회사 | 발견 {jobs_found}개 | 저장 {jobs_saved}개 | 중복 {jobs_skipped}개 | 실패 {jobs_failed}개 | {duration:.1f}초")

    # ── 원티드는 따로 처리 ──────────────────────────────────────
    started_at = datetime.now()
    try:
        wanted_jobs = fetch_wanted()
        jobs_found = len(wanted_jobs)
        jobs_saved = 0
        jobs_skipped = 0

        for job in wanted_jobs:
            key = f"{job['company']}_{job['title']}"
            if key not in seen:
                seen.add(key)
                all_jobs.append(job)
                jobs_saved += 1
            else:
                jobs_skipped += 1

    except Exception as e:
        jobs_found = 0
        jobs_saved = 0
        jobs_skipped = 0
        print(f"[wanted] 오류: {e}")

    finished_at = datetime.now()
    duration = (finished_at - started_at).total_seconds()

    log_pipeline_run({
        "run_id": run_id,
        "source": "wanted",
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "companies_tried": len(WANTED_KEYWORDS),
        "jobs_found": jobs_found,
        "jobs_saved": jobs_saved,
        "jobs_skipped": jobs_skipped,
        "jobs_failed": 0,
        "status": "success",
        "error_message": None
    })

    print(f"[wanted] 키워드 {len(WANTED_KEYWORDS)}개 | 발견 {jobs_found}개 | 저장 {jobs_saved}개 | 중복 {jobs_skipped}개 | {duration:.1f}초")

    print(f"\n✅ 총 {len(all_jobs)}개 데이터 직군 공고 수집 완료")
    return all_jobs


# ── 테스트 실행 ────────────────────────────────────────────────
if __name__ == "__main__":
    jobs = collect_all_jobs()
    for job in jobs[:5]:
        print(f"\n[{job['source'].upper()}] {job['company']}")
        print(f"  제목: {job['title']}")
        print(f"  위치: {job['location']}")
        print(f"  URL:  {job['url']}")