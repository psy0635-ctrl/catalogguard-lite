from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select

from api.main import app
from api.routes import etl_loads as etl_loads_route
from config.database import get_optional_database_url
from db.catalog_promotion_preview_service import (
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
    ETLRejectedRow,
    InspectionResult,
    InspectionRun,
)
from db.session import (
    create_database_engine,
    create_session_factory,
    get_session,
)


ENDPOINT = "/api/v1/etl-loads/42/promotion-preview"
client = TestClient(app, raise_server_exceptions=False)


class WriteGuardSession:
    def add(self, _instance) -> None:
        raise AssertionError("preview endpoint must not add database rows")

    def add_all(self, _instances) -> None:
        raise AssertionError("preview endpoint must not add database rows")

    def delete(self, _instance) -> None:
        raise AssertionError("preview endpoint must not delete database rows")

    def flush(self) -> None:
        raise AssertionError("preview endpoint must not flush")

    def commit(self) -> None:
        raise AssertionError("preview endpoint must not commit")


class _ScalarRows:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None


class ActualPreviewSession(WriteGuardSession):
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
        self.no_autoflush = nullcontext()

    def get(self, model, identity):
        if model is ETLLoadRun and self.load_run is not None:
            if self.load_run.id == identity:
                return self.load_run
        return None

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is CatalogProductStaging:
            return _ScalarRows(self.staging)
        if entity is ETLRejectedRow:
            return _ScalarRows(self.rejected)
        if entity is CatalogProduct:
            return _ScalarRows(self.catalog)
        raise AssertionError(f"Unexpected query entity: {entity}")


def _product_data(**overrides) -> dict[str, str | int | None]:
    values: dict[str, str | int | None] = {
        "external_product_id": "P001",
        "product_group_id": "G001",
        "product_name": "Product",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 10,
        "price": 19900,
        "sale_price": None,
        "image_path": "p001.jpg",
        "description": None,
        "seller": None,
    }
    values.update(overrides)
    return values


def _preview_result(**overrides) -> CatalogPromotionPreview:
    insert_data = _product_data()
    update_before = _product_data(
        external_product_id="P002",
        product_group_id="G002",
        price=19900,
        description="old",
    )
    update_after = dict(update_before)
    update_after.update(price=21900, description=None)
    unchanged_data = _product_data(
        external_product_id="P003",
        product_group_id="G003",
    )
    values = {
        "etl_load_run_id": 42,
        "supplier_key": "supplier-a",
        "inspection_version": "5",
        "preview_schema_version": 1,
        "preview_hash": "a" * 64,
        "promotion_eligible": True,
        "blocked_reasons": [],
        "insert_count": 1,
        "update_count": 1,
        "unchanged_count": 1,
        "error_count": 0,
        "warning_count": 0,
        "items": [
            PromotionPreviewItem(
                supplier_key="supplier-a",
                external_product_id="P001",
                action="insert",
                changed_fields={},
                before_data=None,
                after_data=insert_data,
            ),
            PromotionPreviewItem(
                supplier_key="supplier-a",
                external_product_id="P002",
                action="update",
                changed_fields={
                    "price": {"before": 19900, "after": 21900},
                    "description": {"before": "old", "after": None},
                },
                before_data=update_before,
                after_data=update_after,
            ),
            PromotionPreviewItem(
                supplier_key="supplier-a",
                external_product_id="P003",
                action="unchanged",
                changed_fields={},
                before_data=unchanged_data,
                after_data=unchanged_data,
            ),
        ],
    }
    values.update(overrides)
    return CatalogPromotionPreview(**values)


@pytest.fixture()
def mock_preview_api(monkeypatch):
    session = WriteGuardSession()
    state = SimpleNamespace(
        result=_preview_result(),
        error=None,
        calls=[],
    )

    def override_session():
        yield session

    def fake_preview_catalog_promotion(
        received_session,
        *,
        etl_load_run_id,
    ):
        state.calls.append(
            {
                "session": received_session,
                "etl_load_run_id": etl_load_run_id,
            }
        )
        if state.error is not None:
            raise state.error
        return state.result

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        etl_loads_route,
        "preview_catalog_promotion",
        fake_preview_catalog_promotion,
        raising=False,
    )
    yield state
    app.dependency_overrides.clear()


