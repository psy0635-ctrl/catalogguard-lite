"""Catalog Reconciliation Report: staging batch vs the live catalog.

읽기 전용 보고서이므로 DB를 바꾸지 않는 것까지 fake session이 함께 고정합니다.
"""
from __future__ import annotations

from contextlib import nullcontext
from typing import Any

import pytest

from db.catalog_promotion_preview_service import ETLLoadRunNotFoundError
from db.catalog_reconciliation_service import (
    CatalogReconciliationDuplicateIdentityError,
    build_catalog_reconciliation_report,
)
from db.models import CatalogProduct, CatalogProductStaging, ETLLoadRun


SUPPLIER_KEY = "sample_fashion_vendor"


class _ScalarRows:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None


class ReconciliationSession:
    """Minimal in-memory stand-in that mirrors the queries the service issues.

    tests/test_catalog_promotion_preview_service.py의 PreviewSession과 같은 방식입니다.
    운영 카탈로그 전체를 메모리에 올리지 않는 구조를 검증해야 하므로, 이 fake는
    staging id 목록 기준으로 in / not-in 질의를 나눠 처리합니다.
    """

    def __init__(
        self,
        load_run: ETLLoadRun | None,
        *,
        staging: list[CatalogProductStaging] | None = None,
        catalog: list[CatalogProduct] | None = None,
    ):
        self.load_run = load_run
        self.staging = list(staging or [])
        self.catalog = list(catalog or [])
        self.no_autoflush = nullcontext()
        self.count_calls = 0
        self.not_observed_id_calls = 0

    def _staging_ids(self) -> set[str]:
        return {product.product_id for product in self.staging}

    def _not_observed(self) -> list[CatalogProduct]:
        supplier_key = self.load_run.profile_name
        staging_ids = self._staging_ids()
        return sorted(
            (
                product
                for product in self.catalog
                if product.supplier_key == supplier_key
                and product.external_product_id not in staging_ids
            ),
            key=lambda product: product.external_product_id,
        )

    def get(self, model, identity):
        if model is ETLLoadRun and self.load_run is not None:
            if self.load_run.id == identity:
                return self.load_run
        return None

    def scalars(self, statement):
        description = statement.column_descriptions[0]
        entity = description["entity"]
        if entity is CatalogProductStaging:
            return _ScalarRows(self.staging)
        if entity is CatalogProduct:
            supplier_key = self.load_run.profile_name
            staging_ids = self._staging_ids()
            # external_product_id만 고른 질의는 not_observed 페이지 조회입니다.
            if description["name"] == "external_product_id":
                self.not_observed_id_calls += 1
                rows = [
                    product.external_product_id for product in self._not_observed()
                ]
                offset = statement._offset or 0
                limit = statement._limit
                sliced = rows[offset:]
                if limit is not None:
                    sliced = sliced[:limit]
                return _ScalarRows(sliced)
            return _ScalarRows(
                [
                    product
                    for product in self.catalog
                    if product.supplier_key == supplier_key
                    and product.external_product_id in staging_ids
                ]
            )
        raise AssertionError(f"Unexpected query entity: {entity}")

    def scalar(self, _statement):
        self.count_calls += 1
        return len(self._not_observed())

    def add(self, _instance) -> None:
        raise AssertionError("reconciliation must not add database rows")

    def add_all(self, _instances) -> None:
        raise AssertionError("reconciliation must not add database rows")

    def delete(self, _instance) -> None:
        raise AssertionError("reconciliation must not delete database rows")

    def flush(self) -> None:
        raise AssertionError("reconciliation must not flush")

    def commit(self) -> None:
        raise AssertionError("reconciliation must not commit")


def _load_run(**changes) -> ETLLoadRun:
    values = {
        "id": 42,
        "source_filename": "supplier.csv",
        "profile_name": SUPPLIER_KEY,
        "profile_version": "2",
        "input_file_sha256": "a" * 64,
        "output_file_sha256": "b" * 64,
        "loaded_rows": 1,
        "total_rows": 1,
        "rejected_rows": 0,
        "error_counts": {},
        "reject_details_stored": False,
        "rejects_file_sha256": None,
    }
    values.update(changes)
    return ETLLoadRun(**values)


