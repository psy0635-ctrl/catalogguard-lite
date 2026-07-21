from pathlib import Path
from types import SimpleNamespace

from services.redis_job_store import InspectionJobState


class FakeJobStore:
    def __init__(self, state: InspectionJobState) -> None:
        self.state = state
        self.updates: list[dict] = []

    def get_job(self, job_id: str):
        return self.state if job_id == self.state.job_id else None

    def update_job(self, job_id: str, **fields):
        self.updates.append({"job_id": job_id, **fields})
        self.state = InspectionJobState(
            job_id=self.state.job_id,
            status=fields["status"],
            created_at=self.state.created_at,
            updated_at=fields.get("updated_at", self.state.updated_at),
            source_filename=self.state.source_filename,
            created=fields.get("created", self.state.created),
            inspection_run_id=fields.get(
                "inspection_run_id", self.state.inspection_run_id
            ),
            summary=fields.get("summary", self.state.summary),
            error_code=fields.get("error_code", self.state.error_code),
            safe_error_message=fields.get(
                "safe_error_message", self.state.safe_error_message
            ),
        )
        return self.state


class FakeSession:
    def __init__(self) -> None:
        self.rollback_calls = 0
        self.close_calls = 0

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def make_state(job_id: str) -> InspectionJobState:
    from datetime import datetime, timezone

    timestamp = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    return InspectionJobState(
        job_id=job_id,
        status="queued",
        created_at=timestamp,
        updated_at=timestamp,
        source_filename="products.csv",
    )


def test_new_csv_task_runs_inspection_once_and_cleans_up_file(tmp_path, monkeypatch) -> None:
    import workers.inspection_tasks as tasks

    job_id = "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
    job_file = tmp_path / "job.csv"
    job_file.write_bytes(b"csv bytes")
    store = FakeJobStore(make_state(job_id))
    session = FakeSession()
    calls: list[str] = []

    monkeypatch.setattr(tasks, "get_redis_job_store", lambda: store)
    monkeypatch.setattr(tasks, "is_safe_job_file_path", lambda *_: True)
    monkeypatch.setattr(tasks, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        tasks,
        "validate_and_read_uploaded_csv",
        lambda filename, file_bytes: calls.append("validate") or "dataframe",
    )
    monkeypatch.setattr(
        tasks,
        "find_existing_inspection_run",
        lambda *args, **kwargs: calls.append("identity") or None,
    )
    monkeypatch.setattr(
        tasks,
        "inspect_dataframe",
        lambda dataframe: calls.append("inspect")
        or SimpleNamespace(
            summary=SimpleNamespace(
                total_products=5,
                total_issues=2,
                error_count=1,
                warning_count=1,
            )
        ),
    )
    monkeypatch.setattr(
        tasks,
        "save_inspection_report",
        lambda *args, **kwargs: calls.append("save")
        or SimpleNamespace(inspection_run_id=123, created=True),
    )

    tasks.inspect_csv_task.run(job_id, str(job_file))

    assert calls == ["validate", "identity", "inspect", "save"]
    assert [update["status"] for update in store.updates] == [
        "running",
        "succeeded",
    ]
    assert store.updates[-1]["created"] is True
    assert store.updates[-1]["inspection_run_id"] == 123
    assert store.updates[-1]["summary"] == {
        "total_products": 5,
        "total_issues": 2,
        "error_count": 1,
        "warning_count": 1,
    }
    assert session.rollback_calls == 1
    assert session.close_calls == 1
    assert not job_file.exists()


