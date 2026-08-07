# 역할: Prometheus HTTP metrics와 Web ETL metrics를 검증합니다.
import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import api.main as api_main
from api.dependencies import get_current_user
from api.routes import etl_loads as etl_loads_route
from api.routes import inspections as inspections_route
from config import metrics as metrics_config
from conftest import override_current_user
from config.database import get_optional_database_url
from core.security import create_access_token
from core.upload_validator import CsvUploadValidationError
from db.auth_service import create_user
from db.models import ETLLoadRun, User
from db.session import create_database_engine, create_session_factory, get_session
from etl.db_loader import ETLLoadError
from etl.pipeline import ETLPipelineError
from etl.profile_loader import ETLProfileNotFoundError
from etl.web_service import ETLWebRunOutcome


METRICS_ENV_VAR = metrics_config.CATALOGGUARD_METRICS_ENABLED_ENV_VAR
HTTP_REQUESTS_METRIC = "catalogguard_http_requests_total"
HTTP_DURATION_COUNT_METRIC = "catalogguard_http_request_duration_seconds_count"
WEB_ETL_RUNS_METRIC = "catalogguard_web_etl_runs_total"
WEB_ETL_ROWS_METRIC = "catalogguard_web_etl_rows_total"

client = TestClient(api_main.app)
error_client = TestClient(api_main.app, raise_server_exceptions=False)


def sample(name: str, labels: dict[str, str]) -> float:
    return metrics_config.REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture(autouse=True)
def fake_database_session():
    def override_session():
        yield object()

    api_main.app.dependency_overrides[get_session] = override_session
    override_current_user(role="operator")
    yield
    api_main.app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


# ---- CATALOGGUARD_METRICS_ENABLED parsing -----------------------------------


@pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "YES"])
def test_true_like_values_enable_metrics(monkeypatch, value):
    monkeypatch.setenv(METRICS_ENV_VAR, value)
    assert metrics_config.is_metrics_enabled() is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "", "on", "enabled", "  "])
def test_non_true_values_keep_metrics_disabled(monkeypatch, value):
    monkeypatch.setenv(METRICS_ENV_VAR, value)
    assert metrics_config.is_metrics_enabled() is False


def test_unset_env_var_keeps_metrics_disabled(monkeypatch):
    monkeypatch.delenv(METRICS_ENV_VAR, raising=False)
    assert metrics_config.is_metrics_enabled() is False


# ---- /metrics endpoint availability -----------------------------------------


def test_metrics_disabled_by_default_returns_404(monkeypatch):
    monkeypatch.delenv(METRICS_ENV_VAR, raising=False)

    response = client.get("/metrics")

    assert response.status_code == 404


