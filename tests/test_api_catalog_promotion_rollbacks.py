from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import etl_loads as etl_loads_route
from conftest import clear_current_user_override, override_current_user
from db.session import get_session


client = TestClient(app)
LIST_ENDPOINT = "/api/v1/catalog-promotion-rollbacks"
DETAIL_ENDPOINT = f"{LIST_ENDPOINT}/10"


def _rollback(**overrides):
    started_at = datetime(2026, 8, 11, tzinfo=timezone.utc)
    values = {
        "rollback_run_id": 10,
        "target_promotion_run_id": 7,
        "status": "succeeded",
        "restored_count": 2,
        "deleted_count": 1,
        "conflict_count": 0,
        "failure_code": None,
        "safe_failure_message": None,
        "started_at": started_at,
        "completed_at": started_at + timedelta(seconds=1),
        "created_at": started_at,
        "actor_username": "operator1",
        "preview_hash": "a" * 64,
        "preview_schema_version": "1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def fake_rollback_history_query_service(monkeypatch):
    fake_session = object()
    calls = []
    state = SimpleNamespace(exists=True)
    rollback = _rollback()

    def override_session():
        yield fake_session

    def fake_list(
        session,
        *,
        limit,
        offset,
        status=None,
        target_promotion_run_id=None,
    ):
        calls.append(
            {
                "operation": "list",
                "session": session,
                "limit": limit,
                "offset": offset,
                "status": status,
                "target_promotion_run_id": target_promotion_run_id,
            }
        )
        items = [rollback] if state.exists else []
        return SimpleNamespace(
            items=items,
            total=len(items),
            limit=limit,
            offset=offset,
        )

    def fake_detail(session, *, rollback_run_id):
        calls.append(
            {
                "operation": "detail",
                "session": session,
                "rollback_run_id": rollback_run_id,
            }
        )
        return rollback if state.exists else None

    override_current_user(role="operator")
    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        etl_loads_route,
        "list_catalog_promotion_rollbacks",
        fake_list,
        raising=False,
    )
    monkeypatch.setattr(
        etl_loads_route,
        "get_catalog_promotion_rollback_detail",
        fake_detail,
        raising=False,
    )
    try:
        yield SimpleNamespace(calls=calls, state=state)
    finally:
        app.dependency_overrides.pop(get_session, None)
        clear_current_user_override()


def test_list_catalog_promotion_rollbacks_returns_safe_default_page(
    fake_rollback_history_query_service,
):
    response = client.get(LIST_ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "rollback_run_id": 10,
                "target_promotion_run_id": 7,
                "status": "succeeded",
                "restored_count": 2,
                "deleted_count": 1,
                "conflict_count": 0,
                "failure_code": None,
                "safe_failure_message": None,
                "started_at": "2026-08-11T00:00:00Z",
                "completed_at": "2026-08-11T00:00:01Z",
                "created_at": "2026-08-11T00:00:00Z",
                "actor_username": "operator1",
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }
    assert fake_rollback_history_query_service.calls[-1] == {
        "operation": "list",
        "session": fake_rollback_history_query_service.calls[-1]["session"],
        "limit": 20,
        "offset": 0,
        "status": None,
        "target_promotion_run_id": None,
    }


def test_list_catalog_promotion_rollbacks_forwards_pagination_and_filters(
    fake_rollback_history_query_service,
):
    response = client.get(
        LIST_ENDPOINT,
        params={
            "limit": 10,
            "offset": 20,
            "status": "succeeded",
            "target_promotion_run_id": 123,
        },
    )

    assert response.status_code == 200
    assert fake_rollback_history_query_service.calls[-1] == {
        "operation": "list",
        "session": fake_rollback_history_query_service.calls[-1]["session"],
        "limit": 10,
        "offset": 20,
        "status": "succeeded",
        "target_promotion_run_id": 123,
    }


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"status": "unknown"},
        {"target_promotion_run_id": 0},
    ],
)
def test_list_catalog_promotion_rollbacks_rejects_invalid_filters(
    params,
    fake_rollback_history_query_service,
):
    response = client.get(LIST_ENDPOINT, params=params)

    assert response.status_code == 422
    assert fake_rollback_history_query_service.calls == []


def test_get_catalog_promotion_rollback_detail_returns_existing_run(
    fake_rollback_history_query_service,
):
    response = client.get(DETAIL_ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "rollback_run_id": 10,
        "target_promotion_run_id": 7,
        "status": "succeeded",
        "restored_count": 2,
        "deleted_count": 1,
        "conflict_count": 0,
        "failure_code": None,
        "safe_failure_message": None,
        "started_at": "2026-08-11T00:00:00Z",
        "completed_at": "2026-08-11T00:00:01Z",
        "created_at": "2026-08-11T00:00:00Z",
        "actor_username": "operator1",
        "preview_hash": "a" * 64,
        "preview_schema_version": "1",
    }
    assert "actor_user_id" not in response.json()


def test_get_catalog_promotion_rollback_detail_returns_safe_404(
    fake_rollback_history_query_service,
):
    fake_rollback_history_query_service.state.exists = False

    response = client.get(DETAIL_ENDPOINT)

    assert response.status_code == 404
    assert response.json() == {"detail": "Rollback run not found."}


def test_get_catalog_promotion_rollback_detail_rejects_invalid_id(
    fake_rollback_history_query_service,
):
    response = client.get(f"{LIST_ENDPOINT}/0")

    assert response.status_code == 422
    assert fake_rollback_history_query_service.calls == []
