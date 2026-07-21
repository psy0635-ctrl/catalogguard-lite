from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
from uuid import uuid4

from config.settings import MAX_UPLOAD_SIZE_BYTES
from db.persistence_service import normalize_source_filename
from services.job_files import delete_job_file, write_job_file
from services.redis_job_store import InspectionJobState, RedisJobStore, get_redis_job_store


job_logger = logging.getLogger("catalogguard.inspection_jobs")


class InspectionJobUploadError(ValueError):
    """Raised when an asynchronous upload fails lightweight API validation."""


class InspectionJobEnqueueError(RuntimeError):
    """Raised when the job cannot be handed to Celery."""


@dataclass(frozen=True)
class InspectionJobSubmission:
    job_id: str
    status: str
    status_url: str


def validate_async_upload(filename: str | None, file_bytes: bytes) -> None:
    if not filename or not filename.replace("\\", "/").rsplit("/", 1)[-1].strip():
        raise InspectionJobUploadError("CSV 파일명이 필요합니다.")
    if not filename.casefold().endswith(".csv"):
        raise InspectionJobUploadError("CSV 파일만 업로드할 수 있습니다.")
    if not file_bytes:
        raise InspectionJobUploadError("업로드한 파일이 비어 있습니다.")
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise InspectionJobUploadError("파일 크기 제한을 초과했습니다.")


def enqueue_inspection_task(job_id: str, job_file_path: str) -> None:
    from workers.inspection_tasks import inspect_csv_task

    inspect_csv_task.delay(job_id, job_file_path)


class InspectionJobService:
    def __init__(
        self,
        *,
        job_store: RedisJobStore,
        enqueue=enqueue_inspection_task,
        write_file=write_job_file,
        delete_file=delete_job_file,
        now=datetime.now,
    ) -> None:
        self._job_store = job_store
        self._enqueue = enqueue
        self._write_file = write_file
        self._delete_file = delete_file
        self._now = now

    def submit(
        self,
        *,
        filename: str | None,
        file_bytes: bytes,
    ) -> InspectionJobSubmission:
        validate_async_upload(filename, file_bytes)
        job_id = str(uuid4())
        source_filename = normalize_source_filename(filename)
        job_file_path: Path | None = None

        try:
            job_file_path = self._write_file(job_id, file_bytes)
            timestamp = self._now(timezone.utc)
            self._job_store.create_queued_job(
                job_id,
                source_filename=source_filename,
                created_at=timestamp,
            )
            self._enqueue(job_id, str(job_file_path))
        except Exception as error:
            if job_file_path is not None:
                self._delete_file(job_id, job_file_path)
            try:
                self._job_store.delete_job(job_id)
            except Exception:
                job_logger.exception(
                    "failed to clean up inspection job",
                    extra={"job_id": job_id},
                )
            raise InspectionJobEnqueueError(
                "검수 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요."
            ) from error

        return InspectionJobSubmission(
            job_id=job_id,
            status="queued",
            status_url=f"/api/v1/inspection-jobs/{job_id}",
        )

    def get(self, job_id: str) -> InspectionJobState | None:
        return self._job_store.get_job(job_id)


_default_service: InspectionJobService | None = None


def get_inspection_job_service() -> InspectionJobService:
    global _default_service
    if _default_service is None:
        _default_service = InspectionJobService(job_store=get_redis_job_store())
    return _default_service