def test_metrics_enabled_returns_prometheus_text_format(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert HTTP_REQUESTS_METRIC in body
    assert "catalogguard_http_request_duration_seconds" in body
    assert WEB_ETL_RUNS_METRIC in body
    assert WEB_ETL_ROWS_METRIC in body


def test_metrics_disabled_records_nothing(monkeypatch):
    monkeypatch.delenv(METRICS_ENV_VAR, raising=False)
    labels = {"method": "GET", "route": "/api/v1/auth/me", "status_class": "2xx"}
    before = sample(HTTP_REQUESTS_METRIC, labels)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert sample(HTTP_REQUESTS_METRIC, labels) == before


# ---- HTTP request/duration metrics ------------------------------------------


def test_http_request_counter_increments_with_method_route_status_class(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")
    labels = {"method": "GET", "route": "/api/v1/auth/me", "status_class": "2xx"}
    before = sample(HTTP_REQUESTS_METRIC, labels)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert sample(HTTP_REQUESTS_METRIC, labels) == before + 1


def test_http_duration_histogram_records_observation(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")
    labels = {"method": "GET", "route": "/api/v1/auth/me"}
    before = sample(HTTP_DURATION_COUNT_METRIC, labels)

    client.get("/api/v1/auth/me")

    assert sample(HTTP_DURATION_COUNT_METRIC, labels) == before + 1


def test_dynamic_id_route_uses_template_not_raw_path(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")
    monkeypatch.setattr(etl_loads_route, "get_etl_load_detail", lambda *a, **k: None)
    template_labels = {
        "method": "GET",
        "route": "/api/v1/etl-loads/{etl_load_run_id}",
        "status_class": "4xx",
    }
    before = sample(HTTP_REQUESTS_METRIC, template_labels)

    first = client.get("/api/v1/etl-loads/1")
    second = client.get("/api/v1/etl-loads/999")

    assert first.status_code == 404
    assert second.status_code == 404
    assert sample(HTTP_REQUESTS_METRIC, template_labels) == before + 2
    assert (
        metrics_config.REGISTRY.get_sample_value(
            HTTP_REQUESTS_METRIC,
            {"method": "GET", "route": "/api/v1/etl-loads/1", "status_class": "4xx"},
        )
        is None
    )
    assert (
        metrics_config.REGISTRY.get_sample_value(
            HTTP_REQUESTS_METRIC,
            {"method": "GET", "route": "/api/v1/etl-loads/999", "status_class": "4xx"},
        )
        is None
    )


def test_unmatched_route_uses_fixed_label(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")
    unmatched_labels = {"method": "GET", "route": "unmatched", "status_class": "4xx"}
    before = sample(HTTP_REQUESTS_METRIC, unmatched_labels)

    first = client.get("/not-real-123")
    second = client.get("/not-real-456")

    assert first.status_code == 404
    assert second.status_code == 404
    assert sample(HTTP_REQUESTS_METRIC, unmatched_labels) == before + 2
    assert (
        metrics_config.REGISTRY.get_sample_value(
            HTTP_REQUESTS_METRIC,
            {"method": "GET", "route": "/not-real-123", "status_class": "4xx"},
        )
        is None
    )


def test_health_ready_metrics_paths_excluded_from_http_counter(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")
    monkeypatch.setattr(api_main, "check_database_connection", lambda: None)

    client.get("/health")
    client.get("/ready")
    client.get("/metrics")

    for path in ("/health", "/ready", "/metrics"):
        assert (
            metrics_config.REGISTRY.get_sample_value(
                HTTP_REQUESTS_METRIC,
                {"method": "GET", "route": path, "status_class": "2xx"},
            )
            is None
        )


def test_unhandled_exception_still_returns_safe_500_and_records_5xx(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")

    def fail_list_inspections(*args, **kwargs):
        raise RuntimeError("internal boom, must not leak")

    monkeypatch.setattr(inspections_route, "list_inspections", fail_list_inspections)
    labels = {"method": "GET", "route": "/api/v1/inspections", "status_class": "5xx"}
    before = sample(HTTP_REQUESTS_METRIC, labels)

    response = error_client.get("/api/v1/inspections")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers.get("X-Request-ID")
    assert sample(HTTP_REQUESTS_METRIC, labels) == before + 1


def test_metrics_body_never_contains_pii_or_dynamic_ids(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")
    monkeypatch.setattr(etl_loads_route, "get_etl_load_detail", lambda *a, **k: None)
    override_current_user(role="operator", username="metrics_pii_probe_user")

    response = client.get(
        "/api/v1/etl-loads/424242",
        headers={"X-Request-ID": "client-supplied-should-not-appear-1234567890"},
    )
    assert response.status_code == 404
    request_id = response.headers["X-Request-ID"]

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    body = metrics_response.text
    assert "metrics_pii_probe_user" not in body
    assert request_id not in body
    assert "424242" not in body
    assert "client-supplied-should-not-appear" not in body


# ---- Web ETL run/row metrics (mocked run_web_etl, no PostgreSQL needed) -----


def _files(*, content: bytes = b"header\nvalue\n", filename: str = "vendor.csv"):
    return {"file": (filename, content, "text/csv")}


def test_web_etl_created_increments_run_and_row_counters(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")

    def fake_run_web_etl(session, **kwargs):
        return ETLWebRunOutcome(
            etl_load_run_id=1,
            created=True,
            profile_name="p",
            profile_version="1",
            source_filename="f.csv",
            total_rows=5,
            loaded_rows=4,
            rejected_rows=1,
            error_counts={},
        )

    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)
    before_created = sample(WEB_ETL_RUNS_METRIC, {"outcome": "created"})
    before_loaded = sample(WEB_ETL_ROWS_METRIC, {"result": "loaded"})
    before_rejected = sample(WEB_ETL_ROWS_METRIC, {"result": "rejected"})

    response = client.post(
        "/api/v1/etl-loads",
        files=_files(),
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code == 200
    assert sample(WEB_ETL_RUNS_METRIC, {"outcome": "created"}) == before_created + 1
    assert sample(WEB_ETL_ROWS_METRIC, {"result": "loaded"}) == before_loaded + 4
    assert sample(WEB_ETL_ROWS_METRIC, {"result": "rejected"}) == before_rejected + 1


def test_web_etl_duplicate_increments_run_counter_but_not_rows(monkeypatch):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")

    def fake_run_web_etl(session, **kwargs):
        return ETLWebRunOutcome(
            etl_load_run_id=1,
            created=False,
            profile_name="p",
            profile_version="1",
            source_filename="f.csv",
            total_rows=5,
            loaded_rows=4,
            rejected_rows=1,
            error_counts={},
        )

    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)
    before_duplicate = sample(WEB_ETL_RUNS_METRIC, {"outcome": "duplicate"})
    before_loaded = sample(WEB_ETL_ROWS_METRIC, {"result": "loaded"})
    before_rejected = sample(WEB_ETL_ROWS_METRIC, {"result": "rejected"})

    response = client.post(
        "/api/v1/etl-loads",
        files=_files(),
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code == 200
    assert sample(WEB_ETL_RUNS_METRIC, {"outcome": "duplicate"}) == before_duplicate + 1
    assert sample(WEB_ETL_ROWS_METRIC, {"result": "loaded"}) == before_loaded
    assert sample(WEB_ETL_ROWS_METRIC, {"result": "rejected"}) == before_rejected


@pytest.mark.parametrize(
    "build_error",
    [
        lambda: ETLProfileNotFoundError("Unknown ETL profile"),
        lambda: CsvUploadValidationError("업로드한 파일이 비어 있습니다."),
        lambda: ETLPipelineError("Input CSV is missing required source columns"),
        lambda: ETLLoadError("표준 CSV와 요약 JSON의 output_file_sha256가 일치하지 않습니다"),
    ],
)
def test_web_etl_failure_increments_failed_counter_only(monkeypatch, build_error):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")

    def fake_run_web_etl(session, **kwargs):
        raise build_error()

    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)
    before_failed = sample(WEB_ETL_RUNS_METRIC, {"outcome": "failed"})
    before_loaded = sample(WEB_ETL_ROWS_METRIC, {"result": "loaded"})
    before_rejected = sample(WEB_ETL_ROWS_METRIC, {"result": "rejected"})

    response = client.post(
        "/api/v1/etl-loads",
        files=_files(),
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code in (400, 500)
    assert sample(WEB_ETL_RUNS_METRIC, {"outcome": "failed"}) == before_failed + 1
    assert sample(WEB_ETL_ROWS_METRIC, {"result": "loaded"}) == before_loaded
    assert sample(WEB_ETL_ROWS_METRIC, {"result": "rejected"}) == before_rejected


# ---- Real PostgreSQL end-to-end check ---------------------------------------


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


def build_supplier_csv(rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FASHION_PROFILE_COLUMNS)
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def valid_row(sku):
    return [sku, "테스트 상품", "TOP", "브랜드", "12000", "10000", "BLACK", "M", "3", "설명", "image.jpg"]


@pytest.fixture()
def postgres_api():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL metrics 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        yield session_factory
    finally:
        engine.dispose()


def test_real_web_etl_request_updates_run_and_row_metrics_once_per_new_batch(
    postgres_api, monkeypatch
):
    monkeypatch.setenv(METRICS_ENV_VAR, "true")
    session_factory = postgres_api
    marker = uuid4().hex
    username = f"metrics_actor_{marker[:12]}"
    csv_bytes = build_supplier_csv([valid_row(f"SKU-{marker}-1"), valid_row(f"SKU-{marker}-2")])
    source_filename = f"vendor_{marker}.csv"

    with session_factory() as user_session:
        create_user(user_session, username=username, password="synthetic-pw-metrics", role="operator")
    token, _ = create_access_token(subject=username, role="operator")

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    api_main.app.dependency_overrides[get_session] = override_session
    api_main.app.dependency_overrides.pop(get_current_user, None)

    before_created = sample(WEB_ETL_RUNS_METRIC, {"outcome": "created"})
    before_duplicate = sample(WEB_ETL_RUNS_METRIC, {"outcome": "duplicate"})
    before_loaded = sample(WEB_ETL_ROWS_METRIC, {"result": "loaded"})
    before_rejected = sample(WEB_ETL_ROWS_METRIC, {"result": "rejected"})

    run_id = None
    try:
        first = client.post(
            "/api/v1/etl-loads",
            files=_files(content=csv_bytes, filename=source_filename),
            data={"profile_id": "sample_fashion_vendor_v1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["created"] is True
        run_id = first_body["etl_load_run_id"]

        second = client.post(
            "/api/v1/etl-loads",
            files=_files(content=csv_bytes, filename=source_filename),
            data={"profile_id": "sample_fashion_vendor_v1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second.status_code == 200
        assert second.json()["created"] is False
        assert second.json()["etl_load_run_id"] == run_id
    finally:
        api_main.app.dependency_overrides.clear()
        if run_id is not None:
            with session_factory() as cleanup:
                cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
                cleanup.execute(delete(User).where(User.username == username))
                cleanup.commit()

    assert sample(WEB_ETL_RUNS_METRIC, {"outcome": "created"}) == before_created + 1
    assert sample(WEB_ETL_RUNS_METRIC, {"outcome": "duplicate"}) == before_duplicate + 1
    assert sample(WEB_ETL_ROWS_METRIC, {"result": "loaded"}) == before_loaded + 2
    assert sample(WEB_ETL_ROWS_METRIC, {"result": "rejected"}) == before_rejected
