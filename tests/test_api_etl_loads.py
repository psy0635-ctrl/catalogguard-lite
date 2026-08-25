from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import etl_loads as etl_loads_route
from conftest import (
    FakeSessionWithoutRuntimeOverrides,
    clear_current_user_override,
    override_current_user,
)
from db.session import get_session
import etl.profile_loader as profile_loader


client = TestClient(app)
ENDPOINT = "/api/v1/etl-loads"
QUALITY_SUMMARY_ENDPOINT = f"{ENDPOINT}/quality-summary"
QUALITY_TREND_ENDPOINT = f"{ENDPOINT}/quality-trend"
QUALITY_OBSERVABILITY_ENDPOINT = f"{ENDPOINT}/quality-observability"
QUALITY_OBSERVABILITY_PROFILES_ENDPOINT = (
    f"{QUALITY_OBSERVABILITY_ENDPOINT}/profiles"
)
ETL_PROFILES_ENDPOINT = "/api/v1/etl-profiles"


@pytest.fixture(autouse=True)
def authenticated_operator():
    override_current_user(role="operator")
    yield
    clear_current_user_override()


def _product(**overrides):
    values = {
        "staging_product_id": 101,
        "product_group_id": "GROUP-001",
        "product_id": "SKU-001",
        "product_name": "기본 티셔츠",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 10,
        "price": 19900,
        "sale_price": 15900,
        "image_path": "image.jpg",
        "description": "상품 설명",
        "seller": "판매자",
        "created_at": datetime(2026, 7, 25, 12, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _load(**overrides):
    values = {
        "etl_load_run_id": 12,
        "source_filename": "vendor_products.csv",
        "profile_name": "sample_fashion_vendor_v2",
        "profile_version": "1",
        "loaded_rows": 25,
        "total_rows": 30,
        "rejected_rows": 5,
        "created_at": datetime(2026, 7, 25, 12, tzinfo=timezone.utc),
        "actor_username": "operator_user",
        "initial_source_type": "upload",
        "initial_source_ref": "vendor_products.csv",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def fake_etl_query_service(monkeypatch):
    # 프로필 route가 runtime activation override를 조회하므로, DB 없이 도는 이 fixture도
    # 그 질의에 "override 없음"으로 답할 수 있어야 합니다.
    fake_session = FakeSessionWithoutRuntimeOverrides()
    calls = []
    state = SimpleNamespace(
        load_exists=True,
        observability_empty=False,
        observability_profiles=["sample_fashion_vendor", "sample_marketplace_vendor"],
    )
    load = _load()
    detail = SimpleNamespace(
        etl_load_run_id=12,
        source_filename="vendor_products.csv",
        profile_name="sample_fashion_vendor_v2",
        profile_version="1",
        input_file_sha256="a" * 64,
        output_file_sha256="b" * 64,
        profile_definition_sha256="c" * 64,
        loaded_rows=25,
        total_rows=30,
        rejected_rows=5,
        error_counts={"INVALID_PRICE": 5},
        reject_details_stored=True,
        created_at=load.created_at,
        actor_username="operator_user",
        initial_source_type="upload",
        initial_source_ref="vendor_products.csv",
        products=SimpleNamespace(
            items=[_product(description=None, seller=None, sale_price=None)],
            total=25,
            limit=50,
            offset=0,
        ),
    )

    rejections = SimpleNamespace(
        available=True,
        items=[
            SimpleNamespace(
                rejected_row_id=301,
                source_row_number=4,
                errors=[
                    SimpleNamespace(
                        code="INVALID_PRICE",
                        field="price",
                        message="bad price",
                    )
                ],
                masked_source_data={"description": "010-****-5678"},
                created_at=load.created_at,
            )
        ],
        total=1,
        limit=20,
        offset=0,
    )
    quality_summary = SimpleNamespace(
        batch_count=3,
        quality_available_batch_count=2,
        quality_unavailable_batch_count=1,
        total_rows=300,
        loaded_rows=280,
        rejected_rows=20,
        rejection_rate=6.67,
    )
    quality_trend = SimpleNamespace(
        items=[
            SimpleNamespace(
                etl_load_run_id=12,
                created_at=load.created_at,
                total_rows=30,
                loaded_rows=25,
                rejected_rows=5,
                rejection_rate=16.67,
            )
        ]
    )

    quality_observability = SimpleNamespace(
        profile_name="sample_fashion_vendor",
        limit=10,
        batch_count=2,
        latest_batch=SimpleNamespace(
            etl_load_run_id=12,
            created_at=load.created_at,
            total_rows=100,
            loaded_rows=91,
            rejected_rows=9,
            rejection_rate=9.0,
        ),
        previous_batch=SimpleNamespace(
            etl_load_run_id=11,
            created_at=load.created_at,
            total_rows=100,
            loaded_rows=96,
            rejected_rows=4,
            rejection_rate=4.0,
        ),
        rejection_rate_delta=5.0,
        direction="worsened",
        error_codes=[
            SimpleNamespace(
                error_code="INVALID_PRICE",
                total_count=8,
                affected_batch_count=2,
            )
        ],
        recent_batches=[
            SimpleNamespace(
                etl_load_run_id=11,
                created_at=load.created_at,
                total_rows=100,
                loaded_rows=96,
                rejected_rows=4,
                rejection_rate=4.0,
            ),
            SimpleNamespace(
                etl_load_run_id=12,
                created_at=load.created_at,
                total_rows=100,
                loaded_rows=91,
                rejected_rows=9,
                rejection_rate=9.0,
            ),
        ],
    )
    empty_observability = SimpleNamespace(
        profile_name="sample_fashion_vendor",
        limit=10,
        batch_count=0,
        latest_batch=None,
        previous_batch=None,
        rejection_rate_delta=None,
        direction="no_baseline",
        error_codes=[],
        recent_batches=[],
    )

    def override_session():
        yield fake_session

    def fake_list_etl_loads(session, *, limit, offset, filename=None, profile_name=None):
        calls.append(
            {
                "operation": "list",
                "session": session,
                "limit": limit,
                "offset": offset,
                "filename": filename,
                "profile_name": profile_name,
            }
        )
        if not state.load_exists:
            return SimpleNamespace(items=[], total=0, limit=limit, offset=offset)
        return SimpleNamespace(items=[load], total=1, limit=limit, offset=offset)

    def fake_get_etl_load_detail(
        session,
        *,
        etl_load_run_id,
        product_limit,
        product_offset,
    ):
        calls.append(
            {
                "operation": "detail",
                "session": session,
                "etl_load_run_id": etl_load_run_id,
                "product_limit": product_limit,
                "product_offset": product_offset,
            }
        )
        if not state.load_exists:
            return None
        detail.products.limit = product_limit
        detail.products.offset = product_offset
        return detail

    def fake_list_etl_rejections(
        session,
        *,
        etl_load_run_id,
        limit,
        offset,
    ):
        calls.append(
            {
                "operation": "rejections",
                "session": session,
                "etl_load_run_id": etl_load_run_id,
                "limit": limit,
                "offset": offset,
            }
        )
        if not state.load_exists:
            return None
        rejections.limit = limit
        rejections.offset = offset
        return rejections

    def fake_get_etl_load_quality_summary(session, *, profile_name=None):
        calls.append(
            {
                "operation": "quality-summary",
                "session": session,
                "profile_name": profile_name,
            }
        )
        return quality_summary

    def fake_get_etl_load_quality_trend(session, *, profile_name=None, limit=10):
        calls.append(
            {
                "operation": "quality-trend",
                "session": session,
                "profile_name": profile_name,
                "limit": limit,
            }
        )
        return quality_trend

    def fake_list_etl_quality_observability_profiles(session):
        calls.append({"operation": "quality-observability-profiles", "session": session})
        return SimpleNamespace(
            items=[
                SimpleNamespace(profile_name=profile_name)
                for profile_name in state.observability_profiles
            ]
        )

    def fake_get_etl_quality_observability(session, *, profile_name, limit=10):
        calls.append(
            {
                "operation": "quality-observability",
                "session": session,
                "profile_name": profile_name,
                "limit": limit,
            }
        )
        if state.observability_empty:
            return empty_observability
        return quality_observability

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(etl_loads_route, "list_etl_loads", fake_list_etl_loads)
    monkeypatch.setattr(etl_loads_route, "get_etl_load_detail", fake_get_etl_load_detail)
    monkeypatch.setattr(etl_loads_route, "list_etl_rejections", fake_list_etl_rejections)
    monkeypatch.setattr(
        etl_loads_route,
        "get_etl_load_quality_summary",
        fake_get_etl_load_quality_summary,
        raising=False,
    )
    monkeypatch.setattr(
        etl_loads_route,
        "get_etl_load_quality_trend",
        fake_get_etl_load_quality_trend,
        raising=False,
    )
    monkeypatch.setattr(
        etl_loads_route,
        "get_etl_quality_observability",
        fake_get_etl_quality_observability,
        raising=False,
    )
    monkeypatch.setattr(
        etl_loads_route,
        "list_etl_quality_observability_profiles",
        fake_list_etl_quality_observability_profiles,
        raising=False,
    )
    yield SimpleNamespace(calls=calls, state=state)
    app.dependency_overrides.clear()


def test_list_etl_loads_returns_default_page_and_excludes_hashes(
    fake_etl_query_service,
):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "etl_load_run_id": 12,
                "source_filename": "vendor_products.csv",
                "profile_name": "sample_fashion_vendor_v2",
                "profile_version": "1",
                "loaded_rows": 25,
                "total_rows": 30,
                "rejected_rows": 5,
                "created_at": "2026-07-25T12:00:00Z",
                "actor_username": "operator_user",
                # 목록에서도 배치의 최초 유입 경로를 확인할 수 있어야 합니다.
                "initial_source_type": "upload",
                "initial_source_ref": "vendor_products.csv",
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }
    assert "input_file_sha256" not in response.json()["items"][0]
    assert fake_etl_query_service.calls == [
        {
            "operation": "list",
            "session": fake_etl_query_service.calls[0]["session"],
            "limit": 20,
            "offset": 0,
            "filename": None,
            "profile_name": None,
        }
    ]


def test_list_etl_loads_passes_pagination_and_trimmed_filters(
    fake_etl_query_service,
):
    response = client.get(
        ENDPOINT,
        params={
            "limit": 10,
            "offset": 20,
            "filename": "  vendor  ",
            "profile_name": "  fashion  ",
        },
    )

    assert response.status_code == 200
    assert fake_etl_query_service.calls[-1] == {
        "operation": "list",
        "session": fake_etl_query_service.calls[-1]["session"],
        "limit": 10,
        "offset": 20,
        "filename": "vendor",
        "profile_name": "fashion",
    }


def test_blank_filters_are_omitted(fake_etl_query_service):
    response = client.get(ENDPOINT, params={"filename": "   ", "profile_name": "  "})

    assert response.status_code == 200
    assert fake_etl_query_service.calls[-1]["filename"] is None
    assert fake_etl_query_service.calls[-1]["profile_name"] is None


def test_empty_etl_load_list_is_returned(fake_etl_query_service):
    fake_etl_query_service.state.load_exists = False

    response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_quality_summary_returns_aggregate_values_and_static_route_wins(
    fake_etl_query_service,
):
    response = client.get(QUALITY_SUMMARY_ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "batch_count": 3,
        "quality_available_batch_count": 2,
        "quality_unavailable_batch_count": 1,
        "total_rows": 300,
        "loaded_rows": 280,
        "rejected_rows": 20,
        "rejection_rate": 6.67,
    }
    assert fake_etl_query_service.calls[-1] == {
        "operation": "quality-summary",
        "session": fake_etl_query_service.calls[-1]["session"],
        "profile_name": None,
    }


def test_quality_summary_passes_trimmed_profile_filter(fake_etl_query_service):
    response = client.get(
        QUALITY_SUMMARY_ENDPOINT,
        params={"profile_name": "  fashion  "},
    )

    assert response.status_code == 200
    assert fake_etl_query_service.calls[-1]["profile_name"] == "fashion"


def test_quality_trend_returns_items_and_static_route_wins(fake_etl_query_service):
    response = client.get(QUALITY_TREND_ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "etl_load_run_id": 12,
                "created_at": "2026-07-25T12:00:00Z",
                "total_rows": 30,
                "loaded_rows": 25,
                "rejected_rows": 5,
                "rejection_rate": 16.67,
            }
        ]
    }
    assert fake_etl_query_service.calls[-1] == {
        "operation": "quality-trend",
        "session": fake_etl_query_service.calls[-1]["session"],
        "profile_name": None,
        "limit": 10,
    }


