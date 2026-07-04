# 역할: 검수 실행과 상세 검수 결과를 DB에 저장하는 순수 Repository 함수들을 제공합니다.
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import InspectionResult, InspectionRun


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
) -> InspectionRun:
    # Repository는 DB 객체 생성과 flush만 담당하고, commit은 Service가 담당합니다.
    inspection_run = InspectionRun(
        source_filename=source_filename,
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
