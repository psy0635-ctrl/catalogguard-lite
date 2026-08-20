"""API contract for the read-only Catalog Reconciliation Report."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import etl_loads as etl_loads_route
from conftest import clear_current_user_override, override_current_user
from db.catalog_promotion_preview_service import ETLLoadRunNotFoundError
from db.catalog_reconciliation_service import (
    CatalogReconciliationDuplicateIdentityError,
    CatalogReconciliationItem,
    CatalogReconciliationReport,
)
from db.session import get_session


ENDPOINT = "/api/v1/etl-loads/42/catalog-reconciliation"
client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def authenticated_viewer():
    override_current_user(role="viewer")
    yield
    clear_current_user_override()
    app.dependency_overrides.clear()


def _report(**changes) -> CatalogReconciliationReport:
    values = {
        "etl_load_run_id": 42,
        "supplier_key": "sample_fashion_vendor",
        "total_rows": 4,
        "loaded_rows": 3,
        "rejected_rows": 1,
        "new_count": 1,
        "changed_count": 1,
        "unchanged_count": 1,
        "not_observed_in_batch_count": 1,
        "field_change_counts": {"stock": 1},
        "items": [
            CatalogReconciliationItem(
                external_product_id="P002",
                status="new",
                changed_fields={},
            ),
            CatalogReconciliationItem(
                external_product_id="P001",
                status="changed",
                changed_fields={"stock": {"before": 10, "after": 7}},
            ),
            CatalogReconciliationItem(
                external_product_id="P003",
                status="unchanged",
                changed_fields={},
            ),
            CatalogReconciliationItem(
                external_product_id="P900",
                status="not_observed_in_batch",
                changed_fields={},
            ),
        ],
        "total": 4,
        "limit": 50,
        "offset": 0,
    }
    values.update(changes)
    return CatalogReconciliationReport(**values)


def _override_service(monkeypatch, result_or_error, *, calls=None):
    app.dependency_overrides[get_session] = lambda: iter([object()])

    def fake_build(session, *, etl_load_run_id, limit, offset):
        if calls is not None:
            calls.append({"etl_load_run_id": etl_load_run_id, "limit": limit, "offset": offset})
        if isinstance(result_or_error, Exception):
            raise result_or_error
        return result_or_error

    monkeypatch.setattr(
        etl_loads_route,
        "build_catalog_reconciliation_report",
        fake_build,
    )


def test_reconciliation_returns_counts_field_changes_and_items(monkeypatch):
    _override_service(monkeypatch, _report())

    response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "etl_load_run_id": 42,
        "supplier_key": "sample_fashion_vendor",
        "total_rows": 4,
        "loaded_rows": 3,
        "rejected_rows": 1,
        "new_count": 1,
        "changed_count": 1,
        "unchanged_count": 1,
        "not_observed_in_batch_count": 1,
        "field_change_counts": {"stock": 1},
        "items": [
            {"external_product_id": "P002", "status": "new", "changed_fields": {}},
            {
                "external_product_id": "P001",
                "status": "changed",
                "changed_fields": {"stock": {"before": 10, "after": 7}},
            },
            {"external_product_id": "P003", "status": "unchanged", "changed_fields": {}},
            {
                "external_product_id": "P900",
                "status": "not_observed_in_batch",
                "changed_fields": {},
            },
        ],
        "total": 4,
        "limit": 50,
        "offset": 0,
    }


def test_legacy_batch_reports_null_quality_metadata(monkeypatch):
    # 품질 요약 저장 이전 배치를 0으로 표시하지 않습니다.
    _override_service(
        monkeypatch,
        _report(total_rows=None, rejected_rows=None, loaded_rows=3),
    )

    payload = client.get(ENDPOINT).json()

    assert payload["total_rows"] is None
    assert payload["rejected_rows"] is None
    assert payload["loaded_rows"] == 3


def test_not_observed_item_has_no_synthetic_product_payload(monkeypatch):
    # 상품이 배치에 없다는 뜻으로 빈 문자열 상품 객체를 만들어 내지 않습니다.
    _override_service(monkeypatch, _report())

    items = response_items(client.get(ENDPOINT))
    not_observed = next(
        item for item in items if item["status"] == "not_observed_in_batch"
    )

    assert not_observed["changed_fields"] == {}
    assert set(not_observed) == {"external_product_id", "status", "changed_fields"}


def response_items(response):
    return response.json()["items"]


def test_default_pagination_matches_the_documented_contract(monkeypatch):
    calls: list[dict] = []
    _override_service(monkeypatch, _report(), calls=calls)

    client.get(ENDPOINT)

    assert calls == [{"etl_load_run_id": 42, "limit": 50, "offset": 0}]


def test_explicit_pagination_is_passed_through(monkeypatch):
    calls: list[dict] = []
    _override_service(monkeypatch, _report(limit=10, offset=20), calls=calls)

    response = client.get(ENDPOINT, params={"limit": 10, "offset": 20})

    assert response.status_code == 200
    assert calls == [{"etl_load_run_id": 42, "limit": 10, "offset": 20}]
    assert response.json()["limit"] == 10
    assert response.json()["offset"] == 20


def test_missing_etl_load_run_returns_404(monkeypatch):
    _override_service(monkeypatch, ETLLoadRunNotFoundError(42))

    response = client.get(ENDPOINT)

    assert response.status_code == 404
    assert response.json()["detail"] == "ETL 적재 배치를 찾을 수 없습니다."


def test_duplicate_staging_identity_returns_safe_409(monkeypatch):
    _override_service(
        monkeypatch,
        CatalogReconciliationDuplicateIdentityError(("P001",)),
    )

    response = client.get(ENDPOINT)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "duplicate_product_identity"
    # 내부 경로·SQL·staging row id는 노출하지 않습니다.
    text = response.text.lower()
    assert "select" not in text and "catalog_products" not in text
    assert "/" not in response.json()["detail"]["message"]


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_invalid_limit_is_rejected_with_422(monkeypatch, limit):
    _override_service(monkeypatch, _report())

    assert client.get(ENDPOINT, params={"limit": limit}).status_code == 422


def test_negative_offset_is_rejected_with_422(monkeypatch):
    _override_service(monkeypatch, _report())

    assert client.get(ENDPOINT, params={"offset": -1}).status_code == 422


@pytest.mark.parametrize("etl_load_run_id", [0, -1])
def test_non_positive_etl_load_run_id_is_rejected_with_422(etl_load_run_id):
    app.dependency_overrides[get_session] = lambda: iter([object()])

    response = client.get(
        f"/api/v1/etl-loads/{etl_load_run_id}/catalog-reconciliation"
    )

    assert response.status_code == 422


def test_endpoint_is_read_only_and_uses_get(monkeypatch):
    _override_service(monkeypatch, _report())

    assert client.post(ENDPOINT).status_code == 405
    assert client.delete(ENDPOINT).status_code == 405
