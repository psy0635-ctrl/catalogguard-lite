# 역할: CSV 업로드 검수 API 엔드포인트와 응답 변환 로직을 제공합니다.
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
import pandas as pd
from sqlalchemy.orm import Session

from api.schemas import (
    InspectionResponse,
    InspectionResultItem,
    InspectionSummary,
)
from core.inspection_service import InspectionReport, inspect_uploaded_csv
from core.upload_validator import CsvUploadValidationError
from db.persistence_service import save_inspection_report
from db.session import get_session


router = APIRouter()


# core/presentation.py의 한글 표시 컬럼명을 API 응답 필드명으로 바꿉니다.
RESULT_FIELD_MAP = {
    "검수 상태": "status",
    "상품 그룹 ID": "product_group_id",
    "상품 ID": "product_id",
    "오류 항목": "error_field",
    "오류 이유": "reason",
    "수정 권장사항": "recommendation",
    "위험 수준": "risk_level",
}


def _clean_text_value(value: object) -> str:
    # pandas의 빈 값(None/NaN)은 JSON에서 다루기 쉬운 빈 문자열로 통일합니다.
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value)


def build_inspection_response(
    report: InspectionReport,
    *,
    inspection_run_id: int,
) -> InspectionResponse:
    # 공통 검수 서비스가 만든 InspectionReport를 FastAPI 응답 모델로 변환합니다.
    result_items = []

    for row in report.result_dataframe.to_dict(orient="records"):
        item_data = {
            api_field: _clean_text_value(row.get(result_column))
            for result_column, api_field in RESULT_FIELD_MAP.items()
        }
        result_items.append(InspectionResultItem(**item_data))

    return InspectionResponse(
        inspection_run_id=inspection_run_id,
        summary=InspectionSummary(
            total_products=report.summary.total_products,
            total_issues=report.summary.total_issues,
            error_count=report.summary.error_count,
            warning_count=report.summary.warning_count,
        ),
        results=result_items,
    )


@router.post(
    "/api/v1/inspections",
    response_model=InspectionResponse,
)
async def create_inspection(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> InspectionResponse:
    file_bytes = await file.read()

    try:
        report = inspect_uploaded_csv(file.filename, file_bytes)
    except CsvUploadValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    inspection_run_id = save_inspection_report(
        session,
        source_filename=file.filename,
        report=report,
    )

    return build_inspection_response(
        report,
        inspection_run_id=inspection_run_id,
    )
