"""Runtime activation API: RBAC, contract, and the effect on a new ETL run.

Phase 5B.1 of docs/etl_profile_lifecycle.md.

이 endpoint는 Profile Update API가 아닙니다. 바꾸는 것은 "이미 보존된 어떤 버전을
신규 실행에 쓸 것인가" 하나뿐이고, 프로필 정의는 여기서 손댈 수 없습니다(Policy A).
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.dependencies import get_current_user
from api.main import app
from config.database import get_optional_database_url
from core.security import create_access_token
from db.auth_service import create_user
from db.models import ETLLoadRun, ETLProfileActivation, User
from db.session import create_database_engine, create_session_factory, get_session


client = TestClient(app, raise_server_exceptions=False)

PROFILE_ID = "sample_marketplace_vendor_v1"
OTHER_PROFILE_ID = "sample_fashion_vendor_v1"
ACTIVATION_ENDPOINT = f"/api/v1/etl-profiles/{PROFILE_ID}/activation"
ETL_PROFILES_ENDPOINT = "/api/v1/etl-profiles"
WEB_ETL_ENDPOINT = "/api/v1/etl-loads"

SUPPLIER_CSV_HEADER = (
    "style_id,sku_code,title,category_code,label,regular_price,promo_price,"
    "tone,fit_size,available_qty,details,photo\n"
)


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


@pytest.fixture(name="session_factory")
def fixture_session_factory():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture(name="api")
def fixture_api(session_factory):
    """Wire the real DB into the app and hand out viewer/operator tokens."""

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    usernames: list[str] = []

    def make_token(role: str) -> str:
        username = f"activation_{role}_{uuid4().hex[:10]}"
        with session_factory() as session:
            create_user(
                session,
                username=username,
                password="synthetic-activation-password",
                role=role,
            )
        usernames.append(username)
        token, _ = create_access_token(subject=username, role=role)
        return token

    def clear_activations() -> None:
        with session_factory() as session:
            session.execute(delete(ETLProfileActivation))
            session.commit()

    clear_activations()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides.pop(get_current_user, None)
    try:
        yield make_token
    finally:
        app.dependency_overrides.clear()
        clear_activations()
        with session_factory() as session:
            session.execute(delete(User).where(User.username.in_(usernames)))
            session.commit()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---- RBAC --------------------------------------------------------------------


def test_anonymous_read_is_401(api):
    response = client.get(ACTIVATION_ENDPOINT)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_anonymous_write_is_401(api):
    response = client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_viewer_can_read(api):
    response = client.get(ACTIVATION_ENDPOINT, headers=_headers(api("viewer")))

    assert response.status_code == 200, response.text
    assert response.json()["profile_id"] == PROFILE_ID


def test_operator_can_read(api):
    response = client.get(ACTIVATION_ENDPOINT, headers=_headers(api("operator")))

    assert response.status_code == 200, response.text


def test_viewer_write_is_403_and_changes_nothing(api, session_factory):
    """조회는 되지만 변경은 운영 기능입니다."""
    response = client.put(
        ACTIVATION_ENDPOINT,
        json={"active_version": "1"},
        headers=_headers(api("viewer")),
    )

    assert response.status_code == 403
    with session_factory() as session:
        assert session.scalars(select(ETLProfileActivation)).all() == []


# ---- 조회 계약 ---------------------------------------------------------------


def test_read_without_an_override_reports_the_deployment_default(api):
    body = client.get(ACTIVATION_ENDPOINT, headers=_headers(api("viewer"))).json()

    assert body["deployment_active_version"] == "2"
    assert body["runtime_override_exists"] is False
    assert body["runtime_active_version"] is None
    assert body["effective_active_version"] == "2"
    assert body["is_active"] is True
    assert body["available_versions"] == ["1", "2"]
    assert body["actor_username"] is None
    assert body["updated_at"] is None


def test_read_of_an_unknown_profile_is_404(api):
    response = client.get(
        "/api/v1/etl-profiles/not_a_profile/activation",
        headers=_headers(api("viewer")),
    )

    assert response.status_code == 404


def test_a_deactivated_profile_is_still_readable_here(api):
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    response = client.get(ACTIVATION_ENDPOINT, headers=_headers(token))

    # 이 endpoint의 목적이 "지금 활성인가"를 묻는 것이므로, 비활성이라고 409를 내면
    # 운영자가 상태를 확인할 방법이 없어집니다.
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


# ---- 쓰기 계약 ---------------------------------------------------------------


def test_operator_can_select_an_archived_version(api):
    body = client.put(
        ACTIVATION_ENDPOINT,
        json={"active_version": "1"},
        headers=_headers(api("operator")),
    ).json()

    assert body["runtime_override_exists"] is True
    assert body["runtime_active_version"] == "1"
    assert body["effective_active_version"] == "1"
    # 배포 기본값은 덮인 것이지 지워진 것이 아닙니다.
    assert body["deployment_active_version"] == "2"


def test_null_version_deactivates(api):
    response = client.put(
        ACTIVATION_ENDPOINT,
        json={"active_version": None},
        headers=_headers(api("operator")),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["runtime_override_exists"] is True
    assert body["effective_active_version"] is None
    assert body["is_active"] is False


def test_omitting_active_version_deactivates_explicitly(api):
    """body가 {}이면 active_version=null과 같습니다. 기본값이 하나뿐이라 모호하지 않습니다."""
    response = client.put(
        ACTIVATION_ENDPOINT, json={}, headers=_headers(api("operator"))
    )

    assert response.status_code == 200, response.text
    assert response.json()["effective_active_version"] is None


@pytest.mark.parametrize("bad_version", ["999", "3", "v2", "   "])
def test_unknown_version_is_422_with_the_available_versions(api, bad_version):
    response = client.put(
        ACTIVATION_ENDPOINT,
        json={"active_version": bad_version},
        headers=_headers(api("operator")),
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "unknown_profile_version"
    assert detail["available_versions"] == ["1", "2"]


def test_write_to_an_unknown_profile_is_404(api):
    response = client.put(
        "/api/v1/etl-profiles/not_a_profile/activation",
        json={"active_version": "1"},
        headers=_headers(api("operator")),
    )

    assert response.status_code == 404


def test_write_is_idempotent(api):
    token = api("operator")
    first = client.put(
        ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token)
    ).json()
    second = client.put(
        ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token)
    ).json()

    assert first["effective_active_version"] == second["effective_active_version"] == "1"


# ---- Actor는 인증된 사용자에서만 온다 -----------------------------------------


def test_actor_is_taken_from_the_token_not_the_request_body(api, session_factory):
    """body로 다른 사람 이름을 주장할 수 없어야 합니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))

    with session_factory() as session:
        [row] = session.scalars(select(ETLProfileActivation)).all()

    assert row.actor_username is not None
    assert row.actor_username.startswith("activation_operator_")
    assert row.actor_user_id is not None


