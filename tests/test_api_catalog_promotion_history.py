from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import etl_loads as etl_loads_route
from conftest import clear_current_user_override, override_current_user
from db.session import get_session


client = TestClient(app)
LIST_ENDPOINT = "/api/v1/catalog-promotions"
DETAIL_ENDPOINT = f"{LIST_ENDPOINT}/21"
AUDIT_ENDPOINT = f"{DETAIL_ENDPOINT}/audits"


@pytest.fixture(autouse=True)
def authenticated_operator():
    override_current_user(role="operator")
    yield
    clear_current_user_override()


def _run(**overrides):
    started_at = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    values = {
        "promotion_run_id": 21,
        "etl_load_run_id": 12,
        "source_filename": "vendor.csv",
        "profile_name": "sample_vendor",
        "status": "failed",
        "inserted_count": 2,
        "updated_count": 1,
        "unchanged_count": 3,
        "blocked_count": 0,
        "error_count": 1,
        "warning_count": 0,
        "failure_code": "promotion_apply_failed",
        "safe_failure_message": "Promotion could not be completed.",
        "started_at": started_at,
        "completed_at": started_at + timedelta(seconds=1),
        "created_at": started_at,
        "preview_hash": "a" * 64,
        "preview_schema_version": "1",
        "inspection_version": "1",
        "actor_username": "operator_user",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _audit(**overrides):
    values = {
        "audit_id": 31,
        "promotion_run_id": 21,
        "catalog_product_id": 41,
        "action": "update",
        "changed_fields": {"stock": {"before": 1, "after": 2}},
        "before_data": {"external_product_id": "SKU-001", "stock": 1},
        "after_data": {"external_product_id": "SKU-001", "stock": 2},
        "created_at": datetime(2026, 7, 30, 12, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def fake_promotion_history_query_service(monkeypatch):
    fake_session = object()
    calls = []
    state = SimpleNamespace(exists=True, fail=False)
    run = _run()

    def override_session():
        yield fake_session

    def fake_list(
        session,
        *,
        limit,
        offset,
        status=None,
        etl_load_run_id=None,
        filename=None,
        profile_name=None,
    ):
        calls.append(
            {
                "operation": "list",
                "session": session,
                "limit": limit,
                "offset": offset,
                "status": status,
                "etl_load_run_id": etl_load_run_id,
                "filename": filename,
                "profile_name": profile_name,
            }
        )
        if state.fail:
            raise RuntimeError("postgresql://secret@db/internal query")
        items = [run] if state.exists else []
        return SimpleNamespace(items=items, total=len(items), limit=limit, offset=offset)

    def fake_detail(session, *, promotion_run_id):
        calls.append(
            {
                "operation": "detail",
                "session": session,
                "promotion_run_id": promotion_run_id,
            }
        )
        return run if state.exists else None

    def fake_audits(session, *, promotion_run_id, limit, offset):
        calls.append(
            {
                "operation": "audits",
                "session": session,
                "promotion_run_id": promotion_run_id,
                "limit": limit,
                "offset": offset,
            }
        )
        if not state.exists:
            return None
        return SimpleNamespace(items=[_audit()], total=1, limit=limit, offset=offset)

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        etl_loads_route,
        "list_catalog_promotions",
        fake_list,
        raising=False,
    )
    monkeypatch.setattr(
        etl_loads_route,
        "get_catalog_promotion_detail",
        fake_detail,
        raising=False,
    )
    monkeypatch.setattr(
        etl_loads_route,
        "list_catalog_promotion_audits",
        fake_audits,
        raising=False,
    )
    yield SimpleNamespace(calls=calls, state=state)
    app.dependency_overrides.clear()


def test_list_catalog_promotions_returns_safe_paged_contract(
    fake_promotion_history_query_service,
):
    response = client.get(
        LIST_ENDPOINT,
        params={
            "limit": 10,
            "offset": 20,
            "status": "failed",
            "etl_load_run_id": 12,
            "filename": "  vendor  ",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "promotion_run_id": 21,
                "etl_load_run_id": 12,
                "source_filename": "vendor.csv",
                "profile_name": "sample_vendor",
                "status": "failed",
                "inserted_count": 2,
                "updated_count": 1,
                "unchanged_count": 3,
                "blocked_count": 0,
                "error_count": 1,
                "warning_count": 0,
                "failure_code": "promotion_apply_failed",
                "safe_failure_message": "Promotion could not be completed.",
                "started_at": "2026-07-30T12:00:00Z",
                "completed_at": "2026-07-30T12:00:01Z",
                "created_at": "2026-07-30T12:00:00Z",
                "actor_username": "operator_user",
            }
        ],
        "total": 1,
        "limit": 10,
        "offset": 20,
    }
    assert fake_promotion_history_query_service.calls[-1]["filename"] == "vendor"
    assert fake_promotion_history_query_service.calls[-1]["status"] == "failed"
    assert fake_promotion_history_query_service.calls[-1]["etl_load_run_id"] == 12


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"status": "unknown"},
        {"etl_load_run_id": 0},
    ],
)
def test_list_catalog_promotions_rejects_invalid_filters(params):
    assert client.get(LIST_ENDPOINT, params=params).status_code == 422


