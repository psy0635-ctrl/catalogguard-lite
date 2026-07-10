# 역할: FastAPI health/readiness check의 상태와 정보 비노출을 테스트합니다.
from fastapi.testclient import TestClient

import api.main as api_main


client = TestClient(api_main.app)


def test_health_check_returns_ok_without_database_check(monkeypatch) -> None:
    def fail_if_called() -> None:
        raise AssertionError("/health must not check the database")

    monkeypatch.setattr(
        api_main,
        "check_database_connection",
        fail_if_called,
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "catalogguard-lite-api",
    }


def test_readiness_check_returns_ok_when_database_is_available(monkeypatch) -> None:
    calls = 0

    def database_is_available() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(
        api_main,
        "check_database_connection",
        database_is_available,
    )

    response = client.get("/ready")

    assert calls == 1
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "catalogguard-lite-api",
        "database": "ok",
    }


def test_readiness_check_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    def database_is_unavailable() -> None:
        raise RuntimeError("database connection failed")

    monkeypatch.setattr(
        api_main,
        "check_database_connection",
        database_is_unavailable,
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "service": "catalogguard-lite-api",
            "database": "unavailable",
        }
    }


def test_readiness_check_does_not_expose_database_error_details(monkeypatch) -> None:
    def database_is_unavailable() -> None:
        raise RuntimeError(
            "postgresql://user:secret-password@private-host/database"
        )

    monkeypatch.setattr(
        api_main,
        "check_database_connection",
        database_is_unavailable,
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert "secret-password" not in response.text
    assert "private-host" not in response.text
    assert "postgresql://" not in response.text
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "service": "catalogguard-lite-api",
            "database": "unavailable",
        }
    }
