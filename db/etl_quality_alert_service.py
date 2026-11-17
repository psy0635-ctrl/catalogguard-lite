"""Evaluate operator-supplied thresholds against stored ETL batch counts."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.etl_query_service import compute_rejection_rate, quality_available_condition
from db.models import ETLLoadRun


QualityAlertStatus = Literal["PASS", "ALERT", "INSUFFICIENT_DATA"]
QualityAlertViolationCode = Literal["rejection_rate_exceeded", "rejected_rows_exceeded"]


@dataclass(frozen=True)
class ETLQualityAlertBatch:
    etl_load_run_id: int
    profile_name: str
    total_rows: int | None
    loaded_rows: int | None
    rejected_rows: int | None
    quality_available: bool


@dataclass(frozen=True)
class QualityAlertViolation:
    code: QualityAlertViolationCode
    message: str


@dataclass(frozen=True)
class QualityAlertEvaluation:
    status: QualityAlertStatus
    rejection_rate: float | None
    violations: tuple[QualityAlertViolation, ...] = ()
    data_issue: str | None = None


def get_etl_quality_alert_batch(
    session: Session, *, etl_load_run_id: int,
) -> ETLQualityAlertBatch | None:
    """Read one summary projection without fetching error details or products."""
    row = session.execute(
        select(
            ETLLoadRun.id,
            ETLLoadRun.profile_name,
            ETLLoadRun.total_rows,
            ETLLoadRun.loaded_rows,
            ETLLoadRun.rejected_rows,
            quality_available_condition(),
        ).where(ETLLoadRun.id == etl_load_run_id)
    ).one_or_none()
    return ETLQualityAlertBatch(*row) if row is not None else None


def evaluate_etl_quality_alert(
    batch: ETLQualityAlertBatch,
    *,
    max_rejection_rate: Decimal,
    max_rejected_rows: int | None,
) -> QualityAlertEvaluation:
    """Compare validated thresholds exactly and round the display rate separately."""
    total, loaded, rejected = batch.total_rows, batch.loaded_rows, batch.rejected_rows
    if not batch.quality_available or total is None or loaded is None or rejected is None:
        issue = "저장된 ETL 품질 요약이 누락되었습니다."
    elif min(total, loaded, rejected) < 0 or total != loaded + rejected:
        issue = "저장된 ETL 품질 건수가 유효하지 않습니다."
    elif total == 0:
        issue = "처리한 행이 0건입니다."
    else:
        issue = None
    if issue is not None:
        return QualityAlertEvaluation("INSUFFICIENT_DATA", None, data_issue=issue)

    # Both sides represent the same percentage scaled by total and the threshold
    # denominator. Integer arithmetic preserves equality and sub-cent differences.
    numerator, denominator = max_rejection_rate.as_integer_ratio()
    rate_excess = rejected * 100 * denominator - numerator * total
    violations = []
    if rate_excess > 0:
        excess_points = (Decimal(rate_excess) / Decimal(total * denominator)).normalize()
        violations.append(QualityAlertViolation(
            "rejection_rate_exceeded",
            f"실제 거부율이 허용 거부율을 {excess_points:.6g}%p 초과했습니다.",
        ))
    if max_rejected_rows is not None and rejected > max_rejected_rows:
        violations.append(QualityAlertViolation(
            "rejected_rows_exceeded",
            f"실제 거부 건수가 허용 거부 건수를 {rejected - max_rejected_rows}건 초과했습니다.",
        ))

    return QualityAlertEvaluation(
        status="ALERT" if violations else "PASS",
        rejection_rate=compute_rejection_rate(rejected_rows=rejected, total_rows=total),
        violations=tuple(violations),
    )
