"""Runtime activation state: deployment default + persistent runtime override.

Phase 5B.1 of docs/etl_profile_lifecycle.md.

Phase 5A(tests/etl/test_profile_activation.py)는 배포 registry 하나만 있을 때의
활성/비활성을 고정합니다. 여기서는 그 위에 DB runtime override가 얹혔을 때
**effective** 상태가 무엇이 되는지, 그리고 그 상태가 session을 새로 만들어도
남아 있는지를 고정합니다.
"""
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

import etl.profile_loader as profile_loader
from config.database import get_optional_database_url
from db.etl_profile_activation_service import (
    ETLProfileVersionNotFoundError,
    get_etl_profile_activation,
    set_etl_profile_activation,
)
from db.models import ETLProfileActivation
from db.session import create_database_engine, create_session_factory
from etl.profile_loader import (
    ETLProfileInactiveError,
    ETLProfileNotFoundError,
    get_profile_path,
    get_profile_version_path,
    list_etl_profiles,
    load_profile,
    resolve_etl_profile_activation,
)


FASHION_PROFILE_ID = "sample_fashion_vendor_v1"
MARKETPLACE_PROFILE_ID = "sample_marketplace_vendor_v1"


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


@pytest.fixture(name="clean_activations")
def fixture_clean_activations(session_factory):
    """Keep the runtime override table empty around each test.

    이 표는 프로필당 row 하나뿐인 전역 상태라, 남겨 두면 다음 테스트가 다른 활성
    상태에서 시작합니다.
    """

    def _clear() -> None:
        with session_factory() as session:
            session.execute(delete(ETLProfileActivation))
            session.commit()

    _clear()
    yield
    _clear()


# ---- resolver: 배포 기본값과 runtime override의 관계 --------------------------


def test_without_a_runtime_row_the_deployment_default_applies(
    session_factory, clean_activations
):
    with session_factory() as session:
        activation = resolve_etl_profile_activation(
            MARKETPLACE_PROFILE_ID, session=session
        )

    assert activation.deployment_active_version == "2"
    assert activation.runtime_override_exists is False
    assert activation.runtime_active_version is None
    assert activation.effective_active_version == "2"
    assert activation.is_active is True


def test_runtime_override_selects_an_archived_version(
    session_factory, clean_activations
):
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version="1",
            actor_user_id=None,
            actor_username="operator_user",
        )

    with session_factory() as session:
        activation = resolve_etl_profile_activation(
            MARKETPLACE_PROFILE_ID, session=session
        )

    # 배포 기본값은 그대로 남습니다. override가 그것을 덮어쓴 것이지 지운 것이 아닙니다.
    assert activation.deployment_active_version == "2"
    assert activation.runtime_override_exists is True
    assert activation.runtime_active_version == "1"
    assert activation.effective_active_version == "1"
    assert activation.is_active is True


def test_runtime_null_version_is_deactivation_not_a_missing_override(
    session_factory, clean_activations
):
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version=None,
            actor_user_id=None,
            actor_username="operator_user",
        )

    with session_factory() as session:
        activation = resolve_etl_profile_activation(
            MARKETPLACE_PROFILE_ID, session=session
        )

    # "row 없음"과 "row 있음 + NULL"이 구분되어야 합니다. 둘을 합치면 운영자가 명시적으로
    # 내린 상태가 배포 기본값으로 조용히 되살아납니다.
    assert activation.runtime_override_exists is True
    assert activation.runtime_active_version is None
    assert activation.effective_active_version is None
    assert activation.is_active is False


def test_deactivated_profile_blocks_a_new_etl_run(session_factory, clean_activations):
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version=None,
            actor_user_id=None,
            actor_username="operator_user",
        )

    with session_factory() as session:
        with pytest.raises(ETLProfileInactiveError):
            get_profile_path(MARKETPLACE_PROFILE_ID, session=session)


