from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Literal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from core.inspection_service import inspect_dataframe
from db.models import (
    CatalogProduct,
    CatalogProductStaging,
    ETLLoadRun,
    ETLRejectedRow,
)


PREVIEW_SCHEMA_VERSION = 1
PRODUCT_DATA_FIELDS = (
    "external_product_id",
    "product_group_id",
    "product_name",
    "category",
    "color",
    "size",
    "stock",
    "price",
    "sale_price",
    "image_path",
    "description",
    "seller",
)
COMPARISON_FIELDS = PRODUCT_DATA_FIELDS[1:]
INSPECTION_FIELDS = (
    "product_group_id",
    "product_id",
    "product_name",
    "category",
    "color",
    "size",
    "stock",
    "price",
    "sale_price",
    "image_path",
    "description",
    "seller",
)

ProductValue = str | int | None
PromotionAction = Literal["insert", "update", "unchanged"]


class ETLLoadRunNotFoundError(LookupError):
    def __init__(self, etl_load_run_id: int):
        self.etl_load_run_id = etl_load_run_id
        super().__init__(f"ETL load run {etl_load_run_id} was not found.")


@dataclass(frozen=True)
class PromotionPreviewBlockedReason:
    code: str
    message: str
    supplier_key: str | None = None
    external_product_id: str | None = None
    staging_product_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class PromotionPreviewItem:
    supplier_key: str
    external_product_id: str
    action: PromotionAction
    changed_fields: dict[str, dict[str, ProductValue]]
    before_data: dict[str, ProductValue] | None
    after_data: dict[str, ProductValue]


@dataclass(frozen=True)
class CatalogPromotionPreview:
    etl_load_run_id: int
    supplier_key: str
    inspection_version: str
    preview_schema_version: int
    preview_hash: str | None
    promotion_eligible: bool
    blocked_reasons: list[PromotionPreviewBlockedReason]
    insert_count: int
    update_count: int
    unchanged_count: int
    error_count: int
    warning_count: int
    items: list[PromotionPreviewItem]


def _normalize_integer(value: object, *, nullable: bool) -> int | None:
    if value is None:
        if nullable:
            return None
        raise ValueError("Required numeric catalog value cannot be null.")
    if isinstance(value, bool):
        raise ValueError("Boolean catalog values are not valid integers.")
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric_value = float(value)
        if math.isfinite(numeric_value) and numeric_value.is_integer():
            return int(numeric_value)
        raise ValueError("Catalog numeric values must be whole numbers.")
    if isinstance(value, str):
        cleaned_value = value.strip()
        try:
            return int(cleaned_value)
        except ValueError as error:
            raise ValueError("Catalog numeric strings must contain an integer.") from error
    raise ValueError("Unsupported catalog numeric value.")


def _product_data(
    product: CatalogProductStaging | CatalogProduct,
) -> dict[str, ProductValue]:
    external_product_id = (
        product.product_id
        if isinstance(product, CatalogProductStaging)
        else product.external_product_id
    )
    return {
        "external_product_id": external_product_id,
        "product_group_id": product.product_group_id,
        "product_name": product.product_name,
        "category": product.category,
        "color": product.color,
        "size": product.size,
        "stock": _normalize_integer(product.stock, nullable=False),
        "price": _normalize_integer(product.price, nullable=False),
        "sale_price": _normalize_integer(product.sale_price, nullable=True),
        "image_path": product.image_path,
        "description": product.description,
        "seller": product.seller,
    }


def _inspection_dataframe(
    staging_products: list[CatalogProductStaging],
) -> pd.DataFrame:
    rows = []
    for product in staging_products:
        product_data = _product_data(product)
        rows.append(
            {
                "product_group_id": product_data["product_group_id"],
                "product_id": product_data["external_product_id"],
                "product_name": product_data["product_name"],
                "category": product_data["category"],
                "color": product_data["color"],
                "size": product_data["size"],
                "stock": product_data["stock"],
                "price": product_data["price"],
                "sale_price": product_data["sale_price"],
                "image_path": product_data["image_path"],
                "description": product_data["description"],
                "seller": product_data["seller"],
            }
        )
    return pd.DataFrame(rows, columns=INSPECTION_FIELDS, dtype=object)


