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

    def test_inactive_profile_becomes_its_own_non_retryable_airflow_error(self) -> None:
        """A profile an operator deliberately took down must not look like a system fault."""
        from airflow.exceptions import AirflowFailException
        from etl.http_source import HTTPFeedSourceObject
        from etl.profile_loader import ETLProfileInactiveError

        module = _load_dag_module()
        with patch(
            "etl.http_source.read_http_feed_csv",
            return_value=HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
        ), patch(
            "etl.web_service.run_web_etl",
            side_effect=ETLProfileInactiveError(
                "ETL profile is inactive: sample_fashion_vendor_v1"
            ),
        ):
            with self.assertRaises(AirflowFailException) as error:
                module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")

        message = str(error.exception)
        self.assertEqual(error.exception.__cause__, None)
        self.assertIn("etl_profile_inactive", message)
        # 이 세 가지로 잘못 분류되면 운영자가 할 일이 완전히 달라진다.
        self.assertNotIn("catalogguard_etl_unexpected", message)
        self.assertNotIn("etl_profile_invalid", message)
        self.assertNotIn("etl_input_invalid", message)
        # AirflowFailException은 AirflowException의 subclass라 타입만으로는
        # non-retryable을 증명하지 못한다. 재시도되지 않는 쪽임을 명시적으로 본다.
        from airflow.exceptions import AirflowException

        self.assertIsInstance(error.exception, AirflowException)
        self.assertIsInstance(error.exception, AirflowFailException)

    def test_inactive_profile_does_not_leak_the_profile_or_feed_details(self) -> None:
        """Only the safe code may reach Airflow, exactly as the other branches do."""
        from airflow.exceptions import AirflowFailException
        from etl.http_source import HTTPFeedSourceObject
        from etl.profile_loader import ETLProfileInactiveError

        module = _load_dag_module()
        with patch(
            "etl.http_source.read_http_feed_csv",
            return_value=HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
        ), patch(
            "etl.web_service.run_web_etl",
            side_effect=ETLProfileInactiveError(
                "ETL profile is inactive: sample_fashion_vendor_v1"
            ),
        ):
            with self.assertRaises(AirflowFailException) as error:
                module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")

        message = str(error.exception)
        self.assertEqual(
            message,
            "CatalogGuard HTTP feed ingestion failed [etl_profile_inactive]",
        )
        self.assertNotIn("sample_fashion_vendor_v1", message)
        self.assertNotIn("supplier_feed.csv", message)

    def test_inactive_and_invalid_profiles_get_different_failure_codes(self) -> None:
        """Fixing a misconfigured profile and re-enabling a disabled one are different jobs."""
        from airflow.exceptions import AirflowFailException
        from etl.http_source import HTTPFeedSourceObject
        from etl.profile_loader import ETLProfileInactiveError

        module = _load_dag_module()
        feed = HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n")

        with patch("etl.http_source.read_http_feed_csv", return_value=feed), patch(
            "etl.web_service.run_web_etl",
            side_effect=ETLProfileInactiveError("inactive"),
        ):
            with self.assertRaises(AirflowFailException) as inactive_error:
                module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")

        with patch("etl.http_source.read_http_feed_csv", return_value=feed):
            with self.assertRaises(AirflowFailException) as unknown_error:
                module.run_configured_http_feed_to_staging("not-an-allowlisted-profile")

        self.assertIn("etl_profile_inactive", str(inactive_error.exception))
        self.assertIn("etl_profile_invalid", str(unknown_error.exception))
        self.assertNotEqual(
            str(inactive_error.exception),
            str(unknown_error.exception),
        )

    def test_transient_database_failure_stays_retryable(self) -> None:
        """The inactive branch must not have changed the transient DB retry contract."""
        from airflow.exceptions import AirflowException, AirflowFailException
        from sqlalchemy.exc import OperationalError

        from etl.http_source import HTTPFeedSourceObject

        class _SerializationFailure(Exception):
            sqlstate = "40001"

        module = _load_dag_module()
        with patch(
            "etl.http_source.read_http_feed_csv",
            return_value=HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
        ), patch(
            "etl.web_service.run_web_etl",
            side_effect=OperationalError("SELECT 1", {}, _SerializationFailure()),
        ):
            with self.assertRaises(AirflowException) as error:
                module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")

        self.assertNotIsInstance(error.exception, AirflowFailException)
        self.assertIn("catalogguard_db_transient", str(error.exception))

    def test_unexpected_failure_still_uses_the_generic_code(self) -> None:
        """Narrowing the generic branch must not empty it: real surprises still land there."""
        from airflow.exceptions import AirflowFailException
        from etl.http_source import HTTPFeedSourceObject

        module = _load_dag_module()
        with patch(
            "etl.http_source.read_http_feed_csv",
            return_value=HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
        ), patch(
            "etl.web_service.run_web_etl",
            side_effect=RuntimeError("something nobody predicted"),
        ):
            with self.assertRaises(AirflowFailException) as error:
                module.run_configured_http_feed_to_staging("sample_fashion_vendor_v1")

        message = str(error.exception)
        self.assertEqual(error.exception.__cause__, None)
        self.assertIn("catalogguard_etl_unexpected", message)
        self.assertNotIn("something nobody predicted", message)

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

    @unittest.skipUnless(
        os.environ.get("DATABASE_URL"),
        "CatalogGuard DB is required to persist a runtime activation override",
    )
    def test_a_real_runtime_deactivation_reaches_airflow_as_the_inactive_code(
        self,
    ) -> None:
        """The Phase 5B.1 row, not a patched exception, must produce the new code end to end."""
        from airflow.exceptions import AirflowFailException
        from sqlalchemy import delete

        from db.etl_profile_activation_service import set_etl_profile_activation
        from db.models import ETLProfileActivation
        from db.session import get_session_factory
        from etl.http_source import HTTPFeedSourceObject

        module = _load_dag_module()
        profile_id = "sample_fashion_vendor_v1"
        session_factory = get_session_factory()

        try:
            with session_factory() as session:
                # active_version=None이 Policy G의 Deactivate다. override 제거가 아니다.
                view = set_etl_profile_activation(
                    session,
                    profile_id=profile_id,
                    active_version=None,
                    actor_user_id=None,
                    actor_username=None,
                )
                self.assertTrue(view.runtime_override_exists)
                self.assertFalse(view.is_active)

            with patch(
                "etl.http_source.read_http_feed_csv",
                return_value=HTTPFeedSourceObject(
                    "supplier_feed.csv", b"supplier,csv\n"
                ),
            ):
                with self.assertRaises(AirflowFailException) as error:
                    module.run_configured_http_feed_to_staging(profile_id)

            message = str(error.exception)
            self.assertIn("etl_profile_inactive", message)
            self.assertNotIn("catalogguard_etl_unexpected", message)
        finally:
            # reset API가 없으므로 테스트가 만든 row는 직접 지운다. 남겨 두면 이후
            # 테스트와 로컬 환경에서 이 프로필이 계속 비활성으로 보인다.
            with session_factory() as cleanup:
                cleanup.execute(
                    delete(ETLProfileActivation).where(
                        ETLProfileActivation.profile_id == profile_id
                    )
                )
                cleanup.commit()