def _staging(product_id: str = "P001", **changes) -> CatalogProductStaging:
    values = {
        "id": 100,
        "etl_load_run_id": 42,
        "product_group_id": f"G-{product_id}",
        "product_id": product_id,
        "product_name": f"Product {product_id}",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 10,
        "price": 19900,
        "sale_price": None,
        "image_path": f"{product_id}.jpg",
        "description": None,
        "seller": None,
    }
    values.update(changes)
    return CatalogProductStaging(**values)


def _catalog(product_id: str = "P001", **changes) -> CatalogProduct:
    values = {
        "id": 200,
        "supplier_key": SUPPLIER_KEY,
        "external_product_id": product_id,
        "product_group_id": f"G-{product_id}",
        "product_name": f"Product {product_id}",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 10,
        "price": 19900,
        "sale_price": None,
        "image_path": f"{product_id}.jpg",
        "description": None,
        "seller": None,
        "source_etl_load_run_id": 7,
    }
    values.update(changes)
    return CatalogProduct(**values)


def _report(session, **kwargs):
    return build_catalog_reconciliation_report(session, etl_load_run_id=42, **kwargs)


# --- ETL 품질 메타데이터 ---------------------------------------------------


def test_report_carries_the_batch_quality_summary():
    # 이 보고서는 원본 feed 전체가 아니라 정상 staging 상품을 비교합니다. 그 범위를
    # 읽는 쪽이 판단할 수 있도록 배치 품질 요약을 함께 돌려줍니다.
    session = ReconciliationSession(
        _load_run(total_rows=3, loaded_rows=2, rejected_rows=1),
        staging=[_staging("P001")],
    )

    report = _report(session)

    assert report.total_rows == 3
    assert report.loaded_rows == 2
    assert report.rejected_rows == 1


def test_rejected_rows_do_not_change_how_statuses_are_calculated():
    # reject가 있어도 상태 계산 로직은 그대로입니다. reject row의 identity를 원본에서
    # 다시 추론하지 않으므로, staging에 없는 상품은 여전히 not_observed_in_batch입니다.
    without_rejects = ReconciliationSession(
        _load_run(total_rows=2, loaded_rows=2, rejected_rows=0),
        staging=[_staging("P001")],
        catalog=[_catalog("P001"), _catalog("P003", id=93)],
    )
    with_rejects = ReconciliationSession(
        _load_run(total_rows=3, loaded_rows=2, rejected_rows=1),
        staging=[_staging("P001")],
        catalog=[_catalog("P001"), _catalog("P003", id=93)],
    )

    baseline = _report(without_rejects)
    rejected = _report(with_rejects)

    assert [
        (item.external_product_id, item.status) for item in rejected.items
    ] == [(item.external_product_id, item.status) for item in baseline.items]
    assert rejected.not_observed_in_batch_count == 1
    assert rejected.new_count == baseline.new_count
    assert rejected.changed_count == baseline.changed_count
    assert rejected.unchanged_count == baseline.unchanged_count


def test_legacy_batch_keeps_null_quality_values_instead_of_zero():
    # 품질 요약 저장 이전 배치입니다. "거부 행이 없었다"와 "알 수 없다"는 다른 사실이라
    # None을 0으로 바꾸지 않습니다.
    session = ReconciliationSession(
        _load_run(total_rows=None, loaded_rows=2, rejected_rows=None, error_counts=None),
        staging=[_staging("P001")],
    )

    report = _report(session)

    assert report.total_rows is None
    assert report.rejected_rows is None
    assert report.loaded_rows == 2
    # 상태 계산은 영향을 받지 않습니다.
    assert report.new_count == 1


# --- 상태 판정 -------------------------------------------------------------


def test_staging_only_product_is_new():
    session = ReconciliationSession(_load_run(), staging=[_staging("P001")])

    report = _report(session)

    assert report.new_count == 1
    assert report.changed_count == 0
    assert report.unchanged_count == 0
    assert report.not_observed_in_batch_count == 0
    assert [(item.external_product_id, item.status) for item in report.items] == [
        ("P001", "new")
    ]
    assert report.items[0].changed_fields == {}
    assert report.supplier_key == SUPPLIER_KEY
    assert report.etl_load_run_id == 42


def test_identical_catalog_and_staging_is_unchanged():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001")],
        catalog=[_catalog("P001")],
    )

    report = _report(session)

    assert report.unchanged_count == 1
    assert report.new_count == 0
    assert report.changed_count == 0
    assert report.items[0].status == "unchanged"
    assert report.items[0].changed_fields == {}
    assert report.field_change_counts == {}


