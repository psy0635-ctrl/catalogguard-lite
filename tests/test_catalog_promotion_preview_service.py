from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from dataclasses import asdict
from typing import Any
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import delete, func, select

from config.database import get_optional_database_url
from config import settings
from db.session import create_database_engine, create_session_factory
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogProductStaging,
    CatalogPromotionRun,
    ETLLoadRun,
    ETLRejectedRow,
    InspectionResult,
    InspectionRun,
)


class _ScalarRows:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None


class PreviewSession:
    def __init__(
        self,
        load_run: ETLLoadRun | None,
        *,
        staging: list[CatalogProductStaging] | None = None,
        rejected: list[ETLRejectedRow] | None = None,
        catalog: list[CatalogProduct] | None = None,
    ):
        self.load_run = load_run
        self.staging = list(staging or [])
        self.rejected = list(rejected or [])
        self.catalog = list(catalog or [])
        self.queried_entities: list[type[Any]] = []
        self.no_autoflush = nullcontext()

    def get(self, model, identity):
        if model is ETLLoadRun and self.load_run is not None:
            if self.load_run.id == identity:
                return self.load_run
        return None

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        self.queried_entities.append(entity)
        if entity is CatalogProductStaging:
            return _ScalarRows(self.staging)
        if entity is ETLRejectedRow:
            return _ScalarRows(self.rejected)
        if entity is CatalogProduct:
            return _ScalarRows(self.catalog)
        raise AssertionError(f"Unexpected query entity: {entity}")

    def add(self, _instance) -> None:
        raise AssertionError("preview must not add database rows")

    def add_all(self, _instances) -> None:
        raise AssertionError("preview must not add database rows")

    def delete(self, _instance) -> None:
        raise AssertionError("preview must not delete database rows")

    def flush(self) -> None:
        raise AssertionError("preview must not flush")

    def commit(self) -> None:
        raise AssertionError("preview must not commit")


