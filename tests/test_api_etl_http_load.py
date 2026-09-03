from __future__ import annotations

import csv
import io
import json
import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.dependencies import get_current_user
from api.main import app
from api.routes import etl_loads as etl_loads_route
from config.database import get_optional_database_url
from config.logging import LOGGER_NAME
from conftest import clear_current_user_override, fake_session_without_runtime_overrides, override_current_user
from core.security import create_access_token
from core.upload_validator import CsvUploadValidationError
from db.auth_service import create_user
from db.models import CatalogProductStaging, ETLLoadRun, User
from db.session import create_database_engine, create_session_factory, get_session
from etl.db_loader import ETLLoadError
from etl.http_source import (
    HTTPFeedNotConfiguredError,
    HTTPFeedReadError,
    HTTPFeedSourceObject,
)
from etl.pipeline import ETLPipelineError
from etl.profile_loader import ETLProfileInactiveError, ETLProfileNotFoundError
import etl.profile_loader as profile_loader
from etl.web_service import ETLWebRunOutcome


client = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/api/v1/etl-loads/http"
REQUEST = {"profile_id": "sample_fashion_vendor_v1"}
SECRET_FEED_URL = "https://supplier.example.invalid/catalog.csv?token=secret-feed-token"


@pytest.fixture(autouse=True)
def clear_overrides():
    override_current_user(role="operator")
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


@pytest.fixture()
def captured_api_logs(caplog):
    logger = logging.getLogger(LOGGER_NAME)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def _fake_outcome(
    *,
    source_filename: str,
    actor_username: str | None,
    initial_source_type: str = "http_feed",
    initial_source_ref: str | None = None,
) -> ETLWebRunOutcome:
    return ETLWebRunOutcome(
        etl_load_run_id=42,
        created=True,
        profile_name="sample_fashion_vendor",
        profile_version="1",
        source_filename=source_filename,
        total_rows=2,
        loaded_rows=2,
        rejected_rows=0,
        error_counts={},
        actor_username=actor_username,
    )


def test_http_endpoint_passes_configured_filename_and_authenticated_actor_to_web_etl(
    monkeypatch,
):
    calls: list[dict] = []

    def fake_run_web_etl(
        session,
        *,
        profile_id,
        source_filename,
        input_bytes,
        actor_user_id=None,
        actor_username=None,
        initial_source_type=None,
        initial_source_ref=None,
    ):
        calls.append(
            {
                "profile_id": profile_id,
                "source_filename": source_filename,
                "input_bytes": input_bytes,
                "actor_user_id": actor_user_id,
                "actor_username": actor_username,
                "initial_source_type": initial_source_type,
                "initial_source_ref": initial_source_ref,
            }
        )
        return _fake_outcome(
            source_filename=source_filename,
            actor_username=actor_username,
            initial_source_type=initial_source_type,
            initial_source_ref=initial_source_ref,
        )

    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
    )
    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 200, response.text
    assert calls == [
        {
            "profile_id": "sample_fashion_vendor_v1",
            "source_filename": "supplier_feed.csv",
            "input_bytes": b"supplier,csv\n",
            "actor_user_id": 1,
            "actor_username": "operator_user",
            "initial_source_type": "http_feed",
            # feed URL이 아니라 비밀 없는 고정 식별자입니다.
            "initial_source_ref": "configured_http_feed",
        }
    ]
    assert response.json()["source_filename"] == "supplier_feed.csv"


@pytest.mark.parametrize(
    "extra_field",
    [
        {"url": "http://169.254.169.254/latest/meta-data/"},
        {"feed_url": "https://attacker.example.invalid/evil.csv"},
        {"object_key": "incoming/other.csv"},
    ],
)
def test_http_endpoint_rejects_client_selected_source_without_reading_feed(
    monkeypatch, extra_field
):
    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: pytest.fail("HTTP feed must not be read"),
    )

    response = client.post(ENDPOINT, json={**REQUEST, **extra_field})

    assert response.status_code == 422


