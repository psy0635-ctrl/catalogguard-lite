from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.main import app
from services.inspection_job_service import get_inspection_job_service
from services.redis_job_store import InspectionJobState


DEV_DATA_PATH = Path(__file__).parents[1] / "data" / "dev" / "products_dev.csv"
client = TestClient(app)


def test_submit_inspection_job_returns_accepted_queued_job() -> None:
    class FakeService:
        def submit(self, *, filename: str | None, file_bytes: bytes):
            assert filename == "products.csv"
            assert file_bytes == DEV_DATA_PATH.read_bytes()
            return SimpleNamespace(
                job_id="8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6",
                status="queued",
                status_url=(
                    "/api/v1/inspection-jobs/"
                    "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
                ),
            )

    app.dependency_overrides[get_inspection_job_service] = lambda: FakeService()
    try:
        response = client.post(
            "/api/v1/inspection-jobs",
            files={
                "file": (
                    "products.csv",
                    DEV_DATA_PATH.read_bytes(),
                    "text/csv",
                )
            },
        )
    finally:
        app.dependency_overrides.pop(get_inspection_job_service, None)

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["job_id"]
    assert payload["status_url"] == (
        f"/api/v1/inspection-jobs/{payload['job_id']}"
    )


def test_invalid_async_upload_returns_400_without_job_creation() -> None:
    class FakeService:
        def submit(self, *, filename: str | None, file_bytes: bytes):
            from services.inspection_job_service import InspectionJobUploadError

            raise InspectionJobUploadError("CSV 파일만 업로드할 수 있습니다.")

    app.dependency_overrides[get_inspection_job_service] = lambda: FakeService()
    try:
        response = client.post(
            "/api/v1/inspection-jobs",
            files={"file": ("products.txt", b"not csv", "text/plain")},
        )
    finally:
        app.dependency_overrides.pop(get_inspection_job_service, None)

    assert response.status_code == 400
    assert response.json() == {"detail": "CSV 파일만 업로드할 수 있습니다."}
    assert response.headers["X-Request-ID"]


def test_enqueue_failure_returns_safe_503() -> None:
    class FakeService:
        def submit(self, *, filename: str | None, file_bytes: bytes):
            from services.inspection_job_service import InspectionJobEnqueueError

            raise InspectionJobEnqueueError(
                "검수 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요."
            )

    app.dependency_overrides[get_inspection_job_service] = lambda: FakeService()
    try:
        response = client.post(
            "/api/v1/inspection-jobs",
            files={"file": ("products.csv", b"csv", "text/csv")},
        )
    finally:
        app.dependency_overrides.pop(get_inspection_job_service, None)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "검수 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요."
    }
    assert response.headers["X-Request-ID"]


def test_get_inspection_job_returns_404_for_unknown_job() -> None:
    class FakeService:
        def get(self, job_id: str):
            assert job_id == "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
            return None

    app.dependency_overrides[get_inspection_job_service] = lambda: FakeService()
    try:
        response = client.get(
            "/api/v1/inspection-jobs/8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
        )
    finally:
        app.dependency_overrides.pop(get_inspection_job_service, None)

    assert response.status_code == 404


def test_get_inspection_job_returns_succeeded_result() -> None:
    job_id = "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"
    timestamp = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)

    class FakeService:
        def get(self, requested_job_id: str):
            assert requested_job_id == job_id
            return InspectionJobState(
                job_id=job_id,
                status="succeeded",
                created_at=timestamp,
                updated_at=timestamp,
                created=False,
                inspection_run_id=123,
                summary={
                    "total_products": 5,
                    "total_issues": 2,
                    "error_count": 1,
                    "warning_count": 1,
                },
            )

    app.dependency_overrides[get_inspection_job_service] = lambda: FakeService()
    try:
        response = client.get(f"/api/v1/inspection-jobs/{job_id}")
    finally:
        app.dependency_overrides.pop(get_inspection_job_service, None)

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job_id,
        "status": "succeeded",
        "created": False,
        "inspection_run_id": 123,
        "summary": {
            "total_products": 5,
            "total_issues": 2,
            "error_count": 1,
            "warning_count": 1,
        },
        "error_code": None,
        "message": None,
        "created_at": "2026-07-21T16:00:00Z",
        "updated_at": "2026-07-21T16:00:00Z",
    }


def test_get_inspection_job_rejects_malformed_uuid() -> None:
    response = client.get("/api/v1/inspection-jobs/not-a-uuid")

    assert response.status_code == 422
