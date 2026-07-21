from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from api.schemas import (
    InspectionJobStatusResponse,
    InspectionJobSubmissionResponse,
    InspectionSummary,
)
from services.inspection_job_service import (
    InspectionJobEnqueueError,
    InspectionJobService,
    InspectionJobUploadError,
    get_inspection_job_service,
)


router = APIRouter()


@router.post(
    "/api/v1/inspection-jobs",
    response_model=InspectionJobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_inspection_job(
    file: UploadFile = File(...),
    service: InspectionJobService = Depends(get_inspection_job_service),
) -> InspectionJobSubmissionResponse:
    file_bytes = await file.read()
    try:
        submission = service.submit(filename=file.filename, file_bytes=file_bytes)
    except InspectionJobUploadError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except InspectionJobEnqueueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return InspectionJobSubmissionResponse(
        job_id=submission.job_id,
        status="queued",
        status_url=submission.status_url,
    )


@router.get(
    "/api/v1/inspection-jobs/{job_id}",
    response_model=InspectionJobStatusResponse,
)
def get_inspection_job(
    job_id: UUID,
    service: InspectionJobService = Depends(get_inspection_job_service),
) -> InspectionJobStatusResponse:
    state = service.get(str(job_id))
    if state is None:
        raise HTTPException(status_code=404, detail="검수 작업을 찾을 수 없습니다.")

    return InspectionJobStatusResponse(
        job_id=state.job_id,
        status=state.status,
        created=state.created,
        inspection_run_id=state.inspection_run_id,
        summary=InspectionSummary(**state.summary) if state.summary else None,
        error_code=state.error_code,
        message=state.safe_error_message,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )
