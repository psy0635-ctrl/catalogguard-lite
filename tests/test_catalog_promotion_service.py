from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, or_, select

from config import settings
from config.database import get_optional_database_url
from db.catalog_promotion_preview_service import (
    COMPARISON_FIELDS,
    ETLLoadRunNotFoundError,
    preview_catalog_promotion,
)
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogProductStaging,
    CatalogPromotionRun,
    ETLLoadRun,
)
from db.session import create_database_engine, create_session_factory


VALID_HASH = "a" * 64


class NoDatabaseAccess:
    def __getattr__(self, name):
        raise AssertionError(f"database access is not allowed: {name}")


def test_confirmation_false_is_rejected_before_database_access():
    from db.catalog_promotion_service import (
        CatalogPromotionConfirmationRequiredError,
        execute_catalog_promotion,
    )

    with pytest.raises(CatalogPromotionConfirmationRequiredError):
        execute_catalog_promotion(
            NoDatabaseAccess(),
            etl_load_run_id=42,
            confirmation=False,
            expected_preview_hash=VALID_HASH,
        )


@pytest.mark.parametrize(
    "invalid_hash",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        f" {'a' * 63}",
    ],
)
def test_invalid_expected_hash_is_rejected_before_database_access(invalid_hash):
    from db.catalog_promotion_service import (
        CatalogPromotionInvalidPreviewHashError,
        execute_catalog_promotion,
    )

    with pytest.raises(CatalogPromotionInvalidPreviewHashError):
        execute_catalog_promotion(
            NoDatabaseAccess(),
            etl_load_run_id=42,
            confirmation=True,
            expected_preview_hash=invalid_hash,
        )


def test_promotion_rollback_failure_does_not_mask_primary_failure_or_failed_run(
    monkeypatch,
):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from sqlalchemy.exc import SQLAlchemyError

    import db.catalog_promotion_service as promotion_service

    class ScalarResult:
        def __init__(self, *, first=None, all_items=None) -> None:
            self._first = first
            self._all_items = all_items or []

        def first(self):
            return self._first

        def all(self):
            return self._all_items

    class FailingRollbackSession:
        def __init__(self) -> None:
            self._results = [
                ScalarResult(first=SimpleNamespace(id=101)),
                ScalarResult(),
                ScalarResult(all_items=[]),
            ]
            self.flush_calls = 0
            self.rollback_calls = 0

        def begin(self):
            return nullcontext()

        def scalars(self, _statement):
            return self._results.pop(0)

        def add(self, _instance) -> None:
            pass

        def flush(self) -> None:
            self.flush_calls += 1
            if self.flush_calls == 2:
                raise SQLAlchemyError("primary promotion database failure")

        def rollback(self) -> None:
            self.rollback_calls += 1
            raise RuntimeError("database connection dropped during rollback")

    preview = SimpleNamespace(
        promotion_eligible=True,
        blocked_reasons=[],
        preview_hash="a" * 64,
        preview_schema_version=1,
        inspection_version="13",
        error_count=0,
        warning_count=0,
        items=[],
    )
    failed_run_ids: list[int] = []
    session = FailingRollbackSession()

    monkeypatch.setattr(
        promotion_service,
        "preview_catalog_promotion",
        lambda *_args, **_kwargs: preview,
    )
    monkeypatch.setattr(
        promotion_service,
        "_record_failed_run",
        lambda _session, *, etl_load_run_id, **_kwargs: failed_run_ids.append(
            etl_load_run_id
        )
        or 909,
    )

    with pytest.raises(
        promotion_service.CatalogPromotionExecutionFailedError
    ) as raised:
        promotion_service.execute_catalog_promotion(
            session,
            etl_load_run_id=101,
            confirmation=True,
            expected_preview_hash="a" * 64,
        )

    assert raised.value.promotion_run_id == 909
    assert session.rollback_calls == 1
    assert failed_run_ids == [101]