def _duplicate_identity_reasons(
    supplier_key: str,
    staging_products: list[CatalogProductStaging],
) -> list[PromotionPreviewBlockedReason]:
    staging_ids_by_product_id: dict[str, list[int]] = {}
    for product in staging_products:
        staging_ids_by_product_id.setdefault(product.product_id, []).append(product.id)

    return [
        PromotionPreviewBlockedReason(
            code="duplicate_product_identity",
            message="같은 공급사 상품 식별자가 배치 안에 중복되어 있습니다.",
            supplier_key=supplier_key,
            external_product_id=external_product_id,
            staging_product_ids=tuple(sorted(staging_product_ids)),
        )
        for external_product_id, staging_product_ids in sorted(
            staging_ids_by_product_id.items()
        )
        if len(staging_product_ids) > 1
    ]


def _canonical_preview_hash(
    *,
    etl_load_run_id: int,
    supplier_key: str,
    inspection_version: str,
    staging_products: list[CatalogProductStaging],
    catalog_by_external_id: dict[str, CatalogProduct],
) -> str:
    products = []
    for staging_product in sorted(
        staging_products,
        key=lambda product: (supplier_key, product.product_id),
    ):
        current_catalog = catalog_by_external_id.get(staging_product.product_id)
        products.append(
            {
                "external_product_id": staging_product.product_id,
                "target": _product_data(staging_product),
                "current_catalog": (
                    None
                    if current_catalog is None
                    else _product_data(current_catalog)
                ),
            }
        )
    payload = {
        "preview_schema_version": PREVIEW_SCHEMA_VERSION,
        "inspection_version": inspection_version,
        "etl_load_run_id": etl_load_run_id,
        "supplier_key": supplier_key,
        "products": products,
    }
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _preview_items(
    *,
    supplier_key: str,
    staging_products: list[CatalogProductStaging],
    catalog_by_external_id: dict[str, CatalogProduct],
) -> list[PromotionPreviewItem]:
    items = []
    for staging_product in sorted(
        staging_products,
        key=lambda product: (supplier_key, product.product_id),
    ):
        after_data = _product_data(staging_product)
        current_catalog = catalog_by_external_id.get(staging_product.product_id)
        if current_catalog is None:
            items.append(
                PromotionPreviewItem(
                    supplier_key=supplier_key,
                    external_product_id=staging_product.product_id,
                    action="insert",
                    changed_fields={},
                    before_data=None,
                    after_data=after_data,
                )
            )
            continue

        before_data = _product_data(current_catalog)
        changed_fields = {
            field_name: {
                "before": before_data[field_name],
                "after": after_data[field_name],
            }
            for field_name in COMPARISON_FIELDS
            if before_data[field_name] != after_data[field_name]
        }
        items.append(
            PromotionPreviewItem(
                supplier_key=supplier_key,
                external_product_id=staging_product.product_id,
                action="update" if changed_fields else "unchanged",
                changed_fields=changed_fields,
                before_data=before_data,
                after_data=after_data,
            )
        )
    return items


