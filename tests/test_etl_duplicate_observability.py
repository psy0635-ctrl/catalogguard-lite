# 역할: duplicate ETL 요청(created=false)이 최초 source와 이번 요청 source를 함께 남기는지 검증합니다.
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.dependencies import get_current_user
from api.main import app
from api.routes import etl_loads as etl_loads_route
from config.database import get_optional_database_url
from config.logging import LOGGER_NAME
from conftest import override_current_user
from core.security import create_access_token
from db.auth_service import create_user
from db.models import ETLLoadRun, User
from db.session import create_database_engine, create_session_factory, get_session
from etl.http_source import HTTPFeedSourceObject
from etl.s3_source import S3SourceObject
from etl.web_service import ETLWebRunOutcome


client = TestClient(app, raise_server_exceptions=False)

DUPLICATE_EVENT = "etl_duplicate_ingestion"
COMPLETED_EVENT = "http_request_completed"
UPLOAD_ENDPOINT = "/api/v1/etl-loads"
S3_ENDPOINT = "/api/v1/etl-loads/s3"
HTTP_ENDPOINT = "/api/v1/etl-loads/http"
PROFILE_ID = "sample_fashion_vendor_v1"
EXISTING_RUN_ID = 42

# 로그에 새어 나가면 안 되는 값들입니다. 고정 문자열이라 테스트가 결정적으로 동작하고,
# 랜덤 UUID를 상품/사용자 문자열에 넣지 않아 개인정보 탐지 검사와도 얽히지 않습니다.
SECRET_FEED_URL = "https://supplier.example.invalid/catalog.csv?token=DO_NOT_LOG_THIS"
SECRET_S3_BUCKET = "do-not-log-this-bucket"
SOURCE_FILENAME = "do_not_log_this_supplier_file.csv"
INITIAL_SOURCE_REF = "do_not_log_this_source_ref.csv"
ACTOR_USERNAME = "do_not_log_this_actor"
INPUT_SHA256 = "a" * 64
S3_OBJECT_KEY = "incoming/vendor/do_not_log_this_object_key.csv"
SUPPLIER_CSV = b"vendor_sku,item_name\nSKU-FIXED-A,Product A\n"

LEAKED_VALUES = (
    "DO_NOT_LOG_THIS",
    SECRET_FEED_URL,
    SECRET_S3_BUCKET,
    SOURCE_FILENAME,
    INITIAL_SOURCE_REF,
    ACTOR_USERNAME,
    INPUT_SHA256,
    S3_OBJECT_KEY,
)


@pytest.fixture(autouse=True)
def operator_and_fake_session():
    override_current_user(role="operator")
    app.dependency_overrides[get_session] = lambda: iter([object()])
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def source_configuration(monkeypatch):
    """실제 source 설정을 채워 둡니다.

    route가 이 값들을 로그에 흘리면 secret 검증 테스트가 즉시 실패합니다.
    """
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_URL", SECRET_FEED_URL)
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", SECRET_S3_BUCKET)
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


@pytest.fixture()
def captured_api_logs(caplog):
    logger = logging.getLogger(LOGGER_NAME)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    logger.addHandler(caplog.handler)
    # alembic env.py의 fileConfig()는 기본값이 disable_existing_loggers=True라,
    # 같은 프로세스에서 alembic을 실행한 테스트(tests/test_etl_db_loader.py)가 먼저 돌면
    # catalogguard.api logger가 disabled 상태로 남습니다. 이 파일은 수집 순서상 그 뒤라
    # 캡처 전에 되돌려 둡니다. 원래 값은 teardown에서 복원해 다른 테스트가 보는 상태를
    # 바꾸지 않습니다. 이 전역 오염 자체는 이번 변경과 무관한 기존 문제입니다.
    was_disabled = logger.disabled
    logger.disabled = False
    try:
        yield caplog
    finally:
        logger.disabled = was_disabled
        logger.removeHandler(caplog.handler)


def structured_events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
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


