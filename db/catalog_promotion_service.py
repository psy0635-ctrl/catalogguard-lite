from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.catalog_promotion_preview_service import (
    COMPARISON_FIELDS,
    CatalogPromotionPreview,
    ETLLoadRunNotFoundError,
    PromotionPreviewBlockedReason,
    PromotionPreviewItem,
    preview_catalog_promotion,
)
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogProductStaging,
    CatalogPromotionRun,
    ETLLoadRun,
)


EXPECTED_PREVIEW_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CONFIRMATION_REQUIRED_MESSAGE = (
    "운영 상품 반영을 위해 명시적인 승인이 필요합니다."
)
PROMOTION_BLOCKED_MESSAGE = "현재 데이터는 운영 반영 조건을 충족하지 않습니다."
PREVIEW_STALE_MESSAGE = (
    "미리보기 이후 데이터가 변경되었습니다. 새로운 preview를 확인해 주세요."
)
PROMOTION_FAILED_MESSAGE = "운영 상품 반영 중 오류가 발생했습니다."

PromotionExecutionStatus = Literal["succeeded", "blocked"]


class CatalogPromotionConfirmationRequiredError(ValueError):
    def __init__(self):
        super().__init__(CONFIRMATION_REQUIRED_MESSAGE)


class CatalogPromotionInvalidPreviewHashError(ValueError):
    def __init__(self):
        super().__init__(
            "expected_preview_hash must be a 64 character lowercase SHA-256 hex string"
        )


class CatalogPromotionExecutionFailedError(RuntimeError):
    def __init__(self, promotion_run_id: int | None):
        self.promotion_run_id = promotion_run_id
        super().__init__(PROMOTION_FAILED_MESSAGE)


@dataclass(frozen=True)
class CatalogPromotionExecutionResult:
    promotion_run_id: int
    etl_load_run_id: int
    status: PromotionExecutionStatus
    created: bool
    preview_hash: str | None
    preview_schema_version: int | None
    inspection_version: str | None
    inserted_count: int
    updated_count: int
    unchanged_count: int
    blocked_count: int
    error_count: int
    warning_count: int
    failure_code: str | None
    safe_failure_message: str | None
    blocked_reasons: list[PromotionPreviewBlockedReason]
    started_at: datetime | None
    completed_at: datetime | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _validate_request(
    *,
    confirmation: bool,
    expected_preview_hash: str,
) -> None:
    if confirmation is not True:
        raise CatalogPromotionConfirmationRequiredError()
    if not isinstance(
        expected_preview_hash, str
    ) or EXPECTED_PREVIEW_HASH_PATTERN.fullmatch(expected_preview_hash) is None:
        raise CatalogPromotionInvalidPreviewHashError()


