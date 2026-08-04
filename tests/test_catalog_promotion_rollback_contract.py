from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from api.main import app
from config.database import get_optional_database_url
from db.catalog_promotion_preview_service import preview_catalog_promotion
from db.catalog_promotion_rollback_service import (
    CatalogPromotionRollbackAlreadyExecutedError,
    execute_catalog_promotion_rollback,
    preview_catalog_promotion_rollback,
)
from db.catalog_promotion_service import execute_catalog_promotion
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogProductStaging,
    CatalogPromotionRollback,
    CatalogPromotionRollbackChange,
    CatalogPromotionRun,
    ETLLoadRun,
)
from db.session import create_database_engine, create_session_factory


def _product_data(**changes):
    data = {
        "external_product_id": "SKU-001",
        "product_group_id": "GROUP-001",
        "product_name": "Product 1",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 10,
        "price": 15000,
        "sale_price": 12000,
        "image_path": "product.jpg",
        "description": "description",
        "seller": "seller",
    }
    data.update(changes)
    return data


def test_rollback_schema_has_separate_execution_and_product_audit_tables():
    assert CatalogPromotionRollback.__tablename__ == "catalog_promotion_rollbacks"
    assert CatalogPromotionRollbackChange.__tablename__ == (
        "catalog_promotion_rollback_changes"
    )
    assert {
        "target_promotion_run_id",
        "status",
        "preview_hash",
        "restored_count",
        "deleted_count",
        "conflict_count",
        "failure_code",
        "completed_at",
    }.issubset(CatalogPromotionRollback.__table__.columns.keys())


def test_rollback_preview_hash_changes_when_current_catalog_changes():
    from db.catalog_promotion_rollback_service import (
        build_rollback_preview_hash,
    )

    before = build_rollback_preview_hash(
        target_promotion_run_id=10,
        audit_items=[
            SimpleNamespace(
                id=1,
                catalog_product_id=20,
                action="update",
                before_data=_product_data(price=10000),
                after_data=_product_data(),
            )
        ],
        current_products={20: _product_data()},
    )
    after = build_rollback_preview_hash(
        target_promotion_run_id=10,
        audit_items=[
            SimpleNamespace(
                id=1,
                catalog_product_id=20,
                action="update",
                before_data=_product_data(price=10000),
                after_data=_product_data(),
            )
        ],
        current_products={20: _product_data(price=16000)},
    )
    assert before != after


def test_rollback_preview_item_distinguishes_insert_delete_and_update_restore():
    from db.catalog_promotion_rollback_service import build_rollback_preview_items

    insert_audit = SimpleNamespace(
        id=1,
        catalog_product_id=20,
        action="insert",
        before_data=None,
        after_data=_product_data(),
    )
    update_audit = SimpleNamespace(
        id=2,
        catalog_product_id=21,
        action="update",
        before_data=_product_data(price=10000),
        after_data=_product_data(price=12000),
    )
    items = build_rollback_preview_items(
        [insert_audit, update_audit],
        {
            20: _product_data(),
            21: _product_data(price=12000),
        },
    )
    assert [(item.rollback_action, item.conflict) for item in items] == [
        ("delete", False),
        ("restore", False),
    ]
    assert items[0].restore_data is None
    assert items[1].restore_data["price"] == 10000


def test_rollback_preview_marks_later_promotion_as_conflict():
    from db.catalog_promotion_rollback_service import build_rollback_preview_items

    audit = SimpleNamespace(
        id=1,
        catalog_product_id=20,
        action="update",
        before_data=_product_data(price=10000),
        after_data=_product_data(price=12000),
    )
    items = build_rollback_preview_items(
        [audit], {20: _product_data(price=15000)}
    )
    assert items[0].conflict is True
    assert items[0].conflict_reason == "rollback_conflict"