@pytest.fixture()
def postgres_promotion():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip(
            "TEST_DATABASE_URL is not configured; skipping PostgreSQL promotion integration test."
        )

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    profile_name = f"promotion_service_{uuid4().hex}"
    try:
        yield session_factory, profile_name
    finally:
        with session_factory() as cleanup:
            load_run_ids = select(ETLLoadRun.id).where(
                ETLLoadRun.profile_name == profile_name
            )
            promotion_run_ids = select(CatalogPromotionRun.id).where(
                CatalogPromotionRun.etl_load_run_id.in_(load_run_ids)
            )
            catalog_product_ids = select(CatalogProduct.id).where(
                or_(
                    CatalogProduct.source_etl_load_run_id.in_(load_run_ids),
                    CatalogProduct.supplier_key == profile_name,
                )
            )
            cleanup.execute(
                delete(CatalogProductChange).where(
                    or_(
                        CatalogProductChange.promotion_run_id.in_(
                            promotion_run_ids
                        ),
                        CatalogProductChange.catalog_product_id.in_(
                            catalog_product_ids
                        ),
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
                    or_(
                        CatalogProduct.source_etl_load_run_id.in_(load_run_ids),
                        CatalogProduct.supplier_key == profile_name,
                    )
                )
            )
            cleanup.execute(
                delete(ETLLoadRun).where(ETLLoadRun.id.in_(load_run_ids))
            )
            cleanup.commit()
        engine.dispose()


def _load_run(profile_name: str, *, suffix: str = "") -> ETLLoadRun:
    return ETLLoadRun(
        source_filename=f"supplier{suffix}.csv",
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256=("a" if not suffix else "c") * 64,
        output_file_sha256=("b" if not suffix else "d") * 64,
        loaded_rows=3,
        total_rows=3,
        rejected_rows=0,
        error_counts={},
    )


def _staging(load_run_id: int, product_id: str, **changes):
    values = {
        "etl_load_run_id": load_run_id,
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


def _catalog(
    profile_name: str,
    load_run_id: int,
    product_id: str,
    **changes,
):
    values = {
        "supplier_key": profile_name,
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
        "source_etl_load_run_id": load_run_id,
    }
    values.update(changes)
    return CatalogProduct(**values)


def _preview_hash(session, load_run_id: int) -> str:
    preview = preview_catalog_promotion(
        session,
        etl_load_run_id=load_run_id,
    )
    assert preview.preview_hash is not None
    session.rollback()
    return preview.preview_hash


def test_missing_etl_batch_raises_domain_error(postgres_promotion):
    from db.catalog_promotion_service import execute_catalog_promotion

    session_factory, _ = postgres_promotion
    with session_factory() as session:
        with pytest.raises(ETLLoadRunNotFoundError):
            execute_catalog_promotion(
                session,
                etl_load_run_id=9_999_999_999,
                confirmation=True,
                expected_preview_hash=VALID_HASH,
            )

        assert session.scalar(
            select(func.count())
            .select_from(CatalogPromotionRun)
            .where(CatalogPromotionRun.etl_load_run_id == 9_999_999_999)
        ) == 0


def test_mixed_batch_inserts_updates_and_leaves_unchanged_product_untouched(
    postgres_promotion,
):
    from db.catalog_promotion_service import execute_catalog_promotion

    session_factory, profile_name = postgres_promotion
    with session_factory() as setup:
        source_run = _load_run(profile_name, suffix="-source")
        setup.add(source_run)
        setup.flush()
        update_product = _catalog(
            profile_name,
            source_run.id,
            "P002",
            price=15000,
            description="old",
        )
        unchanged_product = _catalog(profile_name, source_run.id, "P003")
        absent_product = _catalog(profile_name, source_run.id, "P999")
        setup.add_all([update_product, unchanged_product, absent_product])
        setup.commit()
        source_run_id = source_run.id
        update_product_id = update_product.id
        update_updated_at = update_product.updated_at
        unchanged_product_id = unchanged_product.id
        unchanged_updated_at = unchanged_product.updated_at

    with session_factory() as setup:
        load_run = _load_run(profile_name)
        setup.add(load_run)
        setup.flush()
        setup.add_all(
            [
                _staging(load_run.id, "P003"),
                _staging(load_run.id, "P001", description="new"),
                _staging(
                    load_run.id,
                    "P002",
                    price=21900,
                    description=None,
                ),
            ]
        )
        setup.commit()
        load_run_id = load_run.id

    with session_factory() as preview_session:
        expected_hash = _preview_hash(preview_session, load_run_id)

    with session_factory() as session:
        result = execute_catalog_promotion(
            session,
            etl_load_run_id=load_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )

    assert result.status == "succeeded"
    assert result.created is True
    assert (result.inserted_count, result.updated_count, result.unchanged_count) == (
        1,
        1,
        1,
    )
    assert result.preview_schema_version == 1
    assert isinstance(result.started_at, datetime)
    assert isinstance(result.completed_at, datetime)

    with session_factory() as verify:
        products = list(
            verify.scalars(
                select(CatalogProduct)
                .where(CatalogProduct.supplier_key == profile_name)
                .order_by(CatalogProduct.external_product_id)
            )
        )
        assert [product.external_product_id for product in products] == [
            "P001",
            "P002",
            "P003",
            "P999",
        ]
        inserted = products[0]
        updated = products[1]
        unchanged = products[2]
        absent = products[3]
        assert inserted.source_etl_load_run_id == load_run_id
        assert inserted.description == "new"
        assert updated.id == update_product_id
        assert updated.price == 21900
        assert updated.description is None
        assert updated.source_etl_load_run_id == load_run_id
        assert updated.updated_at != update_updated_at
        assert unchanged.id == unchanged_product_id
        assert unchanged.source_etl_load_run_id == source_run_id
        assert unchanged.updated_at == unchanged_updated_at
        assert absent.external_product_id == "P999"

        changes = list(
            verify.scalars(
                select(CatalogProductChange)
                .where(
                    CatalogProductChange.promotion_run_id
                    == result.promotion_run_id
                )
                .order_by(CatalogProductChange.catalog_product_id)
            )
        )
        assert len(changes) == 2
        insert_change = next(change for change in changes if change.action == "insert")
        update_change = next(change for change in changes if change.action == "update")
        assert insert_change.before_data is None
        assert set(insert_change.changed_fields) == set(COMPARISON_FIELDS)
        assert all(
            change["before"] is None
            for change in insert_change.changed_fields.values()
        )
        assert insert_change.after_data["external_product_id"] == "P001"
        assert update_change.changed_fields == {
            "price": {"before": 15000, "after": 21900},
            "description": {"before": "old", "after": None},
        }
        assert update_change.before_data["description"] == "old"
        assert update_change.after_data["description"] is None
        load_run = verify.get(ETLLoadRun, load_run_id)
        assert (load_run.loaded_rows, load_run.total_rows, load_run.rejected_rows) == (
            3,
            3,
            0,
        )
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProductStaging)
            .where(CatalogProductStaging.etl_load_run_id == load_run_id)
        ) == 3