def test_anonymous_http_endpoint_returns_401_without_reading_feed(monkeypatch):
    clear_current_user_override()
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: pytest.fail("HTTP feed must not be read"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 401


def test_viewer_http_endpoint_returns_403_without_reading_feed(monkeypatch):
    override_current_user(role="viewer")
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: pytest.fail("HTTP feed must not be read"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            HTTPFeedNotConfiguredError(SECRET_FEED_URL),
            503,
            "http_feed_not_configured",
        ),
        (HTTPFeedReadError(SECRET_FEED_URL), 502, "http_feed_read_failed"),
    ],
)
def test_http_adapter_failures_are_safe_and_do_not_record_web_etl_metrics(
    monkeypatch, error, expected_status, expected_code
):
    def raise_error():
        raise error

    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(etl_loads_route, "read_http_feed_csv", raise_error)
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *args, **kwargs: pytest.fail("Web ETL must not run"),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "record_web_etl_run",
        lambda outcome: pytest.fail("source failures must not record Web ETL metrics"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert SECRET_FEED_URL not in response.text
    assert "secret-feed-token" not in response.text


def test_http_read_failure_logs_only_safe_structured_fields(
    monkeypatch, captured_api_logs
):
    def raise_error():
        raise HTTPFeedReadError(SECRET_FEED_URL)

    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(etl_loads_route, "read_http_feed_csv", raise_error)

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 502
    payloads = [
        json.loads(record.getMessage())
        for record in captured_api_logs.records
        if record.getMessage().startswith("{")
    ]
    source_events = [
        payload
        for payload in payloads
        if payload.get("event") == "http_etl_source_failed"
    ]
    assert source_events == [
        {
            "event": "http_etl_source_failed",
            "error_code": "http_feed_read_failed",
            "level": "WARNING",
            "timestamp": source_events[0]["timestamp"],
        }
    ]
    assert not any("secret-feed-token" in record.getMessage() for record in captured_api_logs.records)


def test_http_csv_validation_error_is_invalid_upload_without_web_metric(monkeypatch):
    def raise_error():
        raise CsvUploadValidationError("업로드한 파일이 비어 있습니다.")

    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(etl_loads_route, "read_http_feed_csv", raise_error)
    monkeypatch.setattr(
        etl_loads_route,
        "record_web_etl_run",
        lambda outcome: pytest.fail("source failures must not record Web ETL metrics"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_upload"


def test_invalid_configured_feed_filename_returns_503(monkeypatch):
    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_URL", SECRET_FEED_URL)
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_FILENAME", "supplier.txt")

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "http_feed_not_configured"


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (ETLProfileNotFoundError("boom"), 400, "unsupported_profile"),
        (ETLProfileInactiveError("boom"), 409, "inactive_profile"),
        (ETLPipelineError("boom"), 400, "invalid_upload"),
        (ETLLoadError("boom"), 500, "etl_load_failed"),
    ],
)
def test_http_download_then_web_etl_errors_keep_existing_mapping_and_record_failure_metric(
    monkeypatch, error, expected_status, expected_code
):
    run_metrics: list[str] = []
    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
    )

    def raise_error(*args, **kwargs):
        raise error

    monkeypatch.setattr(etl_loads_route, "run_web_etl", raise_error)
    monkeypatch.setattr(etl_loads_route, "record_web_etl_run", run_metrics.append)

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert run_metrics == ["failed"]


