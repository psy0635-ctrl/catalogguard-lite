from fastapi import APIRouter, File, HTTPException, UploadFile
import pandas as pd

from api.schemas import (
    InspectionResponse,
    InspectionResultItem,
    InspectionSummary,
)
from core.inspection_service import InspectionReport, inspect_uploaded_csv
from core.upload_validator import CsvUploadValidationError


router = APIRouter()


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
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value)


def build_inspection_response(report: InspectionReport) -> InspectionResponse:
    result_items = []

    for row in report.result_dataframe.to_dict(orient="records"):
        item_data = {
            api_field: _clean_text_value(row.get(result_column))
            for result_column, api_field in RESULT_FIELD_MAP.items()
        }
        result_items.append(InspectionResultItem(**item_data))

    return InspectionResponse(
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
async def create_inspection(file: UploadFile = File(...)) -> InspectionResponse:
    file_bytes = await file.read()

    try:
        report = inspect_uploaded_csv(file.filename, file_bytes)
    except CsvUploadValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return build_inspection_response(report)