def test_duplicate_csv_task_skips_inspection_and_save(tmp_path, monkeypatch) -> None:
    import workers.inspection_tasks as tasks

    job_id = "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
    job_file = tmp_path / "job.csv"
    job_file.write_bytes(b"csv bytes")
    store = FakeJobStore(make_state(job_id))
    session = FakeSession()
    calls: list[str] = []

    monkeypatch.setattr(tasks, "get_redis_job_store", lambda: store)
    monkeypatch.setattr(tasks, "is_safe_job_file_path", lambda *_: True)
    monkeypatch.setattr(tasks, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        tasks,
        "validate_and_read_uploaded_csv",
        lambda filename, file_bytes: calls.append("validate") or "dataframe",
    )
    monkeypatch.setattr(
        tasks,
        "find_existing_inspection_run",
        lambda *args, **kwargs: calls.append("identity")
        or SimpleNamespace(id=77),
    )
    monkeypatch.setattr(
        tasks,
        "inspect_dataframe",
        lambda dataframe: calls.append("inspect"),
    )
    monkeypatch.setattr(
        tasks,
        "save_inspection_report",
        lambda *args, **kwargs: calls.append("save"),
    )
    monkeypatch.setattr(
        tasks,
        "get_inspection_detail",
        lambda *args, **kwargs: SimpleNamespace(
            inspection_run_id=77,
            total_products=5,
            total_issues=2,
            error_count=1,
            warning_count=1,
        ),
    )

    tasks.inspect_csv_task.run(job_id, str(job_file))

    assert calls == ["validate", "identity"]
    assert store.updates[-1]["status"] == "succeeded"
    assert store.updates[-1]["created"] is False
    assert store.updates[-1]["inspection_run_id"] == 77
    assert session.close_calls == 1
    assert not job_file.exists()


def test_invalid_csv_task_records_safe_failure_and_cleans_up(tmp_path, monkeypatch) -> None:
    import workers.inspection_tasks as tasks
    from core.upload_validator import CsvUploadValidationError

    job_id = "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
    job_file = tmp_path / "job.csv"
    job_file.write_bytes(b"invalid")
    store = FakeJobStore(make_state(job_id))

    monkeypatch.setattr(tasks, "get_redis_job_store", lambda: store)
    monkeypatch.setattr(tasks, "is_safe_job_file_path", lambda *_: True)
    monkeypatch.setattr(
        tasks,
        "validate_and_read_uploaded_csv",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            CsvUploadValidationError("sensitive parser detail")
        ),
    )

    tasks.inspect_csv_task.run(job_id, str(job_file))

    assert store.updates[-1]["status"] == "failed"
    assert store.updates[-1]["error_code"] == "invalid_csv"
    assert store.updates[-1]["safe_error_message"] == (
        "CSV 파일을 처리할 수 없습니다."
    )
    assert "sensitive" not in store.updates[-1]["safe_error_message"]
    assert not job_file.exists()


def test_database_error_task_rolls_back_closes_and_records_safe_failure(
    tmp_path,
    monkeypatch,
) -> None:
    import workers.inspection_tasks as tasks
    from sqlalchemy.exc import SQLAlchemyError

    job_id = "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
    job_file = tmp_path / "job.csv"
    job_file.write_bytes(b"csv bytes")
    store = FakeJobStore(make_state(job_id))
    session = FakeSession()

    monkeypatch.setattr(tasks, "get_redis_job_store", lambda: store)
    monkeypatch.setattr(tasks, "is_safe_job_file_path", lambda *_: True)
    monkeypatch.setattr(tasks, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        tasks,
        "validate_and_read_uploaded_csv",
        lambda *args, **kwargs: "dataframe",
    )
    monkeypatch.setattr(
        tasks,
        "find_existing_inspection_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SQLAlchemyError("postgres password must not leak")
        ),
    )

    tasks.inspect_csv_task.run(job_id, str(job_file))

    assert store.updates[-1]["status"] == "failed"
    assert store.updates[-1]["error_code"] == "database_error"
    assert store.updates[-1]["safe_error_message"] == (
        "검수 작업을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."
    )
    assert "postgres" not in store.updates[-1]["safe_error_message"]
    assert session.rollback_calls == 1
    assert session.close_calls == 1
    assert not job_file.exists()


def test_untrusted_worker_path_is_not_read_or_deleted(tmp_path, monkeypatch) -> None:
    import workers.inspection_tasks as tasks

    job_id = "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
    outside_path = tmp_path / "outside.csv"
    outside_path.write_bytes(b"must remain")
    store = FakeJobStore(make_state(job_id))
    validator_calls: list[tuple] = []

    monkeypatch.setattr(tasks, "get_redis_job_store", lambda: store)
    monkeypatch.setattr(tasks, "is_safe_job_file_path", lambda *_: False)
    monkeypatch.setattr(
        tasks,
        "validate_and_read_uploaded_csv",
        lambda *args, **kwargs: validator_calls.append((args, kwargs)),
    )

    tasks.inspect_csv_task.run(job_id, str(outside_path))

    assert validator_calls == []
    assert store.updates[-1]["status"] == "failed"
    assert outside_path.read_bytes() == b"must remain"
