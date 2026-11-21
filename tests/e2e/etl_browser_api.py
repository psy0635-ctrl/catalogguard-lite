"""Run the real API with controlled ETL task delivery for the Chromium runner."""

import json
import os
from pathlib import Path
from uuid import UUID

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from api.main import app
from services import etl_job_service
from workers.etl_tasks import run_web_etl_job


ETL_JOBS_PATH = "/api/v1/etl-jobs"
CONTROL_DIR = Path(os.environ["E2E_ETL_JOB_CONTROL_DIR"])
PENDING_JOBS: set[str] = set()


def _hold_task(job_id: UUID) -> None:
    PENDING_JOBS.add(str(job_id))


etl_job_service.enqueue_etl_job = _hold_task


@app.middleware("http")
async def control_task_delivery(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/v1/"):
        return await call_next(request)

    job_id = path.removeprefix(f"{ETL_JOBS_PATH}/")
    if request.method == "GET" and path.startswith(f"{ETL_JOBS_PATH}/") and job_id in PENDING_JOBS:
        # A lookup error pauses Streamlit's automatic polling. The test can
        # then attribute the next job lookup to the manual refresh button.
        if not (CONTROL_DIR / "release-etl-job").exists():
            response = JSONResponse({"detail": "Synthetic lookup failure"}, status_code=503)
        else:
            PENDING_JOBS.remove(job_id)
            await run_in_threadpool(run_web_etl_job.run, job_id)
            response = await call_next(request)
    else:
        response = await call_next(request)

    with (CONTROL_DIR / "api-requests.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps([request.method, path, response.status_code]) + "\n")
    return response