def _load_run(**changes) -> ETLLoadRun:
    values = {
        "id": 42,
        "source_filename": "supplier.csv",
        "profile_name": "supplier-a",
        "profile_version": "1",
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
        "supplier_key": "supplier-a",
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


def _rejected_row() -> ETLRejectedRow:
    return ETLRejectedRow(
        id=300,
        etl_load_run_id=42,
        source_row_number=2,
        errors=[{"code": "INVALID_PRICE", "field": "price", "message": "invalid"}],
        masked_source_data={"product_id": "masked"},
    )


def _preview(session: PreviewSession):
    from db.catalog_promotion_preview_service import preview_catalog_promotion

    return preview_catalog_promotion(session, etl_load_run_id=42)


def test_missing_etl_batch_raises_domain_error_without_writes():
    from db.catalog_promotion_preview_service import ETLLoadRunNotFoundError

    session = PreviewSession(None)

    with pytest.raises(ETLLoadRunNotFoundError) as raised:
        _preview(session)

    assert raised.value.etl_load_run_id == 42
    assert "42" in str(raised.value)
    assert session.queried_entities == []


@pytest.mark.parametrize("missing_field", ["total_rows", "rejected_rows", "error_counts"])
def test_missing_quality_summary_blocks_the_whole_batch(missing_field):
    load_run = _load_run()
    setattr(load_run, missing_field, None)

    preview = _preview(PreviewSession(load_run, staging=[_staging()]))

    assert preview.promotion_eligible is False
    assert [reason.code for reason in preview.blocked_reasons] == [
        "quality_summary_missing"
    ]
    assert preview.blocked_reasons[0].message == (
        "ETL 품질 요약이 없는 배치는 운영 반영할 수 없습니다."
    )
    assert preview.items == []
    assert preview.preview_hash is not None


@pytest.mark.parametrize(
    ("rejected_rows", "rejected"),
    [(1, []), (0, [_rejected_row()])],
)
def test_any_etl_rejection_blocks_the_whole_batch(rejected_rows, rejected):
    load_run = _load_run(
        total_rows=1 + rejected_rows,
        rejected_rows=rejected_rows,
        error_counts={"INVALID_PRICE": rejected_rows} if rejected_rows else {},
    )

    preview = _preview(
        PreviewSession(load_run, staging=[_staging()], rejected=rejected)
    )

    assert preview.promotion_eligible is False
    assert [reason.code for reason in preview.blocked_reasons] == [
        "etl_rejections_present"
    ]
    assert preview.blocked_reasons[0].message == (
        "변환이 거부된 상품 행이 있어 운영 반영을 진행할 수 없습니다."
    )
    assert preview.items == []


def test_empty_staging_batch_is_blocked():
    preview = _preview(
        PreviewSession(
            _load_run(loaded_rows=0, total_rows=0),
            staging=[],
        )
    )

    assert preview.promotion_eligible is False
    assert [reason.code for reason in preview.blocked_reasons] == [
        "empty_staging_batch"
    ]
    assert preview.blocked_reasons[0].message == (
        "반영할 정상 staging 상품이 없습니다."
    )
    assert preview.preview_hash is not None
    assert preview.items == []


def test_duplicate_product_identity_is_blocked_with_only_safe_identity_details():
    duplicate_a = _staging("P001", id=101, product_name="Secret first name")
    duplicate_b = _staging("P001", id=102, product_name="Secret second name")

    preview = _preview(
        PreviewSession(_load_run(loaded_rows=2, total_rows=2), staging=[
            duplicate_b,
            duplicate_a,
        ])
    )

    assert preview.promotion_eligible is False
    assert preview.preview_hash is None
    assert preview.items == []
    assert preview.error_count == 0
    assert preview.warning_count == 0
    assert len(preview.blocked_reasons) == 1
    reason = preview.blocked_reasons[0]
    assert reason.code == "duplicate_product_identity"
    assert reason.message == "같은 공급사 상품 식별자가 배치 안에 중복되어 있습니다."
    assert reason.supplier_key == "supplier-a"
    assert reason.external_product_id == "P001"
    assert reason.staging_product_ids == (101, 102)
    assert "Secret" not in repr(reason)


def test_reinspection_errors_block_the_batch_but_keep_a_deterministic_hash():
    first = _staging("P001", product_group_id="G-DUP")
    second = _staging("P002", id=101, product_group_id="G-DUP")

    preview = _preview(
        PreviewSession(_load_run(loaded_rows=2, total_rows=2), staging=[first, second])
    )

    assert preview.promotion_eligible is False
    assert [reason.code for reason in preview.blocked_reasons] == [
        "inspection_errors_present"
    ]
    assert preview.error_count == 2
    assert preview.preview_hash is not None
    assert preview.items == []


def test_warning_only_reinspection_is_eligible_and_uses_current_version():
    warning_product = _staging(color="blue", size="medium")

    preview = _preview(PreviewSession(_load_run(), staging=[warning_product]))

    assert preview.promotion_eligible is True
    assert preview.blocked_reasons == []
    assert preview.error_count == 0
    assert preview.warning_count == 2
    assert preview.inspection_version == settings.INSPECTION_VERSION
    assert preview.preview_schema_version == 1
    assert preview.insert_count == 1


def test_insert_update_and_unchanged_items_include_exact_before_after_values():
    insert_row = _staging("P003", id=103, stock=np.int64(3), price=100.0, sale_price="90")
    update_row = _staging("P002", id=102, price=21900, description=None)
    unchanged_row = _staging("P001", id=101)
    current_update = _catalog("P002", id=202, price=19900, description="old")
    current_unchanged = _catalog("P001", id=201)
    session = PreviewSession(
        _load_run(loaded_rows=3, total_rows=3),
        staging=[insert_row, update_row, unchanged_row],
        catalog=[current_update, current_unchanged],
    )

    preview = _preview(session)

    assert (preview.insert_count, preview.update_count, preview.unchanged_count) == (
        1,
        1,
        1,
    )
    assert [item.external_product_id for item in preview.items] == [
        "P001",
        "P002",
        "P003",
    ]
    assert [item.action for item in preview.items] == [
        "unchanged",
        "update",
        "insert",
    ]
    unchanged, update, insert = preview.items
    assert unchanged.changed_fields == {}
    assert unchanged.before_data == unchanged.after_data
    assert update.changed_fields == {
        "price": {"before": 19900, "after": 21900},
        "description": {"before": "old", "after": None},
    }
    assert update.before_data is not None
    assert update.before_data["description"] == "old"
    assert update.after_data["description"] is None
    assert insert.before_data is None
    assert insert.changed_fields == {}
    assert insert.after_data["stock"] == 3
    assert type(insert.after_data["stock"]) is int
    assert type(insert.after_data["price"]) is int
    assert type(insert.after_data["sale_price"]) is int
    assert session.queried_entities.count(CatalogProduct) == 1


def test_nullable_none_does_not_mean_keep_the_existing_catalog_value():
    staging = _staging(description=None, seller=None, sale_price=None)
    catalog = _catalog(description="", seller="Seller", sale_price=10000)

    item = _preview(
        PreviewSession(_load_run(), staging=[staging], catalog=[catalog])
    ).items[0]

    assert item.action == "update"
    assert item.changed_fields == {
        "sale_price": {"before": 10000, "after": None},
        "description": {"before": "", "after": None},
        "seller": {"before": "Seller", "after": None},
    }


def test_items_are_sorted_independently_of_staging_and_catalog_query_order():
    rows = [_staging("P002", id=102), _staging("P001", id=101)]
    catalog = [_catalog("P002", id=202), _catalog("P001", id=201)]

    preview = _preview(
        PreviewSession(
            _load_run(loaded_rows=2, total_rows=2),
            staging=rows,
            catalog=catalog,
        )
    )

    assert [
        (item.supplier_key, item.external_product_id) for item in preview.items
    ] == [("supplier-a", "P001"), ("supplier-a", "P002")]


def test_canonical_hash_matches_the_hand_built_payload():
    staging = _staging()
    preview = _preview(PreviewSession(_load_run(), staging=[staging]))
    payload = {
        "preview_schema_version": 1,
        "inspection_version": settings.INSPECTION_VERSION,
        "etl_load_run_id": 42,
        "supplier_key": "supplier-a",
        "products": [
            {
                "external_product_id": "P001",
                "target": {
                    "external_product_id": "P001",
                    "product_group_id": "G-P001",
                    "product_name": "Product P001",
                    "category": "TOP",
                    "color": "BLACK",
                    "size": "M",
                    "stock": 10,
                    "price": 19900,
                    "sale_price": None,
                    "image_path": "P001.jpg",
                    "description": None,
                    "seller": None,
                },
                "current_catalog": None,
            }
        ],
    }
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    expected = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    assert preview.preview_hash == expected
    assert len(preview.preview_hash) == 64
    assert preview.preview_hash == preview.preview_hash.lower()


def test_hash_is_repeatable_and_independent_of_query_order():
    rows = [_staging("P002", id=102), _staging("P001", id=101)]
    catalog = [_catalog("P002", id=202), _catalog("P001", id=201)]

    first = _preview(
        PreviewSession(
            _load_run(loaded_rows=2, total_rows=2),
            staging=rows,
            catalog=catalog,
        )
    )
    second = _preview(
        PreviewSession(
            _load_run(loaded_rows=2, total_rows=2),
            staging=list(reversed(rows)),
            catalog=list(reversed(catalog)),
        )
    )

    assert first.preview_hash == second.preview_hash
    assert asdict(first) == asdict(second)


@pytest.mark.parametrize(
    ("staging_change", "catalog_change"),
    [
        ({"stock": 9}, {}),
        ({}, {"stock": 9}),
    ],
)
def test_hash_changes_when_target_or_current_catalog_state_changes(
    staging_change,
    catalog_change,
):
    baseline = _preview(
        PreviewSession(_load_run(), staging=[_staging()], catalog=[_catalog()])
    )
    changed = _preview(
        PreviewSession(
            _load_run(),
            staging=[_staging(**staging_change)],
            catalog=[_catalog(**catalog_change)],
        )
    )

    assert baseline.preview_hash != changed.preview_hash


def test_hash_changes_when_current_inspection_version_changes(monkeypatch):
    first = _preview(PreviewSession(_load_run(), staging=[_staging()]))

    monkeypatch.setattr(settings, "INSPECTION_VERSION", "next-version")
    second = _preview(PreviewSession(_load_run(), staging=[_staging()]))

    assert first.inspection_version != second.inspection_version
    assert first.preview_hash != second.preview_hash


def test_preview_does_not_mutate_loaded_database_objects():
    load_run = _load_run()
    staging = _staging()
    catalog = _catalog()
    before = {
        "load": dict(load_run.__dict__),
        "staging": dict(staging.__dict__),
        "catalog": dict(catalog.__dict__),
    }

    _preview(PreviewSession(load_run, staging=[staging], catalog=[catalog]))

    assert dict(load_run.__dict__) == before["load"]
    assert dict(staging.__dict__) == before["staging"]
    assert dict(catalog.__dict__) == before["catalog"]


@pytest.fixture()
def postgres_preview_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip(
            "TEST_DATABASE_URL is not configured; skipping PostgreSQL integration test."
        )

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    profile_name = f"preview_profile_{uuid4().hex}"
    try:
        yield session, profile_name
    finally:
        session.rollback()
        session.close()
        with session_factory() as cleanup:
            load_run_ids = select(ETLLoadRun.id).where(
                ETLLoadRun.profile_name == profile_name
            )
            cleanup.execute(
                delete(CatalogProductChange).where(
                    CatalogProductChange.catalog_product_id.in_(
                        select(CatalogProduct.id).where(
                            CatalogProduct.source_etl_load_run_id.in_(load_run_ids)
                        )
                    )
                )
            )
            cleanup.execute(
                delete(CatalogPromotionRun).where(
                    CatalogPromotionRun.etl_load_run_id.in_(load_run_ids)
                )
            )
            cleanup.execute(
                delete(CatalogProduct).where(
                    CatalogProduct.source_etl_load_run_id.in_(load_run_ids)
                )
            )
            cleanup.execute(
                delete(ETLLoadRun).where(ETLLoadRun.id.in_(load_run_ids))
            )
            cleanup.commit()
        engine.dispose()


def test_postgresql_preview_leaves_all_related_tables_unchanged(
    postgres_preview_session,
):
    from db.catalog_promotion_preview_service import preview_catalog_promotion

    session, profile_name = postgres_preview_session
    load_run = ETLLoadRun(
        source_filename="supplier.csv",
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256="c" * 64,
        output_file_sha256="d" * 64,
        loaded_rows=1,
        total_rows=1,
        rejected_rows=0,
        error_counts={},
    )
    session.add(load_run)
    session.flush()
    session.add(
        CatalogProductStaging(
            etl_load_run_id=load_run.id,
            product_group_id="G001",
            product_id="P001",
            product_name="Product",
            category="TOP",
            color="BLACK",
            size="M",
            stock=10,
            price=19900,
            sale_price=None,
            image_path="p001.jpg",
            description=None,
            seller=None,
        )
    )
    catalog_product = CatalogProduct(
        supplier_key=profile_name,
        external_product_id="P001",
        product_group_id="G001",
        product_name="Product",
        category="TOP",
        color="BLACK",
        size="M",
        stock=10,
        price=19900,
        sale_price=None,
        image_path="p001.jpg",
        description=None,
        seller=None,
        source_etl_load_run_id=load_run.id,
    )
    session.add(catalog_product)
    session.commit()

    tables = (
        ETLLoadRun,
        CatalogProductStaging,
        ETLRejectedRow,
        CatalogProduct,
        CatalogPromotionRun,
        CatalogProductChange,
        InspectionRun,
        InspectionResult,
    )
    counts_before = {
        model.__tablename__: session.scalar(
            select(func.count()).select_from(model)
        )
        for model in tables
    }
    product_before = {
        "stock": catalog_product.stock,
        "price": catalog_product.price,
        "description": catalog_product.description,
        "source_etl_load_run_id": catalog_product.source_etl_load_run_id,
        "updated_at": catalog_product.updated_at,
    }
    load_summary_before = (
        load_run.total_rows,
        load_run.rejected_rows,
        dict(load_run.error_counts),
    )

    preview = preview_catalog_promotion(session, etl_load_run_id=load_run.id)

    session.expire_all()
    counts_after = {
        model.__tablename__: session.scalar(
            select(func.count()).select_from(model)
        )
        for model in tables
    }
    reloaded_product = session.get(CatalogProduct, catalog_product.id)
    reloaded_load_run = session.get(ETLLoadRun, load_run.id)
    assert preview.promotion_eligible is True
    assert preview.unchanged_count == 1
    assert counts_after == counts_before
    assert {
        "stock": reloaded_product.stock,
        "price": reloaded_product.price,
        "description": reloaded_product.description,
        "source_etl_load_run_id": reloaded_product.source_etl_load_run_id,
        "updated_at": reloaded_product.updated_at,
    } == product_before
    assert (
        reloaded_load_run.total_rows,
        reloaded_load_run.rejected_rows,
        dict(reloaded_load_run.error_counts),
    ) == load_summary_before
