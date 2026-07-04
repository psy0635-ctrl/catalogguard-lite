# 역할: CSV 업로드 검수 API 엔드포인트와 응답 변환 로직을 제공합니다.
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
import pandas as pd
from sqlalchemy.orm import Session

from api.schemas import (
    InspectionDetailResponse,
    InspectionListItemResponse,
    InspectionListResponse,
    InspectionResponse,
    InspectionResultItem,
    InspectionSummary,
)
from core.inspection_service import InspectionReport, inspect_uploaded_csv
from core.upload_validator import CsvUploadValidationError
from db.persistence_service import (
    InspectionDetail,
    InspectionList,
    get_inspection_detail,
    list_inspections,
    save_inspection_report,
)
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


def build_inspection_detail_response(
    detail: InspectionDetail,
) -> InspectionDetailResponse:
    result_items = [
        InspectionResultItem(
            status=_clean_text_value(result.status),
            product_group_id=_clean_text_value(result.product_group_id),
            product_id=_clean_text_value(result.product_id),
            error_field=_clean_text_value(result.error_field),
            reason=_clean_text_value(result.reason),
            recommendation=_clean_text_value(result.recommendation),
            risk_level=_clean_text_value(result.risk_level),
        )
        for result in detail.results
    ]

    return InspectionDetailResponse(
        inspection_run_id=detail.inspection_run_id,
        source_filename=detail.source_filename,
        created_at=detail.created_at,
        summary=InspectionSummary(
            total_products=detail.total_products,
            total_issues=detail.total_issues,
            error_count=detail.error_count,
            warning_count=detail.warning_count,
        ),
        results=result_items,
    )


def build_inspection_list_response(
    inspection_list: InspectionList,
) -> InspectionListResponse:
    return InspectionListResponse(
        items=[
            InspectionListItemResponse(
                inspection_run_id=item.inspection_run_id,
                source_filename=item.source_filename,
                created_at=item.created_at,
                total_products=item.total_products,
                total_issues=item.total_issues,
                error_count=item.error_count,
                warning_count=item.warning_count,
            )
            for item in inspection_list.items
        ],
        total=inspection_list.total,
        limit=inspection_list.limit,
        offset=inspection_list.offset,
    )


def normalize_filename_query(filename: str | None) -> str | None:
    cleaned_filename = "" if filename is None else filename.strip()
    return cleaned_filename or None


@router.get(
    "/api/v1/inspections",
    response_model=InspectionListResponse,
)
def list_inspection_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    filename: str | None = Query(default=None, max_length=100),
    session: Session = Depends(get_session),
) -> InspectionListResponse:
    inspection_list = list_inspections(
        session,
        limit=limit,
        offset=offset,
        filename=normalize_filename_query(filename),
    )

    return build_inspection_list_response(inspection_list)


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


@router.get(
    "/api/v1/inspections/{inspection_run_id}",
    response_model=InspectionDetailResponse,
)
def get_inspection(
    inspection_run_id: int,
    session: Session = Depends(get_session),
) -> InspectionDetailResponse:
    detail = get_inspection_detail(
        session,
        inspection_run_id=inspection_run_id,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="검수 실행 결과를 찾을 수 없습니다.",
        )

    return build_inspection_detail_response(detail)
