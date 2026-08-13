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
from conftest import clear_current_user_override, override_current_user
from core.security import create_access_token
from core.upload_validator import CsvUploadValidationError
from db.auth_service import create_user
from db.models import CatalogProductStaging, ETLLoadRun, User
from db.session import create_database_engine, create_session_factory, get_session
from etl.db_loader import ETLLoadError
from etl.pipeline import ETLPipelineError
from etl.profile_loader import ETLProfileNotFoundError
from etl.s3_source import (
    S3KeyNotAllowedError,
    S3NotConfiguredError,
    S3ObjectNotFoundError,
    S3ReadError,
    S3SourceObject,
)
from etl.web_service import ETLWebRunOutcome


client = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/api/v1/etl-loads/s3"
REQUEST = {
    "profile_id": "sample_fashion_vendor_v1",
    "object_key": "incoming/vendor/products.csv",
}


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
    initial_source_type: str = "s3",
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


def test_s3_endpoint_passes_downloaded_leaf_and_authenticated_actor_to_web_etl(monkeypatch):
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
        assert profile_id == REQUEST["profile_id"]
        assert source_filename == "products.csv"
        assert input_bytes == b"supplier,csv\n"
        assert actor_user_id == 1
        assert actor_username == "operator_user"
        # S3 배치는 bucket이 아니라 허용 prefix를 제거한 상대 key만 locator로 남깁니다.
        assert initial_source_type == "s3"
        assert initial_source_ref == "incoming/vendor/products.csv"
        return _fake_outcome(
            source_filename=source_filename,
            actor_username=actor_username,
            initial_source_type=initial_source_type,
            initial_source_ref=initial_source_ref,
        )

    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: S3SourceObject("products.csv", b"supplier,csv\n"),
    )
    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 200
    assert response.json()["source_filename"] == "products.csv"
    assert response.json()["actor_username"] == "operator_user"


def test_s3_endpoint_rejects_client_selected_bucket_without_reading_adapter(monkeypatch):
    calls: list[str] = []
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: calls.append(key),
    )

    response = client.post(
        ENDPOINT,
        json={**REQUEST, "bucket": "attacker-selected-bucket"},
    )

    assert response.status_code == 422
    assert calls == []


def test_anonymous_s3_endpoint_returns_401_without_reading_s3(monkeypatch):
    clear_current_user_override()
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: pytest.fail("S3 must not be read"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 401


def test_viewer_s3_endpoint_returns_403_without_reading_s3(monkeypatch):
    override_current_user(role="viewer")
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: pytest.fail("S3 must not be read"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (S3NotConfiguredError("raw SDK secret"), 503, "s3_not_configured"),
        (S3ObjectNotFoundError("raw SDK secret"), 404, "s3_object_not_found"),
        (S3KeyNotAllowedError("raw SDK secret"), 400, "s3_key_not_allowed"),
        (S3ReadError("raw SDK secret"), 502, "s3_read_failed"),
    ],
)
def test_s3_adapter_failures_are_safe_and_do_not_record_web_etl_metrics(
    monkeypatch, error, expected_status, expected_code
):
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: (_ for _ in ()).throw(error),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "record_web_etl_run",
        lambda outcome: pytest.fail("adapter failure must not record Web ETL run metric"),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "record_web_etl_rows",
        lambda **kwargs: pytest.fail("adapter failure must not record Web ETL row metric"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == expected_status
    detail = response.json()["detail"]
    assert detail["code"] == expected_code
    assert "raw SDK secret" not in response.text


def test_s3_read_failure_logs_only_safe_structured_fields(
    monkeypatch, captured_api_logs
):
    raw_sdk_message = "AccessDenied secret=request-123"
    object_key = "incoming/vendor/private-products.csv"
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: (_ for _ in ()).throw(S3ReadError(raw_sdk_message)),
    )

    response = client.post(ENDPOINT, json={**REQUEST, "object_key": object_key})

    assert response.status_code == 502
    events = [
        json.loads(record.message)
        for record in captured_api_logs.records
        if record.name == LOGGER_NAME
        and '"event":"s3_etl_source_failed"' in record.message
    ]
    assert events[-1]["event"] == "s3_etl_source_failed"
    assert events[-1]["error_code"] == "s3_read_failed"
    assert raw_sdk_message not in captured_api_logs.text
    assert object_key not in captured_api_logs.text


