from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from db.models import InspectionResult, InspectionRun


@dataclass(frozen=True)
class InspectionResultCreate:
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
    inspection_run = InspectionRun(
        source_filename=source_filename,
        total_products=total_products,
        total_issues=total_issues,
        error_count=error_count,
        warning_count=warning_count,
    )
    session.add(inspection_run)
    session.flush()
    return inspection_run


def create_inspection_results(
    session: Session,
    *,
    inspection_run_id: int,
    result_items: Iterable[InspectionResultCreate],
) -> list[InspectionResult]:
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
    session.flush()
    return inspection_results
