from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from config.settings import INSPECTION_VERSION
from core.inspection_service import inspect_dataframe
from core.upload_validator import (
    CsvUploadValidationError,
    validate_and_read_uploaded_csv,
)
from db.persistence_service import (
    find_existing_inspection_run,
    get_inspection_detail,
    save_inspection_report,
)
from db.session import get_session_factory
from services.job_files import is_safe_job_file_path
from services.redis_job_store import InspectionJobState, get_redis_job_store
from workers.celery_app import celery_app


worker_logger = logging.getLogger("catalogguard.inspection_worker")
INVALID_CSV_MESSAGE = "CSV 파일을 처리할 수 없습니다."
INSPECTION_FAILURE_MESSAGE = "검수 작업을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."


def _summary_from_report(report) -> dict[str, int]:
    return {
        "total_products": report.summary.total_products,
        "total_issues": report.summary.total_issues,
        "error_count": report.summary.error_count,
        "warning_count": report.summary.warning_count,
    }


def _summary_from_detail(detail) -> dict[str, int]:
    return {
        "total_products": detail.total_products,
        "total_issues": detail.total_issues,
        "error_count": detail.error_count,
        "warning_count": detail.warning_count,
    }


def _update_failed_job(store, job_id: str, error_code: str, message: str) -> None:
    try:
        store.update_job(
            job_id,
            status="failed",
            error_code=error_code,
            safe_error_message=message,
        )
    except Exception:
        worker_logger.exception(
            "failed to persist inspection job failure",
            extra={"job_id": job_id, "error_code": error_code},
        )


@celery_app.task(
    bind=False,
    name="catalogguard.inspect_csv",
    ignore_result=True,
)
def inspect_csv_task(job_id: str, job_file_path: str) -> None:
    store = get_redis_job_store()
    session = None
    try:
        state: InspectionJobState | None = store.get_job(job_id)
        if state is None:
            worker_logger.warning("inspection job disappeared before execution", extra={"job_id": job_id})
            return

        store.update_job(job_id, status="running")
        if not is_safe_job_file_path(job_id, job_file_path):
            raise ValueError("inspection job file path is outside the configured job directory")

        file_path = Path(job_file_path)
        file_bytes = file_path.read_bytes()
        dataframe = validate_and_read_uploaded_csv(
            state.source_filename or file_path.name,
            file_bytes,
        )
        file_sha256 = hashlib.sha256(file_bytes).hexdigest()
        session = get_session_factory()()
        existing_run = find_existing_inspection_run(
            session,
            file_sha256=file_sha256,
            inspection_version=INSPECTION_VERSION,
        )

        if existing_run is not None:
            detail = get_inspection_detail(
                session,
                inspection_run_id=existing_run.id,
            )
            if detail is None:
                raise RuntimeError("existing inspection detail was not found")
            store.update_job(
                job_id,
                status="succeeded",
                created=False,
                inspection_run_id=detail.inspection_run_id,
                summary=_summary_from_detail(detail),
            )
            return

        # SQLAlchemy starts an implicit read transaction for the identity lookup.
        # The persistence service owns its own transaction, so close the read
        # transaction before calling save_inspection_report().
        session.rollback()
        report = inspect_dataframe(dataframe)
        save_outcome = save_inspection_report(
            session,
            source_filename=state.source_filename or file_path.name,
            report=report,
            file_sha256=file_sha256,
            inspection_version=INSPECTION_VERSION,
        )
        if save_outcome.created:
            inspection_run_id = save_outcome.inspection_run_id
            summary = _summary_from_report(report)
        else:
            detail = get_inspection_detail(
                session,
                inspection_run_id=save_outcome.inspection_run_id,
            )
            if detail is None:
                raise RuntimeError("existing inspection detail was not found")
            inspection_run_id = detail.inspection_run_id
            summary = _summary_from_detail(detail)

        store.update_job(
            job_id,
            status="succeeded",
            created=save_outcome.created,
            inspection_run_id=inspection_run_id,
            summary=summary,
        )
    except CsvUploadValidationError:
        _update_failed_job(store, job_id, "invalid_csv", INVALID_CSV_MESSAGE)
    except SQLAlchemyError:
        if session is not None:
            session.rollback()
        worker_logger.exception("database error while inspecting CSV", extra={"job_id": job_id})
        _update_failed_job(store, job_id, "database_error", INSPECTION_FAILURE_MESSAGE)
    except Exception:
        if session is not None:
            session.rollback()
        worker_logger.exception("unexpected error while inspecting CSV", extra={"job_id": job_id})
        _update_failed_job(store, job_id, "inspection_failed", INSPECTION_FAILURE_MESSAGE)
    finally:
        if session is not None:
            session.close()
        try:
            if is_safe_job_file_path(job_id, job_file_path):
                Path(job_file_path).unlink(missing_ok=True)
        except (OSError, TypeError, ValueError):
            worker_logger.exception(
                "failed to remove inspection job file",
                extra={"job_id": job_id},
            )
