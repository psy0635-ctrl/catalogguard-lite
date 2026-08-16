from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DAG_PATH = PROJECT_ROOT / "airflow" / "dags" / "catalogguard_airflow_smoke.py"


def _load_smoke_dag():
    spec = importlib.util.spec_from_file_location("catalogguard_airflow_smoke", DAG_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Smoke DAG module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.dag


class CatalogGuardAirflowSmokeDagTest(unittest.TestCase):
    def test_smoke_dag_exposes_the_expected_safe_task_flow(self) -> None:
        """Catches a missing DAG or an accidental ETL task/dependency in the foundation DAG."""
        dag = _load_smoke_dag()

        self.assertEqual(dag.dag_id, "catalogguard_airflow_smoke")
        self.assertEqual(set(dag.task_ids), {"start", "airflow_environment_check"})
        self.assertEqual(dag.get_task("start").downstream_task_ids, {"airflow_environment_check"})
        self.assertEqual(dag.get_task("airflow_environment_check").downstream_task_ids, set())