def test_field_difference_is_changed_with_exact_before_and_after():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001", stock=7)],
        catalog=[_catalog("P001", stock=10)],
    )

    report = _report(session)

    assert report.changed_count == 1
    item = report.items[0]
    assert item.status == "changed"
    # before는 현재 운영 카탈로그, after는 이번 배치입니다.
    assert item.changed_fields == {"stock": {"before": 10, "after": 7}}


def test_identity_column_is_never_reported_as_a_changed_field():
    # external_product_id는 identity이므로 비교 대상이 아닙니다.
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001", price=1000)],
        catalog=[_catalog("P001", price=2000)],
    )

    report = _report(session)

    assert "external_product_id" not in report.items[0].changed_fields


# --- 필드별 변경 건수 ------------------------------------------------------


def test_price_changes_are_counted_per_field():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001", id=1, price=1000), _staging("P002", id=2, price=2000)],
        catalog=[
            _catalog("P001", id=11, price=1500),
            _catalog("P002", id=12, price=2500),
        ],
    )

    report = _report(session)

    assert report.field_change_counts == {"price": 2}


def test_stock_changes_are_counted_per_field():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001", stock=1)],
        catalog=[_catalog("P001", stock=9)],
    )

    report = _report(session)

    assert report.field_change_counts == {"stock": 1}


def test_multiple_changed_fields_are_counted_independently():
    session = ReconciliationSession(
        _load_run(),
        staging=[
            _staging("P001", id=1, stock=1, price=1000),
            _staging("P002", id=2, stock=2),
            _staging("P003", id=3, category="BOTTOM"),
        ],
        catalog=[
            _catalog("P001", id=11, stock=9, price=1500),
            _catalog("P002", id=12, stock=8),
            _catalog("P003", id=13, category="TOP"),
        ],
    )

    report = _report(session)

    # 한 상품이 두 필드를 바꾸면 두 필드 모두 1씩 올라갑니다.
    assert report.field_change_counts == {"category": 1, "stock": 2, "price": 1}
    assert report.changed_count == 3


def test_field_change_counts_follow_the_shared_comparison_field_order():
    from db.catalog_promotion_preview_service import COMPARISON_FIELDS

    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001", stock=1, price=1000, category="BOTTOM")],
        catalog=[_catalog("P001", stock=9, price=1500, category="TOP")],
    )

    report = _report(session)

    ordered = [
        field_name
        for field_name in COMPARISON_FIELDS
        if field_name in report.field_change_counts
    ]
    assert list(report.field_change_counts) == ordered


# --- not_observed_in_batch -------------------------------------------------


def test_catalog_only_product_is_not_observed_in_batch():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001")],
        catalog=[_catalog("P001"), _catalog("P900", id=99)],
    )

    report = _report(session)

    assert report.not_observed_in_batch_count == 1
    statuses = {item.external_product_id: item.status for item in report.items}
    assert statuses["P900"] == "not_observed_in_batch"
    # 상품이 배치에 없다는 뜻이지 변경이 아니므로 changed_fields는 비어 있습니다.
    not_observed = next(
        item for item in report.items if item.external_product_id == "P900"
    )
    assert not_observed.changed_fields == {}


def test_empty_staging_batch_still_reports_catalog_products_as_not_observed():
    session = ReconciliationSession(
        _load_run(),
        staging=[],
        catalog=[_catalog("P900", id=99)],
    )

    report = _report(session)

    assert report.new_count == 0
    assert report.not_observed_in_batch_count == 1
    assert [item.status for item in report.items] == ["not_observed_in_batch"]


def test_other_supplier_catalog_products_are_excluded():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001")],
        catalog=[
            _catalog("P001"),
            _catalog("P900", id=98, supplier_key="other_vendor"),
        ],
    )

    report = _report(session)

    assert report.not_observed_in_batch_count == 0
    assert [item.external_product_id for item in report.items] == ["P001"]


# --- 중복 identity ---------------------------------------------------------


def test_duplicate_staging_identity_is_refused_instead_of_picking_one_row():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001", id=1), _staging("P001", id=2, stock=3)],
        catalog=[_catalog("P001")],
    )

    with pytest.raises(CatalogReconciliationDuplicateIdentityError) as error:
        _report(session)

    assert error.value.external_product_ids == ("P001",)


