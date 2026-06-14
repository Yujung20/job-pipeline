import anthropic
import os
import re
from datetime import datetime
from pathlib import Path

# ── 설정 ───────────────────────────────────────────────────────
BLOG_PATH = Path("/opt/airflow/blog")   # docker-compose.yml에서 연결한 블로그 경로
POSTS_PATH = BLOG_PATH / "_posts"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


def analyze_job(job: dict) -> dict:
    """
    Claude API로 공고 분석
    - 한국어 요약, 필수 지원 조건, 추천 대상, 키워드 추출
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""
다음 채용 공고를 분석해주세요.

회사: {job['company']}
직무: {job['title']}
위치: {job['location']}
공고 내용:
{job['description']}

아래 형식으로 JSON만 반환해주세요. 다른 텍스트는 절대 포함하지 마세요:

{{
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
  "summary": "공고 요약 (3-5문장, 한국어)",
  "requirements": ["필수 조건1", "필수 조건2", "필수 조건3"],
  "recommended_for": ["추천 대상1", "추천 대상2", "추천 대상3"]
}}

규칙:
- keywords: 5~10개 영어 핵심 기술스택/직무 키워드
- summary: 이 회사가 어떤 사람을 찾는지 핵심만 한국어로
- requirements: 필수 지원 조건 3~5개, 한국어
- recommended_for: 이런 사람에게 추천 3~5개, 한국어
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    import json
    response_text = message.content[0].text.strip()
    # JSON 펜스 제거
    response_text = re.sub(r'```json|```', '', response_text).strip()
    return json.loads(response_text)


def generate_filename(company: str, title: str) -> str:
    """
    Jekyll 포스트 파일명 생성
    예: 2026-06-12-anthropic-analytics-data-engineer.md
    """
    today = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r'[^a-z0-9]+', '-', (company + "-" + title).lower()).strip('-')
    slug = slug[:60]  # 너무 길면 자르기
    return f"{today}-{slug}.md"


def check_duplicate_post(company: str, title: str) -> bool:
    """
    블로그에 같은 회사+직무 포스트가 이미 있는지 확인
    """
    if not POSTS_PATH.exists():
        return False

    keyword = re.sub(r'[^a-z0-9]+', '-', (company + "-" + title).lower()).strip('-')[:40]
    for f in POSTS_PATH.iterdir():
        if keyword in f.name:
            return True
    return False


def create_post(job: dict, analysis: dict) -> str:
    """
    마크다운 포스트 파일 생성
    analyze.js와 동일한 형식 유지
    """
    today = datetime.now().strftime("%Y-%m-%d")
    filename = generate_filename(job["company"], job["title"])
    filepath = POSTS_PATH / filename

    # 키워드 태그 형식
    keywords_str = " ".join([f"`{kw}`" for kw in analysis["keywords"]])

    # 필수 조건 목록
    requirements_str = "\n".join([f"- {r}" for r in analysis["requirements"]])

    # 추천 대상 목록
    recommended_str = "\n".join([f"- {r}" for r in analysis["recommended_for"]])

    content = f"""---
layout: post
title: "{job['company']} - {job['title']}"
date: {today}
company: "{job['company']}"
role: "{job['title']}"
location: "{job['location']}"
source: "{job['source']}"
link: "{job['url']}"
---

## 원문

{job['description']}

---

## 핵심 키워드

{keywords_str}

---

## 공고 요약

{analysis['summary']}

---

## 필수 지원 조건

{requirements_str}

---

## 추천 대상

{recommended_str}
"""

    filepath.write_text(content, encoding="utf-8")
    print(f"✅ 포스트 생성: {filename}")
    return str(filepath)


def run_analyzer(jobs: list) -> list:
    """
    미분석 공고 목록을 받아서
    - Claude 분석
    - 마크다운 파일 생성
    - 성공한 job id 목록 반환
    """
    analyzed_ids = []

    for job in jobs:
        try:
            print(f"\n🤖 분석 중: [{job['company']}] {job['title']}")

            # 블로그 중복 확인
            if check_duplicate_post(job["company"], job["title"]):
                print(f"  ⏭️  이미 블로그에 있음, 스킵")
                analyzed_ids.append(job["id"])
                continue

            # description이 너무 짧으면 스킵
            if len(job.get("description", "")) < 50:
                print(f"  ⚠️  공고 내용이 너무 짧음, 스킵")
                continue

            # Claude 분석
            analysis = analyze_job(job)

            # 마크다운 파일 생성
            create_post(job, analysis)
            analyzed_ids.append(job["id"])

        except Exception as e:
            print(f"  ❌ 오류: {e}")
            continue

    print(f"\n✅ 총 {len(analyzed_ids)}개 공고 분석 완료")
    return analyzed_ids
