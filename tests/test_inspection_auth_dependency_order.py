import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.session import get_session


client = TestClient(app, raise_server_exceptions=False)
VALID_MINIMAL_CSV = (
    b"product_group_id,product_id,product_name,category,color,size,stock,price,image_path\n"
    b"G001,P001,Test Product,TOP,BLACK,M,10,19900,image.jpg\n"
)


@pytest.fixture()
def reject_database_dependency():
    calls = 0

    def fail_if_database_dependency_runs():
        nonlocal calls
        calls += 1
        raise AssertionError("database dependency must not run before authentication")

    app.dependency_overrides[get_session] = fail_if_database_dependency_runs
    try:
        yield lambda: calls
    finally:
        app.dependency_overrides.pop(get_session, None)


def assert_authentication_required(response, database_call_count):
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert database_call_count() == 0


def test_anonymous_inspection_list_authenticates_before_database(
    reject_database_dependency,
):
    response = client.get("/api/v1/inspections")

    assert_authentication_required(response, reject_database_dependency)


def test_anonymous_inspection_detail_authenticates_before_database(
    reject_database_dependency,
):
    response = client.get("/api/v1/inspections/1")

    assert_authentication_required(response, reject_database_dependency)


def test_anonymous_inspection_create_authenticates_before_database(
    reject_database_dependency,
):
    response = client.post(
        "/api/v1/inspections",
        files={"file": ("products.csv", VALID_MINIMAL_CSV, "text/csv")},
    )

    assert_authentication_required(response, reject_database_dependency)