def test_quality_trend_passes_trimmed_profile_filter_and_limit(
    fake_etl_query_service,
):
    response = client.get(
        QUALITY_TREND_ENDPOINT,
        params={"profile_name": "  fashion  ", "limit": 3},
    )

    assert response.status_code == 200
    assert fake_etl_query_service.calls[-1]["profile_name"] == "fashion"
    assert fake_etl_query_service.calls[-1]["limit"] == 3


def test_quality_observability_returns_comparison_and_static_route_wins(
    fake_etl_query_service,
):
    response = client.get(
        QUALITY_OBSERVABILITY_ENDPOINT,
        params={"profile_name": "sample_fashion_vendor"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "profile_name": "sample_fashion_vendor",
        "limit": 10,
        "batch_count": 2,
        "latest_batch": {
            "etl_load_run_id": 12,
            "created_at": "2026-07-25T12:00:00Z",
            "total_rows": 100,
            "loaded_rows": 91,
            "rejected_rows": 9,
            "rejection_rate": 9.0,
        },
        "previous_batch": {
            "etl_load_run_id": 11,
            "created_at": "2026-07-25T12:00:00Z",
            "total_rows": 100,
            "loaded_rows": 96,
            "rejected_rows": 4,
            "rejection_rate": 4.0,
        },
        "rejection_rate_delta": 5.0,
        "direction": "worsened",
        "error_codes": [
            {
                "error_code": "INVALID_PRICE",
                "total_count": 8,
                "affected_batch_count": 2,
            }
        ],
        "recent_batches": [
            {
                "etl_load_run_id": 11,
                "created_at": "2026-07-25T12:00:00Z",
                "total_rows": 100,
                "loaded_rows": 96,
                "rejected_rows": 4,
                "rejection_rate": 4.0,
            },
            {
                "etl_load_run_id": 12,
                "created_at": "2026-07-25T12:00:00Z",
                "total_rows": 100,
                "loaded_rows": 91,
                "rejected_rows": 9,
                "rejection_rate": 9.0,
            },
        ],
    }
    assert fake_etl_query_service.calls[-1] == {
        "operation": "quality-observability",
        "session": fake_etl_query_service.calls[-1]["session"],
        "profile_name": "sample_fashion_vendor",
        "limit": 10,
    }


def test_quality_observability_returns_nulls_when_no_batch_matches(
    fake_etl_query_service,
):
    fake_etl_query_service.state.observability_empty = True

    response = client.get(
        QUALITY_OBSERVABILITY_ENDPOINT,
        params={"profile_name": "sample_fashion_vendor"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "profile_name": "sample_fashion_vendor",
        "limit": 10,
        "batch_count": 0,
        "latest_batch": None,
        "previous_batch": None,
        "rejection_rate_delta": None,
        "direction": "no_baseline",
        "error_codes": [],
        "recent_batches": [],
    }


def test_quality_observability_passes_trimmed_profile_and_limit(
    fake_etl_query_service,
):
    response = client.get(
        QUALITY_OBSERVABILITY_ENDPOINT,
        params={"profile_name": "  sample_fashion_vendor  ", "limit": 3},
    )

    assert response.status_code == 200
    assert fake_etl_query_service.calls[-1]["profile_name"] == "sample_fashion_vendor"
    assert fake_etl_query_service.calls[-1]["limit"] == 3


@pytest.mark.parametrize("limit", [1, 50])
def test_quality_observability_accepts_limit_boundaries(fake_etl_query_service, limit):
    response = client.get(
        QUALITY_OBSERVABILITY_ENDPOINT,
        params={"profile_name": "sample_fashion_vendor", "limit": limit},
    )

    assert response.status_code == 200
    assert fake_etl_query_service.calls[-1]["limit"] == limit


@pytest.mark.parametrize("limit", [0, 51, "abc"])
def test_quality_observability_rejects_invalid_limit(fake_etl_query_service, limit):
    response = client.get(
        QUALITY_OBSERVABILITY_ENDPOINT,
        params={"profile_name": "sample_fashion_vendor", "limit": limit},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("params", [{}, {"profile_name": ""}, {"profile_name": "   "}])
def test_quality_observability_requires_a_non_blank_profile_name(
    fake_etl_query_service,
    params,
):
    # profile_name이 없으면 서로 다른 공급사를 비교하게 되므로 조회 자체를 막습니다.
    response = client.get(QUALITY_OBSERVABILITY_ENDPOINT, params=params)

    assert response.status_code == 422
    assert not any(
        call["operation"] == "quality-observability"
        for call in fake_etl_query_service.calls
    )


def test_quality_observability_allows_viewer_and_blocks_anonymous(
    fake_etl_query_service,
):
    override_current_user(role="viewer")
    viewer_response = client.get(
        QUALITY_OBSERVABILITY_ENDPOINT,
        params={"profile_name": "sample_fashion_vendor"},
    )
    override_current_user(role="operator")
    operator_response = client.get(
        QUALITY_OBSERVABILITY_ENDPOINT,
        params={"profile_name": "sample_fashion_vendor"},
    )
    clear_current_user_override()
    anonymous_response = client.get(
        QUALITY_OBSERVABILITY_ENDPOINT,
        params={"profile_name": "sample_fashion_vendor"},
    )

    assert viewer_response.status_code == 200
    assert operator_response.status_code == 200
    assert anonymous_response.status_code == 401


def test_quality_observability_profiles_returns_sorted_names(fake_etl_query_service):
    response = client.get(QUALITY_OBSERVABILITY_PROFILES_ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"profile_name": "sample_fashion_vendor"},
            {"profile_name": "sample_marketplace_vendor"},
        ]
    }
    assert fake_etl_query_service.calls[-1]["operation"] == (
        "quality-observability-profiles"
    )


def test_quality_observability_profiles_returns_empty_items(fake_etl_query_service):
    fake_etl_query_service.state.observability_profiles = []

    response = client.get(QUALITY_OBSERVABILITY_PROFILES_ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_quality_observability_profiles_allows_viewer_and_blocks_anonymous(
    fake_etl_query_service,
):
    override_current_user(role="viewer")
    viewer_response = client.get(QUALITY_OBSERVABILITY_PROFILES_ENDPOINT)
    override_current_user(role="operator")
    operator_response = client.get(QUALITY_OBSERVABILITY_PROFILES_ENDPOINT)
    clear_current_user_override()
    anonymous_response = client.get(QUALITY_OBSERVABILITY_PROFILES_ENDPOINT)

    assert viewer_response.status_code == 200
    assert operator_response.status_code == 200
    assert anonymous_response.status_code == 401


def test_quality_observability_profiles_route_wins_over_load_detail_route(
    fake_etl_query_service,
):
    # 정적 경로가 /api/v1/etl-loads/{etl_load_run_id} 보다 먼저 매칭되어야 합니다.
    response = client.get(QUALITY_OBSERVABILITY_PROFILES_ENDPOINT)

    assert response.status_code == 200
    assert not any(
        call["operation"] == "detail" for call in fake_etl_query_service.calls
    )


def test_etl_profile_detail_returns_safe_allowlisted_metadata_and_list_still_works():
    response = client.get(f"{ETL_PROFILES_ENDPOINT}/sample_fashion_vendor_v1")

    assert response.status_code == 200
    assert response.json() == {
        "id": "sample_fashion_vendor_v1",
        "display_name": "패션 공급사 샘플",
        "profile_name": "sample_fashion_vendor",
        "profile_version": "2",
        "source_columns": {
            "vendor_sku": ["product_group_id", "product_id"],
            "item_name": ["product_name"],
            "main_category": ["category"],
            "brand_name": ["seller"],
            "list_price": ["price"],
            "discount_price": ["sale_price"],
            "colour": ["color"],
            "size_name": ["size"],
            "quantity": ["stock"],
            "description_text": ["description"],
            "image_link": ["image_path"],
        },
        "required_source_columns": [
            "vendor_sku",
            "item_name",
            "main_category",
            "list_price",
            "colour",
            "size_name",
            "image_link",
        ],
        "defaults": {"stock": "0"},
    }
    assert client.get(ETL_PROFILES_ENDPOINT).json()["items"] == [
        {"id": "sample_fashion_vendor_v1", "display_name": "패션 공급사 샘플"},
        {
            "id": "sample_marketplace_vendor_v1",
            "display_name": "마켓플레이스 공급사 샘플",
        },
    ]
    assert not {"filename", "path", "profile_path"} & set(response.json())


def _deactivated_registry_entry(profile_id: str) -> dict:
    entry = dict(profile_loader._ETL_PROFILE_REGISTRY[profile_id])
    entry["active_version"] = None
    return entry


def test_inactive_profile_detail_returns_409_instead_of_the_last_active_version(
    monkeypatch,
):
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        "sample_fashion_vendor_v1",
        _deactivated_registry_entry("sample_fashion_vendor_v1"),
    )

    response = client.get(f"{ETL_PROFILES_ENDPOINT}/sample_fashion_vendor_v1")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "inactive_profile",
        "message": "ETL profile is inactive.",
    }
    # 존재하지 않는다(404)고 말하지도, archive 내부를 노출하지도 않습니다.
    assert "config" not in response.text.lower() and "v2.json" not in response.text


