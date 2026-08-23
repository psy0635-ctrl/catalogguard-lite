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
from db.models import (
    ETLLoadRun,
    ETLProfileActivation,
    ETLProfileActivationEvent,
    User,
)
from db.session import create_database_engine, create_session_factory, get_session


client = TestClient(app, raise_server_exceptions=False)

PROFILE_ID = "sample_marketplace_vendor_v1"
OTHER_PROFILE_ID = "sample_fashion_vendor_v1"
ACTIVATION_ENDPOINT = f"/api/v1/etl-profiles/{PROFILE_ID}/activation"
ACTIVATION_HISTORY_ENDPOINT = f"{ACTIVATION_ENDPOINT}/history"
OTHER_ACTIVATION_ENDPOINT = (
    f"/api/v1/etl-profiles/{OTHER_PROFILE_ID}/activation"
)
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
        # history도 함께 비웁니다. 남겨 두면 다음 테스트가 이전 테스트의 운영 명령을
        # 자기 이력으로 보게 됩니다.
        with session_factory() as session:
            session.execute(delete(ETLProfileActivationEvent))
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


# ---- include_inactive: 관리 화면이 비활성 프로필을 다시 고를 수 있어야 한다 --------


def test_profile_list_default_hides_a_deactivated_profile(api):
    """기본값은 기존 계약 그대로입니다. 실행 selector는 활성 프로필만 봅니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    ids = [
        item["id"]
        for item in client.get(ETL_PROFILES_ENDPOINT, headers=_headers(token)).json()["items"]
    ]

    assert PROFILE_ID not in ids
    assert OTHER_PROFILE_ID in ids


def test_include_inactive_keeps_a_deactivated_profile_selectable(api):
    """이것이 Phase 5B.2의 핵심 회귀입니다.

    비활성 프로필이 관리 목록에서도 사라지면 한 번 내린 프로필을 다시 고를 수 없어
    영영 되살릴 수 없게 됩니다.
    """
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    response = client.get(
        ETL_PROFILES_ENDPOINT,
        params={"include_inactive": "true"},
        headers=_headers(token),
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = [item["id"] for item in items]
    assert PROFILE_ID in ids
    assert OTHER_PROFILE_ID in ids
    # 응답 shape은 기존과 같습니다. 상태는 activation endpoint로 따로 봅니다.
    assert all(sorted(item) == ["display_name", "id"] for item in items)


def test_include_inactive_false_matches_the_default(api):
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    default = client.get(ETL_PROFILES_ENDPOINT, headers=_headers(token)).json()
    explicit_false = client.get(
        ETL_PROFILES_ENDPOINT,
        params={"include_inactive": "false"},
        headers=_headers(token),
    ).json()

    assert default == explicit_false


def test_include_inactive_is_readable_by_viewer(api):
    response = client.get(
        ETL_PROFILES_ENDPOINT,
        params={"include_inactive": "true"},
        headers=_headers(api("viewer")),
    )

    assert response.status_code == 200, response.text


def test_include_inactive_still_requires_authentication(api):
    response = client.get(ETL_PROFILES_ENDPOINT, params={"include_inactive": "true"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_include_inactive_never_exposes_a_profile_outside_the_allowlist(api):
    """필터를 끄는 것이지 후보를 넓히는 것이 아닙니다."""
    items = client.get(
        ETL_PROFILES_ENDPOINT,
        params={"include_inactive": "true"},
        headers=_headers(api("viewer")),
    ).json()["items"]

    assert sorted(item["id"] for item in items) == [
        OTHER_PROFILE_ID,
        PROFILE_ID,
    ]


def test_deactivate_then_reactivate_round_trip_through_the_management_list(api):
    """관리 목록 → 비활성 → 관리 목록에 남음 → 다시 활성화 → 실행 목록 복귀."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    admin_ids = [
        item["id"]
        for item in client.get(
            ETL_PROFILES_ENDPOINT,
            params={"include_inactive": "true"},
            headers=_headers(token),
        ).json()["items"]
    ]
    assert PROFILE_ID in admin_ids

    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))

    run_ids = [
        item["id"]
        for item in client.get(ETL_PROFILES_ENDPOINT, headers=_headers(token)).json()["items"]
    ]
    assert PROFILE_ID in run_ids


# ---- Phase 5B.3: DELETE로 runtime override를 지운다 ---------------------------


def test_anonymous_reset_is_401(api):
    response = client.delete(ACTIVATION_ENDPOINT)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_viewer_reset_is_403_and_changes_nothing(api, session_factory):
    """조회는 되지만 override 제거는 운영 기능입니다."""
    operator = api("operator")
    client.put(
        ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(operator)
    )

    response = client.delete(ACTIVATION_ENDPOINT, headers=_headers(api("viewer")))

    assert response.status_code == 403
    with session_factory() as session:
        [row] = session.scalars(select(ETLProfileActivation)).all()
    assert row.active_version == "1"


