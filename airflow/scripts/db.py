import psycopg2
import os
from datetime import datetime

# ── DB 연결 설정 ───────────────────────────────────────────────
DB_CONFIG = {
    "host": "postgres",      # docker-compose.yml의 서비스 이름
    "port": 5432,
    "dbname": "airflow",     # 기존 Airflow DB에 같이 저장
    "user": "airflow",
    "password": "airflow"
}


def get_connection():
    """DB 연결 반환"""
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    """
    job_postings 테이블 생성
    - 이미 있으면 스킵 (IF NOT EXISTS)
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_postings (
            id           SERIAL PRIMARY KEY,
            company      TEXT NOT NULL,
            title        TEXT NOT NULL,
            url          TEXT UNIQUE,          -- URL 기준 중복 방지
            location     TEXT,
            source       TEXT,                 -- greenhouse / lever / ashby
            description  TEXT,
            collected_at TIMESTAMP DEFAULT NOW(),
            analyzed     BOOLEAN DEFAULT FALSE,
            posted_at    TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ job_postings 테이블 준비 완료")
    init_pipeline_runs_table()


def is_duplicate(url: str) -> bool:
    """
    이미 DB에 있는 공고인지 URL로 확인
    - True: 중복 (스킵)
    - False: 새 공고 (저장)
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM job_postings WHERE url = %s", (url,))
    exists = cur.fetchone() is not None

    cur.close()
    conn.close()
    return exists


def save_job(job: dict) -> bool:
    """
    새 공고를 DB에 저장
    - 중복이면 저장 안 함
    - 저장 성공하면 True, 중복이면 False 반환
    """
    if is_duplicate(job["url"]):
        return False

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO job_postings (company, title, url, location, source, description)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        job["company"],
        job["title"],
        job["url"],
        job["location"],
        job["source"],
        job["description"]
    ))

    conn.commit()
    cur.close()
    conn.close()
    return True


def get_unanalyzed_jobs() -> list:
    """
    아직 Claude 분석이 안 된 공고 목록 반환
    (analyzed = FALSE 인 것들)
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, company, title, url, location, source, description
        FROM job_postings
        WHERE analyzed = FALSE
        ORDER BY collected_at DESC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "id": row[0],
            "company": row[1],
            "title": row[2],
            "url": row[3],
            "location": row[4],
            "source": row[5],
            "description": row[6]
        }
        for row in rows
    ]


def mark_as_analyzed(job_id: int, posted_at: datetime = None):
    """
    공고를 분석 완료로 표시
    블로그에 올린 시간도 같이 저장
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE job_postings
        SET analyzed = TRUE, posted_at = %s
        WHERE id = %s
    """, (posted_at or datetime.now(), job_id))

    conn.commit()
    cur.close()
    conn.close()

def init_pipeline_runs_table():
    """
    pipeline_runs 테이블 생성
    - 파이프라인 실행 로그 저장용
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id               SERIAL PRIMARY KEY,
            run_id           TEXT,
            source           TEXT,
            started_at       TIMESTAMP,
            finished_at      TIMESTAMP,
            duration_seconds FLOAT,
            companies_tried  INT DEFAULT 0,
            jobs_found       INT DEFAULT 0,
            jobs_saved       INT DEFAULT 0,
            jobs_skipped     INT DEFAULT 0,
            jobs_failed      INT DEFAULT 0,
            status           TEXT,
            error_message    TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ pipeline_runs 테이블 준비 완료")


def log_pipeline_run(run: dict):
    """
    파이프라인 실행 결과를 pipeline_runs 테이블에 저장
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO pipeline_runs (
            run_id, source, started_at, finished_at, duration_seconds,
            companies_tried, jobs_found, jobs_saved, jobs_skipped, jobs_failed,
            status, error_message
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        run.get("run_id"),
        run.get("source"),
        run.get("started_at"),
        run.get("finished_at"),
        run.get("duration_seconds"),
        run.get("companies_tried", 0),
        run.get("jobs_found", 0),
        run.get("jobs_saved", 0),
        run.get("jobs_skipped", 0),
        run.get("jobs_failed", 0),
        run.get("status"),
        run.get("error_message")
    ))

    conn.commit()
    cur.close()
    conn.close()