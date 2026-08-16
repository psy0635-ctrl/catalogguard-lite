ARG AIRFLOW_VERSION=3.3.0
FROM apache/airflow:${AIRFLOW_VERSION}-python3.11

ARG AIRFLOW_VERSION

# Keep Airflow/provider resolution on the official, version-matched constraints set.
RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.11.txt" \
    "apache-airflow[postgres]==${AIRFLOW_VERSION}"

# CatalogGuard's own ETL runtime dependencies intentionally install separately.
# Airflow documents this pattern for custom dependencies that are not pinned by
# its constraints; pinning Airflow here prevents an accidental upgrade/downgrade.
COPY airflow/requirements.txt /tmp/catalogguard-airflow-requirements.txt
RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    --requirement /tmp/catalogguard-airflow-requirements.txt

# These packages are available for a future orchestration DAG, but this foundation
# does not import or execute CatalogGuard business logic.
COPY config /opt/catalogguard/config
COPY core /opt/catalogguard/core
COPY db /opt/catalogguard/db
COPY etl /opt/catalogguard/etl
COPY airflow/dags /opt/airflow/dags
COPY airflow/tests /opt/airflow/tests

ENV PYTHONPATH=/opt/catalogguard

USER airflow
