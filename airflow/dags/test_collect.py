import sys
sys.path.insert(0, '/opt/airflow/scripts')
from collectors import fetch_greenhouse

company = 'databricks'

jobs = fetch_greenhouse(company)
print(f'총 {len(jobs)}개 수집')
for job in jobs[:3]:
    print(f'\n제목: {job["title"]}')
    print(f'설명 길이: {len(job["description"])}자')
    print(f'설명 미리보기: {job["description"][:100]}')