def test_quality_block_creates_only_blocked_run(postgres_promotion):
    from db.catalog_promotion_service import execute_catalog_promotion

    session_factory, profile_name = postgres_promotion
    with session_factory() as setup:
        load_run = _load_run(profile_name)
        load_run.loaded_rows = 0
        load_run.total_rows = 0
        setup.add(load_run)
        setup.commit()
        load_run_id = load_run.id

    with session_factory() as session:
        result = execute_catalog_promotion(
            session,
            etl_load_run_id=load_run_id,
            confirmation=True,
            expected_preview_hash=VALID_HASH,
        )

    assert result.status == "blocked"
    assert result.failure_code == "promotion_blocked"
    assert result.blocked_reasons
    with session_factory() as verify:
        run = verify.get(CatalogPromotionRun, result.promotion_run_id)
        assert run.status == "blocked"
        assert run.failure_code == "promotion_blocked"
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProduct)
            .where(CatalogProduct.supplier_key == profile_name)
        ) == 0
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(
                CatalogProductChange.promotion_run_id
                == result.promotion_run_id
            )
        ) == 0

    with session_factory() as repair:
        load_run = repair.get(ETLLoadRun, load_run_id)
        load_run.loaded_rows = 1
        load_run.total_rows = 1
        repair.add(_staging(load_run_id, "P001"))
        repair.commit()

    with session_factory() as preview_session:
        expected_hash = _preview_hash(preview_session, load_run_id)
    with session_factory() as retry:
        retried = execute_catalog_promotion(
            retry,
            etl_load_run_id=load_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )

    assert retried.status == "succeeded"
    assert retried.created is True


