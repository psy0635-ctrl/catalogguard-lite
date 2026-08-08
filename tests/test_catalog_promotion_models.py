from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    delete,
    func,
    or_,
    select,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from config.database import get_optional_database_url
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogPromotionRun,
    ETLLoadRun,
)
from db.session import create_database_engine, create_session_factory


def _check_constraint_names(table) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _index_names(table) -> set[str]:
    return {index.name for index in table.indexes}


def test_catalog_product_model_defines_identity_provenance_and_constraints():
    columns = CatalogProduct.__table__.c

    assert CatalogProduct.__tablename__ == "catalog_products"
    assert isinstance(columns.id.type, BigInteger)
    assert isinstance(columns.supplier_key.type, String)
    assert columns.supplier_key.type.length == 100
    assert isinstance(columns.external_product_id.type, String)
    assert columns.external_product_id.type.length == 100
    assert isinstance(columns.stock.type, Integer)
    assert isinstance(columns.price.type, BigInteger)
    assert isinstance(columns.sale_price.type, BigInteger)
    assert columns.sale_price.nullable is True
    assert isinstance(columns.description.type, Text)
    assert isinstance(columns.created_at.type, DateTime)
    assert columns.created_at.type.timezone is True
    assert columns.created_at.server_default is not None
    assert columns.updated_at.server_default is not None
    assert columns.updated_at.onupdate is None
    assert {
        "ck_catalog_products_stock_non_negative",
        "ck_catalog_products_price_non_negative",
        "ck_catalog_products_sale_price_non_negative",
        "ck_catalog_products_supplier_key_not_blank",
        "ck_catalog_products_external_product_id_not_blank",
    }.issubset(_check_constraint_names(CatalogProduct.__table__))
    assert {
        "ux_catalog_products_supplier_external_product",
        "ix_catalog_products_source_etl_load_run_id",
    }.issubset(_index_names(CatalogProduct.__table__))


def test_catalog_promotion_run_model_uses_partial_success_unique_index():
    columns = CatalogPromotionRun.__table__.c

    assert CatalogPromotionRun.__tablename__ == "catalog_promotion_runs"
    assert isinstance(columns.preview_hash.type, String)
    assert columns.preview_hash.type.length == 64
    assert columns.preview_hash.nullable is True
    assert columns.inserted_count.server_default is not None
    assert columns.warning_count.server_default is not None
    assert {
        "ck_catalog_promotion_runs_status",
        "ck_catalog_promotion_runs_preview_hash_length",
        "ck_catalog_promotion_runs_inserted_count_non_negative",
        "ck_catalog_promotion_runs_updated_count_non_negative",
        "ck_catalog_promotion_runs_unchanged_count_non_negative",
        "ck_catalog_promotion_runs_blocked_count_non_negative",
        "ck_catalog_promotion_runs_error_count_non_negative",
        "ck_catalog_promotion_runs_warning_count_non_negative",
        "ck_catalog_promotion_runs_completed_at_matches_status",
    }.issubset(_check_constraint_names(CatalogPromotionRun.__table__))
    index = next(
        index
        for index in CatalogPromotionRun.__table__.indexes
        if index.name == "ux_catalog_promotion_runs_succeeded_etl_load_run"
    )
    assert index.unique is True
    assert [column.name for column in index.columns] == ["etl_load_run_id"]
    assert "status = 'succeeded'" in str(
        index.dialect_options["postgresql"]["where"]
    )


def test_catalog_product_change_model_limits_actions_and_jsonb_shapes():
    columns = CatalogProductChange.__table__.c

    assert CatalogProductChange.__tablename__ == "catalog_product_changes"
    assert isinstance(columns.changed_fields.type, JSONB)
    assert columns.changed_fields.nullable is False
    assert isinstance(columns.before_data.type, JSONB)
    assert columns.before_data.nullable is True
    assert columns.before_data.type.none_as_null is True
    assert isinstance(columns.after_data.type, JSONB)
    assert columns.after_data.nullable is False
    assert {
        "ck_catalog_product_changes_action",
        "ck_catalog_product_changes_changed_fields_object",
        "ck_catalog_product_changes_changed_fields_non_empty",
        "ck_catalog_product_changes_before_data_object",
        "ck_catalog_product_changes_after_data_object",
        "ck_catalog_product_changes_before_data_matches_action",
    }.issubset(_check_constraint_names(CatalogProductChange.__table__))
    index = next(
        index
        for index in CatalogProductChange.__table__.indexes
        if index.name == "ix_catalog_product_changes_promotion_run_created_at_id"
    )
    compiled_index = str(
        CreateIndex(index).compile(dialect=postgresql.dialect())
    )
    assert "promotion_run_id" in compiled_index
    assert "created_at DESC" in compiled_index
    assert "id DESC" in compiled_index