def test_operator_reset_removes_an_active_override(api, session_factory):
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))

    response = client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["runtime_override_exists"] is False
    assert body["runtime_active_version"] is None
    assert body["effective_active_version"] == "2"
    assert body["deployment_active_version"] == "2"
    assert body["is_active"] is True
    # row가 사라졌으므로 actor/updated_at도 없습니다.
    assert body["actor_username"] is None
    assert body["updated_at"] is None
    with session_factory() as session:
        assert session.scalars(select(ETLProfileActivation)).all() == []


def test_reset_of_an_explicit_inactive_override_reactivates_the_profile(api):
    """reset은 정리가 아니라 상태 전환입니다. 비활성 프로필이 되살아납니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))
    assert (
        client.get(ACTIVATION_ENDPOINT, headers=_headers(token)).json()["is_active"]
        is False
    )

    body = client.delete(ACTIVATION_ENDPOINT, headers=_headers(token)).json()

    assert body["runtime_override_exists"] is False
    assert body["effective_active_version"] == "2"
    assert body["is_active"] is True


def test_reset_is_idempotent_without_an_override(api):
    """두 번째 DELETE는 재시도이지 오류가 아닙니다."""
    token = api("operator")

    first = client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))
    second = client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert first.json()["runtime_override_exists"] is False
    assert first.json()["effective_active_version"] == "2"


def test_reset_of_an_unknown_profile_is_404(api):
    """override가 없는 정상 프로필(200)과 없는 프로필(404)을 구분합니다."""
    response = client.delete(
        "/api/v1/etl-profiles/not_a_profile/activation",
        headers=_headers(api("operator")),
    )

    assert response.status_code == 404


def test_reset_response_matches_the_activation_response_shape(api):
    """새 schema를 만들지 않았습니다. GET/PUT과 같은 응답이어야 합니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))

    reset_body = client.delete(ACTIVATION_ENDPOINT, headers=_headers(token)).json()
    read_body = client.get(ACTIVATION_ENDPOINT, headers=_headers(token)).json()

    assert sorted(reset_body) == sorted(read_body)
    # reset 직후 GET을 한 번 더 해도 같은 상태여야 합니다. 다르면 DELETE 응답이
    # 서버의 실제 상태를 말하지 않는다는 뜻입니다.
    assert reset_body == read_body
    assert read_body["runtime_override_exists"] is False


def test_reset_does_not_accept_a_request_body(api):
    """DELETE에는 고를 것이 없습니다. body를 받으면 계약이 모호해집니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))

    response = client.request(
        "DELETE",
        ACTIVATION_ENDPOINT,
        json={"active_version": "1"},
        headers=_headers(token),
    )

    # body는 route가 읽지 않으므로 무시되고, 결과는 body 없는 DELETE와 같습니다.
    assert response.status_code == 200, response.text
    assert response.json()["runtime_override_exists"] is False


def test_reset_puts_a_deactivated_profile_back_in_the_run_list(api):
    """관리 화면에서 reset했는데 실행 목록이 옛 상태면 안 됩니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))
    hidden = [
        item["id"]
        for item in client.get(ETL_PROFILES_ENDPOINT, headers=_headers(token)).json()["items"]
    ]
    assert PROFILE_ID not in hidden

    client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    ids = [
        item["id"]
        for item in client.get(ETL_PROFILES_ENDPOINT, headers=_headers(token)).json()["items"]
    ]
    assert PROFILE_ID in ids
    assert OTHER_PROFILE_ID in ids