def preview_catalog_promotion(
    session: Session,
    *,
    etl_load_run_id: int,
) -> CatalogPromotionPreview:
    inspection_version = settings.INSPECTION_VERSION
    blocked_reasons: list[PromotionPreviewBlockedReason] = []

    with session.no_autoflush:
        load_run = session.get(ETLLoadRun, etl_load_run_id)
        if load_run is None:
            raise ETLLoadRunNotFoundError(etl_load_run_id)

        if any(
            value is None
            for value in (
                load_run.total_rows,
                load_run.rejected_rows,
                load_run.error_counts,
            )
        ):
            blocked_reasons.append(
                PromotionPreviewBlockedReason(
                    code="quality_summary_missing",
                    message="ETL 품질 요약이 없는 배치는 운영 반영할 수 없습니다.",
                )
            )

        rejected_row = session.scalars(
            select(ETLRejectedRow)
            .where(ETLRejectedRow.etl_load_run_id == etl_load_run_id)
            .limit(1)
        ).first()
        if (load_run.rejected_rows or 0) > 0 or rejected_row is not None:
            blocked_reasons.append(
                PromotionPreviewBlockedReason(
                    code="etl_rejections_present",
                    message=(
                        "변환이 거부된 상품 행이 있어 운영 반영을 진행할 수 없습니다."
                    ),
                )
            )

        staging_products = list(
            session.scalars(
                select(CatalogProductStaging).where(
                    CatalogProductStaging.etl_load_run_id == etl_load_run_id
                )
            ).all()
        )
        if not staging_products:
            blocked_reasons.append(
                PromotionPreviewBlockedReason(
                    code="empty_staging_batch",
                    message="반영할 정상 staging 상품이 없습니다.",
                )
            )

        duplicate_reasons = _duplicate_identity_reasons(
            load_run.profile_name,
            staging_products,
        )
        blocked_reasons.extend(duplicate_reasons)
        if duplicate_reasons:
            return CatalogPromotionPreview(
                etl_load_run_id=load_run.id,
                supplier_key=load_run.profile_name,
                inspection_version=inspection_version,
                preview_schema_version=PREVIEW_SCHEMA_VERSION,
                preview_hash=None,
                promotion_eligible=False,
                blocked_reasons=blocked_reasons,
                insert_count=0,
                update_count=0,
                unchanged_count=0,
                error_count=0,
                warning_count=0,
                items=[],
            )

        error_count = 0
        warning_count = 0
        if staging_products:
            inspection_report = inspect_dataframe(
                _inspection_dataframe(staging_products)
            )
            error_count = inspection_report.summary.error_count
            warning_count = inspection_report.summary.warning_count
            if error_count > 0:
                blocked_reasons.append(
                    PromotionPreviewBlockedReason(
                        code="inspection_errors_present",
                        message=(
                            "상품 검수 오류가 있어 운영 반영을 진행할 수 없습니다."
                        ),
                    )
                )

        external_product_ids = [
            product.product_id for product in staging_products
        ]
        catalog_products = []
        if external_product_ids:
            catalog_products = list(
                session.scalars(
                    select(CatalogProduct).where(
                        CatalogProduct.supplier_key == load_run.profile_name,
                        CatalogProduct.external_product_id.in_(external_product_ids),
                    )
                ).all()
            )
        catalog_by_external_id = {
            product.external_product_id: product for product in catalog_products
        }
        preview_hash = _canonical_preview_hash(
            etl_load_run_id=load_run.id,
            supplier_key=load_run.profile_name,
            inspection_version=inspection_version,
            staging_products=staging_products,
            catalog_by_external_id=catalog_by_external_id,
        )

        if blocked_reasons:
            return CatalogPromotionPreview(
                etl_load_run_id=load_run.id,
                supplier_key=load_run.profile_name,
                inspection_version=inspection_version,
                preview_schema_version=PREVIEW_SCHEMA_VERSION,
                preview_hash=preview_hash,
                promotion_eligible=False,
                blocked_reasons=blocked_reasons,
                insert_count=0,
                update_count=0,
                unchanged_count=0,
                error_count=error_count,
                warning_count=warning_count,
                items=[],
            )

        items = _preview_items(
            supplier_key=load_run.profile_name,
            staging_products=staging_products,
            catalog_by_external_id=catalog_by_external_id,
        )
        return CatalogPromotionPreview(
            etl_load_run_id=load_run.id,
            supplier_key=load_run.profile_name,
            inspection_version=inspection_version,
            preview_schema_version=PREVIEW_SCHEMA_VERSION,
            preview_hash=preview_hash,
            promotion_eligible=True,
            blocked_reasons=[],
            insert_count=sum(item.action == "insert" for item in items),
            update_count=sum(item.action == "update" for item in items),
            unchanged_count=sum(item.action == "unchanged" for item in items),
            error_count=error_count,
            warning_count=warning_count,
            items=items,
        )