def duplicate_events(caplog) -> list[dict[str, object]]:
    return [
        event for event in structured_events(caplog) if event["event"] == DUPLICATE_EVENT
    ]


def application_log_text(caplog) -> str:
    return "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER_NAME
    )


def _outcome(*, created: bool, initial_source_type: str) -> ETLWebRunOutcome:
    """run_web_etl()이 돌려주는 결과입니다.

    duplicate일 때 initial_source_type은 이번 요청 source가 아니라 DB에 저장된
    최초 source라는 점이 이 테스트들의 핵심 전제입니다.
    """
    return ETLWebRunOutcome(
        etl_load_run_id=EXISTING_RUN_ID,
        created=created,
        profile_name="sample_fashion_vendor",
        profile_version="1",
        source_filename=SOURCE_FILENAME,
        total_rows=2,
        loaded_rows=2,
        rejected_rows=0,
        error_counts={},
        actor_username=ACTOR_USERNAME,
        initial_source_type=initial_source_type,
        initial_source_ref=INITIAL_SOURCE_REF,
    )


def post_etl_request(
    monkeypatch,
    *,
    request_source_type: str,
    initial_source_type: str,
    created: bool = False,
):
    """request_source_type 경로로 ETL을 호출하고, 저장된 최초 source를 initial_source_type으로 흉내 냅니다."""
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *args, **kwargs: _outcome(
            created=created,
            initial_source_type=initial_source_type,
        ),
    )

    if request_source_type == "upload":
        return client.post(
            UPLOAD_ENDPOINT,
            files={"file": (SOURCE_FILENAME, SUPPLIER_CSV, "text/csv")},
            data={"profile_id": PROFILE_ID},
        )

    if request_source_type == "s3":
        monkeypatch.setattr(
            etl_loads_route,
            "read_s3_csv_object",
            lambda key: S3SourceObject(SOURCE_FILENAME, SUPPLIER_CSV),
        )
        return client.post(
            S3_ENDPOINT,
            json={"profile_id": PROFILE_ID, "object_key": S3_OBJECT_KEY},
        )

    if request_source_type == "http_feed":
        monkeypatch.setattr(
            etl_loads_route,
            "read_http_feed_csv",
            lambda: HTTPFeedSourceObject(SOURCE_FILENAME, SUPPLIER_CSV),
        )
        return client.post(HTTP_ENDPOINT, json={"profile_id": PROFILE_ID})

    raise AssertionError(f"unsupported request source: {request_source_type}")


@pytest.mark.parametrize(
    ("initial_source_type", "request_source_type", "expected_same_source"),
    [
        ("upload", "upload", "true"),
        ("upload", "http_feed", "false"),
        ("http_feed", "upload", "false"),
        ("s3", "http_feed", "false"),
        ("s3", "s3", "true"),
    ],
    ids=[
        "upload_then_upload",
        "upload_then_http_feed",
        "http_feed_then_upload",
        "s3_then_http_feed",
        "s3_then_s3",
    ],
)
def test_duplicate_request_logs_initial_and_request_source(
    captured_api_logs,
    monkeypatch,
    initial_source_type: str,
    request_source_type: str,
    expected_same_source: str,
) -> None:
    response = post_etl_request(
        monkeypatch,
        request_source_type=request_source_type,
        initial_source_type=initial_source_type,
        created=False,
    )

    assert response.status_code == 200, response.text
    assert response.json()["created"] is False

    events = duplicate_events(captured_api_logs)
    assert len(events) == 1
    event = events[0]
    assert event["level"] == "INFO"
    assert event["etl_load_run_id"] == EXISTING_RUN_ID
    assert event["initial_source_type"] == initial_source_type
    assert event["request_source_type"] == request_source_type
    assert event["same_source"] == expected_same_source
    assert event["request_id"]


