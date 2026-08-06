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