def test_reactivation_makes_the_profile_runnable_again(
    session_factory, clean_activations
):
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version=None,
            actor_user_id=None,
            actor_username="operator_user",
        )
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version="2",
            actor_user_id=None,
            actor_username="operator_user",
        )

    with session_factory() as session:
        profile = load_profile(get_profile_path(MARKETPLACE_PROFILE_ID, session=session))

    assert profile.version == "2"


def test_runtime_override_actually_changes_which_version_runs(
    session_factory, clean_activations
):
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version="1",
            actor_user_id=None,
            actor_username="operator_user",
        )

    with session_factory() as session:
        path = get_profile_path(MARKETPLACE_PROFILE_ID, session=session)
        profile = load_profile(path)

    assert path == get_profile_version_path(MARKETPLACE_PROFILE_ID, "1")
    assert profile.version == "1"


def test_state_survives_a_brand_new_session_and_engine(clean_activations):
    """Persistence is the whole point: an in-memory registry edit would not survive."""
    database_url = get_optional_database_url()

    first_engine = create_database_engine(database_url)
    try:
        with create_session_factory(first_engine)() as session:
            set_etl_profile_activation(
                session,
                profile_id=MARKETPLACE_PROFILE_ID,
                active_version=None,
                actor_user_id=None,
                actor_username="operator_user",
            )
    finally:
        first_engine.dispose()

    # 프로세스가 재시작된 것과 같은 상황을 흉내 냅니다: 새 engine, 새 session factory.
    second_engine = create_database_engine(database_url)
    try:
        with create_session_factory(second_engine)() as session:
            activation = resolve_etl_profile_activation(
                MARKETPLACE_PROFILE_ID, session=session
            )
    finally:
        second_engine.dispose()

    assert activation.runtime_override_exists is True
    assert activation.effective_active_version is None

    # 배포 registry 자체는 건드리지 않았습니다.
    assert profile_loader._ETL_PROFILE_REGISTRY[MARKETPLACE_PROFILE_ID][
        "active_version"
    ] == "2"


def test_one_profile_override_does_not_affect_another(
    session_factory, clean_activations
):
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version=None,
            actor_user_id=None,
            actor_username="operator_user",
        )

    with session_factory() as session:
        other = resolve_etl_profile_activation(FASHION_PROFILE_ID, session=session)

    assert other.runtime_override_exists is False
    assert other.effective_active_version == "2"


# ---- 검증: 무엇을 활성화할 수 있는가 -----------------------------------------


@pytest.mark.parametrize("bad_version", ["999", "3", "v2", "", "   "])
def test_only_preserved_versions_can_be_activated(
    session_factory, clean_activations, bad_version
):
    """임의 문자열을 활성으로 저장하면 다음 실행이 실행 시점에 가서야 실패합니다.

    그 실패는 운영자가 방금 한 행동에서 멀리 떨어져 있어 원인을 찾기 어렵습니다.
    공백 문자열도 비활성 표시가 아니라 잘못된 버전입니다(Phase 5A와 같은 규칙).
    """
    with session_factory() as session:
        with pytest.raises(ETLProfileVersionNotFoundError):
            set_etl_profile_activation(
                session,
                profile_id=MARKETPLACE_PROFILE_ID,
                active_version=bad_version,
                actor_user_id=None,
                actor_username="operator_user",
            )

    with session_factory() as session:
        rows = session.scalars(select(ETLProfileActivation)).all()

    # 거부된 요청은 row를 남기지 않습니다.
    assert rows == []


def test_rejected_version_does_not_change_an_existing_override(
    session_factory, clean_activations
):
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version="1",
            actor_user_id=None,
            actor_username="operator_user",
        )
    with session_factory() as session:
        with pytest.raises(ETLProfileVersionNotFoundError):
            set_etl_profile_activation(
                session,
                profile_id=MARKETPLACE_PROFILE_ID,
                active_version="999",
                actor_user_id=None,
                actor_username="operator_user",
            )

    with session_factory() as session:
        activation = resolve_etl_profile_activation(
            MARKETPLACE_PROFILE_ID, session=session
        )

    assert activation.effective_active_version == "1"


