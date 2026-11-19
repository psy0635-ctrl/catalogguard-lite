import logging
from uuid import UUID

from sqlalchemy.orm import Session

from core.upload_validator import CsvUploadValidationError
from db.models import ETLJob
from db.session import get_session_factory
from etl.db_loader import ETLLoadError
from etl.pipeline import ETLPipelineError
from etl.profile_loader import ETLProfileInactiveError, ETLProfileNotFoundError
from etl.web_service import run_web_etl
from services.etl_job_service import (
    TERMINAL_STATUSES,
    cleanup_etl_job_file,
    etl_job_file,
    lock_etl_submission,
    set_etl_job_status,
)
from workers.celery_app import celery_app


logger = logging.getLogger("catalogguard.etl_worker")


def _claim_job(factory, job_id: UUID) -> str | None:
    with factory.begin() as session:
        lock_etl_submission(session, job_id)
        job = session.get(ETLJob, job_id, with_for_update=True)
        if job is None:
            return None
        if job.status == "queued":
            set_etl_job_status(job, "running")
        return job.status


def _load_batch(session: Session, job: ETLJob):
    # Reuse the synchronous service without letting its internal commit or
    # rollback escape the transaction that owns this job's row lock.
    with session.begin_nested():
        with Session(
            bind=session.connection(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as etl_session:
            return run_web_etl(
                etl_session,
                profile_id=job.profile_id,
                source_filename=job.source_filename,
                input_bytes=etl_job_file(job.job_id).read_bytes(),
                actor_user_id=job.actor_user_id,
                actor_username=job.actor_username,
                initial_source_type="upload",
                initial_source_ref=job.source_filename,
            )


def _execute_job(factory, job_id: UUID) -> None:
    with factory.begin() as session:
        job = session.get(ETLJob, job_id, with_for_update=True)
        if job is None or job.status in TERMINAL_STATUSES:
            return
        try:
            outcome = _load_batch(session, job)
        except ETLProfileNotFoundError:
            job.error_code = "unsupported_profile"
        except ETLProfileInactiveError:
            job.error_code = "inactive_profile"
        except (CsvUploadValidationError, ETLPipelineError):
            job.error_code = "invalid_upload"
        except FileNotFoundError:
            job.error_code = "missing_input"
        except ETLLoadError:
            job.error_code = "etl_failed"
        else:
            job.etl_load_run_id = outcome.etl_load_run_id
            job.created = outcome.created
        set_etl_job_status(job, "failed" if job.error_code else "succeeded")


def _fail_exhausted_job(factory, job_id: UUID) -> None:
    with factory.begin() as session:
        job = session.get(ETLJob, job_id, with_for_update=True)
        if job is not None and job.status not in TERMINAL_STATUSES:
            job.error_code = "etl_failed"
            set_etl_job_status(job, "failed")


@celery_app.task(
    bind=True,
    name="catalogguard.run_web_etl",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    ignore_result=True,
)
def run_web_etl_job(self, job_id: str) -> None:
    job_uuid = UUID(job_id)
    factory = get_session_factory()
    try:
        state = _claim_job(factory, job_uuid)
        # An orphan delivery can follow a rolled-back admission. The admission
        # lock makes it safe to clean the input in that case as well.
        if state is not None and state not in TERMINAL_STATUSES:
            _execute_job(factory, job_uuid)
    except Exception as error:
        # Never log parser, DB or broker exception text with uploaded data.
        logger.warning(
            "ETL job execution interrupted",
            extra={"job_id": job_id, "error_type": type(error).__name__},
        )
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=2 ** self.request.retries) from None
        _fail_exhausted_job(factory, job_uuid)
    cleanup_etl_job_file(job_uuid)
