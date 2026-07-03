# 역할: FastAPI health check 엔드포인트가 정상 상태를 반환하는지 테스트합니다.
from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_health_check_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "catalogguard-lite-api",
    }