@pytest.mark.parametrize("unknown_profile_id", ["nope", "sample_fashion_vendor", ""])
def test_unknown_profile_id_is_rejected_by_read_and_write(
    session_factory, clean_activations, unknown_profile_id
):
    """registry가 allowlist입니다. DB row 하나로 그 밖의 값을 되살릴 수 없어야 합니다."""
    with session_factory() as session:
        with pytest.raises(ETLProfileNotFoundError):
            get_etl_profile_activation(session, profile_id=unknown_profile_id)
        with pytest.raises(ETLProfileNotFoundError):
            set_etl_profile_activation(
                session,
                profile_id=unknown_profile_id,
                active_version="1",
                actor_user_id=None,
                actor_username="operator_user",
            )


def test_a_row_for_a_profile_outside_the_allowlist_does_not_revive_it(
    session_factory, clean_activations
):
    orphan_profile_id = f"ghost_profile_{uuid4().hex[:8]}"
    with session_factory() as session:
        session.add(
            ETLProfileActivation(profile_id=orphan_profile_id, active_version="1")
        )
        session.commit()

    try:
        with session_factory() as session:
            with pytest.raises(ETLProfileNotFoundError):
                resolve_etl_profile_activation(orphan_profile_id, session=session)
    finally:
        with session_factory() as session:
            session.execute(
                delete(ETLProfileActivation).where(
                    ETLProfileActivation.profile_id == orphan_profile_id
                )
            )
            session.commit()


# ---- 동시성 -------------------------------------------------------------------


def test_repeated_writes_keep_exactly_one_row_per_profile(
    session_factory, clean_activations
):
    """두 operator가 번갈아 바꿔도 row는 하나뿐이고 마지막 쓰기가 이깁니다.

    unique index가 중복 row를 막고, ON CONFLICT DO UPDATE가 IntegrityError를 사용자에게
    노출하지 않고 갱신으로 바꿉니다.
    """
    for version, actor in [("1", "operator_a"), (None, "operator_b"), ("2", "operator_a")]:
        with session_factory() as session:
            set_etl_profile_activation(
                session,
                profile_id=MARKETPLACE_PROFILE_ID,
                active_version=version,
                actor_user_id=None,
                actor_username=actor,
            )

    with session_factory() as session:
        rows = session.scalars(
            select(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == MARKETPLACE_PROFILE_ID
            )
        ).all()

    assert len(rows) == 1
    assert rows[0].active_version == "2"
    # 진 쪽이 흔적 없이 사라지지 않도록 마지막으로 누가 바꿨는지 남습니다.
    assert rows[0].actor_username == "operator_a"


def test_duplicate_rows_are_rejected_by_the_database(session_factory, clean_activations):
    from sqlalchemy.exc import IntegrityError

    with session_factory() as session:
        session.add(
            ETLProfileActivation(profile_id=MARKETPLACE_PROFILE_ID, active_version="1")
        )
        session.commit()

    with session_factory() as session:
        session.add(
            ETLProfileActivation(profile_id=MARKETPLACE_PROFILE_ID, active_version="2")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_blank_active_version_is_rejected_by_the_database(
    session_factory, clean_activations
):
    """서비스 검증을 우회해 직접 써도 ''는 비활성 표시가 될 수 없습니다."""
    from sqlalchemy.exc import IntegrityError

    with session_factory() as session:
        session.add(
            ETLProfileActivation(profile_id=MARKETPLACE_PROFILE_ID, active_version="   ")
        )
        with pytest.raises(IntegrityError):
            session.commit()


# ---- 조회 view ---------------------------------------------------------------


def test_activation_view_separates_deployment_runtime_and_effective(
    session_factory, clean_activations
):
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version="1",
            actor_user_id=None,
            actor_username="operator_user",
        )

    with session_factory() as session:
        view = get_etl_profile_activation(session, profile_id=MARKETPLACE_PROFILE_ID)

    assert view.profile_id == MARKETPLACE_PROFILE_ID
    assert view.deployment_active_version == "2"
    assert view.runtime_override_exists is True
    assert view.runtime_active_version == "1"
    assert view.effective_active_version == "1"
    assert view.is_active is True
    assert view.available_versions == ["1", "2"]
    assert view.actor_username == "operator_user"
    assert view.updated_at is not None


