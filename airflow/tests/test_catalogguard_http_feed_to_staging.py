from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


try:
    import airflow.sdk  # noqa: F401
except ModuleNotFoundError:
    raise unittest.SkipTest("Airflow DAG tests run in the isolated Airflow image")


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DAG_PATH = PROJECT_ROOT / "airflow" / "dags" / "catalogguard_http_feed_to_staging.py"


def _load_dag_module():
    spec = importlib.util.spec_from_file_location(
        "catalogguard_http_feed_to_staging",
        DAG_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("HTTP feed DAG module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CatalogGuardHTTPFeedDagTest(unittest.TestCase):
    def test_dag_has_the_single_manual_ingest_task(self) -> None:
        """A split download/transform/load flow would lose the TemporaryDirectory artifact boundary."""
        module = _load_dag_module()

        self.assertEqual(module.dag.dag_id, "catalogguard_http_feed_to_staging")
        self.assertIsNone(module.dag.schedule)
        self.assertFalse(module.dag.catchup)
        self.assertEqual(module.dag.max_active_runs, 1)
        self.assertEqual(module.dag.max_active_tasks, 1)
        self.assertEqual(set(module.dag.task_ids), {"ingest_configured_http_feed_to_staging"})

    def test_transient_source_failure_becomes_a_safe_retryable_airflow_error(self) -> None:
        """A retry must retain only the safe code, never a configured URL or its cause."""
        from airflow.exceptions import AirflowException
        from etl.http_source import HTTPFeedTransientError

        module = _load_dag_module()
        with patch(
            "etl.http_source.read_http_feed_csv",
            side_effect=HTTPFeedTransientError(
                "https://supplier.example/feed.csv?token=do-not-expose"
            ),
        ):
            with self.assertRaises(AirflowException) as error:
                module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")

        self.assertEqual(error.exception.__cause__, None)
        self.assertIn("http_feed_network_retryable", str(error.exception))
        self.assertNotIn("supplier.example", str(error.exception))

    def test_invalid_profile_becomes_a_safe_non_retryable_airflow_error(self) -> None:
        """An allowlist failure must fail once instead of spending retry attempts."""
        from airflow.exceptions import AirflowFailException
        from etl.http_source import HTTPFeedSourceObject

        module = _load_dag_module()
        with patch(
            "etl.http_source.read_http_feed_csv",
            return_value=HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
        ):
            with self.assertRaises(AirflowFailException) as error:
                module.run_configured_http_feed_to_staging("not-an-allowlisted-profile")

        self.assertEqual(error.exception.__cause__, None)
        self.assertIn("etl_profile_invalid", str(error.exception))

    def test_invalid_feed_csv_becomes_a_safe_non_retryable_airflow_error(self) -> None:
        """Input validation must fail once rather than turn a permanent CSV defect into retries."""
        from airflow.exceptions import AirflowFailException
        from etl.http_source import HTTPFeedSourceObject

        module = _load_dag_module()
        with patch(
            "etl.http_source.read_http_feed_csv",
            return_value=HTTPFeedSourceObject("supplier_feed.csv", b""),
        ):
            with self.assertRaises(AirflowFailException) as error:
                module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")

        self.assertEqual(error.exception.__cause__, None)
        self.assertIn("http_feed_csv_invalid", str(error.exception))

    @unittest.skipUnless(
        os.environ.get("DATABASE_URL")
        and os.environ.get("CATALOGGUARD_ETL_HTTP_FEED_URL"),
        "CatalogGuard DB and deterministic HTTP feed are required",
    )
    def test_task_reads_the_configured_feed_and_deduplicates_a_committed_batch(
        self,
    ) -> None:
        """A post-commit retry must reuse the committed batch without duplicate rows."""
        from sqlalchemy import delete, select

        from db.models import CatalogProductStaging, ETLLoadRun, ETLRejectedRow
        from db.session import get_session_factory

        module = _load_dag_module()
        first = module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")
        second = module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")

        self.assertTrue(first["created"])
        self.assertEqual(set(first), {"etl_load_run_id", "created"})
        self.assertNotIn("supplier.example", repr(first))
        self.assertFalse(second["created"])
        self.assertEqual(second["etl_load_run_id"], first["etl_load_run_id"])
        try:
            with get_session_factory()() as session:
                load_run = session.get(ETLLoadRun, first["etl_load_run_id"])
                self.assertEqual(load_run.initial_source_type, "http_feed")
                self.assertEqual(load_run.initial_source_ref, "configured_http_feed")
                self.assertIsNone(load_run.actor_user_id)
                self.assertIsNone(load_run.actor_username)
                matching_load_runs = session.scalars(
                    select(ETLLoadRun).where(
                        ETLLoadRun.input_file_sha256 == load_run.input_file_sha256,
                        ETLLoadRun.profile_name == load_run.profile_name,
                        ETLLoadRun.profile_version == load_run.profile_version,
                    )
                ).all()
                self.assertEqual(len(matching_load_runs), 1)
                rows = session.scalars(
                    select(CatalogProductStaging).where(
                        CatalogProductStaging.etl_load_run_id == first["etl_load_run_id"]
                    )
                ).all()
                self.assertEqual(len(rows), 1)
                rejected_rows = session.scalars(
                    select(ETLRejectedRow).where(
                        ETLRejectedRow.etl_load_run_id == first["etl_load_run_id"]
                    )
                ).all()
                self.assertEqual(len(rejected_rows), 0)
        finally:
            with get_session_factory()() as cleanup:
                cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id == first["etl_load_run_id"]))
                cleanup.commit()