def test_inactive_profile_is_dropped_from_the_selectable_profile_list(monkeypatch):
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        "sample_fashion_vendor_v1",
        _deactivated_registry_entry("sample_fashion_vendor_v1"),
    )

    response = client.get(ETL_PROFILES_ENDPOINT)

    assert response.status_code == 200
    # 활성 프로필은 계속 목록과 상세 조회 모두 정상입니다.
    assert response.json()["items"] == [
        {
            "id": "sample_marketplace_vendor_v1",
            "display_name": "마켓플레이스 공급사 샘플",
        }
    ]
    active_detail = client.get(
        f"{ETL_PROFILES_ENDPOINT}/sample_marketplace_vendor_v1"
    )
    assert active_detail.status_code == 200
    assert active_detail.json()["profile_version"] == "2"


@pytest.mark.parametrize(
    ("profile_id", "detail"),
    [("not-exists", "ETL profile not found."), ("..%2Fsecret", "Not Found")],
)
def test_etl_profile_detail_rejects_unknown_or_traversal_ids_safely(profile_id, detail):
    response = client.get(f"{ETL_PROFILES_ENDPOINT}/{profile_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == detail
    assert "config" not in response.text.lower()


@pytest.mark.parametrize("limit", [0, 51])
def test_quality_trend_rejects_invalid_limit(limit):
    assert client.get(QUALITY_TREND_ENDPOINT, params={"limit": limit}).status_code == 422


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}],
)
def test_list_etl_loads_rejects_invalid_pagination(params):
    assert client.get(ENDPOINT, params=params).status_code == 422


