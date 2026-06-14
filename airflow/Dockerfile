FROM apache/airflow:2.9.1

USER root
RUN apt-get update && apt-get install -y git

USER airflow
RUN pip install --no-cache-dir anthropic psycopg2-binary requests gitpython