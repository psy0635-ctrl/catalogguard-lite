from pathlib import Path
import pytest

from services.inspection_job_service import (
    InspectionJobEnqueueError,
    InspectionJobService,
    InspectionJobUploadError,
)


class FakeJobStore:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.deleted: list[str] = []

    def create_queued_job(self, job_id, **kwargs):
        self.created.append({"job_id": job_id, **kwargs})

    def delete_job(self, job_id):
        self.deleted.append(job_id)


def test_invalid_async_upload_is_rejected_before_side_effects() -> None:
    store = FakeJobStore()
    writes: list[tuple[str, bytes]] = []
    enqueues: list[tuple[str, str]] = []
    service = InspectionJobService(
        job_store=store,
        write_file=lambda job_id, file_bytes: writes.append((job_id, file_bytes)),
        enqueue=lambda job_id, file_path: enqueues.append((job_id, file_path)),
    )

    with pytest.raises(InspectionJobUploadError, match="CSV 파일만"):
        service.submit(filename="products.txt", file_bytes=b"not csv")

    assert writes == []
    assert store.created == []
    assert enqueues == []


def test_submit_writes_server_named_file_and_enqueues_only_job_metadata() -> None:
    store = FakeJobStore()
    writes: list[tuple[str, bytes]] = []
    enqueues: list[tuple[str, str]] = []

    def write_file(job_id: str, file_bytes: bytes) -> Path:
        writes.append((job_id, file_bytes))
        return Path(f"C:/inspection-jobs/{job_id}.csv")

    service = InspectionJobService(
        job_store=store,
        write_file=write_file,
        enqueue=lambda job_id, file_path: enqueues.append((job_id, file_path)),
    )

    submission = service.submit(filename="C:\\uploads\\renamed.csv", file_bytes=b"csv")

    assert submission.status == "queued"
    assert len(writes) == 1
    job_id, file_bytes = writes[0]
    assert file_bytes == b"csv"
    assert job_id == submission.job_id
    assert store.created[0]["source_filename"] == "renamed.csv"
    assert enqueues == [
        (job_id, str(Path(f"C:/inspection-jobs/{job_id}.csv")))
    ]


def test_enqueue_failure_deletes_file_and_redis_job() -> None:
    store = FakeJobStore()
    deleted_files: list[tuple[str, Path]] = []
    service = InspectionJobService(
        job_store=store,
        write_file=lambda job_id, file_bytes: Path(f"C:/inspection-jobs/{job_id}.csv"),
        delete_file=lambda job_id, path: deleted_files.append((job_id, path)),
        enqueue=lambda job_id, file_path: (_ for _ in ()).throw(
            ConnectionError("broker unavailable")
        ),
    )

    with pytest.raises(InspectionJobEnqueueError, match="검수 작업을 시작하지 못했습니다"):
        service.submit(filename="products.csv", file_bytes=b"csv")

    assert len(store.created) == 1
    assert store.deleted == [store.created[0]["job_id"]]
    assert deleted_files == [
        (
            store.created[0]["job_id"],
            Path(f"C:/inspection-jobs/{store.created[0]['job_id']}.csv"),
        )
    ]
