"""Read-only comparison of one supplier's recent ETL batches against each other.

기존 quality summary/trend가 답하지 못하는 두 가지 질문에 답합니다.

1. 이 공급사의 최신 배치는 직전 배치보다 좋아졌는가, 나빠졌는가?
2. 나빠졌다면 어떤 ETL 오류 코드가 가장 많이 발생했는가?

summary는 여러 배치를 하나의 누적 비율로 합치고, trend는 배치별 비율을 나열만 합니다.
둘 다 "직전 배치 대비 변화"와 "그 변화의 원인 후보"를 말해 주지 않습니다. 이 모듈은
같은 profile_name 안에서 두 배치를 직접 비교하고, 같은 관찰 구간의 error_counts를
코드별로 합산합니다.

정책은 새로 만들지 않고 db.etl_query_service의 것을 그대로 씁니다.

* quality metadata가 불완전한 legacy batch 제외: quality_available_condition()
* total_rows == 0 -> rejection_rate 0.0: compute_rejection_rate()
* 배치 표현 필드와 정렬(created_at DESC, id DESC): to_quality_trend_item()

한 가지만 다릅니다. profile_name을 부분 일치(ILIKE)가 아니라 정확히 일치로 봅니다.
부분 일치를 쓰면 "sample"이 sample_fashion_vendor와 sample_marketplace_vendor를 함께
잡아, 서로 다른 공급사의 배치를 직전/최신으로 비교하게 됩니다. 그 비교는 품질 변화가
아니라 공급사 차이를 보여 줄 뿐이므로, 이 조회에서는 정확 일치가 유일하게 안전합니다.

DB에 쓰지 않고, 어떤 자동 조치도 하지 않는 순수 조회입니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.etl_query_service import (
    ETLLoadQualityTrendItem,
    quality_available_condition,
    to_quality_trend_item,
)
from db.models import ETLLoadRun


# 위험 임계값(예: 5% 이상이면 경고)은 이 MVP에서 정하지 않습니다. 임계값은 공급사·시즌·
# 상품군마다 달라서 임의로 정하면 운영자가 잘못된 기준을 믿게 됩니다. 여기서는 방향만
# 말하고, 얼마부터 문제인지는 사람이 판단합니다.
ETLQualityDirection = Literal["improved", "unchanged", "worsened", "no_baseline"]

DEFAULT_BATCH_LIMIT = 10
# quality-trend와 같은 1~50을 씁니다. 두 조회가 같은 limit을 받고도 서로 다른 개수의
# 배치를 보면 화면이 설명하기 어려워지기 때문입니다. limit=1이면 비교 대상이 최신 배치
# 하나뿐이라 direction은 정의상 no_baseline이 됩니다.
MIN_BATCH_LIMIT = 1
MAX_BATCH_LIMIT = 50


@dataclass(frozen=True)
class ETLQualityErrorCodeCount:
    error_code: str
    # 관찰 구간 전체에서 이 코드로 거부된 행 수의 합입니다.
    total_count: int
    # 이 코드가 한 번이라도 나타난 배치 수입니다. 한 배치에서만 터진 사고인지,
    # 여러 배치에 걸친 구조적 문제인지 구분하는 데 씁니다.
    affected_batch_count: int


@dataclass(frozen=True)
class ETLQualityObservabilityProfile:
    # ETLLoadRun에 기록된 원본 profile_name 그대로입니다. 이 값이 그대로 비교 조회의
    # 정확 일치 입력이 되므로 strip이나 lower로 identity를 바꾸지 않습니다.
    profile_name: str


@dataclass(frozen=True)
class ETLQualityObservabilityProfileList:
    items: list[ETLQualityObservabilityProfile]


@dataclass(frozen=True)
class ETLQualityObservability:
    profile_name: str
    limit: int
    # 관찰 구간에 들어온 quality-available 배치 수입니다(= recent_batches 길이).
    batch_count: int
    latest_batch: ETLLoadQualityTrendItem | None
    previous_batch: ETLLoadQualityTrendItem | None
    # 퍼센트 포인트(%p) 차이입니다. 4.0% -> 9.0%이면 +5.0입니다. 비교 대상이 없으면 None입니다.
    rejection_rate_delta: float | None
    direction: ETLQualityDirection
    error_codes: list[ETLQualityErrorCodeCount]
    # 오래된 배치부터 최신 배치 순서입니다. quality-trend와 같은 정렬을 씁니다.
    recent_batches: list[ETLLoadQualityTrendItem]


def _aggregate_error_codes(
    load_runs: list[ETLLoadRun],
) -> list[ETLQualityErrorCodeCount]:
    """Sum error_counts across the observed batches, deterministically ordered."""
    total_counts: dict[str, int] = {}
    affected_batch_counts: dict[str, int] = {}
    for load_run in load_runs:
        error_counts = load_run.error_counts or {}
        if not isinstance(error_counts, dict):
            continue
        for error_code, count in error_counts.items():
            # JSONB는 어떤 값이든 담을 수 있으므로, 합계를 망가뜨릴 값은 조용히 건너뜁니다.
            # bool은 int의 하위 타입이라 따로 걸러 냅니다.
            if not isinstance(error_code, str) or not error_code.strip():
                continue
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                continue
            total_counts[error_code] = total_counts.get(error_code, 0) + count
            affected_batch_counts[error_code] = (
                affected_batch_counts.get(error_code, 0) + 1
            )
    # 많이 터진 코드가 먼저 오고, 같은 수면 코드 이름 순서로 고정합니다.
    return [
        ETLQualityErrorCodeCount(
            error_code=error_code,
            total_count=total_count,
            affected_batch_count=affected_batch_counts[error_code],
        )
        for error_code, total_count in sorted(
            total_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _resolve_direction(
    latest: ETLLoadQualityTrendItem | None,
    previous: ETLLoadQualityTrendItem | None,
) -> ETLQualityDirection:
    if latest is None or previous is None:
        return "no_baseline"
    if latest.rejection_rate < previous.rejection_rate:
        return "improved"
    if latest.rejection_rate > previous.rejection_rate:
        return "worsened"
    return "unchanged"


def get_etl_quality_observability(
    session: Session,
    *,
    profile_name: str,
    limit: int = DEFAULT_BATCH_LIMIT,
) -> ETLQualityObservability:
    """Compare one supplier's latest quality-available batch with the previous one."""
    normalized_profile_name = profile_name.strip()
    if not normalized_profile_name:
        raise ValueError("profile_name must not be empty")
    if type(limit) is not int or not MIN_BATCH_LIMIT <= limit <= MAX_BATCH_LIMIT:
        raise ValueError(
            f"limit must be between {MIN_BATCH_LIMIT} and {MAX_BATCH_LIMIT}"
        )

    statement = (
        select(ETLLoadRun)
        .where(ETLLoadRun.profile_name == normalized_profile_name)
        .where(quality_available_condition())
        # created_at이 같은 배치가 있어도 id로 순서가 하나로 정해집니다.
        .order_by(ETLLoadRun.created_at.desc(), ETLLoadRun.id.desc())
        .limit(limit)
    )
    newest_first = list(session.scalars(statement).all())

    items = [to_quality_trend_item(load_run) for load_run in newest_first]
    latest = items[0] if items else None
    previous = items[1] if len(items) >= 2 else None
    # 화면에 보이는 값과 변화량이 어긋나지 않도록, 이미 반올림된 rejection_rate로 뺍니다.
    delta = (
        round(latest.rejection_rate - previous.rejection_rate, 2)
        if latest is not None and previous is not None
        else None
    )

    return ETLQualityObservability(
        profile_name=normalized_profile_name,
        limit=limit,
        batch_count=len(items),
        latest_batch=latest,
        previous_batch=previous,
        rejection_rate_delta=delta,
        direction=_resolve_direction(latest, previous),
        error_codes=_aggregate_error_codes(newest_first),
        recent_batches=list(reversed(items)),
    )