def test_s3_csv_validation_error_is_invalid_upload_without_web_metric(monkeypatch):
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: (_ for _ in ()).throw(CsvUploadValidationError("invalid key")),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "record_web_etl_run",
        lambda outcome: pytest.fail("adapter validation must not record Web ETL metric"),
    )

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_upload"


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (ETLProfileNotFoundError("unknown"), 400, "unsupported_profile"),
        (CsvUploadValidationError("invalid upload"), 400, "invalid_upload"),
        (ETLPipelineError("invalid pipeline"), 400, "invalid_upload"),
        (ETLLoadError("internal sha256 detail"), 500, "etl_load_failed"),
    ],
)
def test_s3_download_then_web_etl_errors_keep_existing_mapping_and_record_failure_metric(
    monkeypatch, error, expected_status, expected_code
):
    metrics: list[str] = []
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: S3SourceObject("products.csv", b"supplier,csv\n"),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )
    monkeypatch.setattr(etl_loads_route, "record_web_etl_run", metrics.append)

    response = client.post(ENDPOINT, json=REQUEST)

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert metrics == ["failed"]
    assert "sha256" not in response.text


def test_s3_success_records_same_created_metrics_as_multipart_endpoint(monkeypatch):
    run_metrics: list[str] = []
    row_metrics: list[dict[str, int | None]] = []
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: S3SourceObject("products.csv", b"supplier,csv\n"),
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


def test_s3_duplicate_success_records_only_duplicate_run_metric(monkeypatch):
    run_metrics: list[str] = []
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: S3SourceObject("products.csv", b"supplier,csv\n"),
    )
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *args, **kwargs: ETLWebRunOutcome(
            etl_load_run_id=42,
            created=False,
            profile_name="sample_fashion_vendor",
            profile_version="1",
            source_filename="products.csv",
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
            "12000",
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


def test_s3_endpoint_persists_staging_actor_and_reuses_duplicate_identity(
    postgres_api, monkeypatch
):
    session_factory = postgres_api
    marker = uuid4().hex
    username = f"s3_etl_actor_{marker[:12]}"
    source_filename = f"products_{marker}.csv"
    content = _supplier_csv(marker)

    with session_factory() as user_session:
        user = create_user(
            user_session,
            username=username,
            password="synthetic-s3-etl-password",
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
    # 허용 prefix를 설정해 두면 저장되는 locator에서 그 prefix가 실제로 제거되는지 확인할 수 있습니다.
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_PREFIX", "incoming/")
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: S3SourceObject(source_filename, content),
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

    try:
        with session_factory() as verify_session:
            runs = verify_session.scalars(
                select(ETLLoadRun).where(ETLLoadRun.source_filename == source_filename)
            ).all()
            assert len(runs) == 1
            run = runs[0]
            assert run.id == run_id
            assert run.actor_user_id == user.id
            assert run.actor_username == username
            # 최초 유입 경로가 s3로 기록되고, locator는 허용 prefix를 제거한 상대 key입니다.
            assert run.initial_source_type == "s3"
            assert run.initial_source_ref == "vendor/products.csv"
            # bucket 이름은 provenance에 필요하지 않으므로 저장하지 않습니다.
            assert "catalogguard-source" not in (run.initial_source_ref or "")
            assert not (run.initial_source_ref or "").startswith("s3://")
            products = verify_session.scalars(
                select(CatalogProductStaging).where(
                    CatalogProductStaging.etl_load_run_id == run_id
                )
            ).all()
            assert len(products) == 1
    finally:
        with session_factory() as cleanup:
            cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
            cleanup.execute(delete(User).where(User.username == username))
            cleanup.commit()
