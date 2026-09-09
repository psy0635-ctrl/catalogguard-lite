"""Authenticated, read-only endpoint for the Inspection Copilot."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from agents import AgentsException, MaxTurnsExceeded

from api.dependencies import require_viewer
from api.schemas import InspectionCopilotAskRequest, InspectionCopilotAskResponse
from db.session import get_session
from services.inspection_copilot_service import (
    InspectionCopilotUnavailableError,
    ask_inspection_copilot,
)


router = APIRouter()
AGENT_NOT_CONFIGURED_DETAIL = {
    "code": "agent_not_configured",
    "message": "Inspection Copilot이 서버에 설정되지 않았습니다.",
}
AGENT_UNAVAILABLE_DETAIL = {
    "code": "agent_unavailable",
    "message": "Inspection Copilot 응답을 지금 가져올 수 없습니다.",
}


@router.post(
    "/api/v1/inspection-copilot/ask",
    response_model=InspectionCopilotAskResponse,
)
def ask_inspection_copilot_route(
    request: InspectionCopilotAskRequest,
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> InspectionCopilotAskResponse:
    try:
        response = ask_inspection_copilot(
            session=session,
            current_run_id=request.current_run_id,
            question=request.question,
            baseline_run_id=request.baseline_run_id,
            target_run_id=request.target_run_id,
        )
    except InspectionCopilotUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=AGENT_NOT_CONFIGURED_DETAIL,
        ) from error
    except (TimeoutError, ValueError, MaxTurnsExceeded, AgentsException):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=AGENT_UNAVAILABLE_DETAIL,
        ) from None
    return InspectionCopilotAskResponse(**response.model_dump())
