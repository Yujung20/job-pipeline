from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import subprocess
import sys
import os
import git as gitlib

sys.path.insert(0, '/opt/airflow/scripts')

from collectors import collect_all_jobs
from db import init_db, save_job, get_unanalyzed_jobs, mark_as_analyzed
from analyzer import run_analyzer

# ── DAG 기본 설정 ───────────────────────────────────────────────
default_args = {
    "owner": "airflow",
    "retries": 2,                        # 실패시 2번 재시도
    "retry_delay": timedelta(minutes=10), # 5분 후 재시도
}

with DAG(
    dag_id="job_pipeline",               # Airflow UI에서 보이는 이름
    default_args=default_args,
    description="채용 공고 자동 수집 → 분석 → 블로그 배포",
    schedule_interval="0 0 * * *",       # 매일 10시 (한국시간 기준 설정 필요)
    start_date=datetime(2026, 6, 15),
    catchup=False,                       # 과거 날짜 소급 실행 안 함
    tags=["jobs", "pipeline"],
) as dag:

    # ── Task 1: DB 초기화 ────────────────────────────────────────
    def task_init_db():
        init_db()

    t1 = PythonOperator(
        task_id="init_db",
        python_callable=task_init_db,
    )

    # ── Task 2: 공고 수집 ────────────────────────────────────────
    def task_collect_jobs(**context):
        jobs = collect_all_jobs()

        # 새 공고만 DB에 저장
        new_count = 0
        for job in jobs:
            if save_job(job):
                new_count += 1

        print(f"✅ 새로운 공고 {new_count}개 저장 완료")

        # 다음 Task에 새 공고 수 전달
        context["ti"].xcom_push(key="new_count", value=new_count)

    t2 = PythonOperator(
        task_id="collect_jobs",
        python_callable=task_collect_jobs,
        provide_context=True,
        execution_timeout=timedelta(minutes=60),
    )

    # ── Task 3: Claude 분석 ──────────────────────────────────────
    def task_analyze_jobs(**context):
        new_count = context["ti"].xcom_pull(key="new_count", task_ids="collect_jobs")

        if new_count == 0:
            print("새로운 공고 없음, 분석 스킵")
            return

        # 미분석 공고 가져와서 분석
        jobs = get_unanalyzed_jobs()
        analyzed_ids = run_analyzer(jobs)

        # 분석 완료 표시
        for job_id in analyzed_ids:
            mark_as_analyzed(job_id)

        print(f"✅ {len(analyzed_ids)}개 공고 분석 완료")

    t3 = PythonOperator(
        task_id="analyze_jobs",
        python_callable=task_analyze_jobs,
        provide_context=True,
        execution_timeout=timedelta(minutes=90),
    )

    # ── Task 4: git push ─────────────────────────────────────────
    def task_git_push():

        pat = os.environ.get("GITHUB_PAT")

        blog_path = "/opt/airflow/blog"
        remote_url = f"https://{pat}@github.com/yujung20/yujung20.github.io.git"

        # 원격 최신 정보 받아오기 (비교 정확도를 위해 먼저 실행)
        subprocess.run(["git", "fetch", remote_url, "main"], cwd=blog_path, check=True)

        # 1) 커밋 안 된 변경사항이 있는지 확인
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=blog_path, capture_output=True, text=True
        )
        has_uncommitted = bool(status.stdout.strip())

        # 2) 커밋은 됐지만 원격에 안 올라간(push 안 된) 것이 있는지 확인
        unpushed = subprocess.run(
            ["git", "log", "FETCH_HEAD..HEAD", "--oneline"],
            cwd=blog_path, capture_output=True, text=True
        )
        has_unpushed = bool(unpushed.stdout.strip())

        if not has_uncommitted and not has_unpushed:
            print("ℹ️ 변경사항 없음, push 생략")
            return

        if has_unpushed:
            print(f"ℹ️ 이전에 커밋되었지만 push 안 된 커밋 발견:\n{unpushed.stdout}")

        try:
            if has_uncommitted:
                subprocess.run(["git", "add", "."], cwd=blog_path, check=True)
                subprocess.run(
                    ["git", "commit", "-m", f"자동 업데이트: {datetime.now().strftime('%Y-%m-%d')}"],
                    cwd=blog_path, check=True
                )
            subprocess.run(
                ["git", "push", remote_url, "main"],
                cwd=blog_path, check=True
            )
            print("✅ git push 완료")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ git push 오류: {e}")
            raise
        

    t4 = PythonOperator(
        task_id="git_push",
        python_callable=task_git_push,
    )

    # ── 실행 순서 정의 ───────────────────────────────────────────
    # t1 → t2 → t3 → t4
    t1 >> t2 >> t3 >> t4