def test_reset_restores_the_deployment_default_version_for_a_new_run(
    api, session_factory
):
    """override로 v1을 쓰던 프로필이 reset 뒤에는 배포 기본값 v2로 실행돼야 합니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))
    client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    response = _post_web_etl(token, uuid4().hex[:10])

    assert response.status_code == 200, response.text
    run_id = response.json()["etl_load_run_id"]
    try:
        with session_factory() as session:
            assert session.get(ETLLoadRun, run_id).profile_version == "2"
    finally:
        with session_factory() as session:
            session.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
            session.commit()


def test_reset_only_touches_the_requested_profile(api, session_factory):
    token = api("operator")
    for profile_id in (PROFILE_ID, OTHER_PROFILE_ID):
        client.put(
            f"/api/v1/etl-profiles/{profile_id}/activation",
            json={"active_version": "1"},
            headers=_headers(token),
        )

    client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    other = client.get(
        f"/api/v1/etl-profiles/{OTHER_PROFILE_ID}/activation", headers=_headers(token)
    ).json()
    assert other["runtime_override_exists"] is True
    assert other["effective_active_version"] == "1"
    with session_factory() as session:
        rows = session.scalars(select(ETLProfileActivation)).all()
    assert [row.profile_id for row in rows] == [OTHER_PROFILE_ID]


def test_put_null_still_means_explicit_inactive_after_reset_exists(api, session_factory):
    """이번 Phase가 기존 계약을 바꾸지 않았다는 회귀입니다.

    PUT null이 reset처럼 동작하기 시작하면 운영자가 내린 결정이 배포 기본값으로
    조용히 되살아납니다.
    """
    token = api("operator")

    body = client.put(
        ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token)
    ).json()

    assert body["runtime_override_exists"] is True
    assert body["effective_active_version"] is None
    assert body["is_active"] is False
    with session_factory() as session:
        [row] = session.scalars(select(ETLProfileActivation)).all()
    assert row.active_version is None


def test_reset_does_not_delete_past_etl_history(api, session_factory):
    """override를 지우는 것이지 배치를 지우는 것이 아닙니다."""
    token = api("operator")
    response = _post_web_etl(token, uuid4().hex[:10])
    assert response.status_code == 200, response.text
    run_id = response.json()["etl_load_run_id"]
    client.put(ACTIVATION_ENDPOINT, json={"active_version": None}, headers=_headers(token))

    client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    try:
        detail = client.get(f"{WEB_ETL_ENDPOINT}/{run_id}", headers=_headers(token))
        assert detail.status_code == 200, detail.text
        with session_factory() as session:
            assert session.get(ETLLoadRun, run_id) is not None
    finally:
        with session_factory() as session:
            session.execute(delete(ETLLoadRun).where(ETLLoadRun.id == run_id))
            session.commit()


def test_reset_does_not_change_the_profile_definition(api):
    """Policy A. reset은 어떤 버전을 쓸지만 되돌립니다."""
    token = api("operator")
    client.put(ACTIVATION_ENDPOINT, json={"active_version": "1"}, headers=_headers(token))

    client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    detail = client.get(
        f"{ETL_PROFILES_ENDPOINT}/{PROFILE_ID}", headers=_headers(token)
    ).json()
    assert detail["profile_version"] == "2"
    assert detail["profile_name"] == "sample_marketplace_vendor"
    assert detail["source_columns"]["style_id"] == ["product_group_id"]


# ---- Phase 5B.4: 성공한 운영 명령의 append-only 이력 --------------------------


HISTORY_ITEM_KEYS = {
    "event_id",
    "profile_id",
    "action",
    "deployment_active_version",
    "runtime_override_exists",
    "runtime_active_version",
    "effective_active_version",
    "actor_username",
    "created_at",
}


def _history(token: str, **params):
    return client.get(
        ACTIVATION_HISTORY_ENDPOINT, headers=_headers(token), params=params or None
    )


def test_anonymous_history_read_is_401(api):
    response = client.get(ACTIVATION_HISTORY_ENDPOINT)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_viewer_can_read_the_history(api):
    """운영 기록을 읽는 것은 상태를 바꾸는 것이 아닙니다.

    상태를 바꿀 수 없는 사람도 "왜 지금 이렇게 되어 있는가"는 확인할 수 있어야 합니다.
    """
    response = _history(api("viewer"))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["limit"] == 20
    assert payload["offset"] == 0


def test_operator_can_read_the_history(api):
    response = _history(api("operator"))

    assert response.status_code == 200, response.text


def test_history_of_an_unknown_profile_is_404(api):
    response = client.get(
        "/api/v1/etl-profiles/nope/activation/history",
        headers=_headers(api("viewer")),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "ETL profile not found."


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": -1},
        {"offset": -1},
        {"limit": "many"},
        {"offset": "start"},
    ],
)
def test_invalid_pagination_is_422(api, params):
    response = _history(api("viewer"), **params)

    assert response.status_code == 422


def test_history_records_every_successful_mutation(api):
    """PUT version / PUT null / DELETE가 각각 event 하나를 남깁니다."""
    token = api("operator")
    assert (
        client.put(
            ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
        ).status_code
        == 200
    )
    assert (
        client.put(
            ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": None}
        ).status_code
        == 200
    )
    assert client.delete(ACTIVATION_ENDPOINT, headers=_headers(token)).status_code == 200

    payload = _history(token).json()
    assert payload["total"] == 3
    # 최신순입니다.
    assert [item["action"] for item in payload["items"]] == [
        "reset",
        "deactivate",
        "activate",
    ]


def test_a_failed_mutation_records_nothing(api):
    """없는 버전으로 실패한 요청은 이력에 흔적을 남기지 않습니다."""
    token = api("operator")
    response = client.put(
        ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "999"}
    )

    assert response.status_code == 422
    assert _history(token).json()["total"] == 0


def test_a_forbidden_mutation_records_nothing(api):
    """403은 service까지 도달하지 않으므로 event가 생길 자리가 없습니다."""
    viewer_token = api("viewer")
    response = client.put(
        ACTIVATION_ENDPOINT,
        headers=_headers(viewer_token),
        json={"active_version": "1"},
    )

    assert response.status_code == 403
    assert _history(viewer_token).json()["total"] == 0


def test_history_item_shape_and_actor(api):
    token = api("operator")
    client.put(
        ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
    )

    [item] = _history(token).json()["items"]
    assert set(item) == HISTORY_ITEM_KEYS
    # DB 관계용 ID는 응답에 없습니다. 화면에 필요한 것은 username snapshot입니다.
    assert "actor_user_id" not in item
    assert item["profile_id"] == PROFILE_ID
    assert item["action"] == "activate"
    assert item["deployment_active_version"] == "2"
    assert item["runtime_override_exists"] is True
    assert item["runtime_active_version"] == "1"
    assert item["effective_active_version"] == "1"
    assert item["actor_username"].startswith("activation_operator_")
    assert item["created_at"]


def test_reset_keeps_the_actor_in_history_while_current_state_has_none(api):
    """모순이 아니라 서로 다른 질문에 대한 답입니다.

    current-state row는 지워졌으므로 "지금 이 override를 만든 사람"은 없습니다.
    "그 override를 지운 명령을 내린 사람"은 이력에 남습니다.
    """
    token = api("operator")
    client.put(
        ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
    )
    reset_response = client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    assert reset_response.status_code == 200
    assert reset_response.json()["actor_username"] is None
    assert reset_response.json()["updated_at"] is None

    reset_event = _history(token).json()["items"][0]
    assert reset_event["action"] == "reset"
    assert reset_event["actor_username"].startswith("activation_operator_")
    # override는 사라졌지만 배포 기본값이 활성이라 실제 적용 버전은 있습니다.
    assert reset_event["runtime_override_exists"] is False
    assert reset_event["effective_active_version"] == "2"


def test_repeated_identical_commands_still_add_events(api):
    """상태 idempotency와 audit event idempotency는 다른 개념입니다."""
    token = api("operator")
    for _ in range(2):
        client.put(
            ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
        )
    for _ in range(2):
        client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    payload = _history(token).json()
    assert payload["total"] == 4
    assert [item["action"] for item in payload["items"]] == [
        "reset",
        "reset",
        "activate",
        "activate",
    ]


def test_history_paginates(api):
    token = api("operator")
    for _ in range(3):
        client.put(
            ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
        )

    first = _history(token, limit=2, offset=0).json()
    second = _history(token, limit=2, offset=2).json()

    assert first["total"] == 3
    assert first["limit"] == 2
    assert len(first["items"]) == 2
    assert second["offset"] == 2
    assert len(second["items"]) == 1
    assert not {item["event_id"] for item in first["items"]} & {
        item["event_id"] for item in second["items"]
    }


def test_history_is_scoped_to_one_profile(api):
    token = api("operator")
    client.put(
        ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
    )
    client.put(
        OTHER_ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
    )

    payload = _history(token).json()
    assert payload["total"] == 1
    assert [item["profile_id"] for item in payload["items"]] == [PROFILE_ID]


def test_mutation_responses_did_not_gain_a_history_field(api):
    """기존 PUT/DELETE 응답 계약은 그대로입니다. 이력은 별도 endpoint로만 읽습니다."""
    token = api("operator")
    put_response = client.put(
        ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
    )
    delete_response = client.delete(ACTIVATION_ENDPOINT, headers=_headers(token))

    expected_keys = {
        "profile_id",
        "display_name",
        "deployment_active_version",
        "runtime_override_exists",
        "runtime_active_version",
        "effective_active_version",
        "is_active",
        "available_versions",
        "actor_username",
        "updated_at",
    }
    assert set(put_response.json()) == expected_keys
    assert set(delete_response.json()) == expected_keys


def test_history_has_no_write_endpoints(api):
    """append-only는 애플리케이션 계약입니다. 수정/삭제 경로를 두지 않습니다."""
    token = api("operator")
    client.put(
        ACTIVATION_ENDPOINT, headers=_headers(token), json={"active_version": "1"}
    )
    event_id = _history(token).json()["items"][0]["event_id"]

    for send in (
        lambda: client.put(
            ACTIVATION_HISTORY_ENDPOINT, headers=_headers(token), json={"action": "x"}
        ),
        lambda: client.delete(ACTIVATION_HISTORY_ENDPOINT, headers=_headers(token)),
        lambda: client.post(ACTIVATION_HISTORY_ENDPOINT, headers=_headers(token)),
        lambda: client.delete(
            f"{ACTIVATION_HISTORY_ENDPOINT}/{event_id}", headers=_headers(token)
        ),
    ):
        assert send().status_code in (404, 405)

    assert _history(token).json()["total"] == 1