def test_activation_view_without_an_override_reports_no_actor(
    session_factory, clean_activations
):
    """아무도 바꾼 적 없는 상태를 누군가 바꾼 것처럼 보이면 안 됩니다."""
    with session_factory() as session:
        view = get_etl_profile_activation(session, profile_id=MARKETPLACE_PROFILE_ID)

    assert view.runtime_override_exists is False
    assert view.actor_username is None
    assert view.updated_at is None
    assert view.effective_active_version == "2"


def test_deactivated_profile_is_not_selectable_but_archives_stay_readable(
    session_factory, clean_activations
):
    """Deactivate는 Delete가 아닙니다(Policy G)."""
    with session_factory() as session:
        set_etl_profile_activation(
            session,
            profile_id=MARKETPLACE_PROFILE_ID,
            active_version=None,
            actor_user_id=None,
            actor_username="operator_user",
        )

    with session_factory() as session:
        selectable = [item["id"] for item in list_etl_profiles(session=session)]

    assert MARKETPLACE_PROFILE_ID not in selectable
    assert FASHION_PROFILE_ID in selectable

    # 과거 배치가 참조하는 정의는 계속 읽을 수 있어야 합니다.
    for version in ("1", "2"):
        assert load_profile(
            get_profile_version_path(MARKETPLACE_PROFILE_ID, version)
        ).version == version


# ---- activation 조회가 뒤따르는 쓰기 트랜잭션을 막지 않는다 --------------------


def test_activation_read_leaves_the_session_ready_for_a_write_transaction(
    session_factory, clean_activations
):
    """조회가 autobegin시킨 트랜잭션을 정리하지 않으면 ETL 적재가 통째로 실패합니다.

    load_standard_csv()가 `with session.begin()`으로 자기 트랜잭션을 열기 때문에,
    activation 조회가 session을 붙들고 있으면 "A transaction is already begun"이 됩니다.
    """
    from db.etl_profile_activation_service import end_activation_read_transaction

    with session_factory() as session:
        get_profile_path(MARKETPLACE_PROFILE_ID, session=session)
        assert session.in_transaction() is True

        end_activation_read_transaction(session)

        assert session.in_transaction() is False
        # 이제 쓰기 경로가 자기 트랜잭션을 열 수 있습니다.
        with session.begin():
            pass


def test_a_pending_write_is_reported_instead_of_being_silently_discarded(
    session_factory, clean_activations
):
    """호출자가 쓰기를 들고 있으면 조용히 버리지 않고 소리를 냅니다.

    지금은 Web/S3/HTTP/Airflow 어느 경로도 이 시점에 쓰기를 들고 있지 않지만, 나중에
    누군가 앞에 쓰기를 추가했을 때 그것이 흔적 없이 사라지면 안 됩니다.
    """
    from db.etl_profile_activation_service import (
        PendingWriteBeforeActivationReadError,
        end_activation_read_transaction,
    )

    orphan_profile_id = f"pending_write_{uuid4().hex[:8]}"
    with session_factory() as session:
        session.add(
            ETLProfileActivation(profile_id=orphan_profile_id, active_version="1")
        )

        with pytest.raises(PendingWriteBeforeActivationReadError):
            end_activation_read_transaction(session)

        # 보류 중이던 쓰기는 rollback되지 않고 그대로 남아 있습니다.
        assert any(
            obj.profile_id == orphan_profile_id for obj in session.new
        )