def list_etl_quality_observability_profiles(
    session: Session,
) -> ETLQualityObservabilityProfileList:
    """List the supplier profiles that this comparison can actually be run for.

    후보 근거는 ETL Profile Registry가 아니라 ETLLoadRun 이력입니다. registry에서
    사라진 과거 공급사라도 quality-available 배치가 남아 있으면 비교할 수 있고,
    반대로 registry에 있어도 품질 정보가 있는 배치가 없으면 비교할 것이 없습니다.

    그래서 get_etl_quality_observability()와 같은 quality_available_condition()을
    씁니다. 두 조회가 다른 기준을 쓰면 목록에 보이는데 고르면 빈 결과가 나오는
    공급사가 생깁니다.

    DISTINCT와 정렬은 DB가 합니다. 모든 ETLLoadRun을 읽어 Python에서 set으로 줄이면
    배치가 늘어날수록 필요 없는 행을 전부 전송하게 됩니다.
    """
    statement = (
        select(ETLLoadRun.profile_name)
        .where(quality_available_condition())
        .distinct()
        .order_by(ETLLoadRun.profile_name.asc())
    )
    return ETLQualityObservabilityProfileList(
        items=[
            ETLQualityObservabilityProfile(profile_name=profile_name)
            for profile_name in session.scalars(statement).all()
        ]
    )
