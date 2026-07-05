# 역할: 검수 실행과 상세 검수 결과를 DB에 저장하는 순수 Repository 함수들을 제공합니다.
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config.settings import INSPECTION_VERSION
from db.models import InspectionResult, InspectionRun

LIKE_ESCAPE_CHARACTER = "\\"


@dataclass(frozen=True)
class InspectionResultCreate:
    # DB 모델을 만들기 전에 Service가 준비해 주는 상세 결과 입력값입니다.
    product_group_id: str | None
    product_id: str | None
    status: str
    error_field: str
    reason: str
    recommendation: str
    risk_level: str


def create_inspection_run(
    session: Session,
    *,
    source_filename: str,
    total_products: int,
    total_issues: int,
    error_count: int,
    warning_count: int,
    file_sha256: str | None = None,
    inspection_version: str = INSPECTION_VERSION,
) -> InspectionRun:
    # Repository는 DB 객체 생성과 flush만 담당하고, commit은 Service가 담당합니다.
    inspection_run = InspectionRun(
        source_filename=source_filename,
        file_sha256=file_sha256,
        inspection_version=inspection_version,
        total_products=total_products,
        total_issues=total_issues,
        error_count=error_count,
        warning_count=warning_count,
    )
    session.add(inspection_run)
    # flush를 해야 DB가 만든 id를 commit 전에 확인할 수 있습니다.
    session.flush()
    return inspection_run


def create_inspection_results(
    session: Session,
    *,
    inspection_run_id: int,
    result_items: Iterable[InspectionResultCreate],
) -> list[InspectionResult]:
    # 이미 생성된 inspection_run_id를 이용해 상세 문제 목록을 한 번에 저장합니다.
    inspection_results = [
        InspectionResult(
            inspection_run_id=inspection_run_id,
            product_group_id=item.product_group_id,
            product_id=item.product_id,
            status=item.status,
            error_field=item.error_field,
            reason=item.reason,
            recommendation=item.recommendation,
            risk_level=item.risk_level,
        )
        for item in result_items
    ]

    session.add_all(inspection_results)
    # 여기서도 commit하지 않아야 상위 트랜잭션이 전체 성공/실패를 결정할 수 있습니다.
    session.flush()
    return inspection_results


def get_inspection_run_by_id(
    session: Session,
    *,
    inspection_run_id: int,
) -> InspectionRun | None:
    return session.get(InspectionRun, inspection_run_id)


def get_inspection_run_by_file_identity(
    session: Session,
    *,
    file_sha256: str | None,
    inspection_version: str,
) -> InspectionRun | None:
    if file_sha256 is None:
        return None

    statement = (
        select(InspectionRun)
        .where(InspectionRun.file_sha256 == file_sha256)
        .where(InspectionRun.inspection_version == inspection_version)
        .limit(1)
    )
    return session.scalar(statement)


def get_inspection_results_by_run_id(
    session: Session,
    *,
    inspection_run_id: int,
) -> list[InspectionResult]:
    statement = (
        select(InspectionResult)
        .where(InspectionResult.inspection_run_id == inspection_run_id)
        .order_by(InspectionResult.id.asc())
    )
    return list(session.scalars(statement).all())


def normalize_filename_filter(filename: str | None) -> str | None:
    # Repository에서도 한 번 더 정리해 빈 문자열 검색이 전체 목록이 되게 합니다.
    cleaned_filename = "" if filename is None else str(filename).strip()
    return cleaned_filename or None


def escape_like_pattern(value: str) -> str:
    # %, _, \는 SQL LIKE에서 특별한 뜻이 있으므로 일반 글자로 검색되게 표시합니다.
    return (
        value.replace(LIKE_ESCAPE_CHARACTER, LIKE_ESCAPE_CHARACTER * 2)
        .replace("%", f"{LIKE_ESCAPE_CHARACTER}%")
        .replace("_", f"{LIKE_ESCAPE_CHARACTER}_")
    )


def apply_filename_filter(statement, filename: str | None):
    filename_filter = normalize_filename_filter(filename)
    if filename_filter is None:
        return statement

    # 앞뒤에 %를 붙여 파일명 앞/중간/뒤 어디에 검색어가 있어도 찾습니다.
    pattern = f"%{escape_like_pattern(filename_filter)}%"
    return statement.where(
        InspectionRun.source_filename.ilike(
            pattern,
            escape=LIKE_ESCAPE_CHARACTER,
        )
    )


def list_inspection_runs(
    session: Session,
    *,
    limit: int,
    offset: int,
    filename: str | None = None,
) -> list[InspectionRun]:
    statement = (
        apply_filename_filter(select(InspectionRun), filename)
        # 최신 검수 이력이 먼저 보이도록 기존 정렬 순서를 그대로 유지합니다.
        .order_by(InspectionRun.created_at.desc(), InspectionRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement).all())


def count_inspection_runs(
    session: Session,
    *,
    filename: str | None = None,
) -> int:
    # total도 목록과 같은 filename 조건으로 세야 pagination이 맞습니다.
    statement = apply_filename_filter(
        select(func.count()).select_from(InspectionRun),
        filename,
    )
    return int(session.scalar(statement) or 0)
