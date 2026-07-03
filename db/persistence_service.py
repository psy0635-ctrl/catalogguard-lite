from pathlib import PurePath

import pandas as pd
from sqlalchemy.orm import Session

from core.inspection_service import InspectionReport
from db import repositories
from db.repositories import InspectionResultCreate


RESULT_COLUMN_MAP = {
    "검수 상태": "status",
    "오류 항목": "error_field",
    "상품 그룹 ID": "product_group_id",
    "상품 ID": "product_id",
    "오류 이유": "reason",
    "수정 권장사항": "recommendation",
    "위험 수준": "risk_level",
}

DEFAULT_SOURCE_FILENAME = "uploaded.csv"
MAX_SOURCE_FILENAME_LENGTH = 255
REQUIRED_RESULT_FIELDS = (
    "status",
    "error_field",
    "reason",
    "recommendation",
    "risk_level",
)


def normalize_source_filename(source_filename: str | None) -> str:
    cleaned_filename = "" if source_filename is None else str(source_filename)
    cleaned_filename = cleaned_filename.replace("\\", "/").strip()
    filename = PurePath(cleaned_filename).name.strip()
    if not filename:
        return DEFAULT_SOURCE_FILENAME
    if len(filename) <= MAX_SOURCE_FILENAME_LENGTH:
        return filename

    suffix = PurePath(filename).suffix
    if suffix and len(suffix) < MAX_SOURCE_FILENAME_LENGTH:
        stem_length = MAX_SOURCE_FILENAME_LENGTH - len(suffix)
        return f"{filename[:-len(suffix)][:stem_length]}{suffix}"

    return filename[:MAX_SOURCE_FILENAME_LENGTH]


def _clean_text_value(value: object) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value)


def _clean_optional_text_value(value: object) -> str | None:
    cleaned_value = _clean_text_value(value).strip()
    return cleaned_value or None


def _validate_required_result_fields(item: InspectionResultCreate) -> None:
    missing_fields = [
        field_name
        for field_name in REQUIRED_RESULT_FIELDS
        if not getattr(item, field_name).strip()
    ]
    if missing_fields:
        missing_text = ", ".join(missing_fields)
        raise ValueError(f"Inspection result required fields are blank: {missing_text}")


def _validate_summary_matches_results(
    report: InspectionReport,
    result_items: list[InspectionResultCreate],
) -> None:
    if report.summary.total_issues != len(result_items):
        raise ValueError(
            "Inspection summary total_issues does not match result count: "
            f"{report.summary.total_issues} != {len(result_items)}"
        )


def build_result_create_items(
    report: InspectionReport,
) -> list[InspectionResultCreate]:
    result_items = []

    for row in report.result_dataframe.to_dict(orient="records"):
        item_data = {
            api_field: row.get(result_column)
            for result_column, api_field in RESULT_COLUMN_MAP.items()
        }
        result_item = InspectionResultCreate(
            product_group_id=_clean_optional_text_value(item_data["product_group_id"]),
            product_id=_clean_optional_text_value(item_data["product_id"]),
            status=_clean_text_value(item_data["status"]),
            error_field=_clean_text_value(item_data["error_field"]),
            reason=_clean_text_value(item_data["reason"]),
            recommendation=_clean_text_value(item_data["recommendation"]),
            risk_level=_clean_text_value(item_data["risk_level"]),
        )
        _validate_required_result_fields(result_item)
        result_items.append(result_item)

    return result_items


def save_inspection_report(
    session: Session,
    *,
    source_filename: str | None,
    report: InspectionReport,
) -> int:
    source_basename = normalize_source_filename(source_filename)
    result_items = build_result_create_items(report)
    _validate_summary_matches_results(report, result_items)

    with session.begin():
        inspection_run = repositories.create_inspection_run(
            session,
            source_filename=source_basename,
            total_products=report.summary.total_products,
            total_issues=report.summary.total_issues,
            error_count=report.summary.error_count,
            warning_count=report.summary.warning_count,
        )
        repositories.create_inspection_results(
            session,
            inspection_run_id=inspection_run.id,
            result_items=result_items,
        )

    return inspection_run.id
