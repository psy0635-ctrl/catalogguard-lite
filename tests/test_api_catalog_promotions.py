from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import etl_loads as etl_loads_route
from db.catalog_promotion_preview_service import (
    ETLLoadRunNotFoundError,
    PromotionPreviewBlockedReason,
)
from db.session import get_session


ENDPOINT = "/api/v1/etl-loads/42/promotions"
VALID_HASH = "a" * 64
client = TestClient(app, raise_server_exceptions=False)


def _result(**changes):
    now = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    values = {
        "promotion_run_id": 15,
        "etl_load_run_id": 42,
        "status": "succeeded",
        "created": True,
        "preview_hash": VALID_HASH,
        "preview_schema_version": 1,
        "inspection_version": "5",
        "inserted_count": 3,
        "updated_count": 2,
        "unchanged_count": 10,
        "blocked_count": 0,
        "error_count": 0,
        "warning_count": 1,
        "failure_code": None,
        "safe_failure_message": None,
        "blocked_reasons": [],
        "started_at": now,
        "completed_at": now,
    }
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.fixture()
def promotion_api(monkeypatch):
    from db.catalog_promotion_service import (
        CatalogPromotionConfirmationRequiredError,
        CatalogPromotionExecutionFailedError,
    )

    session = object()
    state = SimpleNamespace(result=_result(), error=None, calls=[])

    def override_session():
        yield session

    def fake_execute(
        received_session,
        *,
        etl_load_run_id,
        confirmation,
        expected_preview_hash,
    ):
        state.calls.append(
            {
                "session": received_session,
                "etl_load_run_id": etl_load_run_id,
                "confirmation": confirmation,
                "expected_preview_hash": expected_preview_hash,
            }
        )
        if state.error is not None:
            raise state.error
        if not confirmation:
            raise CatalogPromotionConfirmationRequiredError()
        return state.result

    state.confirmation_error = CatalogPromotionConfirmationRequiredError
    state.execution_error = CatalogPromotionExecutionFailedError
    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        etl_loads_route,
        "execute_catalog_promotion",
        fake_execute,
        raising=False,
    )
    yield state
    app.dependency_overrides.clear()


def test_success_returns_complete_contract_and_no_store(promotion_api):
    response = client.post(
        ENDPOINT,
        json={"confirmation": True, "expected_preview_hash": VALID_HASH},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "promotion_run_id": 15,
        "etl_load_run_id": 42,
        "status": "succeeded",
        "created": True,
        "preview_hash": VALID_HASH,
        "preview_schema_version": 1,
        "inspection_version": "5",
        "inserted_count": 3,
        "updated_count": 2,
        "unchanged_count": 10,
        "blocked_count": 0,
        "error_count": 0,
        "warning_count": 1,
        "started_at": "2026-07-29T08:00:00Z",
        "completed_at": "2026-07-29T08:00:00Z",
    }
    assert promotion_api.calls[0]["session"] is not None


def test_existing_success_returns_created_false(promotion_api):
    promotion_api.result = _result(created=False)

    response = client.post(
        ENDPOINT,
        json={"confirmation": True, "expected_preview_hash": VALID_HASH},
    )

    assert response.status_code == 200
    assert response.json()["created"] is False


def test_confirmation_false_returns_safe_400(promotion_api):
    response = client.post(
        ENDPOINT,
        json={"confirmation": False, "expected_preview_hash": VALID_HASH},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "code": "confirmation_required",
            "message": "운영 상품 반영을 위해 명시적인 승인이 필요합니다.",
        }
    }


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"confirmation": True},
        {"expected_preview_hash": VALID_HASH},
        {"confirmation": True, "expected_preview_hash": "a" * 63},
        {"confirmation": True, "expected_preview_hash": "a" * 65},
        {"confirmation": True, "expected_preview_hash": "A" * 64},
        {"confirmation": True, "expected_preview_hash": "g" * 64},
    ],
)
def test_malformed_request_returns_422_without_calling_service(
    promotion_api,
    body,
):
    response = client.post(ENDPOINT, json=body)

    assert response.status_code == 422
    assert promotion_api.calls == []


def test_missing_etl_returns_safe_404(promotion_api):
    promotion_api.error = ETLLoadRunNotFoundError(42)

    response = client.post(
        ENDPOINT,
        json={"confirmation": True, "expected_preview_hash": VALID_HASH},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "etl_load_not_found",
            "message": "ETL 적재 배치를 찾을 수 없습니다.",
        }
    }


def test_blocked_result_returns_safe_409_with_reasons(promotion_api):
    promotion_api.result = _result(
        status="blocked",
        failure_code="promotion_blocked",
        safe_failure_message="현재 데이터는 운영 반영 조건을 충족하지 않습니다.",
        blocked_reasons=[
            PromotionPreviewBlockedReason(
                code="empty_staging_batch",
                message="반영할 정상 staging 상품이 없습니다.",
            )
        ],
    )

    response = client.post(
        ENDPOINT,
        json={"confirmation": True, "expected_preview_hash": VALID_HASH},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "promotion_blocked",
            "message": "현재 데이터는 운영 반영 조건을 충족하지 않습니다.",
            "promotion_run_id": 15,
            "blocked_reasons": [
                {
                    "code": "empty_staging_batch",
                    "message": "반영할 정상 staging 상품이 없습니다.",
                    "supplier_key": None,
                    "external_product_id": None,
                    "staging_product_ids": [],
                }
            ],
        }
    }


def test_stale_result_returns_safe_409_without_current_hash(promotion_api):
    promotion_api.result = _result(
        status="blocked",
        preview_hash="f" * 64,
        failure_code="preview_stale",
        safe_failure_message=(
            "미리보기 이후 데이터가 변경되었습니다. 새로운 preview를 확인해 주세요."
        ),
    )

    response = client.post(
        ENDPOINT,
        json={"confirmation": True, "expected_preview_hash": VALID_HASH},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "preview_stale",
            "message": (
                "미리보기 이후 데이터가 변경되었습니다. 새로운 preview를 확인해 주세요."
            ),
            "promotion_run_id": 15,
        }
    }
    assert "preview_hash" not in response.text


def test_internal_failure_returns_safe_500_with_only_recorded_run_id(
    promotion_api,
):
    promotion_api.error = promotion_api.execution_error(77)

    response = client.post(
        ENDPOINT,
        json={"confirmation": True, "expected_preview_hash": VALID_HASH},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "promotion_failed",
            "message": "운영 상품 반영 중 오류가 발생했습니다.",
            "promotion_run_id": 77,
        }
    }
    assert "SQL" not in response.text
    assert "postgresql://" not in response.text
