# 역할: FastAPI 요청 구조화 로그와 민감정보 비기록을 테스트합니다.
import importlib
import json
import logging

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.routes import inspections as inspections_route
from db.session import get_session


LOGGER_NAME = "catalogguard.api"
REQUEST_ID_HEADER = "X-Request-ID"
client = TestClient(api_main.app)
error_client = TestClient(api_main.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def fake_database_session():
    def override_session():
        yield object()

    api_main.app.dependency_overrides[get_session] = override_session
    yield
    api_main.app.dependency_overrides.clear()


@pytest.fixture
def captured_api_logs(caplog):
    logger = logging.getLogger(LOGGER_NAME)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def structured_events(caplog) -> list[dict[str, object]]:
    events = []
    for record in caplog.records:
        if record.name != LOGGER_NAME:
            continue
        try:
            event = json.loads(record.getMessage())
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and "event" in event:
            events.append(event)
    return events


def events_for_request(caplog, request_id: str) -> list[dict[str, object]]:
    return [
        event
        for event in structured_events(caplog)
        if event.get("request_id") == request_id
    ]


def application_log_text(caplog) -> str:
    return "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER_NAME
    )


def test_logging_configuration_does_not_duplicate_project_handler() -> None:
    logging_config = importlib.import_module("config.logging")

    logger = logging_config.configure_logging()
    same_logger = logging_config.configure_logging()

    project_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_catalogguard_handler", False)
    ]
    assert same_logger is logger
    assert len(project_handlers) == 1
    assert logger.level == logging.INFO
    assert logger.propagate is False


def test_health_response_has_request_id_and_one_completed_event(
    captured_api_logs,
) -> None:
    response = client.get("/health")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id

    completed_events = [
        event
        for event in events_for_request(captured_api_logs, request_id)
        if event["event"] == "http_request_completed"
    ]
    assert len(completed_events) == 1
    event = completed_events[0]
    assert event["level"] == "INFO"
    assert str(event["timestamp"]).endswith("Z")
    assert event["method"] == "GET"
    assert event["path"] == "/health"
    assert event["status_code"] == 200
    assert isinstance(event["duration_ms"], (int, float))
    assert event["duration_ms"] >= 0


def test_each_request_gets_a_new_server_generated_request_id() -> None:
    supplied_request_id = "client-supplied-request-id"

    first_response = client.get(
        "/health",
        headers={REQUEST_ID_HEADER: supplied_request_id},
    )
    second_response = client.get("/health")

    first_request_id = first_response.headers[REQUEST_ID_HEADER]
    second_request_id = second_response.headers[REQUEST_ID_HEADER]
    assert first_request_id != supplied_request_id
    assert first_request_id != second_request_id


def test_query_string_is_not_recorded(captured_api_logs) -> None:
    secret_query_value = "secret-query-value"

    response = client.get(f"/health?token={secret_query_value}")

    request_id = response.headers[REQUEST_ID_HEADER]
    completed_event = next(
        event
        for event in events_for_request(captured_api_logs, request_id)
        if event["event"] == "http_request_completed"
    )
    assert completed_event["path"] == "/health"
    assert "?" not in str(completed_event["path"])
    assert secret_query_value not in application_log_text(captured_api_logs)
    assert "http://testserver" not in application_log_text(captured_api_logs)


@pytest.mark.parametrize(
    ("method", "path", "expected_status_code"),
    [
        ("GET", "/missing", 404),
        ("POST", "/api/v1/inspections", 422),
    ],
)
def test_handled_error_is_recorded_once_as_completed(
    captured_api_logs,
    method: str,
    path: str,
    expected_status_code: int,
) -> None:
    response = client.request(method, path)

    request_id = response.headers[REQUEST_ID_HEADER]
    request_events = events_for_request(captured_api_logs, request_id)
    completed_events = [
        event
        for event in request_events
        if event["event"] == "http_request_completed"
    ]
    assert response.status_code == expected_status_code
    assert len(completed_events) == 1
    assert completed_events[0]["status_code"] == expected_status_code
    assert all(event["event"] != "http_request_failed" for event in request_events)


def test_unhandled_exception_is_safely_logged_and_keeps_500_response(
    captured_api_logs,
    monkeypatch,
) -> None:
    internal_error = "postgresql://user:secret-password@private-host/database"

    def fail_list_inspections(*args, **kwargs):
        raise RuntimeError(internal_error)

    monkeypatch.setattr(
        inspections_route,
        "list_inspections",
        fail_list_inspections,
    )

    response = error_client.get("/api/v1/inspections")

    request_id = response.headers[REQUEST_ID_HEADER]
    request_events = events_for_request(captured_api_logs, request_id)
    failed_events = [
        event for event in request_events if event["event"] == "http_request_failed"
    ]
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert len(failed_events) == 1
    event = failed_events[0]
    assert event["status_code"] == 500
    assert isinstance(event["duration_ms"], (int, float))
    assert event["error_type"] in {"RuntimeError", "ExceptionGroup"}
    assert all(event["event"] != "http_request_completed" for event in request_events)
    assert "secret-password" not in application_log_text(captured_api_logs)
    assert "private-host" not in application_log_text(captured_api_logs)
    assert internal_error not in application_log_text(captured_api_logs)


def test_readiness_failure_logs_database_event_and_completed_503(
    captured_api_logs,
    monkeypatch,
) -> None:
    internal_error = "postgresql://user:secret-password@private-host/database"

    def database_is_unavailable() -> None:
        raise RuntimeError(internal_error)

    monkeypatch.setattr(
        api_main,
        "check_database_connection",
        database_is_unavailable,
    )

    response = client.get("/ready")

    request_id = response.headers[REQUEST_ID_HEADER]
    request_events = events_for_request(captured_api_logs, request_id)
    database_events = [
        event
        for event in request_events
        if event["event"] == "database_readiness_failed"
    ]
    completed_events = [
        event
        for event in request_events
        if event["event"] == "http_request_completed"
    ]
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "service": "catalogguard-lite-api",
            "database": "unavailable",
        }
    }
    assert len(database_events) == 1
    assert database_events[0]["error_type"] == "RuntimeError"
    assert len(completed_events) == 1
    assert completed_events[0]["status_code"] == 503
    assert all(event["event"] != "http_request_failed" for event in request_events)
    assert "secret-password" not in application_log_text(captured_api_logs)
    assert "private-host" not in application_log_text(captured_api_logs)
    assert internal_error not in application_log_text(captured_api_logs)


def test_post_request_body_is_not_recorded(captured_api_logs) -> None:
    private_body_marker = "private-product-body-marker"

    response = client.post(
        "/api/v1/inspections",
        files={
            "file": (
                "products.txt",
                private_body_marker.encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 400
    assert private_body_marker not in application_log_text(captured_api_logs)
