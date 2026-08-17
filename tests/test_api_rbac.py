# 역할: 실제 PostgreSQL 사용자·JWT를 사용해 인증(401)과 권한(403) 경계를 endpoint 단위로 검증합니다.
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api import dependencies as auth_dependencies
from api.main import app
from config.database import get_optional_database_url
from config.settings import CATALOGGUARD_JWT_ALGORITHM, get_jwt_secret
from core.security import create_access_token
from db.auth_service import create_user
from db.models import User
from db.session import create_database_engine, create_session_factory, get_session


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


@pytest.fixture()
def postgres_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session, session_factory
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _cleanup_users(session_factory, usernames: list[str]) -> None:
    if not usernames:
        return
    with session_factory() as cleanup:
        cleanup.execute(delete(User).where(User.username.in_(usernames)))
        cleanup.commit()


@pytest.fixture()
def viewer_token(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("rbac_viewer")
    create_user(session, username=username, password="synthetic-pw-1", role="viewer")
    token, _ = create_access_token(subject=username, role="viewer")
    try:
        yield token
    finally:
        _cleanup_users(session_factory, [username])


@pytest.fixture()
def operator_token(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("rbac_operator")
    create_user(session, username=username, password="synthetic-pw-2", role="operator")
    token, _ = create_access_token(subject=username, role="operator")
    try:
        yield token
    finally:
        _cleanup_users(session_factory, [username])


@pytest.fixture()
def inactive_viewer_token(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("rbac_inactive")
    create_user(
        session,
        username=username,
        password="synthetic-pw-3",
        role="viewer",
        is_active=False,
    )
    token, _ = create_access_token(subject=username, role="viewer")
    try:
        yield token
    finally:
        _cleanup_users(session_factory, [username])


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def reject_route_database_dependency():
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


# ---- 401: 인증 자체가 안 된 경우 --------------------------------------------


def test_no_token_returns_401_on_protected_read_endpoint(
    reject_route_database_dependency,
):
    response = client.get("/api/v1/etl-loads")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert reject_route_database_dependency() == 0


def test_no_token_returns_401_on_etl_quality_summary_before_database(
    reject_route_database_dependency,
):
    response = client.get("/api/v1/etl-loads/quality-summary")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert reject_route_database_dependency() == 0


def test_no_token_returns_401_on_etl_detail_before_database(
    reject_route_database_dependency,
):
    response = client.get("/api/v1/etl-loads/1")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert reject_route_database_dependency() == 0


def test_no_token_returns_401_on_etl_rejections_before_database(
    reject_route_database_dependency,
):
    response = client.get("/api/v1/etl-loads/1/rejections")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert reject_route_database_dependency() == 0


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/api/v1/catalog-promotions", None),
        ("GET", "/api/v1/catalog-promotions/1", None),
        ("GET", "/api/v1/catalog-promotions/1/audits", None),
        ("POST", "/api/v1/etl-loads/1/promotion-preview", None),
        (
            "POST",
            "/api/v1/etl-loads/1/promotions",
            {"confirmation": True, "expected_preview_hash": "a" * 64},
        ),
        ("POST", "/api/v1/catalog-promotions/1/rollback-preview", None),
        (
            "POST",
            "/api/v1/catalog-promotions/1/rollback",
            {"confirmation": True, "expected_preview_hash": "a" * 64},
        ),
    ],
    ids=[
        "promotion-list",
        "promotion-detail",
        "promotion-audits",
        "promotion-preview",
        "promotion-run",
        "rollback-preview",
        "rollback-run",
    ],
)
def test_no_token_returns_401_before_database_for_promotion_routes(
    method,
    path,
    json_body,
    reject_route_database_dependency,
):
    response = client.request(method, path, json=json_body)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert reject_route_database_dependency() == 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/catalog-promotion-rollbacks",
        "/api/v1/catalog-promotion-rollbacks/1",
        "/api/v1/catalog-promotion-rollbacks/1/changes",
    ],
    ids=[
        "rollback-history-list",
        "rollback-history-detail",
        "rollback-change-list",
    ],
)
def test_no_token_returns_401_before_database_for_rollback_history_routes(
    path,
    reject_route_database_dependency,
):
    response = client.get(path)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert reject_route_database_dependency() == 0