def test_preview_endpoint_returns_complete_insert_update_unchanged_contract(
    mock_preview_api,
):
    response = client.post(ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "etl_load_run_id": 42,
        "supplier_key": "supplier-a",
        "inspection_version": "5",
        "preview_schema_version": 1,
        "preview_hash": "a" * 64,
        "promotion_eligible": True,
        "blocked_reasons": [],
        "insert_count": 1,
        "update_count": 1,
        "unchanged_count": 1,
        "error_count": 0,
        "warning_count": 0,
        "items": [
            {
                "supplier_key": "supplier-a",
                "external_product_id": "P001",
                "action": "insert",
                "changed_fields": {},
                "before_data": None,
                "after_data": _product_data(),
            },
            {
                "supplier_key": "supplier-a",
                "external_product_id": "P002",
                "action": "update",
                "changed_fields": {
                    "price": {"before": 19900, "after": 21900},
                    "description": {"before": "old", "after": None},
                },
                "before_data": _product_data(
                    external_product_id="P002",
                    product_group_id="G002",
                    price=19900,
                    description="old",
                ),
                "after_data": _product_data(
                    external_product_id="P002",
                    product_group_id="G002",
                    price=21900,
                    description=None,
                ),
            },
            {
                "supplier_key": "supplier-a",
                "external_product_id": "P003",
                "action": "unchanged",
                "changed_fields": {},
                "before_data": _product_data(
                    external_product_id="P003",
                    product_group_id="G003",
                ),
                "after_data": _product_data(
                    external_product_id="P003",
                    product_group_id="G003",
                ),
            },
        ],
    }


def test_preview_endpoint_calls_service_once_with_injected_session(mock_preview_api):
    response = client.post(ENDPOINT)

    assert response.status_code == 200
    assert mock_preview_api.calls == [
        {
            "session": mock_preview_api.calls[0]["session"],
            "etl_load_run_id": 42,
        }
    ]


def test_warning_only_preview_remains_eligible(mock_preview_api):
    mock_preview_api.result = _preview_result(warning_count=2)

    response = client.post(ENDPOINT)

    assert response.status_code == 200
    assert response.json()["promotion_eligible"] is True
    assert response.json()["warning_count"] == 2


def test_blocked_preview_remains_http_200_with_safe_reason(mock_preview_api):
    mock_preview_api.result = _preview_result(
        promotion_eligible=False,
        blocked_reasons=[
            PromotionPreviewBlockedReason(
                code="inspection_errors_present",
                message="상품 검수 오류가 있어 운영 반영을 진행할 수 없습니다.",
            )
        ],
        insert_count=0,
        update_count=0,
        unchanged_count=0,
        error_count=1,
        items=[],
    )

    response = client.post(ENDPOINT)

    assert response.status_code == 200
    reason = response.json()["blocked_reasons"][0]
    assert reason["code"] == "inspection_errors_present"
    assert reason["message"] == "상품 검수 오류가 있어 운영 반영을 진행할 수 없습니다."


def test_duplicate_identity_preview_preserves_null_hash_and_safe_details(
    mock_preview_api,
):
    mock_preview_api.result = _preview_result(
        preview_hash=None,
        promotion_eligible=False,
        blocked_reasons=[
            PromotionPreviewBlockedReason(
                code="duplicate_product_identity",
                message="같은 공급사 상품 식별자가 배치 안에 중복되어 있습니다.",
                supplier_key="supplier-a",
                external_product_id="P001",
                staging_product_ids=(101, 102),
            )
        ],
        insert_count=0,
        update_count=0,
        unchanged_count=0,
        items=[],
    )

    response = client.post(ENDPOINT)

    assert response.status_code == 200
    assert response.json()["preview_hash"] is None
    assert response.json()["blocked_reasons"] == [
        {
            "code": "duplicate_product_identity",
            "message": "같은 공급사 상품 식별자가 배치 안에 중복되어 있습니다.",
            "supplier_key": "supplier-a",
            "external_product_id": "P001",
            "staging_product_ids": [101, 102],
        }
    ]


def test_successful_preview_response_disables_caching(mock_preview_api):
    response = client.post(ENDPOINT)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_missing_batch_domain_error_becomes_safe_404(mock_preview_api):
    mock_preview_api.error = ETLLoadRunNotFoundError(999999)

    response = client.post("/api/v1/etl-loads/999999/promotion-preview")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "ETL 적재 배치를 찾을 수 없습니다."
    }


@pytest.mark.parametrize("path_value", ["0", "-1", "not-a-number"])
def test_invalid_preview_path_id_returns_422(path_value, mock_preview_api):
    response = client.post(
        f"/api/v1/etl-loads/{path_value}/promotion-preview"
    )

    assert response.status_code == 422
    assert mock_preview_api.calls == []


def test_unexpected_service_error_does_not_leak_sensitive_details(mock_preview_api):
    mock_preview_api.error = RuntimeError(
        "postgresql://admin:secret@db.internal/catalog SQL SELECT private"
    )

    response = client.post(ENDPOINT)

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert "secret" not in response.text
    assert "SELECT" not in response.text


