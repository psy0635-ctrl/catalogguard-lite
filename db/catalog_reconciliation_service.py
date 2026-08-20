"""Read-only comparison of one ETL staging batch against the live catalog.

"선택한 ETL 배치에서 정상 staging에 적재된 상품이 지금 운영 카탈로그와 어떻게 다른가"에
답하는 보고서입니다. 원본 supplier feed 전체가 아니라 CatalogProductStaging을 기준으로
비교하므로, ETL 변환에서 거부된 행은 비교 대상에 들어오지 않습니다.

Promotion Preview와 목적이 다릅니다. Preview는 "이 배치를 반영해도 되는가"를 판정하며
staging에 있는 상품만 봅니다. 여기서는 반영 여부를 판정하지 않고, staging에 없지만
카탈로그에 남아 있는 상품(not_observed_in_batch)까지 포함해 차이를 설명합니다.

비교 필드와 값 정규화는 db.catalog_promotion_preview_service의 계약을 그대로 씁니다.
같은 로직을 복제하면 두 화면이 서로 다른 "변경"을 말하게 되기 때문입니다. 이 모듈은
preview의 동작·hash·eligibility를 읽기만 하고 바꾸지 않습니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.catalog_promotion_preview_service import (
    COMPARISON_FIELDS,
    ETLLoadRunNotFoundError,
    ProductValue,
    _product_data,
)
from db.models import CatalogProduct, CatalogProductStaging, ETLLoadRun


ReconciliationStatus = Literal[
    "new",
    "changed",
    "unchanged",
    "not_observed_in_batch",
]

# 표시 순서를 코드 한 곳에서 정합니다. 운영자가 먼저 봐야 할 차이가 위로 옵니다.
STATUS_ORDER: tuple[ReconciliationStatus, ...] = (
    "new",
    "changed",
    "unchanged",
    "not_observed_in_batch",
)
_STATUS_PRIORITY = {status: index for index, status in enumerate(STATUS_ORDER)}

DEFAULT_ITEM_LIMIT = 50
MAX_ITEM_LIMIT = 100


class CatalogReconciliationDuplicateIdentityError(ValueError):
    """Raised when one staging batch carries the same product identity twice.

    Promotion Preview는 같은 상황을 duplicate_product_identity로 막습니다. 여기서도
    같은 안전 철학을 씁니다. 어느 행이 진짜인지 시스템이 알 수 없으므로 첫 번째나
    마지막 행을 임의로 고르지 않고 보고서 생성을 거부합니다. 임의로 골랐다면 운영자가
    보는 diff가 실제와 달라지고, 그 사실이 화면에 드러나지도 않습니다.
    """

    def __init__(self, external_product_ids: tuple[str, ...]):
        self.external_product_ids = external_product_ids
        super().__init__(
            "Duplicate product identity in staging batch: "
            + ", ".join(external_product_ids)
        )


@dataclass(frozen=True)
class CatalogReconciliationItem:
    external_product_id: str
    status: ReconciliationStatus
    # changed일 때만 채웁니다. new/unchanged/not_observed_in_batch는 항상 빈 dict입니다.
    changed_fields: dict[str, dict[str, ProductValue]] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogReconciliationReport:
    etl_load_run_id: int
    supplier_key: str
    # ETLLoadRun이 이미 가진 품질 요약을 그대로 전달합니다. 이 보고서가 비교하는 것은
    # 원본 feed 전체가 아니라 staging에 정상 적재된 상품이므로, 그 범위를 읽는 사람이
    # 판단할 수 있어야 합니다. loaded_rows는 NOT NULL이고 total_rows/rejected_rows는
    # 품질 요약 저장 이전 legacy 배치에서 None일 수 있습니다. None을 0으로 바꾸지
    # 않습니다. "거부 행이 없었다"와 "알 수 없다"는 다른 사실입니다.
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    new_count: int
    changed_count: int
    unchanged_count: int
    not_observed_in_batch_count: int
    field_change_counts: dict[str, int]
    items: list[CatalogReconciliationItem]
    total: int
    limit: int
    offset: int


def _duplicate_external_product_ids(
    staging_products: list[CatalogProductStaging],
) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    for product in staging_products:
        counts[product.product_id] = counts.get(product.product_id, 0) + 1
    return tuple(
        sorted(
            external_product_id
            for external_product_id, count in counts.items()
            if count > 1
        )
    )


def _staging_derived_items(
    *,
    staging_products: list[CatalogProductStaging],
    catalog_by_external_id: dict[str, CatalogProduct],
) -> list[CatalogReconciliationItem]:
    """Classify every staging row as new / changed / unchanged.

    not_observed_in_batch는 여기서 나오지 않습니다. staging에 없는 상품이므로 DB에서
    따로 세고 필요한 페이지만 읽습니다.
    """
    items: list[CatalogReconciliationItem] = []
    for staging_product in staging_products:
        external_product_id = staging_product.product_id
        current_catalog = catalog_by_external_id.get(external_product_id)
        if current_catalog is None:
            items.append(
                CatalogReconciliationItem(
                    external_product_id=external_product_id,
                    status="new",
                    changed_fields={},
                )
            )
            continue

        after_data = _product_data(staging_product)
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
            CatalogReconciliationItem(
                external_product_id=external_product_id,
                status="changed" if changed_fields else "unchanged",
                changed_fields=changed_fields,
            )
        )
    return sorted(
        items,
        key=lambda item: (_STATUS_PRIORITY[item.status], item.external_product_id),
    )


def _field_change_counts(
    items: list[CatalogReconciliationItem],
) -> dict[str, int]:
    """Count how many products changed per field, in COMPARISON_FIELDS order."""
    counts: dict[str, int] = {}
    for item in items:
        for field_name in item.changed_fields:
            counts[field_name] = counts.get(field_name, 0) + 1
    return {
        field_name: counts[field_name]
        for field_name in COMPARISON_FIELDS
        if field_name in counts
    }


def build_catalog_reconciliation_report(
    session: Session,
    *,
    etl_load_run_id: int,
    limit: int = DEFAULT_ITEM_LIMIT,
    offset: int = 0,
) -> CatalogReconciliationReport:
    """Compare one staging batch with the live catalog for the same supplier.

    비교 기준은 원본 CSV가 아니라 staging에 정상 적재된 상품입니다. 그래서 배치의
    품질 요약(total_rows/loaded_rows/rejected_rows)을 함께 돌려줍니다. reject가 있으면
    "이번 배치 미관측"에 원본에는 있었지만 거부되어 staging에 없는 상품이 섞일 수
    있는데, 그 가능성을 읽는 사람이 알 수 있어야 하기 때문입니다.

    reject된 행의 상품 식별자를 원본에서 다시 추론하지 않습니다. reject raw data에는
    마스킹 대상 원본 값이 들어 있어 이 보고서와 join하면 노출 위험이 생깁니다.

    읽기 전용입니다. CatalogProduct/CatalogProductStaging/ETLLoadRun을 수정하지 않습니다.

    운영 카탈로그는 배치보다 훨씬 커질 수 있으므로 전체를 Python list로 들고 오지
    않습니다. staging 배치 크기만큼만 메모리에서 분류하고, not_observed_in_batch는
    DB에서 개수를 세고 요청한 페이지 구간만 읽습니다.
    """
    with session.no_autoflush:
        load_run = session.get(ETLLoadRun, etl_load_run_id)
        if load_run is None:
            raise ETLLoadRunNotFoundError(etl_load_run_id)

        supplier_key = load_run.profile_name
        staging_products = list(
            session.scalars(
                select(CatalogProductStaging).where(
                    CatalogProductStaging.etl_load_run_id == etl_load_run_id
                )
            ).all()
        )

        duplicate_ids = _duplicate_external_product_ids(staging_products)
        if duplicate_ids:
            raise CatalogReconciliationDuplicateIdentityError(duplicate_ids)

        staging_external_ids = [product.product_id for product in staging_products]

        # supplier_key로 먼저 좁힙니다. 다른 공급사의 상품은 이 보고서에 들어오지 않습니다.
        catalog_products: list[CatalogProduct] = []
        if staging_external_ids:
            catalog_products = list(
                session.scalars(
                    select(CatalogProduct).where(
                        CatalogProduct.supplier_key == supplier_key,
                        CatalogProduct.external_product_id.in_(staging_external_ids),
                    )
                ).all()
            )
        catalog_by_external_id = {
            product.external_product_id: product for product in catalog_products
        }

        observed_items = _staging_derived_items(
            staging_products=staging_products,
            catalog_by_external_id=catalog_by_external_id,
        )

        not_observed_filters = [CatalogProduct.supplier_key == supplier_key]
        if staging_external_ids:
            not_observed_filters.append(
                CatalogProduct.external_product_id.notin_(staging_external_ids)
            )
        not_observed_count = int(
            session.scalar(
                select(func.count())
                .select_from(CatalogProduct)
                .where(*not_observed_filters)
            )
            or 0
        )

        # STATUS_ORDER에서 not_observed_in_batch가 마지막이므로, 전체 정렬은
        # [staging 기반 항목] + [미관측 항목]이 됩니다. 덕분에 페이지 구간을 두 조각으로
        # 나눠 읽을 수 있고 카탈로그 전체를 메모리에 올리지 않아도 됩니다.
        page_items = observed_items[offset : offset + limit]
        remaining = limit - len(page_items)
        if remaining > 0 and not_observed_count > 0:
            not_observed_offset = max(0, offset - len(observed_items))
            if not_observed_offset < not_observed_count:
                not_observed_ids = list(
                    session.scalars(
                        select(CatalogProduct.external_product_id)
                        .where(*not_observed_filters)
                        .order_by(CatalogProduct.external_product_id.asc())
                        .limit(remaining)
                        .offset(not_observed_offset)
                    ).all()
                )
                page_items = page_items + [
                    CatalogReconciliationItem(
                        external_product_id=external_product_id,
                        status="not_observed_in_batch",
                        changed_fields={},
                    )
                    for external_product_id in not_observed_ids
                ]

        return CatalogReconciliationReport(
            etl_load_run_id=load_run.id,
            supplier_key=supplier_key,
            total_rows=load_run.total_rows,
            loaded_rows=load_run.loaded_rows,
            rejected_rows=load_run.rejected_rows,
            new_count=sum(item.status == "new" for item in observed_items),
            changed_count=sum(item.status == "changed" for item in observed_items),
            unchanged_count=sum(item.status == "unchanged" for item in observed_items),
            not_observed_in_batch_count=not_observed_count,
            # 필드별 건수는 페이지가 아니라 배치 전체 기준입니다.
            field_change_counts=_field_change_counts(observed_items),
            items=page_items,
            total=len(observed_items) + not_observed_count,
            limit=limit,
            offset=offset,
        )