def test_http_success_records_same_created_metrics_as_multipart_endpoint(monkeypatch):
    run_metrics: list[str] = []
    row_metrics: list[dict[str, int | None]] = []
    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *args, **kwargs: _fake_outcome(
            source_filename=kwargs["source_filename"],
            actor_username=kwargs["actor_username"],
        ),
    )
    monkeypatch.setattr(etl_loads_route, "record_web_etl_run", run_metrics.append)
    monkeypatch.setattr(
        etl_loads_route,
        "record_web_etl_rows",
        lambda **kwargs: row_metrics.append(kwargs),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 200
    assert run_metrics == ["created"]
    assert row_metrics == [{"loaded_rows": 2, "rejected_rows": 0}]


def test_http_duplicate_success_records_only_duplicate_run_metric(monkeypatch):
    run_metrics: list[str] = []
    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: HTTPFeedSourceObject("supplier_feed.csv", b"supplier,csv\n"),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *args, **kwargs: ETLWebRunOutcome(
            etl_load_run_id=42,
            created=False,
            profile_name="sample_fashion_vendor",
            profile_version="1",
            source_filename="supplier_feed.csv",
            total_rows=2,
            loaded_rows=2,
            rejected_rows=0,
            error_counts={},
            actor_username=kwargs["actor_username"],
        ),
    )
    monkeypatch.setattr(etl_loads_route, "record_web_etl_run", run_metrics.append)
    monkeypatch.setattr(
        etl_loads_route,
        "record_web_etl_rows",
        lambda **kwargs: pytest.fail("duplicate must not record Web ETL row metrics"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert run_metrics == ["duplicate"]


FASHION_PROFILE_COLUMNS = [
    "vendor_sku",
    "item_name",
    "main_category",
    "brand_name",
    "list_price",
    "discount_price",
    "colour",
    "size_name",
    "quantity",
    "description_text",
    "image_link",
]


def _supplier_csv(marker: str) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FASHION_PROFILE_COLUMNS)
    writer.writerow(
        [
            f"SKU-{marker}",
            "test product",
            "TOP",
            "brand",
            # 기존 transformer가 쉼표 가격을 정수로 바꾸는지 함께 확인합니다.
            "12,000",
            "10000",
            "BLACK",
            "M",
            "3",
            "description",
            "image.jpg",
        ]
    )
    return output.getvalue().encode("utf-8")


@pytest.fixture()
def postgres_api():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        yield session_factory
    finally:
        engine.dispose()


def test_http_endpoint_persists_staging_actor_and_reuses_duplicate_identity(
    postgres_api, monkeypatch
):
    session_factory = postgres_api
    marker = uuid4().hex
    username = f"http_etl_actor_{marker[:12]}"
    source_filename = f"feed_{marker}.csv"
    content = _supplier_csv(marker)

    with session_factory() as user_session:
        user = create_user(
            user_session,
            username=username,
            password="synthetic-http-etl-password",
            role="operator",
        )
    token, _ = create_access_token(subject=username, role="operator")

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides.pop(get_current_user, None)
    # 실제 운영처럼 credential이 붙은 feed URL을 설정해 두고, 그것이 저장되지 않는지 확인합니다.
    monkeypatch.setenv(
        "CATALOGGUARD_ETL_HTTP_FEED_URL",
        "https://supplier.example.test/catalog.csv?token=secret-feed-token",
    )
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: HTTPFeedSourceObject(source_filename, content),
    )
    try:
        first = client.post(
            ENDPOINT,
            json=REQUEST,
            headers={"Authorization": f"Bearer {token}"},
        )
        second = client.post(
            ENDPOINT,
            json=REQUEST,
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    run_id = first.json()["etl_load_run_id"]
    # 같은 CSV를 두 번 가져와도 기존 dedup 계약대로 같은 배치를 재사용합니다.
    assert second.json()["etl_load_run_id"] == run_id

    try:
        with session_factory() as verify_session:
            runs = verify_session.scalars(
                select(ETLLoadRun).where(ETLLoadRun.source_filename == source_filename)
            ).all()
            assert len(runs) == 1
            run = runs[0]
            assert run.id == run_id
            assert run.profile_name == "sample_fashion_vendor"
            assert run.loaded_rows == 1
            assert run.rejected_rows == 0
            assert run.input_file_sha256
            # Actor Audit은 새 source adapter가 아니라 기존 실행 경로가 기록합니다.
            assert run.actor_user_id == user.id
            assert run.actor_username == username
            # 최초 유입 경로는 http_feed이고, locator는 비밀 없는 고정 식별자입니다.
            assert run.initial_source_type == "http_feed"
            assert run.initial_source_ref == "configured_http_feed"
            # feed URL 원문, host, query, token 중 어느 것도 DB에 남지 않아야 합니다.
            stored = f"{run.initial_source_ref} {run.source_filename}"
            assert "secret-feed-token" not in stored
            assert "token=" not in stored
            assert "https://" not in stored
            assert "supplier.example.test" not in stored
            # API 응답에서도 마찬가지입니다(DB 저장 전에 이미 안전한 값이어야 합니다).
            assert "secret-feed-token" not in first.text
            assert "supplier.example.test" not in first.text
            assert first.json()["initial_source_type"] == "http_feed"
            assert first.json()["initial_source_ref"] == "configured_http_feed"
            products = verify_session.scalars(
                select(CatalogProductStaging).where(
                    CatalogProductStaging.etl_load_run_id == run_id
                )
            ).all()
            assert len(products) == 1
            # 기존 transformer 계약: "12,000" -> 12000
            assert products[0].price == 12000
            assert products[0].sale_price == 10000
            assert products[0].category == "TOP"
    finally:
        with session_factory() as cleanup:
            cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
            cleanup.execute(delete(User).where(User.username == username))
            cleanup.commit()


def _deactivated_registry_entry(profile_id: str) -> dict:
    entry = dict(profile_loader._ETL_PROFILE_REGISTRY[profile_id])
    entry["active_version"] = None
    return entry


def test_inactive_profile_is_rejected_before_any_http_feed_read(monkeypatch):
    # 비활성 프로필 때문에 외부 feed를 건드리지 않습니다. 나가지 않아야 할 요청이
    # 나가고 나서 409를 주는 것은 정책을 지킨 것이 아닙니다.
    metrics: list[str] = []
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        "sample_fashion_vendor_v1",
        _deactivated_registry_entry("sample_fashion_vendor_v1"),
    )
    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: pytest.fail("inactive profile must not reach the HTTP feed source"),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *args, **kwargs: pytest.fail("inactive profile must not run Web ETL"),
    )
    monkeypatch.setattr(etl_loads_route, "record_web_etl_run", metrics.append)

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "inactive_profile"
    assert metrics == ["failed"]


def test_inactive_profile_outranks_a_source_error_that_would_fire_first(monkeypatch):
    # feed 미설정(503)처럼 source가 먼저 실패했을 상황에서도 비활성 차단이 앞섭니다.
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        "sample_fashion_vendor_v1",
        _deactivated_registry_entry("sample_fashion_vendor_v1"),
    )
    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: (_ for _ in ()).throw(HTTPFeedNotConfiguredError("not configured")),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "inactive_profile"


def test_unknown_profile_keeps_the_existing_source_error_precedence(monkeypatch):
    app.dependency_overrides[get_session] = fake_session_without_runtime_overrides
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: (_ for _ in ()).throw(HTTPFeedReadError("boom")),
    )

    response = client.post(ENDPOINT, json={**REQUEST, "profile_id": "not-exists"})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "http_feed_read_failed"