def test_preview_item_schema_rejects_unknown_action():
    from api.schemas import CatalogPromotionPreviewItemResponse

    with pytest.raises(ValidationError):
        CatalogPromotionPreviewItemResponse(
            supplier_key="supplier-a",
            external_product_id="P001",
            action="delete",
            changed_fields={},
            before_data=None,
            after_data=_product_data(),
        )


def test_blocked_reason_schema_accepts_minimum_fields_without_shared_defaults():
    from api.schemas import CatalogPromotionBlockedReasonResponse

    first = CatalogPromotionBlockedReasonResponse(
        code="inspection_errors_present",
        message="blocked",
    )
    second = CatalogPromotionBlockedReasonResponse(
        code="quality_summary_missing",
        message="blocked",
    )

    first.staging_product_ids.append(101)

    assert first.staging_product_ids == [101]
    assert second.staging_product_ids == []


def test_endpoint_uses_real_preview_service_and_preserves_nullable_values(
    monkeypatch,
):
    load_run = ETLLoadRun(
        id=42,
        source_filename="supplier.csv",
        profile_name="supplier-a",
        profile_version="1",
        input_file_sha256="a" * 64,
        output_file_sha256="b" * 64,
        loaded_rows=1,
        total_rows=1,
        rejected_rows=0,
        error_counts={},
        reject_details_stored=False,
        rejects_file_sha256=None,
    )
    staging = CatalogProductStaging(
        id=101,
        etl_load_run_id=42,
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
    session = ActualPreviewSession(load_run, staging=[staging])

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        etl_loads_route,
        "preview_catalog_promotion",
        preview_catalog_promotion,
        raising=False,
    )
    try:
        response = client.post(ENDPOINT)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["promotion_eligible"] is True
    assert data["insert_count"] == 1
    assert len(data["preview_hash"]) == 64
    assert data["items"][0]["before_data"] is None
    assert data["items"][0]["after_data"]["sale_price"] is None
    assert data["items"][0]["after_data"]["description"] is None
    assert data["items"][0]["after_data"]["seller"] is None


@pytest.fixture()
def postgres_preview_api():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip(
            "TEST_DATABASE_URL is not configured; skipping PostgreSQL API integration test."
        )

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    profile_name = f"preview_api_profile_{uuid4().hex}"
    try:
        yield session_factory, profile_name
    finally:
        app.dependency_overrides.clear()
        with session_factory() as cleanup:
            load_run_ids = select(ETLLoadRun.id).where(
                ETLLoadRun.profile_name == profile_name
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
                    CatalogProduct.source_etl_load_run_id.in_(load_run_ids)
                )
            )
            cleanup.execute(
                delete(ETLLoadRun).where(ETLLoadRun.id.in_(load_run_ids))
            )
            cleanup.commit()
        engine.dispose()


def test_postgresql_api_preview_leaves_all_related_tables_unchanged(
    postgres_preview_api,
):
    session_factory, profile_name = postgres_preview_api
    with session_factory() as setup:
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
        setup.add(load_run)
        setup.flush()
        setup.add(
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
        setup.add(catalog_product)
        setup.commit()
        load_run_id = load_run.id
        catalog_product_id = catalog_product.id

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
    with session_factory() as before_session:
        counts_before = {
            model.__tablename__: before_session.scalar(
                select(func.count()).select_from(model)
            )
            for model in tables
        }
        product = before_session.get(CatalogProduct, catalog_product_id)
        run = before_session.get(ETLLoadRun, load_run_id)
        product_before = (
            product.stock,
            product.price,
            product.description,
            product.updated_at,
        )
        load_summary_before = (
            run.total_rows,
            run.rejected_rows,
            dict(run.error_counts),
        )

    def override_session():
        with session_factory() as request_session:
            yield request_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = client.post(
            f"/api/v1/etl-loads/{load_run_id}/promotion-preview"
        )
    finally:
        app.dependency_overrides.clear()

    with session_factory() as after_session:
        counts_after = {
            model.__tablename__: after_session.scalar(
                select(func.count()).select_from(model)
            )
            for model in tables
        }
        product = after_session.get(CatalogProduct, catalog_product_id)
        run = after_session.get(ETLLoadRun, load_run_id)
        product_after = (
            product.stock,
            product.price,
            product.description,
            product.updated_at,
        )
        load_summary_after = (
            run.total_rows,
            run.rejected_rows,
            dict(run.error_counts),
        )

    assert response.status_code == 200
    assert response.json()["unchanged_count"] == 1
    assert counts_after == counts_before
    assert product_after == product_before
    assert load_summary_after == load_summary_before
