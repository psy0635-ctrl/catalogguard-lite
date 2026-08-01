from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from config.database import get_optional_database_url
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogPromotionRun,
    ETLLoadRun,
)
from db.session import create_database_engine, create_session_factory


class _Rows:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ReadOnlyListSession:
    def __init__(self, rows):
        self.rows = rows
        self.scalar_calls = 0

    def execute(self, _statement):
        return _Rows(self.rows)

    def scalar(self, _statement):
        self.scalar_calls += 1
        return len(self.rows)

    def commit(self):
        raise AssertionError("query service must not commit")

    def rollback(self):
        raise AssertionError("query service must not rollback")


def test_list_catalog_promotions_maps_joined_rows_without_writes():
    from db.catalog_promotion_query_service import list_catalog_promotions

    created_at = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    promotion = SimpleNamespace(
        id=21,
        etl_load_run_id=12,
        status="succeeded",
        inserted_count=2,
        updated_count=1,
        unchanged_count=3,
        blocked_count=0,
        error_count=0,
        warning_count=1,
        failure_code=None,
        safe_failure_message=None,
        started_at=created_at,
        completed_at=created_at + timedelta(seconds=1),
        created_at=created_at,
    )
    load = SimpleNamespace(
        source_filename="vendor.csv",
        profile_name="sample_vendor",
    )
    session = _ReadOnlyListSession([(promotion, load)])

    result = list_catalog_promotions(session, limit=20, offset=0)

    assert result.total == 1
    assert result.items[0].promotion_run_id == 21
    assert result.items[0].source_filename == "vendor.csv"
    assert result.items[0].inserted_count == 2
    assert result.items[0].status == "succeeded"
    assert session.scalar_calls == 1


@pytest.fixture()
def seeded_promotions():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    profile_prefix = f"promotion_query_{uuid4().hex}"
    base_time = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)

    def add_load(index: int, filename: str) -> ETLLoadRun:
        load = ETLLoadRun(
            source_filename=filename,
            profile_name=f"{profile_prefix}_{index}",
            profile_version="1",
            input_file_sha256=f"{index}" * 64,
            output_file_sha256=f"{index + 3}" * 64,
            loaded_rows=1,
            total_rows=1,
            rejected_rows=0,
            error_counts={},
            reject_details_stored=False,
            created_at=base_time + timedelta(minutes=index),
        )
        session.add(load)
        session.flush()
        return load

    def add_promotion(
        load: ETLLoadRun,
        *,
        status: str,
        created_at: datetime,
        inserted_count: int = 0,
        updated_count: int = 0,
        unchanged_count: int = 0,
        failure_code: str | None = None,
        safe_failure_message: str | None = None,
    ) -> CatalogPromotionRun:
        run = CatalogPromotionRun(
            etl_load_run_id=load.id,
            status=status,
            preview_hash="a" * 64,
            preview_schema_version="1",
            inspection_version="1",
            inserted_count=inserted_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            blocked_count=1 if status == "blocked" else 0,
            error_count=0,
            warning_count=0,
            failure_code=failure_code,
            safe_failure_message=safe_failure_message,
            started_at=created_at,
            completed_at=created_at + timedelta(seconds=1),
            created_at=created_at,
        )
        session.add(run)
        session.flush()
        return run

    oldest_load = add_load(1, "old-vendor.csv")
    failed_load = add_load(2, "failed-vendor.csv")
    newest_load = add_load(3, "new-vendor.csv")
    oldest = add_promotion(
        oldest_load,
        status="succeeded",
        created_at=base_time,
        inserted_count=1,
    )
    failed = add_promotion(
        failed_load,
        status="failed",
        created_at=base_time + timedelta(minutes=1),
        failure_code="promotion_apply_failed",
        safe_failure_message="Promotion could not be completed.",
    )
    newest = add_promotion(
        newest_load,
        status="blocked",
        created_at=base_time + timedelta(minutes=2),
        failure_code="preview_stale",
        safe_failure_message="Preview is stale.",
    )

    product = CatalogProduct(
        supplier_key=oldest_load.profile_name,
        external_product_id="SKU-001",
        product_group_id="GROUP-001",
        product_name="Product 1",
        category="TOP",
        color="BLACK",
        size="M",
        stock=5,
        price=1000,
        sale_price=900,
        image_path="image.jpg",
        description=None,
        seller="Seller",
        source_etl_load_run_id=oldest_load.id,
    )
    session.add(product)
    session.flush()
    for index in range(3):
        session.add(
            CatalogProductChange(
                promotion_run_id=oldest.id,
                catalog_product_id=product.id,
                action="update",
                changed_fields={
                    "stock": {"before": index, "after": index + 1}
                },
                before_data={"external_product_id": "SKU-001", "stock": index},
                after_data={"external_product_id": "SKU-001", "stock": index + 1},
                created_at=base_time + timedelta(seconds=index),
            )
        )
    session.commit()

    try:
        yield session, profile_prefix, oldest, failed, newest
    finally:
        session.rollback()
        session.close()
        with session_factory() as cleanup:
            load_ids = select(ETLLoadRun.id).where(
                ETLLoadRun.profile_name.like(f"{profile_prefix}%")
            )
            promotion_ids = select(CatalogPromotionRun.id).where(
                CatalogPromotionRun.etl_load_run_id.in_(load_ids)
            )
            cleanup.execute(
                delete(CatalogProductChange).where(
                    CatalogProductChange.promotion_run_id.in_(promotion_ids)
                )
            )
            cleanup.execute(
                delete(CatalogProduct).where(
                    CatalogProduct.source_etl_load_run_id.in_(load_ids)
                )
            )
            cleanup.execute(
                delete(CatalogPromotionRun).where(
                    CatalogPromotionRun.etl_load_run_id.in_(load_ids)
                )
            )
            cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id.in_(load_ids)))
            cleanup.commit()
        engine.dispose()


