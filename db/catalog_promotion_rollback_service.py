from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.catalog_promotion_preview_service import COMPARISON_FIELDS
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogPromotionRollback,
    CatalogPromotionRollbackChange,
    CatalogPromotionRun,
)


ROLLBACK_PREVIEW_SCHEMA_VERSION = 1
EXPECTED_ROLLBACK_PREVIEW_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ROLLBACK_CONFIRMATION_MESSAGE = "Explicit confirmation is required to execute rollback."
ROLLBACK_PREVIEW_STALE_MESSAGE = "The rollback preview is stale. Create a new preview and try again."
ROLLBACK_CONFLICT_MESSAGE = "Rollback was blocked because the current catalog state differs from the selected promotion."
ROLLBACK_NOT_ELIGIBLE_MESSAGE = "The selected promotion run cannot be rolled back."
ROLLBACK_FAILED_MESSAGE = "Rollback could not be completed."
rollback_logger = logging.getLogger("catalogguard.catalog_promotion_rollback")

RollbackAction = Literal["delete", "restore"]
RollbackStatus = Literal["succeeded", "blocked"]
ProductData = dict[str, object]


class CatalogPromotionRollbackNotFoundError(ValueError):
    def __init__(self, promotion_run_id: int):
        self.promotion_run_id = promotion_run_id
        super().__init__("Promotion run not found.")


class CatalogPromotionRollbackConfirmationRequiredError(ValueError):
    def __init__(self):
        super().__init__(ROLLBACK_CONFIRMATION_MESSAGE)


class CatalogPromotionRollbackInvalidPreviewHashError(ValueError):
    def __init__(self):
        super().__init__("expected_preview_hash must be a lowercase SHA-256 hex string")


class CatalogPromotionRollbackAlreadyExecutedError(ValueError):
    def __init__(self, rollback_run_id: int):
        self.rollback_run_id = rollback_run_id
        super().__init__("This promotion run has already been rolled back.")


class CatalogPromotionRollbackExecutionFailedError(RuntimeError):
    def __init__(self, rollback_run_id: int | None):
        self.rollback_run_id = rollback_run_id
        super().__init__(ROLLBACK_FAILED_MESSAGE)


@dataclass(frozen=True)
class RollbackBlockedReason:
    code: str
    message: str
    catalog_product_id: int | None = None
    external_product_id: str | None = None


@dataclass(frozen=True)
class CatalogPromotionRollbackPreviewItem:
    audit_id: int
    catalog_product_id: int
    external_product_id: str
    rollback_action: RollbackAction
    current_data: ProductData | None
    restore_data: ProductData | None
    conflict: bool
    conflict_reason: str | None


@dataclass(frozen=True)
class CatalogPromotionRollbackPreview:
    target_promotion_run_id: int
    preview_schema_version: int
    preview_hash: str | None
    rollback_eligible: bool
    blocked_reasons: list[RollbackBlockedReason]
    restore_count: int
    delete_count: int
    conflict_count: int
    items: list[CatalogPromotionRollbackPreviewItem]


@dataclass(frozen=True)
class CatalogPromotionRollbackExecutionResult:
    rollback_run_id: int
    target_promotion_run_id: int
    status: RollbackStatus
    created: bool
    preview_hash: str | None
    preview_schema_version: int | None
    restored_count: int
    deleted_count: int
    conflict_count: int
    failure_code: str | None
    safe_failure_message: str | None
    blocked_reasons: list[RollbackBlockedReason]
    started_at: datetime | None
    completed_at: datetime | None
    actor_username: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _product_data(product: CatalogProduct) -> ProductData:
    return {
        "external_product_id": product.external_product_id,
        "product_group_id": product.product_group_id,
        "product_name": product.product_name,
        "category": product.category,
        "color": product.color,
        "size": product.size,
        "stock": product.stock,
        "price": product.price,
        "sale_price": product.sale_price,
        "image_path": product.image_path,
        "description": product.description,
        "seller": product.seller,
    }


def _as_product_data(value: object) -> ProductData | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    return _product_data(value)  # type: ignore[arg-type]