def test_garbage_token_returns_401(reject_route_database_dependency):
    response = client.get(
        "/api/v1/etl-loads",
        headers=_auth_headers("this-is-not-a-jwt"),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_token"
    assert reject_route_database_dependency() == 0


def test_malformed_bearer_format_returns_401(reject_route_database_dependency):
    response = client.get(
        "/api/v1/etl-loads",
        headers={"Authorization": "Token abc.def.ghi"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert reject_route_database_dependency() == 0


def test_expired_token_returns_401(reject_route_database_dependency):
    expired_payload_token = jwt.encode(
        {"sub": "someone", "role": "operator", "exp": 1},
        get_jwt_secret(),
        algorithm=CATALOGGUARD_JWT_ALGORITHM,
    )

    response = client.get(
        "/api/v1/etl-loads",
        headers=_auth_headers(expired_payload_token),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_token"
    assert reject_route_database_dependency() == 0


def test_token_for_unknown_user_returns_401(
    reject_route_database_dependency,
    monkeypatch,
):
    monkeypatch.setattr(
        auth_dependencies,
        "get_session_factory",
        lambda: lambda: nullcontext(object()),
    )
    monkeypatch.setattr(
        auth_dependencies,
        "get_user_by_username",
        lambda _session, _username: None,
    )
    token, _ = create_access_token(subject="no-such-user-in-db", role="operator")

    response = client.get("/api/v1/etl-loads", headers=_auth_headers(token))

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_token"
    assert reject_route_database_dependency() == 0


def test_inactive_user_token_returns_401_even_though_signature_is_valid(
    inactive_viewer_token,
):
    response = client.get(
        "/api/v1/etl-loads",
        headers=_auth_headers(inactive_viewer_token),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "inactive_user"


# ---- 403: 인증은 됐지만 역할이 부족한 경우 -----------------------------------


def test_viewer_token_is_forbidden_from_running_web_etl(viewer_token):
    response = client.post(
        "/api/v1/etl-loads",
        headers=_auth_headers(viewer_token),
        files={"file": ("vendor.csv", b"a,b\n1,2\n", "text/csv")},
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


def test_viewer_token_is_forbidden_from_running_promotion(viewer_token):
    response = client.post(
        "/api/v1/etl-loads/1/promotions",
        headers=_auth_headers(viewer_token),
        json={"confirmation": True, "expected_preview_hash": "a" * 64},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


def test_viewer_token_is_forbidden_from_running_rollback(viewer_token):
    response = client.post(
        "/api/v1/catalog-promotions/1/rollback",
        headers=_auth_headers(viewer_token),
        json={"confirmation": True, "expected_preview_hash": "a" * 64},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


# ---- Operator/viewer가 조회·preview는 통과해야 함(401/403이 아니어야 함) ------


def test_viewer_token_can_read_etl_load_list(viewer_token):
    response = client.get("/api/v1/etl-loads", headers=_auth_headers(viewer_token))

    assert response.status_code == 200


def test_viewer_token_can_read_etl_quality_summary(viewer_token):
    response = client.get(
        "/api/v1/etl-loads/quality-summary",
        headers=_auth_headers(viewer_token),
    )

    assert response.status_code == 200


def test_operator_token_can_read_etl_quality_summary(operator_token):
    response = client.get(
        "/api/v1/etl-loads/quality-summary",
        headers=_auth_headers(operator_token),
    )

    assert response.status_code == 200


def test_viewer_token_can_read_etl_profiles(viewer_token):
    response = client.get("/api/v1/etl-profiles", headers=_auth_headers(viewer_token))

    assert response.status_code == 200


def test_viewer_token_can_read_rollback_history(viewer_token):
    response = client.get(
        "/api/v1/catalog-promotion-rollbacks",
        headers=_auth_headers(viewer_token),
    )

    assert response.status_code == 200


def test_operator_token_can_read_rollback_history(operator_token):
    response = client.get(
        "/api/v1/catalog-promotion-rollbacks",
        headers=_auth_headers(operator_token),
    )

    assert response.status_code == 200


@pytest.fixture()
def empty_rollback_changes_route(monkeypatch):
    fake_session = object()

    def override_session():
        yield fake_session

    def fake_changes(session, *, rollback_run_id, limit, offset):
        assert session is fake_session
        assert rollback_run_id == 1
        return SimpleNamespace(items=[], total=0, limit=limit, offset=offset)

    from api.routes import etl_loads as etl_loads_route

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        etl_loads_route,
        "list_catalog_promotion_rollback_changes",
        fake_changes,
        raising=False,
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize("token_fixture", ["viewer_token", "operator_token"])
def test_viewer_and_operator_can_read_rollback_changes(
    token_fixture,
    request,
    empty_rollback_changes_route,
):
    token = request.getfixturevalue(token_fixture)

    response = client.get(
        "/api/v1/catalog-promotion-rollbacks/1/changes",
        headers=_auth_headers(token),
    )

    assert response.status_code == 200


def test_viewer_token_can_request_promotion_preview_but_not_blocked_by_role(
    viewer_token,
):
    # 대상 batch가 없어 404가 나더라도 401/403이 아니라는 점이 핵심입니다.
    response = client.post(
        "/api/v1/etl-loads/999999/promotion-preview",
        headers=_auth_headers(viewer_token),
    )

    assert response.status_code not in (401, 403)


def test_viewer_token_can_request_rollback_preview_but_not_blocked_by_role(
    viewer_token,
):
    response = client.post(
        "/api/v1/catalog-promotions/999999/rollback-preview",
        headers=_auth_headers(viewer_token),
    )

    assert response.status_code not in (401, 403)


def test_operator_token_passes_auth_for_web_etl_and_reaches_business_validation(
    operator_token,
):
    # 잘못된 CSV라 400이 나더라도, 401/403이 아니라는 점이 auth 통과의 증거입니다.
    response = client.post(
        "/api/v1/etl-loads",
        headers=_auth_headers(operator_token),
        files={"file": ("vendor.csv", b"not,a,valid,header\n1,2\n", "text/csv")},
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code not in (401, 403)


def test_operator_token_passes_auth_for_promotion_and_reaches_not_found(
    operator_token,
):
    response = client.post(
        "/api/v1/etl-loads/999999/promotions",
        headers=_auth_headers(operator_token),
        json={"confirmation": True, "expected_preview_hash": "a" * 64},
    )

    assert response.status_code not in (401, 403)


def test_operator_token_passes_auth_for_rollback_and_reaches_not_found(
    operator_token,
):
    response = client.post(
        "/api/v1/catalog-promotions/999999/rollback",
        headers=_auth_headers(operator_token),
        json={"confirmation": True, "expected_preview_hash": "a" * 64},
    )

    assert response.status_code not in (401, 403)


def test_operator_token_can_submit_csv_inspection_and_is_not_blocked_by_role(
    operator_token,
):
    response = client.post(
        "/api/v1/inspections",
        headers=_auth_headers(operator_token),
        files={"file": ("vendor.csv", b"not,a,valid,header\n1,2\n", "text/csv")},
    )

    assert response.status_code not in (401, 403)


def test_viewer_token_is_forbidden_from_submitting_csv_inspection(viewer_token):
    response = client.post(
        "/api/v1/inspections",
        headers=_auth_headers(viewer_token),
        files={"file": ("vendor.csv", b"a,b\n1,2\n", "text/csv")},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


# ---- Public endpoint은 계속 인증 없이 동작해야 함 ----------------------------


def test_health_endpoint_remains_public():
    response = client.get("/health")

    assert response.status_code == 200


def test_ready_endpoint_does_not_require_authentication_header():
    response = client.get("/ready")

    # DB 연결 상태에 따라 200 또는 503일 수 있지만 401은 아니어야 합니다.
    assert response.status_code != 401
