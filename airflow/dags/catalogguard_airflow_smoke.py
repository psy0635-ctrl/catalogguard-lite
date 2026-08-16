"""A no-side-effect DAG proving that the isolated Airflow foundation can parse tasks."""

from __future__ import annotations

from datetime import datetime, timezone

from airflow.sdk import DAG, task


with DAG(
    dag_id="catalogguard_airflow_smoke",
    description="Validates the isolated CatalogGuard Airflow runtime without running ETL.",
    start_date=datetime(2026, 8, 15, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    tags=["catalogguard", "foundation", "smoke"],
) as dag:

    @task
    def start() -> str:
        return "catalogguard-airflow-foundation"

    @task
    def airflow_environment_check() -> dict[str, str]:
        return {
            "dag": "catalogguard_airflow_smoke",
            "purpose": "safe_import_and_structure_check",
        }

    start() >> airflow_environment_check()
