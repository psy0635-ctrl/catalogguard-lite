# 역할: Web ETL·Promotion·Rollback 실행 이력에 실행한 로그인 사용자(actor)가
# 클라이언트가 보낸 값이 아니라 실제 JWT current_user에서만 기록되는지 실제 PostgreSQL로 검증합니다.
from __future__ import annotations

import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from api.dependencies import get_current_user
from api.main import app
from config.database import get_optional_database_url
from core.security import create_access_token
from db.auth_service import create_user
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogProductStaging,
    CatalogPromotionRollback,
    CatalogPromotionRollbackChange,
    CatalogPromotionRun,
    ETLLoadRun,
    User,
)
from db.session import create_database_engine, create_session_factory, get_session


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


@pytest.fixture()
def postgres_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session, session_factory
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _cleanup_users(session_factory, usernames: list[str]) -> None:
    if not usernames:
        return
    with session_factory() as cleanup:
        cleanup.execute(delete(User).where(User.username.in_(usernames)))
        cleanup.commit()


@pytest.fixture()
def operator_account(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("actor_operator")
    user = create_user(session, username=username, password="synthetic-pw-actor-1", role="operator")
    token, _ = create_access_token(subject=username, role="operator")
    try:
        yield username, user.id, token
    finally:
        _cleanup_users(session_factory, [username])


@pytest.fixture()
def viewer_token(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("actor_viewer")
    create_user(session, username=username, password="synthetic-pw-actor-2", role="viewer")
    token, _ = create_access_token(subject=username, role="viewer")
    try:
        yield token
    finally:
        _cleanup_users(session_factory, [username])


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---- Web ETL --------------------------------------------------------------

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


def build_supplier_csv(rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FASHION_PROFILE_COLUMNS)
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def valid_row(sku: str) -> list[str]:
    return [sku, "테스트 상품", "TOP", "브랜드", "12000", "10000", "BLACK", "M", "3", "설명", "image.jpg"]


@pytest.fixture()
def etl_cleanup(postgres_session):
    _, session_factory = postgres_session
    marker = uuid4().hex
    yield marker, session_factory
    with session_factory() as cleanup:
        load_run_ids = select(ETLLoadRun.id).where(
            ETLLoadRun.profile_name.like(f"actor_audit_{marker}%")
        )
        promotion_run_ids = select(CatalogPromotionRun.id).where(
            CatalogPromotionRun.etl_load_run_id.in_(load_run_ids)
        )
        catalog_product_ids = select(CatalogProduct.id).where(
            or_(
                CatalogProduct.source_etl_load_run_id.in_(load_run_ids),
                CatalogProduct.supplier_key.like(f"actor_audit_{marker}%"),
            )
        )
        rollback_run_ids = select(CatalogPromotionRollback.id).where(
            CatalogPromotionRollback.target_promotion_run_id.in_(promotion_run_ids)
        )
        cleanup.execute(
            delete(CatalogPromotionRollbackChange).where(
                CatalogPromotionRollbackChange.rollback_run_id.in_(rollback_run_ids)
            )
        )
        cleanup.execute(
            delete(CatalogPromotionRollback).where(
                CatalogPromotionRollback.id.in_(rollback_run_ids)
            )
        )
        cleanup.execute(
            delete(CatalogProductChange).where(
                or_(
                    CatalogProductChange.promotion_run_id.in_(promotion_run_ids),
                    CatalogProductChange.catalog_product_id.in_(catalog_product_ids),
                )
            )
        )
        cleanup.execute(
            delete(CatalogPromotionRun).where(
                CatalogPromotionRun.etl_load_run_id.in_(load_run_ids)
            )
        )
        cleanup.execute(
            delete(CatalogProduct).where(
                or_(
                    CatalogProduct.source_etl_load_run_id.in_(load_run_ids),
                    CatalogProduct.supplier_key.like(f"actor_audit_{marker}%"),
                )
            )
        )
        cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id.in_(load_run_ids)))
        cleanup.commit()