@pytest.mark.parametrize("stale_source", ["staging", "catalog", "inspection_version"])
def test_current_state_changes_create_stale_run_without_product_changes(
    postgres_promotion,
    monkeypatch,
    stale_source,
):
    from db.catalog_promotion_service import execute_catalog_promotion

    session_factory, profile_name = postgres_promotion
    with session_factory() as setup:
        source_run = _load_run(profile_name, suffix="-source")
        setup.add(source_run)
        setup.flush()
        existing = _catalog(profile_name, source_run.id, "P001")
        setup.add(existing)
        setup.commit()
        existing_id = existing.id
        source_run_id = source_run.id

    with session_factory() as setup:
        load_run = _load_run(profile_name)
        setup.add(load_run)
        setup.flush()
        staging = _staging(load_run.id, "P001", price=21900)
        setup.add(staging)
        setup.commit()
        load_run_id = load_run.id
        staging_id = staging.id

    with session_factory() as preview_session:
        expected_hash = _preview_hash(preview_session, load_run_id)

    if stale_source == "inspection_version":
        monkeypatch.setattr(
            settings,
            "INSPECTION_VERSION",
            f"{settings.INSPECTION_VERSION}-changed",
        )
    else:
        with session_factory() as mutate:
            if stale_source == "staging":
                mutate.get(CatalogProductStaging, staging_id).stock = 11
            else:
                mutate.get(CatalogProduct, existing_id).color = "WHITE"
            mutate.commit()

    with session_factory() as session:
        result = execute_catalog_promotion(
            session,
            etl_load_run_id=load_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )

    assert result.status == "blocked"
    assert result.failure_code == "preview_stale"
    with session_factory() as verify:
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(
                CatalogProductChange.promotion_run_id
                == result.promotion_run_id
            )
        ) == 0
        assert verify.get(CatalogPromotionRun, result.promotion_run_id).status == "blocked"
        product = verify.get(CatalogProduct, existing_id)
        assert product.color == (
            "WHITE" if stale_source == "catalog" else "BLACK"
        )
        assert product.price == 19900
        assert product.stock == 10
        assert product.source_etl_load_run_id == source_run_id


