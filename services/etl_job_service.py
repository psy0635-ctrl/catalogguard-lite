from datetime import datetime, timezone
import logging
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.orm import Session

from config.settings import get_inspection_job_dir
from core.upload_validator import validate_csv_filename, validate_csv_file_size
from db.etl_profile_activation_service import end_activation_read_transaction
from db.models import ETLJob
from etl.profile_loader import get_profile_path
from services.job_files import delete_job_file, get_job_file_path, write_job_file


logger = logging.getLogger("catalogguard.etl_jobs")
TERMINAL_STATUSES = {"succeeded", "failed"}
ERROR_MESSAGES = {
    "unsupported_profile": "지원하지 않는 공급사 프로필입니다.",
    "inactive_profile": "비활성화된 공급사 프로필입니다.",
    "invalid_upload": "CSV 파일을 처리할 수 없습니다.",
    "missing_input": "작업의 임시 CSV 파일을 찾을 수 없습니다.",
    "etl_failed": "ETL 작업을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.",
}


class ETLJobSubmissionError(RuntimeError):
    """The job could not be submitted."""


def etl_job_directory() -> Path:
    # The existing inspection input volume is shared by the API and Worker.
    return get_inspection_job_dir() / "etl"


def etl_job_file(job_id: UUID) -> Path:
    return get_job_file_path(job_id, directory=etl_job_directory())


def cleanup_etl_job_file(job_id: UUID) -> None:
    try:
        delete_job_file(job_id, directory=etl_job_directory())
    except OSError:
        logger.warning("ETL job input cleanup failed", extra={"job_id": str(job_id)})


def lock_etl_submission(session: Session, job_id: UUID) -> None:
    # The broker can deliver before the submission transaction commits. Waiting
    # here lets the worker distinguish a committed job from a rolled-back one.
    key = int.from_bytes(job_id.bytes[:8], byteorder="big", signed=True)
    session.execute(select(func.pg_advisory_xact_lock(cast(key, BigInteger))))


def enqueue_etl_job(job_id: UUID) -> None:
    from workers.etl_tasks import run_web_etl_job

    run_web_etl_job.apply_async(args=(str(job_id),), retry=False)


def submit_etl_job(
    session: Session,
    *,
    profile_id: str,
    source_filename: str,
    file_bytes: bytes,
    actor_user_id: int,
    actor_username: str,
) -> UUID:
    # Same allowlist and activation policy as synchronous Web ETL. The
    # auth dependency may already have opened a read transaction.
    get_profile_path(profile_id, session=session)
    validate_csv_filename(source_filename)
    validate_csv_file_size(file_bytes)
    end_activation_read_transaction(session)

    job_id = uuid4()
    published = False
    try:
        with session.begin():
            lock_etl_submission(session, job_id)
            session.add(ETLJob(
                job_id=job_id,
                status="queued",
                profile_id=profile_id,
                source_filename=source_filename,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
            ))
            session.flush()
            write_job_file(job_id, file_bytes, directory=etl_job_directory())
            enqueue_etl_job(job_id)
            published = True
    except Exception:
        if published:
            # A commit error can have an ambiguous outcome. Never remove input
            # until PostgreSQL confirms that admission did not commit.
            try:
                with session.begin():
                    lock_etl_submission(session, job_id)
                    if session.get(ETLJob, job_id) is not None:
                        return job_id
            except Exception:
                logger.warning("ETL job admission could not be confirmed", extra={"job_id": str(job_id)})
                raise ETLJobSubmissionError from None
        cleanup_etl_job_file(job_id)
        raise ETLJobSubmissionError from None
    return job_id


def set_etl_job_status(job: ETLJob, status: str) -> None:
    job.status = status
    job.updated_at = datetime.now(timezone.utc)