@pytest.fixture()
def postgres_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    profile_name = f"promotion_profile_{uuid4().hex}"
    try:
        yield session, profile_name
    finally:
        session.rollback()
        session.close()
        with session_factory() as cleanup:
            load_run_ids = select(ETLLoadRun.id).where(
                ETLLoadRun.profile_name.like(f"{profile_name}%")
            )
            promotion_run_ids = select(CatalogPromotionRun.id).where(
                CatalogPromotionRun.etl_load_run_id.in_(load_run_ids)
            )
            catalog_product_ids = select(CatalogProduct.id).where(
                CatalogProduct.source_etl_load_run_id.in_(load_run_ids)
            )
            cleanup.execute(
                delete(CatalogProductChange).where(
                    or_(
                        CatalogProductChange.promotion_run_id.in_(promotion_run_ids),
                        CatalogProductChange.catalog_product_id.in_(catalog_product_ids),
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


def _create_etl_load_run(session, profile_name: str) -> ETLLoadRun:
    load_run = ETLLoadRun(
        source_filename="supplier.csv",
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256="a" * 64,
        output_file_sha256="b" * 64,
        loaded_rows=0,
    )
    session.add(load_run)
    session.flush()
    return load_run


def _create_catalog_product(session, load_run: ETLLoadRun, **changes) -> CatalogProduct:
    values = {
        "supplier_key": load_run.profile_name,
        "external_product_id": "P001",
        "product_group_id": "G001",
        "product_name": "상품",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 1,
        "price": 100,
        "sale_price": None,
        "image_path": "image.jpg",
        "source_etl_load_run_id": load_run.id,
    }
    values.update(changes)
    product = CatalogProduct(**values)
    session.add(product)
    session.flush()
    return product


def _assert_integrity_error(session, instance) -> None:
    session.add(instance)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_catalog_product_identity_allows_same_external_id_for_different_suppliers(
    postgres_session,
):
    session, profile_name = postgres_session
    source = _create_etl_load_run(session, profile_name)
    _create_catalog_product(session, source)
    session.commit()

    _create_catalog_product(session, source, supplier_key=f"{profile_name}_other")
    session.commit()

    duplicate = CatalogProduct(
        supplier_key=profile_name,
        external_product_id="P001",
        product_group_id="G002",
        product_name="중복 상품",
        category="TOP",
        color="WHITE",
        size="L",
        stock=0,
        price=200,
        image_path="duplicate.jpg",
        source_etl_load_run_id=source.id,
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.flush()


def test_catalog_product_enforces_database_identity_value_and_provenance_constraints(
    postgres_session,
):
    session, profile_name = postgres_session
    source = _create_etl_load_run(session, profile_name)
    product = _create_catalog_product(session, source)
    session.commit()

    assert product.created_at is not None
    assert product.updated_at is not None

    _create_catalog_product(
        session,
        source,
        supplier_key=profile_name,
        external_product_id="P002",
    )
    session.commit()

    def candidate(**changes) -> CatalogProduct:
        values = {
            "supplier_key": profile_name,
            "external_product_id": "P003",
            "product_group_id": "G003",
            "product_name": "constraint product",
            "category": "TOP",
            "color": "BLACK",
            "size": "M",
            "stock": 1,
            "price": 100,
            "image_path": "constraint.jpg",
            "source_etl_load_run_id": source.id,
        }
        values.update(changes)
        return CatalogProduct(**values)

    _assert_integrity_error(
        session,
        candidate(external_product_id="P001"),
    )
    _assert_integrity_error(session, candidate(supplier_key=""))
    _assert_integrity_error(session, candidate(supplier_key="   "))
    _assert_integrity_error(session, candidate(external_product_id=""))
    _assert_integrity_error(session, candidate(external_product_id="   "))
    _assert_integrity_error(session, candidate(stock=-1))
    _assert_integrity_error(session, candidate(price=-1))
    _assert_integrity_error(session, candidate(sale_price=-1))
    _assert_integrity_error(
        session,
        candidate(source_etl_load_run_id=source.id + 1_000_000),
    )


def test_promotion_run_allows_failed_retry_but_blocks_second_success(postgres_session):
    session, profile_name = postgres_session
    source = _create_etl_load_run(session, profile_name)
    session.add(
        CatalogPromotionRun(
            etl_load_run_id=source.id,
            status="failed",
            completed_at=datetime.now(UTC),
        )
    )
    session.add(
        CatalogPromotionRun(
            etl_load_run_id=source.id,
            status="blocked",
            completed_at=datetime.now(UTC),
        )
    )
    session.commit()

    session.add_all(
        [
            CatalogPromotionRun(
                etl_load_run_id=source.id,
                status="failed",
                completed_at=datetime.now(UTC),
            ),
            CatalogPromotionRun(
                etl_load_run_id=source.id,
                status="blocked",
                completed_at=datetime.now(UTC),
            ),
        ]
    )
    session.commit()

    session.add(
        CatalogPromotionRun(
            etl_load_run_id=source.id,
            status="succeeded",
            completed_at=datetime.now(UTC),
        )
    )
    session.commit()

    session.add(
        CatalogPromotionRun(
            etl_load_run_id=source.id,
            status="succeeded",
            completed_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    other_source = _create_etl_load_run(session, f"{profile_name}_other")
    session.add(
        CatalogPromotionRun(
            etl_load_run_id=other_source.id,
            status="succeeded",
            completed_at=datetime.now(UTC),
        )
    )
    session.commit()


def test_product_change_requires_update_before_data_and_object_jsonb(postgres_session):
    session, profile_name = postgres_session
    source = _create_etl_load_run(session, profile_name)
    product = _create_catalog_product(session, source)
    run = CatalogPromotionRun(etl_load_run_id=source.id, status="applying")
    session.add(run)
    session.commit()

    session.add(
        CatalogProductChange(
            promotion_run_id=run.id,
            catalog_product_id=product.id,
            action="update",
            changed_fields={"price": True},
            before_data=None,
            after_data={"price": 200},
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_product_change_enforces_jsonb_shapes_and_action_before_data_rules(
    postgres_session,
):
    session, profile_name = postgres_session
    source = _create_etl_load_run(session, profile_name)
    product = _create_catalog_product(session, source)
    run = CatalogPromotionRun(etl_load_run_id=source.id, status="applying")
    session.add(run)
    session.commit()

    def change(**changes) -> CatalogProductChange:
        values = {
            "promotion_run_id": run.id,
            "catalog_product_id": product.id,
            "action": "insert",
            "changed_fields": {"price": {"before": 100, "after": 200}},
            "before_data": None,
            "after_data": {"price": 200},
        }
        values.update(changes)
        return CatalogProductChange(**values)

    session.add(change())
    session.add(
        change(
            action="update",
            before_data={"price": 100},
            after_data={"price": 200},
        )
    )
    session.commit()

    _assert_integrity_error(session, change(changed_fields={}))
    _assert_integrity_error(session, change(changed_fields=[]))
    _assert_integrity_error(session, change(changed_fields="price"))
    _assert_integrity_error(session, change(before_data=[]))
    _assert_integrity_error(session, change(before_data="before"))
    _assert_integrity_error(session, change(before_data=100))
    _assert_integrity_error(session, change(action="insert", before_data={"price": 100}))
    _assert_integrity_error(session, change(action="update", before_data=None))
    _assert_integrity_error(session, change(after_data=[]))
    _assert_integrity_error(session, change(after_data="after"))
    _assert_integrity_error(session, change(after_data=None))


def test_catalog_promotion_audit_keeps_history_when_operational_product_deleted(postgres_session):
    session, profile_name = postgres_session
    product_source = _create_etl_load_run(session, profile_name)
    product = _create_catalog_product(session, product_source)
    run_source = _create_etl_load_run(session, f"{profile_name}_run")
    run = CatalogPromotionRun(etl_load_run_id=run_source.id, status="applying")
    session.add(run)
    session.flush()
    change = CatalogProductChange(
        promotion_run_id=run.id,
        catalog_product_id=product.id,
        action="insert",
        changed_fields={"price": {"before": 100, "after": 100}},
        before_data=None,
        after_data={"price": 100},
    )
    session.add(change)
    session.commit()

    session.execute(delete(CatalogProduct).where(CatalogProduct.id == product.id))
    session.commit()

    assert session.scalar(
        select(func.count())
        .select_from(CatalogProductChange)
        .where(CatalogProductChange.id == change.id)
    ) == 1
