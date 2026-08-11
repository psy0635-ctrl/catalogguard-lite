from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import CatalogPromotionRollback


@dataclass(frozen=True)
class CatalogPromotionRollbackRunListItem:
    rollback_run_id: int
    target_promotion_run_id: int
    status: str
    restored_count: int
    deleted_count: int
    conflict_count: int
    failure_code: str | None
    safe_failure_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    actor_username: str | None = None


@dataclass(frozen=True)
class CatalogPromotionRollbackRunList:
    items: list[CatalogPromotionRollbackRunListItem]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class CatalogPromotionRollbackRunDetail(CatalogPromotionRollbackRunListItem):
    preview_hash: str | None = None
    preview_schema_version: str | None = None


def _apply_rollback_filters(
    statement,
    *,
    status: str | None = None,
    target_promotion_run_id: int | None = None,
):
    if status is not None:
        statement = statement.where(CatalogPromotionRollback.status == status)
    if target_promotion_run_id is not None:
        statement = statement.where(
            CatalogPromotionRollback.target_promotion_run_id
            == target_promotion_run_id
        )
    return statement


def _to_rollback_run_list_item(
    rollback: CatalogPromotionRollback,
) -> CatalogPromotionRollbackRunListItem:
    return CatalogPromotionRollbackRunListItem(
        rollback_run_id=rollback.id,
        target_promotion_run_id=rollback.target_promotion_run_id,
        status=rollback.status,
        restored_count=rollback.restored_count,
        deleted_count=rollback.deleted_count,
        conflict_count=rollback.conflict_count,
        failure_code=rollback.failure_code,
        safe_failure_message=rollback.safe_failure_message,
        started_at=rollback.started_at,
        completed_at=rollback.completed_at,
        created_at=rollback.created_at,
        actor_username=rollback.actor_username,
    )


def list_catalog_promotion_rollbacks(
    session: Session,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
    target_promotion_run_id: int | None = None,
) -> CatalogPromotionRollbackRunList:
    items_statement = _apply_rollback_filters(
        select(CatalogPromotionRollback),
        status=status,
        target_promotion_run_id=target_promotion_run_id,
    ).order_by(
        CatalogPromotionRollback.created_at.desc(),
        CatalogPromotionRollback.id.desc(),
    )
    rollbacks = list(
        session.scalars(items_statement.limit(limit).offset(offset)).all()
    )

    total_statement = _apply_rollback_filters(
        select(func.count()).select_from(CatalogPromotionRollback),
        status=status,
        target_promotion_run_id=target_promotion_run_id,
    )
    total = int(session.scalar(total_statement) or 0)
    return CatalogPromotionRollbackRunList(
        items=[_to_rollback_run_list_item(rollback) for rollback in rollbacks],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_catalog_promotion_rollback_detail(
    session: Session,
    *,
    rollback_run_id: int,
) -> CatalogPromotionRollbackRunDetail | None:
    rollback = session.scalars(
        select(CatalogPromotionRollback).where(
            CatalogPromotionRollback.id == rollback_run_id
        )
    ).first()
    if rollback is None:
        return None

    item = _to_rollback_run_list_item(rollback)
    return CatalogPromotionRollbackRunDetail(
        **item.__dict__,
        preview_hash=rollback.preview_hash,
        preview_schema_version=rollback.preview_schema_version,
    )
