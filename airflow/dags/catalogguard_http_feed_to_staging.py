"""Manual CatalogGuard HTTP feed ingestion using the existing ETL services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from airflow.exceptions import AirflowException, AirflowFailException
from airflow.sdk import DAG, task


def _is_transient_database_error(error: Exception) -> bool:
    """Return true only for PostgreSQL failures safe enough for a task retry."""
    if not getattr(error, "connection_invalidated", False):
        original_error = getattr(error, "orig", None)
        sqlstate = getattr(original_error, "sqlstate", None) or getattr(
            original_error, "pgcode", None
        )
        return sqlstate in {"40001", "40P01"}
    return True


def _safe_airflow_failure(code: str, *, retryable: bool) -> None:
    message = f"CatalogGuard HTTP feed ingestion failed [{code}]"
    if retryable:
        raise AirflowException(message) from None
    raise AirflowFailException(message) from None


def run_configured_http_feed_to_staging(profile_id: str) -> dict[str, int | bool]:
    """Fetch one configured feed and stage it through the existing Web ETL service."""
    # Imports stay inside task execution so the DAG processor does not require
    # CatalogGuard DB/feed settings merely to parse the DAG.
    from sqlalchemy.exc import OperationalError, SQLAlchemyError

    from config.settings import ETL_HTTP_FEED_SOURCE_REF
    from core.upload_validator import CsvUploadValidationError
    from db.session import get_session_factory
    from etl.db_loader import ETLLoadError
    from etl.http_source import (
        HTTPFeedNotConfiguredError,
        HTTPFeedPermanentError,
        HTTPFeedTransientError,
        read_http_feed_csv,
    )
    from etl.pipeline import ETLPipelineError
    from etl.profile_loader import ETLProfileNotFoundError
    from etl.web_service import run_web_etl

    try:
        source = read_http_feed_csv()
        with get_session_factory()() as session:
            outcome = run_web_etl(
                session,
                profile_id=profile_id,
                source_filename=source.source_filename,
                input_bytes=source.content,
                actor_user_id=None,
                actor_username=None,
                initial_source_type="http_feed",
                initial_source_ref=ETL_HTTP_FEED_SOURCE_REF,
            )
    except HTTPFeedTransientError as error:
        _safe_airflow_failure(error.error_code, retryable=True)
    except HTTPFeedPermanentError as error:
        _safe_airflow_failure(error.error_code, retryable=False)
    except HTTPFeedNotConfiguredError:
        _safe_airflow_failure("http_feed_not_configured", retryable=False)
    except CsvUploadValidationError:
        _safe_airflow_failure("http_feed_csv_invalid", retryable=False)
    except ETLProfileNotFoundError:
        _safe_airflow_failure("etl_profile_invalid", retryable=False)
    except (ETLPipelineError, ETLLoadError):
        _safe_airflow_failure("etl_input_invalid", retryable=False)
    except OperationalError as error:
        retryable = _is_transient_database_error(error)
        _safe_airflow_failure(
            "catalogguard_db_transient"
            if retryable
            else "catalogguard_db_non_retryable",
            retryable=retryable,
        )
    except SQLAlchemyError:
        _safe_airflow_failure("catalogguard_db_non_retryable", retryable=False)
    except Exception:
        _safe_airflow_failure("catalogguard_etl_unexpected", retryable=False)

    return {
        "etl_load_run_id": outcome.etl_load_run_id,
        "created": outcome.created,
    }


with DAG(
    dag_id="catalogguard_http_feed_to_staging",
    description="Manually stages a configured HTTP feed through CatalogGuard ETL.",
    start_date=datetime(2026, 8, 16, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    params={"profile_id": "sample_fashion_vendor_v1"},
    tags=["catalogguard", "http-feed", "staging"],
) as dag:

    @task(
        retries=2,
        retry_delay=timedelta(minutes=2),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=10),
        execution_timeout=timedelta(minutes=5),
    )
    def ingest_configured_http_feed_to_staging(
        profile_id: str,
    ) -> dict[str, int | bool]:
        return run_configured_http_feed_to_staging(profile_id)

    ingest_configured_http_feed_to_staging("{{ params.profile_id }}")
