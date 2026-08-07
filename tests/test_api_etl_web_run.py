import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.dependencies import get_current_user
from api.main import app
from api.routes import etl_loads as etl_loads_route
from conftest import override_current_user
from config.database import get_optional_database_url
from config.settings import MAX_UPLOAD_SIZE_BYTES
from core.security import create_access_token
from core.upload_validator import CsvUploadValidationError
from db.auth_service import create_user
from db.models import CatalogProductStaging, ETLLoadRun, User
from db.session import create_database_engine, create_session_factory, get_session
from etl.db_loader import ETLLoadError
from etl.pipeline import ETLPipelineError
from etl.profile_loader import ETLProfileNotFoundError
from etl.web_service import ETLWebRunOutcome


client = TestClient(app)
ENDPOINT = "/api/v1/etl-loads"


def _files(*, content: bytes = b"header\nvalue\n", filename: str = "vendor.csv"):
    return {"file": (filename, content, "text/csv")}


@pytest.fixture(autouse=True)
def clear_overrides():
    override_current_user(role="operator")
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


def test_success_returns_etl_web_run_contract(monkeypatch):
    def fake_run_web_etl(
        session,
        *,
        profile_id,
        source_filename,
        input_bytes,
        actor_user_id=None,
        actor_username=None,
    ):
        assert profile_id == "sample_fashion_vendor_v1"
        assert source_filename == "vendor.csv"
        assert input_bytes == b"header\nvalue\n"
        return ETLWebRunOutcome(
            etl_load_run_id=42,
            created=True,
            profile_name="sample_fashion_vendor",
            profile_version="1",
            source_filename="vendor.csv",
            total_rows=2,
            loaded_rows=2,
            rejected_rows=0,
            error_counts={},
            actor_username=actor_username,
        )

    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)

    response = client.post(
        ENDPOINT,
        files=_files(),
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "etl_load_run_id": 42,
        "created": True,
        "profile_name": "sample_fashion_vendor",
        "profile_version": "1",
        "source_filename": "vendor.csv",
        "total_rows": 2,
        "loaded_rows": 2,
        "rejected_rows": 0,
        "error_counts": {},
        "actor_username": "operator_user",
    }