def test_list_catalog_promotions_sorts_latest_and_uses_sql_pagination(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import list_catalog_promotions

    session, profile_prefix, oldest, failed, newest = seeded_promotions

    first_page = list_catalog_promotions(
        session,
        limit=2,
        offset=0,
        filename="vendor",
        profile_name=profile_prefix,
    )
    second_page = list_catalog_promotions(
        session,
        limit=2,
        offset=2,
        filename="vendor",
        profile_name=profile_prefix,
    )

    assert [item.promotion_run_id for item in first_page.items] == [
        newest.id,
        failed.id,
    ]
    assert first_page.items[0].source_filename == "new-vendor.csv"
    assert first_page.total == 3
    assert first_page.limit == 2
    assert first_page.offset == 0
    assert [item.promotion_run_id for item in second_page.items] == [oldest.id]


def test_list_catalog_promotions_filters_status_and_etl_load_run(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import list_catalog_promotions

    session, _profile_prefix, _oldest, failed, newest = seeded_promotions

    failed_result = list_catalog_promotions(
        session,
        limit=20,
        offset=0,
        status="failed",
    )
    load_result = list_catalog_promotions(
        session,
        limit=20,
        offset=0,
        etl_load_run_id=newest.etl_load_run_id,
    )

    assert [item.promotion_run_id for item in failed_result.items] == [failed.id]
    assert [item.promotion_run_id for item in load_result.items] == [newest.id]


def test_get_catalog_promotion_detail_returns_existing_run_or_none(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import get_catalog_promotion_detail

    session, _profile_prefix, _oldest, failed, _newest = seeded_promotions

    detail = get_catalog_promotion_detail(
        session,
        promotion_run_id=failed.id,
    )

    assert detail is not None
    assert detail.promotion_run_id == failed.id
    assert detail.etl_load_run_id == failed.etl_load_run_id
    assert detail.source_filename == "failed-vendor.csv"
    assert detail.status == "failed"
    assert detail.failure_code == "promotion_apply_failed"
    assert detail.safe_failure_message == "Promotion could not be completed."
    assert get_catalog_promotion_detail(
        session,
        promotion_run_id=999999999,
    ) is None


def test_list_catalog_promotion_audits_isolated_paginated_and_empty(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import list_catalog_promotion_audits

    session, _profile_prefix, oldest, failed, _newest = seeded_promotions

    first_page = list_catalog_promotion_audits(
        session,
        promotion_run_id=oldest.id,
        limit=2,
        offset=0,
    )
    second_page = list_catalog_promotion_audits(
        session,
        promotion_run_id=oldest.id,
        limit=2,
        offset=2,
    )
    empty = list_catalog_promotion_audits(
        session,
        promotion_run_id=failed.id,
        limit=20,
        offset=0,
    )

    assert first_page is not None
    assert first_page.total == 3
    assert len(first_page.items) == 2
    assert all(item.promotion_run_id == oldest.id for item in first_page.items)
    assert first_page.items[0].audit_id > first_page.items[1].audit_id
    assert second_page is not None
    assert len(second_page.items) == 1
    assert empty is not None
    assert empty.items == []
    assert empty.total == 0
    assert list_catalog_promotion_audits(
        session,
        promotion_run_id=999999999,
        limit=20,
        offset=0,
    ) is None


def test_catalog_promotion_queries_do_not_modify_database(seeded_promotions):
    from db.catalog_promotion_query_service import (
        get_catalog_promotion_detail,
        list_catalog_promotion_audits,
        list_catalog_promotions,
    )

    session, profile_prefix, oldest, _failed, _newest = seeded_promotions
    before_runs = session.scalar(
        select(CatalogPromotionRun).where(CatalogPromotionRun.id == oldest.id)
    ).inserted_count
    before_audits = session.scalar(
        select(CatalogProductChange).where(
            CatalogProductChange.promotion_run_id == oldest.id
        )
    ).changed_fields

    list_catalog_promotions(
        session,
        limit=20,
        offset=0,
        profile_name=profile_prefix,
    )
    get_catalog_promotion_detail(session, promotion_run_id=oldest.id)
    list_catalog_promotion_audits(
        session,
        promotion_run_id=oldest.id,
        limit=20,
        offset=0,
    )

    assert session.get(CatalogPromotionRun, oldest.id).inserted_count == before_runs
    assert session.scalar(
        select(CatalogProductChange).where(
            CatalogProductChange.promotion_run_id == oldest.id
        )
    ).changed_fields == before_audits
