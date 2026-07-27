from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import etl_loads as etl_loads_route
from db.session import get_session


client = TestClient(app)
ENDPOINT = "/api/v1/etl-loads"


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
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def fake_etl_query_service(monkeypatch):
    fake_session = object()
    calls = []
    state = SimpleNamespace(load_exists=True)
    load = _load()
    detail = SimpleNamespace(
        etl_load_run_id=12,
        source_filename="vendor_products.csv",
        profile_name="sample_fashion_vendor_v2",
        profile_version="1",
        input_file_sha256="a" * 64,
        output_file_sha256="b" * 64,
        loaded_rows=25,
        total_rows=30,
        rejected_rows=5,
        error_counts={"INVALID_PRICE": 5},
        created_at=load.created_at,
        products=SimpleNamespace(
            items=[_product(description=None, seller=None, sale_price=None)],
            total=25,
            limit=50,
            offset=0,
        ),
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

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(etl_loads_route, "list_etl_loads", fake_list_etl_loads)
    monkeypatch.setattr(etl_loads_route, "get_etl_load_detail", fake_get_etl_load_detail)
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
    assert data["total_rows"] == 30
    assert data["rejected_rows"] == 5
    assert data["error_counts"] == {"INVALID_PRICE": 5}
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


def test_etl_load_routes_are_registered():
    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif hasattr(route, "original_router"):
            paths.update(child.path for child in route.original_router.routes)
    assert ENDPOINT in paths
    assert f"{ENDPOINT}/{{etl_load_run_id}}" in paths
