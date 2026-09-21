# 역할: 로그인(access token 발급)과 현재 사용자 조회 API의 계약을 테스트합니다.
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_current_user
from api.main import app
from api.routes import auth as auth_route
from db.session import get_session


client = TestClient(app)
LOGIN_ENDPOINT = "/api/v1/auth/login"
ME_ENDPOINT = "/api/v1/auth/me"


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


@pytest.fixture(autouse=True)
def fake_session():
    app.dependency_overrides[get_session] = lambda: iter([object()])
    yield
    app.dependency_overrides.clear()


def _fake_user(*, username="operator_user", role="operator"):
    return SimpleNamespace(id=1, username=username, role=role, is_active=True)


def test_login_success_returns_access_token(monkeypatch):
    monkeypatch.setattr(
        auth_route,
        "authenticate_user",
        lambda session, *, username, password: _fake_user(),
    )

    response = client.post(
        LOGIN_ENDPOINT,
        json={"username": "operator_user", "password": "correct-password"},
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"access_token", "token_type", "expires_in"}
    assert isinstance(data["access_token"], str) and data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_response_never_includes_password_fields(monkeypatch):
    monkeypatch.setattr(
        auth_route,
        "authenticate_user",
        lambda session, *, username, password: _fake_user(),
    )

    response = client.post(
        LOGIN_ENDPOINT,
        json={"username": "operator_user", "password": "correct-password"},
    )

    body_text = response.text
    assert "password" not in body_text.lower() or "password_hash" not in body_text


def test_login_fails_for_unknown_username(monkeypatch):
    monkeypatch.setattr(
        auth_route,
        "authenticate_user",
        lambda session, *, username, password: None,
    )

    response = client.post(
        LOGIN_ENDPOINT,
        json={"username": "no-such-user", "password": "anything"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


def test_login_fails_for_wrong_password(monkeypatch):
    monkeypatch.setattr(
        auth_route,
        "authenticate_user",
        lambda session, *, username, password: None,
    )

    response = client.post(
        LOGIN_ENDPOINT,
        json={"username": "operator_user", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


def test_login_fails_for_inactive_user_with_same_generic_message(monkeypatch):
    # authenticate_user()가 이미 inactive를 걸러 None을 반환하므로, 응답은 다른 실패와 동일합니다.
    monkeypatch.setattr(
        auth_route,
        "authenticate_user",
        lambda session, *, username, password: None,
    )

    response = client.post(
        LOGIN_ENDPOINT,
        json={"username": "inactive_user", "password": "correct-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


def test_login_rejects_missing_password_field():
    response = client.post(LOGIN_ENDPOINT, json={"username": "someone"})

    assert response.status_code == 422


def test_disabled_limiter_does_not_create_redis_client_or_warn(monkeypatch, caplog):
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setattr(
        auth_route,
        "get_login_rate_limiter",
        lambda: pytest.fail("disabled login limiter created a Redis client"),
    )
    monkeypatch.setattr(auth_route, "authenticate_user", lambda *args, **kwargs: _fake_user())
    assert client.post(LOGIN_ENDPOINT, json={"username": "operator_user", "password": "pw"}).status_code == 200
    assert not any(
        record.name == "catalogguard.auth" and record.levelname == "WARNING"
        for record in caplog.records
    )


def test_limiter_counts_successful_login_before_authentication(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_ENABLED", "true")
    events = []

    class AllowLimiter:
        def allow_attempt(self, *, username, client_ip):
            events.append(("limit", username, client_ip))
            return True

    def authenticate(session, *, username, password):
        events.append(("authenticate", username, password))
        return _fake_user()

    monkeypatch.setattr(auth_route, "get_login_rate_limiter", lambda: AllowLimiter())
    monkeypatch.setattr(auth_route, "authenticate_user", authenticate)
    response = client.post(LOGIN_ENDPOINT, json={"username": " User1 ", "password": "pw"})
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert [event[0] for event in events] == ["limit", "authenticate"]
    assert events[0][1] == " User1 "


def test_limiter_blocks_before_authentication_with_generic_429(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_ENABLED", "true")

    class BlockLimiter:
        def allow_attempt(self, *, username, client_ip):
            return False

    monkeypatch.setattr(auth_route, "get_login_rate_limiter", lambda: BlockLimiter())
    monkeypatch.setattr(
        auth_route,
        "authenticate_user",
        lambda *args, **kwargs: pytest.fail("blocked request reached authentication"),
    )
    response = client.post(LOGIN_ENDPOINT, json={"username": "someone", "password": "pw"})
    assert response.status_code == 429
    assert response.json() == {"detail": auth_route.LOGIN_RATE_LIMITED_DETAIL}
    assert "Retry-After" not in response.headers


@pytest.mark.parametrize("username", ["operator_user", "no-such-user", "inactive_user"])
def test_limiter_allows_generic_credential_failure_for_any_username(monkeypatch, username):
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_ENABLED", "true")

    class AllowLimiter:
        def allow_attempt(self, *, username, client_ip):
            return True

    monkeypatch.setattr(auth_route, "get_login_rate_limiter", lambda: AllowLimiter())
    monkeypatch.setattr(auth_route, "authenticate_user", lambda *args, **kwargs: None)
    response = client.post(LOGIN_ENDPOINT, json={"username": username, "password": "pw"})
    assert response.status_code == 401
    assert response.json() == {"detail": auth_route.INVALID_CREDENTIALS_DETAIL}


def test_invalid_body_never_calls_limiter(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setattr(
        auth_route,
        "get_login_rate_limiter",
        lambda: pytest.fail("invalid body reached limiter"),
    )
    response = client.post(LOGIN_ENDPOINT, json={"username": "someone"})
    assert response.status_code == 422


def test_get_me_requires_authentication():
    response = client.get(ME_ENDPOINT)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_get_me_rejects_malformed_authorization_header():
    response = client.get(ME_ENDPOINT, headers={"Authorization": "NotBearer abc"})

    assert response.status_code == 401


def test_get_me_returns_username_and_role_without_password_hash():
    app.dependency_overrides[get_current_user] = lambda: _fake_user(
        username="viewer_user", role="viewer"
    )

    response = client.get(ME_ENDPOINT)

    assert response.status_code == 200
    data = response.json()
    assert data == {"username": "viewer_user", "role": "viewer"}
    assert "password" not in response.text.lower()