def test_unknown_body_fields_are_rejected_instead_of_silently_ignored(api):
    """이 endpoint를 Profile Update API로 오해한 요청이 조용히 성공하면 안 됩니다."""
    response = client.put(
        ACTIVATION_ENDPOINT,
        json={
            "active_version": "1",
            "actor_username": "someone_else",
            "source_columns": {"style_id": "product_group_id"},
        },
        headers=_headers(api("operator")),
    )

    assert response.status_code == 422


def test_activation_api_cannot_change_the_profile_definition(api):
    """활성 버전을 바꿔도 그 버전의 정의는 archive 그대로입니다(Policy A)."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))

    detail = client.get(
        f"{ETL_PROFILES_ENDPOINT}/{PROFILE_ID}", headers=_headers(token)
    ).json()

    assert detail["profile_version"] == "1"
    assert detail["profile_name"] == "sample_marketplace_vendor"
    assert detail["source_columns"]["style_id"] == ["product_group_id"]


# ---- 신규 실행 차단과 기존 계약 -----------------------------------------------


def _supplier_csv(marker: str) -> bytes:
    row = (
        f"GRP-{marker},SKU-{marker},상품 {marker},TOP,판매자,10000,9000,"
        "BLACK,M,5,설명,image.jpg\n"
    )
    return (SUPPLIER_CSV_HEADER + row).encode("utf-8")


def _post_web_etl(token: str, marker: str):
    return client.post(
        WEB_ETL_ENDPOINT,
        data={"profile_id": PROFILE_ID},
        files={"file": (f"vendor_{marker}.csv", _supplier_csv(marker), "text/csv")},
        headers=_headers(token),
    )


def test_runtime_deactivation_blocks_a_new_web_etl_run(api):
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    response = _post_web_etl(token, uuid4().hex[:10])

    # Phase 5A의 409 inactive_profile 계약을 그대로 유지합니다.
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "inactive_profile"


def test_reactivation_lets_a_new_run_succeed_again(api, session_factory):
    token = api("operator")
    marker = uuid4().hex[:10]
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))
    assert _post_web_etl(token, marker).status_code == 409

    client.put(ACTIVATION_ENDPOINT, json={"active_version": "2"}, headers=_headers(token))
    response = _post_web_etl(token, marker)

    assert response.status_code == 200, response.text
    run_id = response.json()["etl_load_run_id"]
    try:
        with session_factory() as session:
            run = session.get(ETLLoadRun, run_id)
            assert run.profile_version == "2"
    finally:
        with session_factory() as session:
            session.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
            session.commit()


def test_runtime_version_choice_is_recorded_on_the_batch(api, session_factory):
    """활성 버전을 v1으로 내리면 새 배치의 profile_version도 v1이어야 합니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))

    response = _post_web_etl(token, uuid4().hex[:10])

    assert response.status_code == 200, response.text
    run_id = response.json()["etl_load_run_id"]
    try:
        with session_factory() as session:
            assert session.get(ETLLoadRun, run_id).profile_version == "1"
    finally:
        with session_factory() as session:
            session.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
            session.commit()