def test_detail_returns_nullable_fields_and_hashes(fake_etl_query_service):
    response = client.get(f"{ENDPOINT}/12")

    assert response.status_code == 200
    data = response.json()
    assert data["input_file_sha256"] == "a" * 64
    assert data["output_file_sha256"] == "b" * 64
    assert data["profile_definition_sha256"] == "c" * 64
    assert data["total_rows"] == 30
    assert data["rejected_rows"] == 5
    assert data["error_counts"] == {"INVALID_PRICE": 5}
    assert data["reject_details_stored"] is True
    assert data["products"]["items"][0]["sale_price"] is None
    assert data["products"]["items"][0]["description"] is None
    assert data["products"]["items"][0]["seller"] is None
    assert fake_etl_query_service.calls[-1]["etl_load_run_id"] == 12


def test_detail_passes_product_pagination(fake_etl_query_service):
    response = client.get(
        f"{ENDPOINT}/12",
        params={"product_limit": 10, "product_offset": 30},
    )

    assert response.status_code == 200
    assert fake_etl_query_service.calls[-1]["product_limit"] == 10
    assert fake_etl_query_service.calls[-1]["product_offset"] == 30
    assert response.json()["products"]["limit"] == 10
    assert response.json()["products"]["offset"] == 30


def test_missing_etl_load_returns_404(fake_etl_query_service):
    fake_etl_query_service.state.load_exists = False

    response = client.get(f"{ENDPOINT}/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "ETL 적재 배치를 찾을 수 없습니다."


@pytest.mark.parametrize(
    "params",
    [
        {"product_limit": 0},
        {"product_limit": 101},
        {"product_offset": -1},
    ],
)
def test_detail_rejects_invalid_product_pagination(params):
    assert client.get(f"{ENDPOINT}/12", params=params).status_code == 422


def test_non_positive_path_id_is_rejected(fake_etl_query_service):
    assert client.get(f"{ENDPOINT}/0").status_code == 422
    assert client.get(f"{ENDPOINT}/-1").status_code == 422


def test_rejections_endpoint_returns_structured_masked_rows(fake_etl_query_service):
    response = client.get(f"{ENDPOINT}/12/rejections")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "items": [
            {
                "rejected_row_id": 301,
                "source_row_number": 4,
                "errors": [
                    {
                        "code": "INVALID_PRICE",
                        "field": "price",
                        "message": "bad price",
                    }
                ],
                "masked_source_data": {"description": "010-****-5678"},
                "created_at": "2026-07-25T12:00:00Z",
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }
    assert fake_etl_query_service.calls[-1]["operation"] == "rejections"


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}],
)
def test_rejections_endpoint_rejects_invalid_pagination(params):
    assert client.get(f"{ENDPOINT}/12/rejections", params=params).status_code == 422


def test_rejections_endpoint_returns_404_for_missing_batch(fake_etl_query_service):
    fake_etl_query_service.state.load_exists = False

    response = client.get(f"{ENDPOINT}/999999/rejections")

    assert response.status_code == 404


def test_etl_load_routes_are_registered():
    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif hasattr(route, "original_router"):
            paths.update(child.path for child in route.original_router.routes)
    assert ENDPOINT in paths
    assert f"{ENDPOINT}/{{etl_load_run_id}}" in paths