def test_duplicate_event_reports_stored_initial_source_not_the_request_source(
    captured_api_logs,
    monkeypatch,
) -> None:
    """관측을 추가해도 배치의 최초 source 의미는 바뀌지 않아야 합니다."""
    response = post_etl_request(
        monkeypatch,
        request_source_type="http_feed",
        initial_source_type="upload",
        created=False,
    )

    event = duplicate_events(captured_api_logs)[0]
    # 응답과 로그 모두 저장된 최초 source를 그대로 보고하고, 이번 요청 source로 덮어쓰지 않습니다.
    assert response.json()["initial_source_type"] == "upload"
    assert event["initial_source_type"] == "upload"
    assert event["request_source_type"] == "http_feed"


@pytest.mark.parametrize(
    "request_source_type",
    ["upload", "s3", "http_feed"],
)
def test_newly_created_run_does_not_log_a_duplicate_event(
    captured_api_logs,
    monkeypatch,
    request_source_type: str,
) -> None:
    response = post_etl_request(
        monkeypatch,
        request_source_type=request_source_type,
        initial_source_type=request_source_type,
        created=True,
    )

    assert response.status_code == 200, response.text
    assert response.json()["created"] is True
    assert duplicate_events(captured_api_logs) == []


def test_duplicate_event_reuses_the_request_id_of_the_same_request(
    captured_api_logs,
    monkeypatch,
) -> None:
    """duplicate 이벤트와 기존 요청 로그가 같은 correlation key를 갖는지 확인합니다."""
    response = post_etl_request(
        monkeypatch,
        request_source_type="http_feed",
        initial_source_type="upload",
        created=False,
    )

    request_id = response.headers["X-Request-ID"]
    duplicate_event = duplicate_events(captured_api_logs)[0]
    completed_events = [
        event
        for event in structured_events(captured_api_logs)
        if event["event"] == COMPLETED_EVENT and event["request_id"] == request_id
    ]

    assert request_id
    assert duplicate_event["request_id"] == request_id
    assert len(completed_events) == 1
    assert completed_events[0]["path"] == HTTP_ENDPOINT


@pytest.mark.parametrize(
    ("initial_source_type", "request_source_type"),
    [
        ("upload", "upload"),
        ("upload", "http_feed"),
        ("http_feed", "upload"),
        ("s3", "http_feed"),
    ],
)
def test_duplicate_event_never_records_locators_secrets_or_actor(
    captured_api_logs,
    monkeypatch,
    initial_source_type: str,
    request_source_type: str,
) -> None:
    post_etl_request(
        monkeypatch,
        request_source_type=request_source_type,
        initial_source_type=initial_source_type,
        created=False,
    )

    event = duplicate_events(captured_api_logs)[0]
    logged_text = application_log_text(captured_api_logs)

    assert set(event) == {
        "timestamp",
        "level",
        "event",
        "etl_load_run_id",
        "initial_source_type",
        "request_source_type",
        "same_source",
        "request_id",
    }
    for secret in LEAKED_VALUES:
        assert secret not in json.dumps(event)
        assert secret not in logged_text


# 아래는 실제 PostgreSQL dedup을 거치는 end-to-end 검증입니다. 위 테스트들은 route 계층만
# 확인하므로, 저장된 최초 source가 정말로 로그에 실리는지는 여기서 확인합니다.
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