def test_deactivated_profile_disappears_from_the_selectable_list(api):
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    items = client.get(ETL_PROFILES_ENDPOINT, headers=_headers(token)).json()["items"]

    ids = [item["id"] for item in items]
    assert PROFILE_ID not in ids
    assert OTHER_PROFILE_ID in ids


def test_deactivated_profile_detail_is_409_not_404(api):
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    response = client.get(
        f"{ETL_PROFILES_ENDPOINT}/{PROFILE_ID}", headers=_headers(token)
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "inactive_profile"


def test_historical_reads_stay_available_while_deactivated(api, session_factory):
    """Deactivate는 신규 실행만 막습니다. 과거 데이터 조회는 그대로여야 합니다."""
    token = api("operator")
    response = _post_web_etl(token, uuid4().hex[:10])
    assert response.status_code == 200, response.text
    run_id = response.json()["etl_load_run_id"]

    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    try:
        assert client.get(WEB_ETL_ENDPOINT, headers=_headers(token)).status_code == 200
        assert (
            client.get(f"{WEB_ETL_ENDPOINT}/{run_id}", headers=_headers(token)).status_code
            == 200
        )
        for path in (
            f"{WEB_ETL_ENDPOINT}/quality-summary",
            f"{WEB_ETL_ENDPOINT}/quality-trend",
            f"{WEB_ETL_ENDPOINT}/{run_id}/catalog-reconciliation",
        ):
            assert client.get(path, headers=_headers(token)).status_code == 200, path
    finally:
        with session_factory() as session:
            session.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
            session.commit()


# ---- S3 / HTTP feed도 같은 resolver를 쓴다 -------------------------------------


def test_runtime_deactivation_blocks_s3_before_any_source_read(api, monkeypatch):
    """S3 handler가 배포 기본값만 보면 외부를 먼저 읽고 나서야 막힙니다."""
    from api.routes import etl_loads as etl_loads_route

    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.setattr(
        etl_loads_route,
        "read_s3_csv_object",
        lambda key: pytest.fail("inactive profile must not reach the S3 source"),
    )

    response = client.post(
        f"{WEB_ETL_ENDPOINT}/s3",
        json={"profile_id": PROFILE_ID, "object_key": "incoming/vendor.csv"},
        headers=_headers(token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "inactive_profile"


def test_runtime_deactivation_blocks_http_feed_before_any_source_read(api, monkeypatch):
    from api.routes import etl_loads as etl_loads_route

    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    monkeypatch.setattr(
        etl_loads_route,
        "read_http_feed_csv",
        lambda: pytest.fail("inactive profile must not reach the HTTP feed"),
    )

    response = client.post(
        f"{WEB_ETL_ENDPOINT}/http",
        json={"profile_id": PROFILE_ID},
        headers=_headers(token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "inactive_profile"