def _result_from_run(
    run: CatalogPromotionRun,
    *,
    created: bool,
    blocked_reasons: list[PromotionPreviewBlockedReason] | None = None,
) -> CatalogPromotionExecutionResult:
    preview_schema_version = (
        None
        if run.preview_schema_version is None
        else int(run.preview_schema_version)
    )
    return CatalogPromotionExecutionResult(
        promotion_run_id=run.id,
        etl_load_run_id=run.etl_load_run_id,
        status=run.status,
        created=created,
        preview_hash=run.preview_hash,
        preview_schema_version=preview_schema_version,
        inspection_version=run.inspection_version,
        inserted_count=run.inserted_count,
        updated_count=run.updated_count,
        unchanged_count=run.unchanged_count,
        blocked_count=run.blocked_count,
        error_count=run.error_count,
        warning_count=run.warning_count,
        failure_code=run.failure_code,
        safe_failure_message=run.safe_failure_message,
        blocked_reasons=list(blocked_reasons or []),
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _create_terminal_run(
    session: Session,
    *,
    etl_load_run_id: int,
    status: Literal["blocked", "failed"],
    failure_code: str,
    safe_failure_message: str,
    started_at: datetime,
    completed_at: datetime,
    preview: CatalogPromotionPreview | None,
    blocked_count: int,
) -> CatalogPromotionRun:
    run = CatalogPromotionRun(
        etl_load_run_id=etl_load_run_id,
        status=status,
        preview_hash=None if preview is None else preview.preview_hash,
        preview_schema_version=(
            None if preview is None else str(preview.preview_schema_version)
        ),
        inspection_version=(
            None if preview is None else preview.inspection_version
        ),
        inserted_count=0,
        updated_count=0,
        unchanged_count=0,
        blocked_count=blocked_count,
        error_count=0 if preview is None else preview.error_count,
        warning_count=0 if preview is None else preview.warning_count,
        failure_code=failure_code,
        safe_failure_message=safe_failure_message,
        started_at=started_at,
        completed_at=completed_at,
    )
    session.add(run)
    session.flush()
    return run


def _create_catalog_product_change(
    session: Session,
    *,
    promotion_run_id: int,
    catalog_product_id: int,
    action: Literal["insert", "update"],
    changed_fields: dict[str, dict[str, str | int | None]],
    before_data: dict[str, str | int | None] | None,
    after_data: dict[str, str | int | None],
) -> None:
    session.add(
        CatalogProductChange(
            promotion_run_id=promotion_run_id,
            catalog_product_id=catalog_product_id,
            action=action,
            changed_fields=changed_fields,
            before_data=before_data,
            after_data=after_data,
        )
    )


def _insert_catalog_product(
    session: Session,
    *,
    promotion_run_id: int,
    etl_load_run_id: int,
    item: PromotionPreviewItem,
) -> CatalogProduct:
    data = item.after_data
    product = CatalogProduct(
        supplier_key=item.supplier_key,
        external_product_id=item.external_product_id,
        product_group_id=data["product_group_id"],
        product_name=data["product_name"],
        category=data["category"],
        color=data["color"],
        size=data["size"],
        stock=data["stock"],
        price=data["price"],
        sale_price=data["sale_price"],
        image_path=data["image_path"],
        description=data["description"],
        seller=data["seller"],
        source_etl_load_run_id=etl_load_run_id,
    )
    session.add(product)
    session.flush()
    changed_fields = {
        field_name: {
            "before": None,
            "after": data[field_name],
        }
        for field_name in COMPARISON_FIELDS
    }
    _create_catalog_product_change(
        session,
        promotion_run_id=promotion_run_id,
        catalog_product_id=product.id,
        action="insert",
        changed_fields=changed_fields,
        before_data=None,
        after_data=dict(data),
    )
    return product


def _update_catalog_product(
    session: Session,
    *,
    promotion_run_id: int,
    etl_load_run_id: int,
    product: CatalogProduct,
    item: PromotionPreviewItem,
) -> None:
    if item.before_data is None or not item.changed_fields:
        raise RuntimeError("Invalid update preview item.")

    for field_name in COMPARISON_FIELDS:
        setattr(product, field_name, item.after_data[field_name])
    product.source_etl_load_run_id = etl_load_run_id
    product.updated_at = func.now()
    _create_catalog_product_change(
        session,
        promotion_run_id=promotion_run_id,
        catalog_product_id=product.id,
        action="update",
        changed_fields={
            field_name: dict(change)
            for field_name, change in item.changed_fields.items()
        },
        before_data=dict(item.before_data),
        after_data=dict(item.after_data),
    )


def _record_failed_run(
    session: Session,
    *,
    etl_load_run_id: int,
    started_at: datetime,
    preview: CatalogPromotionPreview | None,
) -> int | None:
    try:
        with session.begin():
            run = _create_terminal_run(
                session,
                etl_load_run_id=etl_load_run_id,
                status="failed",
                failure_code="promotion_apply_failed",
                safe_failure_message=PROMOTION_FAILED_MESSAGE,
                started_at=started_at,
                completed_at=_utc_now(),
                preview=preview,
                blocked_count=0,
            )
            return run.id
    except Exception:
        session.rollback()
        return None


def execute_catalog_promotion(
    session: Session,
    *,
    etl_load_run_id: int,
    confirmation: bool,
    expected_preview_hash: str,
) -> CatalogPromotionExecutionResult:
    _validate_request(
        confirmation=confirmation,
        expected_preview_hash=expected_preview_hash,
    )

    started_at = _utc_now()
    preview: CatalogPromotionPreview | None = None
    locked_load_run_id: int | None = None
    try:
        with session.begin():
            load_run = session.scalars(
                select(ETLLoadRun)
                .where(ETLLoadRun.id == etl_load_run_id)
                .with_for_update()
            ).first()
            if load_run is None:
                raise ETLLoadRunNotFoundError(etl_load_run_id)
            locked_load_run_id = load_run.id

            existing_run = session.scalars(
                select(CatalogPromotionRun)
                .where(
                    CatalogPromotionRun.etl_load_run_id == etl_load_run_id,
                    CatalogPromotionRun.status == "succeeded",
                )
                .order_by(CatalogPromotionRun.id)
                .limit(1)
            ).first()
            if existing_run is not None:
                return _result_from_run(existing_run, created=False)

            staging_products = list(
                session.scalars(
                    select(CatalogProductStaging)
                    .where(
                        CatalogProductStaging.etl_load_run_id
                        == etl_load_run_id
                    )
                    .order_by(
                        CatalogProductStaging.product_id,
                        CatalogProductStaging.id,
                    )
                    .with_for_update()
                ).all()
            )
            external_product_ids = sorted(
                {product.product_id for product in staging_products}
            )
            catalog_products: list[CatalogProduct] = []
            if external_product_ids:
                catalog_products = list(
                    session.scalars(
                        select(CatalogProduct)
                        .where(
                            CatalogProduct.supplier_key
                            == load_run.profile_name,
                            CatalogProduct.external_product_id.in_(
                                external_product_ids
                            ),
                        )
                        .order_by(
                            CatalogProduct.supplier_key,
                            CatalogProduct.external_product_id,
                        )
                        .with_for_update()
                    ).all()
                )

            preview = preview_catalog_promotion(
                session,
                etl_load_run_id=etl_load_run_id,
            )
            if (
                not preview.promotion_eligible
                or preview.blocked_reasons
                or preview.preview_hash is None
            ):
                blocked_run = _create_terminal_run(
                    session,
                    etl_load_run_id=etl_load_run_id,
                    status="blocked",
                    failure_code="promotion_blocked",
                    safe_failure_message=PROMOTION_BLOCKED_MESSAGE,
                    started_at=started_at,
                    completed_at=_utc_now(),
                    preview=preview,
                    blocked_count=len(staging_products),
                )
                return _result_from_run(
                    blocked_run,
                    created=True,
                    blocked_reasons=preview.blocked_reasons,
                )

            if expected_preview_hash != preview.preview_hash:
                stale_run = _create_terminal_run(
                    session,
                    etl_load_run_id=etl_load_run_id,
                    status="blocked",
                    failure_code="preview_stale",
                    safe_failure_message=PREVIEW_STALE_MESSAGE,
                    started_at=started_at,
                    completed_at=_utc_now(),
                    preview=preview,
                    blocked_count=len(staging_products),
                )
                return _result_from_run(stale_run, created=True)

            promotion_run = CatalogPromotionRun(
                etl_load_run_id=etl_load_run_id,
                status="applying",
                preview_hash=preview.preview_hash,
                preview_schema_version=str(preview.preview_schema_version),
                inspection_version=preview.inspection_version,
                inserted_count=0,
                updated_count=0,
                unchanged_count=0,
                blocked_count=0,
                error_count=preview.error_count,
                warning_count=preview.warning_count,
                failure_code=None,
                safe_failure_message=None,
                started_at=started_at,
                completed_at=None,
            )
            session.add(promotion_run)
            session.flush()

            catalog_by_external_id = {
                product.external_product_id: product
                for product in catalog_products
            }
            inserted_count = 0
            updated_count = 0
            unchanged_count = 0
            for item in preview.items:
                if item.action == "insert":
                    product = _insert_catalog_product(
                        session,
                        promotion_run_id=promotion_run.id,
                        etl_load_run_id=etl_load_run_id,
                        item=item,
                    )
                    catalog_by_external_id[item.external_product_id] = product
                    inserted_count += 1
                elif item.action == "update":
                    product = catalog_by_external_id.get(
                        item.external_product_id
                    )
                    if product is None:
                        raise RuntimeError("Locked catalog product is missing.")
                    _update_catalog_product(
                        session,
                        promotion_run_id=promotion_run.id,
                        etl_load_run_id=etl_load_run_id,
                        product=product,
                        item=item,
                    )
                    updated_count += 1
                else:
                    unchanged_count += 1

            promotion_run.status = "succeeded"
            promotion_run.inserted_count = inserted_count
            promotion_run.updated_count = updated_count
            promotion_run.unchanged_count = unchanged_count
            promotion_run.completed_at = _utc_now()
            session.flush()
            return _result_from_run(promotion_run, created=True)
    except ETLLoadRunNotFoundError:
        raise
    except Exception:
        session.rollback()
        failed_run_id = None
        if locked_load_run_id is not None:
            failed_run_id = _record_failed_run(
                session,
                etl_load_run_id=locked_load_run_id,
                started_at=started_at,
                preview=preview,
            )
        raise CatalogPromotionExecutionFailedError(failed_run_id) from None