@pytest.mark.parametrize("action", ["insert", "update"])
def test_apply_failure_rolls_back_all_changes_and_records_safe_failed_run(
    postgres_promotion,
    monkeypatch,
    action,
):
    import db.catalog_promotion_service as promotion_service

    session_factory, profile_name = postgres_promotion
    source_run_id = None
    if action == "update":
        with session_factory() as setup:
            source_run = _load_run(profile_name, suffix="-source")
            setup.add(source_run)
            setup.flush()
            setup.add(
                _catalog(
                    profile_name,
                    source_run.id,
                    "P001",
                    price=15000,
                )
            )
            setup.commit()
            source_run_id = source_run.id

    with session_factory() as setup:
        load_run = _load_run(profile_name)
        load_run.loaded_rows = 1
        load_run.total_rows = 1
        setup.add(load_run)
        setup.flush()
        setup.add(
            _staging(
                load_run.id,
                "P001",
                price=21900 if action == "update" else 19900,
            )
        )
        setup.commit()
        load_run_id = load_run.id

    with session_factory() as preview_session:
        expected_hash = _preview_hash(preview_session, load_run_id)

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError(
            "postgresql://admin:secret@db.internal/catalog SELECT private"
        )

    original_create_change = promotion_service._create_catalog_product_change
    monkeypatch.setattr(
        promotion_service,
        "_create_catalog_product_change",
        fail_audit,
    )

    with session_factory() as session:
        with pytest.raises(
            promotion_service.CatalogPromotionExecutionFailedError
        ) as raised:
            promotion_service.execute_catalog_promotion(
                session,
                etl_load_run_id=load_run_id,
                confirmation=True,
                expected_preview_hash=expected_hash,
            )

    assert raised.value.promotion_run_id is not None
    assert "secret" not in str(raised.value)
    with session_factory() as verify:
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProduct)
            .where(CatalogProduct.supplier_key == profile_name)
        ) == (0 if action == "insert" else 1)
        if action == "update":
            product = verify.scalar(
                select(CatalogProduct).where(
                    CatalogProduct.supplier_key == profile_name
                )
            )
            assert product.price == 15000
            assert product.source_etl_load_run_id == source_run_id
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(
                CatalogProductChange.promotion_run_id
                == raised.value.promotion_run_id
            )
        ) == 0
        runs = list(
            verify.scalars(
                select(CatalogPromotionRun).where(
                    CatalogPromotionRun.etl_load_run_id == load_run_id
                )
            )
        )
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].failure_code == "promotion_apply_failed"
        assert "secret" not in runs[0].safe_failure_message

    monkeypatch.setattr(
        promotion_service,
        "_create_catalog_product_change",
        original_create_change,
    )
    with session_factory() as retry:
        retried = promotion_service.execute_catalog_promotion(
            retry,
            etl_load_run_id=load_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )

    assert retried.status == "succeeded"
    assert retried.created is True


def test_second_request_returns_existing_success_without_new_writes(
    postgres_promotion,
):
    from db.catalog_promotion_service import execute_catalog_promotion

    session_factory, profile_name = postgres_promotion
    with session_factory() as setup:
        load_run = _load_run(profile_name)
        load_run.loaded_rows = 1
        load_run.total_rows = 1
        setup.add(load_run)
        setup.flush()
        setup.add(_staging(load_run.id, "P001"))
        setup.commit()
        load_run_id = load_run.id

    with session_factory() as preview_session:
        expected_hash = _preview_hash(preview_session, load_run_id)

    with session_factory() as first_session:
        first = execute_catalog_promotion(
            first_session,
            etl_load_run_id=load_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )

    with session_factory() as before:
        product = before.scalar(
            select(CatalogProduct).where(
                CatalogProduct.supplier_key == profile_name
            )
        )
        product_updated_at = product.updated_at
        audit_count = before.scalar(
            select(func.count()).select_from(CatalogProductChange)
        )

    with session_factory() as second_session:
        second = execute_catalog_promotion(
            second_session,
            etl_load_run_id=load_run_id,
            confirmation=True,
            expected_preview_hash="f" * 64,
        )

    assert second.promotion_run_id == first.promotion_run_id
    assert second.created is False
    with session_factory() as verify:
        product = verify.scalar(
            select(CatalogProduct).where(
                CatalogProduct.supplier_key == profile_name
            )
        )
        assert product.updated_at == product_updated_at
        assert verify.scalar(
            select(func.count()).select_from(CatalogProductChange)
        ) == audit_count
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogPromotionRun)
            .where(
                CatalogPromotionRun.etl_load_run_id == load_run_id,
                CatalogPromotionRun.status == "succeeded",
            )
        ) == 1