def build_rollback_preview_items(
    audit_items: list[CatalogProductChange],
    current_products: dict[int, object],
) -> list[CatalogPromotionRollbackPreviewItem]:
    items: list[CatalogPromotionRollbackPreviewItem] = []
    for audit in sorted(audit_items, key=lambda item: (item.catalog_product_id, item.id)):
        current = _as_product_data(current_products.get(audit.catalog_product_id))
        expected = dict(audit.after_data)
        restore = None if audit.action == "insert" else dict(audit.before_data or {})
        conflict = current != expected
        items.append(
            CatalogPromotionRollbackPreviewItem(
                audit_id=audit.id,
                catalog_product_id=audit.catalog_product_id,
                external_product_id=str(expected["external_product_id"]),
                rollback_action="delete" if audit.action == "insert" else "restore",
                current_data=current,
                restore_data=restore,
                conflict=conflict,
                conflict_reason="rollback_conflict" if conflict else None,
            )
        )
    return items


def build_rollback_preview_hash(
    *,
    target_promotion_run_id: int,
    audit_items: list[CatalogProductChange],
    current_products: dict[int, object],
) -> str:
    items = []
    for audit in sorted(audit_items, key=lambda item: (item.catalog_product_id, item.id)):
        items.append(
            {
                "audit_id": audit.id,
                "catalog_product_id": audit.catalog_product_id,
                "action": audit.action,
                "expected_after": audit.after_data,
                "restore_before": audit.before_data,
                "current": _as_product_data(current_products.get(audit.catalog_product_id)),
            }
        )
    canonical = json.dumps(
        {
            "preview_schema_version": ROLLBACK_PREVIEW_SCHEMA_VERSION,
            "target_promotion_run_id": target_promotion_run_id,
            "items": items,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_preview(
    *,
    target: CatalogPromotionRun,
    audits: list[CatalogProductChange],
    current_products: dict[int, object],
    extra_reasons: list[RollbackBlockedReason] | None = None,
) -> CatalogPromotionRollbackPreview:
    reasons = list(extra_reasons or [])
    items = build_rollback_preview_items(audits, current_products)
    conflict_items = [item for item in items if item.conflict]
    reasons.extend(
        RollbackBlockedReason(
            code="rollback_conflict",
            message=ROLLBACK_CONFLICT_MESSAGE,
            catalog_product_id=item.catalog_product_id,
            external_product_id=item.external_product_id,
        )
        for item in conflict_items
    )
    preview_hash = build_rollback_preview_hash(
        target_promotion_run_id=target.id,
        audit_items=audits,
        current_products=current_products,
    ) if audits else None
    return CatalogPromotionRollbackPreview(
        target_promotion_run_id=target.id,
        preview_schema_version=ROLLBACK_PREVIEW_SCHEMA_VERSION,
        preview_hash=preview_hash,
        rollback_eligible=bool(audits) and not reasons and not conflict_items,
        blocked_reasons=reasons,
        restore_count=sum(item.rollback_action == "restore" for item in items),
        delete_count=sum(item.rollback_action == "delete" for item in items),
        conflict_count=len(conflict_items),
        items=items,
    )


def preview_catalog_promotion_rollback(
    session: Session,
    *,
    promotion_run_id: int,
) -> CatalogPromotionRollbackPreview:
    target = session.get(CatalogPromotionRun, promotion_run_id)
    if target is None:
        raise CatalogPromotionRollbackNotFoundError(promotion_run_id)
    reasons: list[RollbackBlockedReason] = []
    if target.status != "succeeded":
        reasons.append(RollbackBlockedReason("promotion_not_succeeded", ROLLBACK_NOT_ELIGIBLE_MESSAGE))
    existing = session.scalar(
        select(CatalogPromotionRollback).where(
            CatalogPromotionRollback.target_promotion_run_id == promotion_run_id,
            CatalogPromotionRollback.status == "succeeded",
        )
    )
    if existing is not None:
        reasons.append(RollbackBlockedReason("already_rolled_back", "This promotion run has already been rolled back."))
    audits = list(
        session.scalars(
            select(CatalogProductChange)
            .where(CatalogProductChange.promotion_run_id == promotion_run_id)
            .order_by(CatalogProductChange.id)
        ).all()
    )
    if not audits:
        reasons.append(RollbackBlockedReason("audit_missing", "Promotion audit data is missing."))
    product_ids = [audit.catalog_product_id for audit in audits]
    products = list(
        session.scalars(
            select(CatalogProduct).where(CatalogProduct.id.in_(product_ids))
        ).all()
    ) if product_ids else []
    return _build_preview(
        target=target,
        audits=audits,
        current_products={product.id: product for product in products},
        extra_reasons=reasons,
    )


def _result_from_run(
    run: CatalogPromotionRollback,
    *,
    created: bool,
    blocked_reasons: list[RollbackBlockedReason] | None = None,
) -> CatalogPromotionRollbackExecutionResult:
    return CatalogPromotionRollbackExecutionResult(
        rollback_run_id=run.id,
        target_promotion_run_id=run.target_promotion_run_id,
        status=run.status,
        created=created,
        preview_hash=run.preview_hash,
        preview_schema_version=(None if run.preview_schema_version is None else int(run.preview_schema_version)),
        restored_count=run.restored_count,
        deleted_count=run.deleted_count,
        conflict_count=run.conflict_count,
        failure_code=run.failure_code,
        safe_failure_message=run.safe_failure_message,
        blocked_reasons=list(blocked_reasons or []),
        started_at=run.started_at,
        completed_at=run.completed_at,
        actor_username=run.actor_username,
    )


def _validate_request(*, confirmation: bool, expected_preview_hash: str) -> None:
    if confirmation is not True:
        raise CatalogPromotionRollbackConfirmationRequiredError()
    if not isinstance(expected_preview_hash, str) or EXPECTED_ROLLBACK_PREVIEW_HASH_PATTERN.fullmatch(expected_preview_hash) is None:
        raise CatalogPromotionRollbackInvalidPreviewHashError()


def _create_terminal_run(
    session: Session,
    *,
    target_promotion_run_id: int,
    status: Literal["blocked", "failed"],
    failure_code: str,
    message: str,
    started_at: datetime,
    preview: CatalogPromotionRollbackPreview | None,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
) -> CatalogPromotionRollback:
    run = CatalogPromotionRollback(
        target_promotion_run_id=target_promotion_run_id,
        status=status,
        preview_hash=None if preview is None else preview.preview_hash,
        preview_schema_version=None if preview is None else str(preview.preview_schema_version),
        restored_count=0,
        deleted_count=0,
        conflict_count=0 if preview is None else preview.conflict_count,
        failure_code=failure_code,
        safe_failure_message=message,
        started_at=started_at,
        completed_at=_utc_now(),
        actor_user_id=actor_user_id,
        actor_username=actor_username,
    )
    session.add(run)
    session.flush()
    return run


def _rollback_session_best_effort(
    session: Session,
    *,
    target_promotion_run_id: int,
) -> None:
    try:
        session.rollback()
    except Exception:
        rollback_logger.exception(
            "failed to roll back catalog promotion rollback session",
            extra={"target_promotion_run_id": target_promotion_run_id},
        )


def _record_failed_run(
    session: Session,
    *,
    target_promotion_run_id: int,
    started_at: datetime,
    preview: CatalogPromotionRollbackPreview | None,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
) -> int | None:
    try:
        with session.begin():
            run = _create_terminal_run(
                session,
                target_promotion_run_id=target_promotion_run_id,
                status="failed",
                failure_code="rollback_apply_failed",
                message=ROLLBACK_FAILED_MESSAGE,
                started_at=started_at,
                preview=preview,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
            )
            return run.id
    except Exception:
        _rollback_session_best_effort(
            session,
            target_promotion_run_id=target_promotion_run_id,
        )
        return None


def execute_catalog_promotion_rollback(
    session: Session,
    *,
    promotion_run_id: int,
    confirmation: bool,
    expected_preview_hash: str,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
) -> CatalogPromotionRollbackExecutionResult:
    _validate_request(confirmation=confirmation, expected_preview_hash=expected_preview_hash)
    started_at = _utc_now()
    preview: CatalogPromotionRollbackPreview | None = None
    try:
        with session.begin():
            target = session.scalars(
                select(CatalogPromotionRun)
                .where(CatalogPromotionRun.id == promotion_run_id)
                .with_for_update()
            ).first()
            if target is None:
                raise CatalogPromotionRollbackNotFoundError(promotion_run_id)
            existing = session.scalars(
                select(CatalogPromotionRollback)
                .where(
                    CatalogPromotionRollback.target_promotion_run_id == promotion_run_id,
                    CatalogPromotionRollback.status == "succeeded",
                )
                .with_for_update()
            ).first()
            if existing is not None:
                raise CatalogPromotionRollbackAlreadyExecutedError(existing.id)
            audits = list(
                session.scalars(
                    select(CatalogProductChange)
                    .where(CatalogProductChange.promotion_run_id == promotion_run_id)
                    .order_by(CatalogProductChange.id)
                    .with_for_update()
                ).all()
            )
            product_ids = [audit.catalog_product_id for audit in audits]
            products = list(
                session.scalars(
                    select(CatalogProduct)
                    .where(CatalogProduct.id.in_(product_ids))
                    .with_for_update()
                ).all()
            ) if product_ids else []
            preview = _build_preview(
                target=target,
                audits=audits,
                current_products={product.id: product for product in products},
                extra_reasons=([] if target.status == "succeeded" else [RollbackBlockedReason("promotion_not_succeeded", ROLLBACK_NOT_ELIGIBLE_MESSAGE)]),
            )
            if not preview.rollback_eligible or preview.preview_hash is None:
                run = _create_terminal_run(
                    session,
                    target_promotion_run_id=promotion_run_id,
                    status="blocked",
                    failure_code="rollback_conflict" if preview.conflict_count else "rollback_not_eligible",
                    message=ROLLBACK_CONFLICT_MESSAGE if preview.conflict_count else ROLLBACK_NOT_ELIGIBLE_MESSAGE,
                    started_at=started_at,
                    preview=preview,
                    actor_user_id=actor_user_id,
                    actor_username=actor_username,
                )
                return _result_from_run(run, created=True, blocked_reasons=preview.blocked_reasons)
            if expected_preview_hash != preview.preview_hash:
                run = _create_terminal_run(
                    session,
                    target_promotion_run_id=promotion_run_id,
                    status="blocked",
                    failure_code="preview_stale",
                    message=ROLLBACK_PREVIEW_STALE_MESSAGE,
                    started_at=started_at,
                    preview=preview,
                    actor_user_id=actor_user_id,
                    actor_username=actor_username,
                )
                return _result_from_run(run, created=True)

            rollback_run = CatalogPromotionRollback(
                target_promotion_run_id=promotion_run_id,
                status="applying",
                preview_hash=preview.preview_hash,
                preview_schema_version=str(preview.preview_schema_version),
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
            )
            session.add(rollback_run)
            session.flush()
            products_by_id = {product.id: product for product in products}
            for item in preview.items:
                product = products_by_id[item.catalog_product_id]
                before = dict(item.current_data or {})
                if item.rollback_action == "delete":
                    session.add(CatalogPromotionRollbackChange(
                        rollback_run_id=rollback_run.id,
                        original_audit_id=item.audit_id,
                        catalog_product_id=product.id,
                        action="delete",
                        changed_fields={field: {"before": before.get(field), "after": None} for field in COMPARISON_FIELDS},
                        before_data=before,
                        after_data=None,
                    ))
                    session.delete(product)
                else:
                    restore = dict(item.restore_data or {})
                    for field in COMPARISON_FIELDS:
                        setattr(product, field, restore[field])
                    product.updated_at = func.now()
                    session.add(CatalogPromotionRollbackChange(
                        rollback_run_id=rollback_run.id,
                        original_audit_id=item.audit_id,
                        catalog_product_id=product.id,
                        action="restore",
                        changed_fields={field: {"before": before.get(field), "after": restore.get(field)} for field in COMPARISON_FIELDS if before.get(field) != restore.get(field)},
                        before_data=before,
                        after_data=restore,
                    ))
            rollback_run.status = "succeeded"
            rollback_run.restored_count = preview.restore_count
            rollback_run.deleted_count = preview.delete_count
            rollback_run.completed_at = _utc_now()
            session.flush()
            return _result_from_run(rollback_run, created=True)
    except (CatalogPromotionRollbackNotFoundError, CatalogPromotionRollbackAlreadyExecutedError):
        raise
    except Exception:
        _rollback_session_best_effort(
            session,
            target_promotion_run_id=promotion_run_id,
        )
        failed_run_id = _record_failed_run(
            session,
            target_promotion_run_id=promotion_run_id,
            started_at=started_at,
            preview=preview,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
        )
        raise CatalogPromotionRollbackExecutionFailedError(failed_run_id) from None