def test_rollback_api_exposes_preview_and_requires_confirmation(monkeypatch):
    from api.routes import etl_loads as route
    from db.catalog_promotion_rollback_service import (
        CatalogPromotionRollbackConfirmationRequiredError,
    )

    preview = SimpleNamespace(
        target_promotion_run_id=7,
        preview_schema_version=1,
        preview_hash="a" * 64,
        rollback_eligible=True,
        blocked_reasons=[],
        restore_count=1,
        delete_count=1,
        conflict_count=0,
        items=[],
    )
    monkeypatch.setattr(route, "preview_catalog_promotion_rollback", lambda *_args, **_kwargs: preview)
    monkeypatch.setattr(
        route,
        "execute_catalog_promotion_rollback",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CatalogPromotionRollbackConfirmationRequiredError()
        ),
    )
    session = object()

    def override_session():
        yield session

    app.dependency_overrides[route.get_session] = override_session
    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.post(
            "/api/v1/catalog-promotions/7/rollback-preview"
        )
        assert response.status_code == 200
        assert response.json()["rollback_eligible"] is True
        assert response.json()["delete_count"] == 1

        response = client.post(
            "/api/v1/catalog-promotions/7/rollback",
            json={"confirmation": False, "expected_preview_hash": "a" * 64},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "confirmation_required"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("action", ["delete", "restore"])
def test_rollback_change_action_contract(action):
    assert action in {"delete", "restore"}


@pytest.fixture()
def postgres_rollback():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip(
            "TEST_DATABASE_URL이 설정되지 않아 PostgreSQL Rollback 통합 테스트를 건너뜁니다."
        )

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    profile_name = f"rollback_contract_{uuid4().hex}"
    try:
        yield session_factory, profile_name
    finally:
        with session_factory() as cleanup:
            load_run_ids = select(ETLLoadRun.id).where(
                ETLLoadRun.profile_name.like(f"{profile_name}%")
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
            rollback_run_ids = select(CatalogPromotionRollback.id).where(
                CatalogPromotionRollback.target_promotion_run_id.in_(
                    promotion_run_ids
                )
            )
            cleanup.execute(
                delete(CatalogPromotionRollbackChange).where(
                    CatalogPromotionRollbackChange.rollback_run_id.in_(
                        rollback_run_ids
                    )
                )
            )
            cleanup.execute(
                delete(CatalogPromotionRollback).where(
                    CatalogPromotionRollback.id.in_(rollback_run_ids)
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


def _rollback_load_run(profile_name: str, *, suffix: str = "") -> ETLLoadRun:
    return ETLLoadRun(
        source_filename=f"supplier{suffix}.csv",
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256=("a" if not suffix else "c") * 64,
        output_file_sha256=("b" if not suffix else "d") * 64,
        loaded_rows=1,
        total_rows=1,
        rejected_rows=0,
        error_counts={},
    )


def _rollback_staging(load_run_id: int, product_id: str, **changes):
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


def _rollback_catalog(profile_name: str, load_run_id: int, product_id: str, **changes):
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


def _promote(session_factory, profile_name: str, staging_rows: list[CatalogProductStaging]) -> int:
    with session_factory() as setup:
        load_run = _rollback_load_run(profile_name)
        setup.add(load_run)
        setup.flush()
        for row in staging_rows:
            row.etl_load_run_id = load_run.id
            setup.add(row)
        setup.commit()
        load_run_id = load_run.id

    with session_factory() as preview_session:
        preview = preview_catalog_promotion(
            preview_session, etl_load_run_id=load_run_id
        )
        assert preview.preview_hash is not None
        expected_hash = preview.preview_hash
        preview_session.rollback()

    with session_factory() as session:
        result = execute_catalog_promotion(
            session,
            etl_load_run_id=load_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )
    assert result.status == "succeeded"
    return result.promotion_run_id


def test_postgres_insert_rollback_deletes_product_and_preserves_audits(
    postgres_rollback,
):
    session_factory, profile_name = postgres_rollback
    promotion_run_id = _promote(
        session_factory,
        profile_name,
        [_rollback_staging(0, "P001")],
    )

    with session_factory() as session:
        preview = preview_catalog_promotion_rollback(
            session, promotion_run_id=promotion_run_id
        )
        assert preview.rollback_eligible is True
        assert preview.delete_count == 1
        assert preview.restore_count == 0
        expected_hash = preview.preview_hash

    with session_factory() as session:
        result = execute_catalog_promotion_rollback(
            session,
            promotion_run_id=promotion_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )
    assert result.status == "succeeded"
    assert result.deleted_count == 1
    assert result.restored_count == 0

    with session_factory() as verify:
        assert (
            verify.scalar(
                select(func.count())
                .select_from(CatalogProduct)
                .where(CatalogProduct.supplier_key == profile_name)
            )
            == 0
        )
        original_audit = verify.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(CatalogProductChange.promotion_run_id == promotion_run_id)
        )
        assert original_audit == 1
        rollback_change = verify.scalar(
            select(func.count())
            .select_from(CatalogPromotionRollbackChange)
            .where(CatalogPromotionRollbackChange.rollback_run_id == result.rollback_run_id)
        )
        assert rollback_change == 1
        promotion_run = verify.get(CatalogPromotionRun, promotion_run_id)
        assert promotion_run is not None
        assert promotion_run.status == "succeeded"


def test_postgres_update_rollback_restores_prior_values_exactly(postgres_rollback):
    session_factory, profile_name = postgres_rollback
    with session_factory() as setup:
        source_run = _rollback_load_run(profile_name, suffix="-source")
        setup.add(source_run)
        setup.flush()
        product = _rollback_catalog(
            profile_name,
            source_run.id,
            "P002",
            price=15000,
            sale_price=None,
            stock=7,
            description=None,
            seller=None,
        )
        setup.add(product)
        setup.commit()
        product_id = product.id

    promotion_run_id = _promote(
        session_factory,
        profile_name,
        [
            _rollback_staging(
                0,
                "P002",
                price=21900,
                sale_price=19900,
                stock=3,
                description="updated",
                seller="new-seller",
            )
        ],
    )

    with session_factory() as verify:
        promoted = verify.get(CatalogProduct, product_id)
        assert promoted.price == 21900
        assert promoted.sale_price == 19900
        assert promoted.stock == 3

    with session_factory() as session:
        preview = preview_catalog_promotion_rollback(
            session, promotion_run_id=promotion_run_id
        )
        assert preview.rollback_eligible is True
        assert preview.restore_count == 1
        expected_hash = preview.preview_hash

    with session_factory() as session:
        result = execute_catalog_promotion_rollback(
            session,
            promotion_run_id=promotion_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )
    assert result.status == "succeeded"
    assert result.restored_count == 1

    with session_factory() as verify:
        restored = verify.get(CatalogProduct, product_id)
        assert restored.price == 15000
        assert restored.sale_price is None
        assert restored.stock == 7
        assert restored.description is None
        assert restored.seller is None
        assert (
            verify.scalar(
                select(func.count())
                .select_from(CatalogProductChange)
                .where(CatalogProductChange.promotion_run_id == promotion_run_id)
            )
            == 1
        )


def test_postgres_rollback_blocked_when_product_changed_after_promotion(
    postgres_rollback,
):
    session_factory, profile_name = postgres_rollback
    promotion_run_id = _promote(
        session_factory,
        profile_name,
        [_rollback_staging(0, "P003", price=10000)],
    )

    with session_factory() as mutate:
        product = mutate.scalar(
            select(CatalogProduct).where(
                CatalogProduct.supplier_key == profile_name
            )
        )
        product_id = product.id
        product.price = 99999
        mutate.commit()

    with session_factory() as session:
        preview = preview_catalog_promotion_rollback(
            session, promotion_run_id=promotion_run_id
        )
        assert preview.rollback_eligible is False
        assert preview.conflict_count == 1
        assert any(
            reason.code == "rollback_conflict" for reason in preview.blocked_reasons
        )

    with session_factory() as session:
        result = execute_catalog_promotion_rollback(
            session,
            promotion_run_id=promotion_run_id,
            confirmation=True,
            expected_preview_hash="f" * 64,
        )
    assert result.status == "blocked"
    assert result.failure_code in {"rollback_conflict", "preview_stale"}

    with session_factory() as verify:
        untouched = verify.get(CatalogProduct, product_id)
        assert untouched.price == 99999


def test_postgres_stale_preview_hash_is_rejected_without_mutating_catalog(
    postgres_rollback,
):
    session_factory, profile_name = postgres_rollback
    promotion_run_id = _promote(
        session_factory,
        profile_name,
        [_rollback_staging(0, "P004")],
    )

    with session_factory() as session:
        preview = preview_catalog_promotion_rollback(
            session, promotion_run_id=promotion_run_id
        )
        assert preview.rollback_eligible is True

    with session_factory() as session:
        result = execute_catalog_promotion_rollback(
            session,
            promotion_run_id=promotion_run_id,
            confirmation=True,
            expected_preview_hash="0" * 64,
        )
    assert result.status == "blocked"
    assert result.failure_code == "preview_stale"

    with session_factory() as verify:
        assert (
            verify.scalar(
                select(func.count())
                .select_from(CatalogProduct)
                .where(CatalogProduct.supplier_key == profile_name)
            )
            == 1
        )


def test_postgres_duplicate_rollback_is_blocked_at_service_and_db_level(
    postgres_rollback,
):
    session_factory, profile_name = postgres_rollback
    promotion_run_id = _promote(
        session_factory,
        profile_name,
        [_rollback_staging(0, "P005")],
    )

    with session_factory() as session:
        preview = preview_catalog_promotion_rollback(
            session, promotion_run_id=promotion_run_id
        )
        expected_hash = preview.preview_hash

    with session_factory() as session:
        first = execute_catalog_promotion_rollback(
            session,
            promotion_run_id=promotion_run_id,
            confirmation=True,
            expected_preview_hash=expected_hash,
        )
    assert first.status == "succeeded"

    with session_factory() as session:
        with pytest.raises(CatalogPromotionRollbackAlreadyExecutedError):
            execute_catalog_promotion_rollback(
                session,
                promotion_run_id=promotion_run_id,
                confirmation=True,
                expected_preview_hash=expected_hash,
            )

    with session_factory() as raw:
        duplicate = CatalogPromotionRollback(
            target_promotion_run_id=promotion_run_id,
            status="succeeded",
            preview_hash="1" * 64,
            preview_schema_version="1",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        raw.add(duplicate)
        with pytest.raises(IntegrityError):
            raw.flush()
        raw.rollback()


def test_postgres_rollback_transaction_is_atomic_on_partial_failure(
    postgres_rollback,
):
    session_factory, profile_name = postgres_rollback
    with session_factory() as setup:
        source_run = _rollback_load_run(profile_name, suffix="-source")
        setup.add(source_run)
        setup.flush()
        good_product = _rollback_catalog(
            profile_name, source_run.id, "P006", price=10000
        )
        bad_product = _rollback_catalog(
            profile_name, source_run.id, "P007", price=12000
        )
        setup.add_all([good_product, bad_product])
        setup.commit()
        good_id = good_product.id
        bad_id = bad_product.id

    promotion_run_id = _promote(
        session_factory,
        profile_name,
        [
            _rollback_staging(0, "P006", price=15000),
            _rollback_staging(0, "P007", price=17000),
        ],
    )

    with session_factory() as after_promotion:
        good_updated_at = after_promotion.get(CatalogProduct, good_id).updated_at
        bad_updated_at = after_promotion.get(CatalogProduct, bad_id).updated_at

    # Corrupt one of the two recorded audits so its restore violates the
    # catalog_products price>=0 CHECK constraint. This forces a failure
    # partway through the rollback loop, after the first product's restore
    # has already been applied in-session but before the transaction commits.
    with session_factory() as corrupt:
        bad_change = corrupt.scalar(
            select(CatalogProductChange).where(
                CatalogProductChange.catalog_product_id == bad_id,
                CatalogProductChange.promotion_run_id == promotion_run_id,
            )
        )
        before = dict(bad_change.before_data)
        before["price"] = -1
        bad_change.before_data = before
        corrupt.commit()

    with session_factory() as session:
        preview = preview_catalog_promotion_rollback(
            session, promotion_run_id=promotion_run_id
        )
        assert preview.rollback_eligible is True
        expected_hash = preview.preview_hash

    with session_factory() as session:
        from db.catalog_promotion_rollback_service import (
            CatalogPromotionRollbackExecutionFailedError,
        )

        with pytest.raises(CatalogPromotionRollbackExecutionFailedError):
            execute_catalog_promotion_rollback(
                session,
                promotion_run_id=promotion_run_id,
                confirmation=True,
                expected_preview_hash=expected_hash,
            )

    with session_factory() as verify:
        good = verify.get(CatalogProduct, good_id)
        bad = verify.get(CatalogProduct, bad_id)
        assert good.price == 15000
        assert good.updated_at == good_updated_at
        assert bad.price == 17000
        assert bad.updated_at == bad_updated_at
        assert (
            verify.scalar(
                select(func.count())
                .select_from(CatalogPromotionRollbackChange)
                .join(
                    CatalogPromotionRollback,
                    CatalogPromotionRollback.id
                    == CatalogPromotionRollbackChange.rollback_run_id,
                )
                .where(
                    CatalogPromotionRollback.target_promotion_run_id
                    == promotion_run_id
                )
            )
            == 0
        )
        runs = list(
            verify.scalars(
                select(CatalogPromotionRollback).where(
                    CatalogPromotionRollback.target_promotion_run_id
                    == promotion_run_id
                )
            )
        )
        assert len(runs) == 1
        assert runs[0].status == "failed"