def test_unsupported_profile_returns_safe_400_without_leaking_paths(monkeypatch):
    def fake_run_web_etl(session, **kwargs):
        raise ETLProfileNotFoundError("Unknown ETL profile: ../../etc/passwd")

    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)

    response = client.post(
        ENDPOINT,
        files=_files(),
        data={"profile_id": "../../etc/passwd"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "unsupported_profile"
    assert "/" not in detail["message"] and "\\" not in detail["message"]


def test_empty_upload_returns_safe_400(monkeypatch):
    def fake_run_web_etl(session, **kwargs):
        raise CsvUploadValidationError("업로드한 파일이 비어 있습니다.")

    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)

    response = client.post(
        ENDPOINT,
        files=_files(content=b""),
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_upload"


def test_pipeline_failure_returns_safe_400_without_traceback(monkeypatch):
    def fake_run_web_etl(session, **kwargs):
        raise ETLPipelineError("Input CSV is missing required source columns")

    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)

    response = client.post(
        ENDPOINT,
        files=_files(),
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["code"] == "invalid_upload"
    assert "Traceback" not in response.text


def test_staging_load_failure_returns_safe_500_without_internals(monkeypatch):
    def fake_run_web_etl(session, **kwargs):
        raise ETLLoadError("표준 CSV와 요약 JSON의 output_file_sha256가 일치하지 않습니다")

    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_run_web_etl)

    response = client.post(
        ENDPOINT,
        files=_files(),
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "etl_load_failed"
    assert "sha256" not in detail["message"]


def test_missing_profile_id_returns_422_without_calling_service(monkeypatch):
    calls = []
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *a, **k: calls.append(1),
    )

    response = client.post(ENDPOINT, files=_files())

    assert response.status_code == 422
    assert calls == []


def test_missing_file_returns_422_without_calling_service(monkeypatch):
    calls = []
    app.dependency_overrides[get_session] = lambda: iter([object()])
    monkeypatch.setattr(
        etl_loads_route,
        "run_web_etl",
        lambda *a, **k: calls.append(1),
    )

    response = client.post(ENDPOINT, data={"profile_id": "sample_fashion_vendor_v1"})

    assert response.status_code == 422
    assert calls == []


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
        pytest.skip(
            "TEST_DATABASE_URL이 설정되지 않아 PostgreSQL API 통합 테스트를 건너뜁니다."
        )

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        yield session_factory
    finally:
        engine.dispose()


def test_real_endpoint_persists_batch_and_staging_products_in_postgresql(postgres_api):
    # 실제 users.id를 참조하는 actor_user_id FK가 있으므로, 이 테스트만은 다른 테스트의
    # 고정 id=1 가짜 current_user override 대신 실제 PostgreSQL에 존재하는 operator
    # 계정과 실제 JWT로 로그인해 actor가 정확히 기록되는지 확인합니다.
    session_factory = postgres_api
    marker = uuid4().hex
    csv_bytes = build_supplier_csv([valid_row(f"SKU-{marker}-1"), valid_row(f"SKU-{marker}-2")])
    source_filename = f"vendor_{marker}.csv"
    username = f"etl_actor_{marker[:12]}"

    with session_factory() as user_session:
        create_user(user_session, username=username, password="synthetic-pw-etl-actor", role="operator")
    token, _ = create_access_token(subject=username, role="operator")

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post(
            ENDPOINT,
            files=_files(content=csv_bytes, filename=source_filename),
            data={"profile_id": "sample_fashion_vendor_v1"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    run_id = body["etl_load_run_id"]
    try:
        assert body["created"] is True
        assert body["loaded_rows"] == 2
        assert body["rejected_rows"] == 0
        assert body["source_filename"] == source_filename
        assert body["actor_username"] == username

        with session_factory() as verify_session:
            run = verify_session.get(ETLLoadRun, run_id)
            assert run is not None
            assert run.actor_username == username
            assert run.actor_user_id is not None
            products = verify_session.scalars(
                select(CatalogProductStaging).where(
                    CatalogProductStaging.etl_load_run_id == run_id
                )
            ).all()
            assert len(products) == 2
    finally:
        with session_factory() as cleanup:
            cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
            cleanup.execute(delete(User).where(User.username == username))
            cleanup.commit()


def test_real_endpoint_rejects_unknown_profile_without_touching_database(postgres_api):
    session_factory = postgres_api
    marker = uuid4().hex
    csv_bytes = build_supplier_csv([valid_row(f"SKU-{marker}-1")])

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    try:
        response = client.post(
            ENDPOINT,
            files=_files(content=csv_bytes, filename="vendor.csv"),
            data={"profile_id": "unknown_profile"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_profile"
    with session_factory() as verify_session:
        count = verify_session.scalar(
            select(ETLLoadRun.id).where(ETLLoadRun.source_filename == "vendor.csv")
        )
        assert count is None


def test_real_endpoint_rejects_oversized_upload_with_no_pipeline_run_and_no_db_change(
    postgres_api,
):
    session_factory = postgres_api

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    before_count = 0
    with session_factory() as before_session:
        before_count = before_session.scalar(select(ETLLoadRun.id).limit(1))

    oversized_bytes = b"a,b\n" + b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)
    app.dependency_overrides[get_session] = override_session
    try:
        response = client.post(
            ENDPOINT,
            files=_files(content=oversized_bytes, filename="vendor.csv"),
            data={"profile_id": "sample_fashion_vendor_v1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_upload"
    with session_factory() as after_session:
        after_count = after_session.scalar(select(ETLLoadRun.id).limit(1))
        assert after_count == before_count