def _supplier_csv(product_name: str) -> bytes:
    """결정적인 공급사 CSV입니다.

    랜덤 UUID를 넣지 않아 SHA가 매 실행 고정되고, 사람이 읽는 상품명에 무작위 숫자열이
    섞이지 않습니다. 서로 다른 SHA가 필요하면 product_name만 바꿉니다.
    """
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FASHION_PROFILE_COLUMNS)
    writer.writerow(
        [
            "SKU-DUPLICATE-OBSERVABILITY",
            product_name,
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


PRODUCT_A_CSV = _supplier_csv("Product A")
PRODUCT_B_CSV = _supplier_csv("Product B")
E2E_FILENAME = "duplicate_observability_supplier.csv"
# 고정 이름입니다. 랜덤 UUID를 사용자 문자열에 넣지 않고, fixture가 매번 지우고 다시 만들어
# 반복 실행에도 결정적으로 동작합니다.
E2E_USERNAME = "duplicate_observability_operator"


@pytest.fixture()
def postgres_api():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)

    def remove_fixture_rows() -> None:
        # CSV가 결정적이라 SHA도 고정입니다. 이전 실행이 남긴 배치를 지워야
        # 첫 요청이 실제로 created=true가 됩니다.
        hashes = [
            hashlib.sha256(content).hexdigest()
            for content in (PRODUCT_A_CSV, PRODUCT_B_CSV)
        ]
        with session_factory() as session:
            session.execute(
                delete(ETLLoadRun).where(ETLLoadRun.input_file_sha256.in_(hashes))
            )
            session.execute(delete(User).where(User.username == E2E_USERNAME))
            session.commit()

    remove_fixture_rows()
    # actor_user_id는 users를 참조하는 FK라, 실제 로그인 사용자로 호출해야 합니다.
    with session_factory() as session:
        create_user(
            session,
            username=E2E_USERNAME,
            password="synthetic-duplicate-observability-password",
            role="operator",
        )
    token, _ = create_access_token(subject=E2E_USERNAME, role="operator")

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    # 이 테스트들만 실제 인증을 씁니다. 위쪽 autouse override는 걷어냅니다.
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides.pop(get_current_user, None)
    try:
        yield session_factory, {"Authorization": f"Bearer {token}"}
    finally:
        app.dependency_overrides.clear()
        remove_fixture_rows()
        engine.dispose()


def test_real_dedup_logs_the_stored_initial_source_for_a_cross_source_duplicate(
    postgres_api,
    captured_api_logs,
    monkeypatch,
) -> None:
    """HTTP feed로 처음 들어온 배치를 같은 bytes로 업로드하면 두 source가 모두 남아야 합니다."""
    session_factory, auth_headers = postgres_api
    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: HTTPFeedSourceObject(E2E_FILENAME, PRODUCT_A_CSV),
    )

    first = client.post(
        HTTP_ENDPOINT,
        json={"profile_id": PROFILE_ID},
        headers=auth_headers,
    )
    second = client.post(
        UPLOAD_ENDPOINT,
        files={"file": (E2E_FILENAME, PRODUCT_A_CSV, "text/csv")},
        data={"profile_id": PROFILE_ID},
        headers=auth_headers,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    run_id = first.json()["etl_load_run_id"]
    assert second.json()["etl_load_run_id"] == run_id

    events = duplicate_events(captured_api_logs)
    assert len(events) == 1
    event = events[0]
    assert event["etl_load_run_id"] == run_id
    assert event["initial_source_type"] == "http_feed"
    assert event["request_source_type"] == "upload"
    assert event["same_source"] == "false"
    assert event["request_id"] == second.headers["X-Request-ID"]

    # lineage 불변식: 관측을 추가해도 DB의 최초 source는 그대로여야 합니다.
    with session_factory() as verify_session:
        stored = verify_session.scalar(
            select(ETLLoadRun).where(ETLLoadRun.id == run_id)
        )
        assert stored.initial_source_type == "http_feed"


def test_real_new_batch_does_not_log_a_duplicate_event(
    postgres_api,
    captured_api_logs,
) -> None:
    """다른 bytes는 신규 적재이므로 duplicate 이벤트가 없어야 합니다."""
    _session_factory, auth_headers = postgres_api

    first = client.post(
        UPLOAD_ENDPOINT,
        files={"file": (E2E_FILENAME, PRODUCT_A_CSV, "text/csv")},
        data={"profile_id": PROFILE_ID},
        headers=auth_headers,
    )
    second = client.post(
        UPLOAD_ENDPOINT,
        files={"file": (E2E_FILENAME, PRODUCT_B_CSV, "text/csv")},
        data={"profile_id": PROFILE_ID},
        headers=auth_headers,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["created"] is True
    assert second.json()["created"] is True
    assert first.json()["etl_load_run_id"] != second.json()["etl_load_run_id"]
    assert duplicate_events(captured_api_logs) == []
