# 역할: InspectionReport를 하나의 트랜잭션으로 PostgreSQL에 저장합니다.
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
import re

import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.settings import INSPECTION_VERSION
from core.inspection_service import InspectionReport
from db import repositories
from db.repositories import InspectionResultCreate


# 화면 표시용 한글 컬럼명을 DB 저장용 영문 필드명으로 바꿉니다.
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
MAX_INSPECTION_VERSION_LENGTH = 20
FILE_IDENTITY_UNIQUE_INDEX_NAME = (
    "ux_inspection_runs_file_sha256_inspection_version"
)
FILE_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_RESULT_FIELDS = (
    "status",
    "error_field",
    "reason",
    "recommendation",
    "risk_level",
)


@dataclass(frozen=True)
class InspectionDetail:
    inspection_run_id: int
    source_filename: str
    created_at: datetime
    total_products: int
    total_issues: int
    error_count: int
    warning_count: int
    results: list[InspectionResultCreate]


@dataclass(frozen=True)
class InspectionListItem:
    inspection_run_id: int
    source_filename: str
    created_at: datetime
    total_products: int
    total_issues: int
    error_count: int
    warning_count: int


@dataclass(frozen=True)
class InspectionList:
    items: list[InspectionListItem]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class InspectionSaveOutcome:
    inspection_run_id: int
    created: bool


def normalize_source_filename(source_filename: str | None) -> str:
    # 경로 전체가 들어와도 DB에는 파일명만 저장합니다.
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


def normalize_file_sha256(file_sha256: str | None) -> str | None:
    if file_sha256 is None:
        return None

    normalized_hash = str(file_sha256).strip().lower()
    if not FILE_SHA256_PATTERN.fullmatch(normalized_hash):
        raise ValueError("file_sha256 must be a 64 character lowercase SHA-256 hex string")
    return normalized_hash


def normalize_inspection_version(inspection_version: str) -> str:
    normalized_version = str(inspection_version).strip()
    if not normalized_version:
        raise ValueError("inspection_version must not be blank")
    if len(normalized_version) > MAX_INSPECTION_VERSION_LENGTH:
        raise ValueError(
            f"inspection_version must be {MAX_INSPECTION_VERSION_LENGTH} characters or fewer"
        )
    return normalized_version


def _clean_text_value(value: object) -> str:
    # pandas NaN은 문자열로 바꾸면 "nan"이 되므로 먼저 빈 문자열로 정리합니다.
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value)


def _clean_optional_text_value(value: object) -> str | None:
    # product_id처럼 비어 있어도 되는 값은 빈 문자열 대신 DB NULL로 저장합니다.
    cleaned_value = _clean_text_value(value).strip()
    return cleaned_value or None


def _validate_required_result_fields(item: InspectionResultCreate) -> None:
    # DB의 NOT NULL 컬럼에 빈 필수 값이 들어가기 전에 명확한 오류로 중단합니다.
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
    # 요약의 문제 수와 실제 저장할 상세 문제 수가 다르면 데이터가 어긋난 상태입니다.
    if report.summary.total_issues != len(result_items):
        raise ValueError(
            "Inspection summary total_issues does not match result count: "
            f"{report.summary.total_issues} != {len(result_items)}"
        )


def _is_file_identity_unique_violation(error: IntegrityError) -> bool:
    orig = getattr(error, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    return constraint_name == FILE_IDENTITY_UNIQUE_INDEX_NAME


def build_result_create_items(
    report: InspectionReport,
) -> list[InspectionResultCreate]:
    # InspectionReport의 결과 DataFrame을 Repository가 저장할 입력 객체 목록으로 바꿉니다.
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
    file_sha256: str | None = None,
    inspection_version: str = INSPECTION_VERSION,
) -> InspectionSaveOutcome:
    # 이 Service가 하나의 트랜잭션 경계를 맡아 run과 results를 함께 저장합니다.
    source_basename = normalize_source_filename(source_filename)
    normalized_file_sha256 = normalize_file_sha256(file_sha256)
    normalized_inspection_version = normalize_inspection_version(inspection_version)
    result_items = build_result_create_items(report)
    _validate_summary_matches_results(report, result_items)

    created_run_id: int | None = None
    with session.begin():
        existing_run = repositories.get_inspection_run_by_file_identity(
            session,
            file_sha256=normalized_file_sha256,
            inspection_version=normalized_inspection_version,
        )
        if existing_run is not None:
            return InspectionSaveOutcome(
                inspection_run_id=existing_run.id,
                created=False,
            )

        # run을 먼저 저장하고 flush된 id를 이용해 상세 결과를 연결합니다.
        try:
            with session.begin_nested():
                inspection_run = repositories.create_inspection_run(
                    session,
                    source_filename=source_basename,
                    total_products=report.summary.total_products,
                    total_issues=report.summary.total_issues,
                    error_count=report.summary.error_count,
                    warning_count=report.summary.warning_count,
                    file_sha256=normalized_file_sha256,
                    inspection_version=normalized_inspection_version,
                )
                repositories.create_inspection_results(
                    session,
                    inspection_run_id=inspection_run.id,
                    result_items=result_items,
                )
                created_run_id = inspection_run.id
        except IntegrityError as error:
            if _is_file_identity_unique_violation(error):
                existing_run = repositories.get_inspection_run_by_file_identity(
                    session,
                    file_sha256=normalized_file_sha256,
                    inspection_version=normalized_inspection_version,
                )
                if existing_run is not None:
                    return InspectionSaveOutcome(
                        inspection_run_id=existing_run.id,
                        created=False,
                    )
            raise

    if created_run_id is None:
        raise RuntimeError("inspection run was not created")
    return InspectionSaveOutcome(inspection_run_id=created_run_id, created=True)


def get_inspection_detail(
    session: Session,
    *,
    inspection_run_id: int,
) -> InspectionDetail | None:
    inspection_run = repositories.get_inspection_run_by_id(
        session,
        inspection_run_id=inspection_run_id,
    )
    if inspection_run is None:
        return None

    inspection_results = repositories.get_inspection_results_by_run_id(
        session,
        inspection_run_id=inspection_run_id,
    )
    result_items = [
        InspectionResultCreate(
            product_group_id=result.product_group_id,
            product_id=result.product_id,
            status=result.status,
            error_field=result.error_field,
            reason=result.reason,
            recommendation=result.recommendation,
            risk_level=result.risk_level,
        )
        for result in inspection_results
    ]

    return InspectionDetail(
        inspection_run_id=inspection_run.id,
        source_filename=inspection_run.source_filename,
        created_at=inspection_run.created_at,
        total_products=inspection_run.total_products,
        total_issues=inspection_run.total_issues,
        error_count=inspection_run.error_count,
        warning_count=inspection_run.warning_count,
        results=result_items,
    )


def list_inspections(
    session: Session,
    *,
    limit: int,
    offset: int,
    filename: str | None = None,
) -> InspectionList:
    # 목록과 total은 같은 filename 조건을 써야 화면의 페이지 수가 정확합니다.
    inspection_runs = repositories.list_inspection_runs(
        session,
        limit=limit,
        offset=offset,
        filename=filename,
    )
    total = repositories.count_inspection_runs(session, filename=filename)
    items = [
        InspectionListItem(
            inspection_run_id=inspection_run.id,
            source_filename=inspection_run.source_filename,
            created_at=inspection_run.created_at,
            total_products=inspection_run.total_products,
            total_issues=inspection_run.total_issues,
            error_count=inspection_run.error_count,
            warning_count=inspection_run.warning_count,
        )
        for inspection_run in inspection_runs
    ]

    return InspectionList(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