def _make_load_run(profile_name: str, *, suffix: str = "") -> ETLLoadRun:
    return ETLLoadRun(
        source_filename=f"actor_audit{suffix}.csv",
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256=("a" if not suffix else "c") * 64,
        output_file_sha256=("b" if not suffix else "d") * 64,
        loaded_rows=1,
        total_rows=1,
        rejected_rows=0,
        error_counts={},
    )


def _make_staging(load_run_id: int, product_id: str) -> CatalogProductStaging:
    return CatalogProductStaging(
        etl_load_run_id=load_run_id,
        product_group_id=f"G-{product_id}",
        product_id=product_id,
        product_name=f"Product {product_id}",
        category="TOP",
        color="BLACK",
        size="M",
        stock=10,
        price=19900,
        sale_price=None,
        image_path=f"{product_id}.jpg",
        description=None,
        seller=None,
    )


def test_web_etl_actor_is_recorded_from_jwt_current_user(etl_cleanup, operator_account):
    marker, session_factory = etl_cleanup
    username, user_id, token = operator_account
    csv_bytes = build_supplier_csv([valid_row(f"SKU-{marker}")])

    response = client.post(
        "/api/v1/etl-loads",
        files={"file": (f"actor_audit_{marker}.csv", csv_bytes, "text/csv")},
        data={"profile_id": "sample_fashion_vendor_v1"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actor_username"] == username
    run_id = body["etl_load_run_id"]

    with session_factory() as verify:
        run = verify.get(ETLLoadRun, run_id)
        assert run.actor_user_id == user_id
        assert run.actor_username == username

    with session_factory() as cleanup:
        cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
        cleanup.commit()


def test_anonymous_web_etl_is_blocked_and_creates_no_run():
    csv_bytes = build_supplier_csv([valid_row("SKU-ANON")])
    database_calls = 0

    def fail_if_database_dependency_runs():
        nonlocal database_calls
        database_calls += 1
        raise AssertionError("database dependency must not run before authentication")

    app.dependency_overrides[get_session] = fail_if_database_dependency_runs

    response = client.post(
        "/api/v1/etl-loads",
        files={"file": ("actor_audit_anon.csv", csv_bytes, "text/csv")},
        data={"profile_id": "sample_fashion_vendor_v1"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert database_calls == 0


def test_viewer_web_etl_is_blocked_and_creates_no_run(etl_cleanup, viewer_token):
    marker, session_factory = etl_cleanup
    csv_bytes = build_supplier_csv([valid_row(f"SKU-{marker}")])
    profile_name_prefix = f"actor_audit_{marker}"

    response = client.post(
        "/api/v1/etl-loads",
        files={"file": (f"{profile_name_prefix}.csv", csv_bytes, "text/csv")},
        data={"profile_id": "sample_fashion_vendor_v1"},
        headers=_auth_headers(viewer_token),
    )

    assert response.status_code == 403
    with session_factory() as verify:
        existing = verify.scalar(
            select(ETLLoadRun).where(ETLLoadRun.source_filename == f"{profile_name_prefix}.csv")
        )
        assert existing is None


def test_actor_cannot_be_forged_via_request_body(etl_cleanup, operator_account):
    marker, session_factory = etl_cleanup
    username, user_id, token = operator_account
    csv_bytes = build_supplier_csv([valid_row(f"SKU-{marker}")])

    response = client.post(
        "/api/v1/etl-loads",
        files={"file": (f"actor_audit_{marker}.csv", csv_bytes, "text/csv")},
        # profile_id 외에 actor_username을 함께 보내도 서버는 이 값을 받는 필드가 없으므로 무시해야 합니다.
        data={"profile_id": "sample_fashion_vendor_v1", "actor_username": "someone_else"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actor_username"] == username
    assert body["actor_username"] != "someone_else"
    run_id = body["etl_load_run_id"]

    with session_factory() as verify:
        run = verify.get(ETLLoadRun, run_id)
        assert run.actor_user_id == user_id
        assert run.actor_username == username

    with session_factory() as cleanup:
        cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
        cleanup.commit()


# ---- Promotion --------------------------------------------------------------


def test_promotion_actor_is_recorded_from_jwt_current_user(etl_cleanup, operator_account):
    marker, session_factory = etl_cleanup
    username, user_id, token = operator_account
    profile_name = f"actor_audit_{marker}"

    with session_factory() as setup:
        load_run = _make_load_run(profile_name)
        setup.add(load_run)
        setup.flush()
        setup.add(_make_staging(load_run.id, f"P-{marker}"))
        setup.commit()
        load_run_id = load_run.id

    preview_response = client.post(
        f"/api/v1/etl-loads/{load_run_id}/promotion-preview",
        headers=_auth_headers(token),
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_hash = preview_response.json()["preview_hash"]

    response = client.post(
        f"/api/v1/etl-loads/{load_run_id}/promotions",
        json={"confirmation": True, "expected_preview_hash": preview_hash},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actor_username"] == username
    promotion_run_id = body["promotion_run_id"]

    with session_factory() as verify:
        run = verify.get(CatalogPromotionRun, promotion_run_id)
        assert run.status == "succeeded"
        assert run.actor_user_id == user_id
        assert run.actor_username == username


def test_viewer_promotion_is_blocked_and_creates_no_run(etl_cleanup, viewer_token, operator_account):
    marker, session_factory = etl_cleanup
    profile_name = f"actor_audit_{marker}"
    _, _, operator_token_value = operator_account

    with session_factory() as setup:
        load_run = _make_load_run(profile_name)
        setup.add(load_run)
        setup.flush()
        setup.add(_make_staging(load_run.id, f"P-{marker}"))
        setup.commit()
        load_run_id = load_run.id

    # Preview는 viewer도 조회할 수 있어야 합니다(운영 데이터를 변경하지 않으므로).
    preview_response = client.post(
        f"/api/v1/etl-loads/{load_run_id}/promotion-preview",
        headers=_auth_headers(viewer_token),
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_hash = preview_response.json()["preview_hash"]

    response = client.post(
        f"/api/v1/etl-loads/{load_run_id}/promotions",
        json={"confirmation": True, "expected_preview_hash": preview_hash},
        headers=_auth_headers(viewer_token),
    )

    assert response.status_code == 403
    with session_factory() as verify:
        existing = verify.scalar(
            select(CatalogPromotionRun).where(
                CatalogPromotionRun.etl_load_run_id == load_run_id
            )
        )
        assert existing is None


# ---- Rollback --------------------------------------------------------------


def _promote_via_http(session_factory, profile_name: str, product_id: str, token: str) -> int:
    with session_factory() as setup:
        load_run = _make_load_run(profile_name)
        setup.add(load_run)
        setup.flush()
        setup.add(_make_staging(load_run.id, product_id))
        setup.commit()
        load_run_id = load_run.id

    preview_response = client.post(
        f"/api/v1/etl-loads/{load_run_id}/promotion-preview",
        headers=_auth_headers(token),
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_hash = preview_response.json()["preview_hash"]

    response = client.post(
        f"/api/v1/etl-loads/{load_run_id}/promotions",
        json={"confirmation": True, "expected_preview_hash": preview_hash},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["promotion_run_id"]


def test_rollback_actor_is_recorded_from_jwt_current_user(etl_cleanup, operator_account):
    marker, session_factory = etl_cleanup
    username, user_id, token = operator_account
    profile_name = f"actor_audit_{marker}"
    promotion_run_id = _promote_via_http(session_factory, profile_name, f"P-{marker}", token)

    preview_response = client.post(
        f"/api/v1/catalog-promotions/{promotion_run_id}/rollback-preview",
        headers=_auth_headers(token),
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_hash = preview_response.json()["preview_hash"]

    response = client.post(
        f"/api/v1/catalog-promotions/{promotion_run_id}/rollback",
        json={"confirmation": True, "expected_preview_hash": preview_hash},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actor_username"] == username
    rollback_run_id = body["rollback_run_id"]

    with session_factory() as verify:
        run = verify.get(CatalogPromotionRollback, rollback_run_id)
        assert run.status == "succeeded"
        assert run.actor_user_id == user_id
        assert run.actor_username == username


def test_viewer_rollback_is_blocked_and_creates_no_run(etl_cleanup, viewer_token, operator_account):
    marker, session_factory = etl_cleanup
    profile_name = f"actor_audit_{marker}"
    _, _, operator_token_value = operator_account
    promotion_run_id = _promote_via_http(
        session_factory, profile_name, f"P-{marker}", operator_token_value
    )

    preview_response = client.post(
        f"/api/v1/catalog-promotions/{promotion_run_id}/rollback-preview",
        headers=_auth_headers(viewer_token),
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_hash = preview_response.json()["preview_hash"]

    response = client.post(
        f"/api/v1/catalog-promotions/{promotion_run_id}/rollback",
        json={"confirmation": True, "expected_preview_hash": preview_hash},
        headers=_auth_headers(viewer_token),
    )

    assert response.status_code == 403
    with session_factory() as verify:
        existing = verify.scalar(
            select(CatalogPromotionRollback).where(
                CatalogPromotionRollback.target_promotion_run_id == promotion_run_id
            )
        )
        assert existing is None


# ---- Failure atomicity -------------------------------------------------------


def test_promotion_failure_records_failed_status_not_false_success(
    etl_cleanup, operator_account, monkeypatch
):
    from db import catalog_promotion_service

    marker, session_factory = etl_cleanup
    username, user_id, token = operator_account
    profile_name = f"actor_audit_{marker}"

    with session_factory() as setup:
        load_run = _make_load_run(profile_name)
        setup.add(load_run)
        setup.flush()
        setup.add(_make_staging(load_run.id, f"P-{marker}"))
        setup.commit()
        load_run_id = load_run.id

    preview_response = client.post(
        f"/api/v1/etl-loads/{load_run_id}/promotion-preview",
        headers=_auth_headers(token),
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_hash = preview_response.json()["preview_hash"]

    def failing_insert_catalog_product(*args, **kwargs):
        raise RuntimeError("forced promotion insert failure for actor audit test")

    monkeypatch.setattr(
        catalog_promotion_service, "_insert_catalog_product", failing_insert_catalog_product
    )

    response = client.post(
        f"/api/v1/etl-loads/{load_run_id}/promotions",
        json={"confirmation": True, "expected_preview_hash": preview_hash},
        headers=_auth_headers(token),
    )

    assert response.status_code == 500

    with session_factory() as verify:
        runs = verify.scalars(
            select(CatalogPromotionRun).where(
                CatalogPromotionRun.etl_load_run_id == load_run_id
            )
        ).all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].actor_user_id == user_id
        assert runs[0].actor_username == username
        # 실패했으므로 운영 상품이 실제로 생성되지 않아야 합니다.
        products = verify.scalars(
            select(CatalogProduct).where(CatalogProduct.supplier_key == profile_name)
        ).all()
        assert products == []


# ---- Legacy row (no actor) --------------------------------------------------


def test_legacy_run_without_actor_is_returned_safely(etl_cleanup, viewer_token):
    marker, session_factory = etl_cleanup
    profile_name = f"actor_audit_{marker}"

    with session_factory() as setup:
        load_run = _make_load_run(profile_name)
        # migration 이전 row를 흉내 내기 위해 actor를 명시적으로 채우지 않습니다(NULL로 남음).
        setup.add(load_run)
        setup.commit()
        load_run_id = load_run.id

    response = client.get(
        f"/api/v1/etl-loads/{load_run_id}",
        headers=_auth_headers(viewer_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["actor_username"] is None
