import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import inspection_copilot as copilot_route
from conftest import clear_current_user_override, override_current_user
from db.session import get_session


client = TestClient(app)
ENDPOINT = "/api/v1/inspection-copilot/ask"


@pytest.fixture(autouse=True)
def authenticated_viewer(monkeypatch):
    override_current_user(role="viewer")
    app.dependency_overrides[get_session] = lambda: iter([object()])
    yield
    app.dependency_overrides.pop(get_session, None)
    clear_current_user_override()


def test_ask_copilot_requires_viewer_authentication():
    clear_current_user_override()

    response = client.post(ENDPOINT, json={"question": "요약해줘", "current_run_id": 101})

    assert response.status_code == 401


def test_ask_copilot_returns_structured_answer_and_session_comparison_ids(monkeypatch):
    captured = {}
    from services.inspection_copilot_service import (
        InspectionCopilotAnswer,
        InspectionCopilotEvidence,
    )

    response_value = InspectionCopilotAnswer(
        answer="오류부터 확인하세요.",
        evidence=[
            InspectionCopilotEvidence(
                run_id=101,
                source_row_number=2,
                rule_codes=["필수 값 누락"],
                comparison_run_ids=[101, 114],
            )
        ],
        limitations=["저장된 검수 결과만 설명합니다."],
    )

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return response_value

    monkeypatch.setattr(copilot_route, "ask_inspection_copilot", fake_ask)

    response = client.post(
        ENDPOINT,
        json={
            "question": "수정 전후 차이를 설명해줘",
            "current_run_id": 114,
            "baseline_run_id": 101,
            "target_run_id": 114,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "오류부터 확인하세요.",
        "evidence": [
            {
                "run_id": 101,
                "source_row_number": 2,
                "rule_codes": ["필수 값 누락"],
                "comparison_run_ids": [101, 114],
            }
        ],
        "limitations": ["저장된 검수 결과만 설명합니다."],
    }
    assert captured["current_run_id"] == 114
    assert captured["baseline_run_id"] == 101
    assert captured["target_run_id"] == 114


def test_ask_copilot_reports_missing_api_key_without_affecting_other_routes(monkeypatch):
    monkeypatch.setattr(
        copilot_route,
        "ask_inspection_copilot",
        lambda **kwargs: (_ for _ in ()).throw(
            copilot_route.InspectionCopilotUnavailableError("agent_not_configured")
        ),
    )

    response = client.post(ENDPOINT, json={"question": "요약해줘", "current_run_id": 101})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "agent_not_configured"


def test_ask_copilot_bounds_question_length_before_model_execution(monkeypatch):
    monkeypatch.setattr(
        copilot_route,
        "ask_inspection_copilot",
        lambda **kwargs: pytest.fail("agent must not run for an oversized question"),
    )

    response = client.post(ENDPOINT, json={"question": "가" * 1001, "current_run_id": 101})

    assert response.status_code == 422