def test_duplicate_identity_error_lists_every_duplicated_id_sorted():
    session = ReconciliationSession(
        _load_run(),
        staging=[
            _staging("P002", id=1),
            _staging("P002", id=2),
            _staging("P001", id=3),
            _staging("P001", id=4),
        ],
    )

    with pytest.raises(CatalogReconciliationDuplicateIdentityError) as error:
        _report(session)

    assert error.value.external_product_ids == ("P001", "P002")


# --- 없는 batch ------------------------------------------------------------


def test_missing_etl_load_run_raises_the_shared_not_found_error():
    session = ReconciliationSession(None)

    with pytest.raises(ETLLoadRunNotFoundError):
        _report(session)


# --- 정렬과 pagination -----------------------------------------------------


def test_items_are_ordered_by_status_then_external_product_id():
    session = ReconciliationSession(
        _load_run(),
        staging=[
            _staging("B-unchanged", id=1),
            _staging("A-unchanged", id=2),
            _staging("B-changed", id=3, stock=1),
            _staging("A-changed", id=4, stock=1),
            _staging("B-new", id=5),
            _staging("A-new", id=6),
        ],
        catalog=[
            _catalog("B-unchanged", id=11),
            _catalog("A-unchanged", id=12),
            _catalog("B-changed", id=13, stock=9),
            _catalog("A-changed", id=14, stock=9),
            _catalog("Z-gone", id=15),
        ],
    )

    report = _report(session)

    assert [item.external_product_id for item in report.items] == [
        "A-new",
        "B-new",
        "A-changed",
        "B-changed",
        "A-unchanged",
        "B-unchanged",
        "Z-gone",
    ]
    assert [item.status for item in report.items] == [
        "new",
        "new",
        "changed",
        "changed",
        "unchanged",
        "unchanged",
        "not_observed_in_batch",
    ]


def test_pagination_slices_the_deterministic_order_without_gaps():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging(f"P{index:03d}", id=index) for index in range(1, 4)],
        catalog=[_catalog(f"C{index:03d}", id=100 + index) for index in range(1, 4)],
    )

    full = _report(session, limit=100, offset=0)
    pages = [
        _report(session, limit=2, offset=0),
        _report(session, limit=2, offset=2),
        _report(session, limit=2, offset=4),
    ]

    paged_ids = [item.external_product_id for page in pages for item in page.items]
    assert paged_ids == [item.external_product_id for item in full.items]
    assert full.total == 6
    assert all(page.total == 6 for page in pages)


def test_counts_and_field_change_counts_are_batch_wide_not_page_wide():
    session = ReconciliationSession(
        _load_run(),
        staging=[
            _staging("P001", id=1, stock=1),
            _staging("P002", id=2, stock=1),
            _staging("P003", id=3, stock=1),
        ],
        catalog=[
            _catalog("P001", id=11, stock=9),
            _catalog("P002", id=12, stock=9),
            _catalog("P003", id=13, stock=9),
        ],
    )

    page = _report(session, limit=1, offset=0)

    assert len(page.items) == 1
    assert page.changed_count == 3
    assert page.field_change_counts == {"stock": 3}
    assert page.limit == 1
    assert page.offset == 0


def test_offset_past_the_end_returns_no_items_but_keeps_counts():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001")],
        catalog=[_catalog("P001"), _catalog("P900", id=99)],
    )

    page = _report(session, limit=50, offset=10)

    assert page.items == []
    assert page.total == 2
    assert page.not_observed_in_batch_count == 1


def test_not_observed_products_are_counted_in_sql_not_loaded_wholesale():
    # 운영 카탈로그가 커져도 미관측 상품 전체를 메모리로 가져오지 않아야 합니다.
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging("P001")],
        catalog=[_catalog("P001")]
        + [_catalog(f"C{index:03d}", id=300 + index) for index in range(1, 10)],
    )

    page = _report(session, limit=2, offset=0)

    assert page.not_observed_in_batch_count == 9
    assert session.count_calls == 1
    assert len(page.items) == 2


def test_page_fully_inside_the_staging_section_skips_the_not_observed_query():
    session = ReconciliationSession(
        _load_run(),
        staging=[_staging(f"P{index:03d}", id=index) for index in range(1, 4)],
        catalog=[_catalog("C001", id=101)],
    )

    page = _report(session, limit=3, offset=0)

    assert [item.status for item in page.items] == ["new", "new", "new"]
    assert session.not_observed_id_calls == 0