def test_get_catalog_promotion_detail_returns_existing_run(
    fake_promotion_history_query_service,
):
    response = client.get(DETAIL_ENDPOINT)

    assert response.status_code == 200
    data = response.json()
    assert data["promotion_run_id"] == 21
    assert data["source_filename"] == "vendor.csv"
    assert data["failure_code"] == "promotion_apply_failed"
    assert data["safe_failure_message"] == "Promotion could not be completed."
    assert data["preview_hash"] == "a" * 64


def test_get_catalog_promotion_detail_returns_safe_404(
    fake_promotion_history_query_service,
):
    fake_promotion_history_query_service.state.exists = False

    response = client.get(DETAIL_ENDPOINT)

    assert response.status_code == 404
    assert response.json() == {"detail": "Promotion run not found."}


def test_list_catalog_promotion_audits_returns_only_requested_run_page(
    fake_promotion_history_query_service,
):
    response = client.get(AUDIT_ENDPOINT, params={"limit": 10, "offset": 20})

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "audit_id": 31,
                "promotion_run_id": 21,
                "catalog_product_id": 41,
                "action": "update",
                "changed_fields": {"stock": {"before": 1, "after": 2}},
                "before_data": {"external_product_id": "SKU-001", "stock": 1},
                "after_data": {"external_product_id": "SKU-001", "stock": 2},
                "created_at": "2026-07-30T12:00:00Z",
            }
        ],
        "total": 1,
        "limit": 10,
        "offset": 20,
    }
    assert fake_promotion_history_query_service.calls[-1] == {
        "operation": "audits",
        "session": fake_promotion_history_query_service.calls[-1]["session"],
        "promotion_run_id": 21,
        "limit": 10,
        "offset": 20,
    }


def test_list_catalog_promotion_audits_returns_safe_404(
    fake_promotion_history_query_service,
):
    fake_promotion_history_query_service.state.exists = False

    response = client.get(AUDIT_ENDPOINT)

    assert response.status_code == 404
    assert response.json() == {"detail": "Promotion run not found."}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_catalog_promotion_audits_rejects_invalid_pagination(params):
    assert client.get(AUDIT_ENDPOINT, params=params).status_code == 422


def test_catalog_promotion_history_hides_internal_database_errors(
    fake_promotion_history_query_service,
):
    fake_promotion_history_query_service.state.fail = True
    safe_client = TestClient(app, raise_server_exceptions=False)

    response = safe_client.get(LIST_ENDPOINT)

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert "postgresql" not in response.text.lower()
    assert "secret" not in response.text.lower()
