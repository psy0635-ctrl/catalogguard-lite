from __future__ import annotations

import os
from pathlib import Path
import time

import pytest
import requests


API_BASE_URL = os.environ.get("ASYNC_E2E_API_BASE_URL", "http://127.0.0.1:8000")
POLL_INTERVAL_SECONDS = 1
POLL_TIMEOUT_SECONDS = 45
REQUEST_TIMEOUT_SECONDS = 5
DEV_CSV_PATH = Path(__file__).parents[2] / "data" / "dev" / "products_dev.csv"
SUMMARY_FIELDS = (
    "total_products",
    "total_issues",
    "error_count",
    "warning_count",
)


def _get(path: str) -> requests.Response:
    return requests.get(
        f"{API_BASE_URL}{path}",
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def _submit_csv(csv_bytes: bytes) -> dict[str, object]:
    response = requests.post(
        f"{API_BASE_URL}/api/v1/inspection-jobs",
        files={"file": ("products_dev.csv", csv_bytes, "text/csv")},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["status"] == "queued"
    assert isinstance(payload["job_id"], str) and payload["job_id"]
    assert payload["status_url"] == f"/api/v1/inspection-jobs/{payload['job_id']}"
    return payload


def _wait_for_job(job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_status: object = None
    while time.monotonic() < deadline:
        response = _get(f"/api/v1/inspection-jobs/{job_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        status = payload["status"]
        last_status = status
        if status == "succeeded":
            return payload
        if status == "failed":
            pytest.fail(f"inspection job failed: {payload}")
        assert status in {"queued", "running"}, payload
        time.sleep(POLL_INTERVAL_SECONDS)

    pytest.fail(
        "inspection job did not finish within "
        f"{POLL_TIMEOUT_SECONDS} seconds; last status: {last_status!r}"
    )


def _assert_job_files_removed(job_directory: Path) -> None:
    deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not list(job_directory.glob("*.csv")):
            return
        time.sleep(0.1)

    pytest.fail(f"inspection job CSV files remain in {job_directory}")


def _assert_summary(summary: object) -> None:
    assert isinstance(summary, dict)
    for field in SUMMARY_FIELDS:
        value = summary.get(field)
        assert type(value) is int and value >= 0


@pytest.mark.e2e
def test_async_inspection_job_uses_real_api_worker_and_services() -> None:
    csv_bytes = DEV_CSV_PATH.read_bytes()
    job_directory = Path(
        os.environ.get("INSPECTION_JOB_DIR", "var/inspection_jobs")
    )

    assert _get("/health").status_code == 200
    assert _get("/ready").status_code == 200

    first_submission = _submit_csv(csv_bytes)
    first_result = _wait_for_job(str(first_submission["job_id"]))
    assert first_result["created"] is True
    first_run_id = first_result["inspection_run_id"]
    assert type(first_run_id) is int and first_run_id > 0
    _assert_summary(first_result["summary"])

    detail_response = _get(
        f"/api/v1/inspections/{first_run_id}"
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["inspection_run_id"] == first_run_id
    _assert_summary(detail["summary"])

    second_submission = _submit_csv(csv_bytes)
    assert second_submission["job_id"] != first_submission["job_id"]
    second_result = _wait_for_job(str(second_submission["job_id"]))
    assert second_result["created"] is False
    assert second_result["inspection_run_id"] == first_run_id

    _assert_job_files_removed(job_directory)
