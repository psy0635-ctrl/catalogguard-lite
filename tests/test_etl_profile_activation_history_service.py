"""Append-only history of successful activation commands.

Phase 5B.4 of docs/etl_profile_lifecycle.md.

이 파일이 고정하는 것은 스키마가 아니라 **audit의 뜻**입니다.

* 기록 단위는 "상태가 실제로 달라진 순간"이 아니라 "서버가 성공으로 처리한 operator
  명령"이다. 같은 버전을 다시 활성화하거나 override 없는 프로필을 다시 reset해도
  event가 생긴다.
* 실패한 요청은 아무것도 남기지 않는다.
* 상태 변경과 기록은 같은 트랜잭션이다. 한쪽만 남는 순간이 없어야 한다.

current-state 계약 자체(tests/test_etl_profile_activation_service.py)는 이 Phase에서
바뀌지 않았으므로 여기서 다시 검증하지 않습니다.
"""
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from config.database import get_optional_database_url
from db.auth_service import create_user
from db.etl_profile_activation_service import (
    ETLProfileVersionNotFoundError,
    list_etl_profile_activation_history,
    reset_etl_profile_activation,
    set_etl_profile_activation,
)
from db.models import ETLProfileActivation, ETLProfileActivationEvent, User
from db.session import create_database_engine, create_session_factory
from etl.profile_loader import ETLProfileNotFoundError


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


@pytest.fixture(name="clean_history")
def fixture_clean_history(session_factory):
    """Start every test from an empty history and an empty current state.

    두 표를 함께 비웁니다. history만 비우면 남아 있던 override 때문에 다음 테스트의
    첫 명령이 다른 상태에서 시작합니다.
    """

    def _clear() -> None:
        with session_factory() as session:
            session.execute(delete(ETLProfileActivationEvent))
            session.execute(delete(ETLProfileActivation))
            session.commit()

    _clear()
    yield
    _clear()


@pytest.fixture(name="operator_account")
def fixture_operator_account(session_factory):
    """One real user row, so the actor FK and its snapshot can both be checked."""
    username = f"history_operator_{uuid4().hex[:10]}"
    with session_factory() as session:
        user = create_user(
            session,
            username=username,
            password="synthetic-history-password",
            role="operator",
        )
        user_id = user.id

    yield user_id, username

    with session_factory() as session:
        session.execute(delete(User).where(User.id == user_id))
        session.commit()


def _events(session_factory, profile_id=None):
    with session_factory() as session:
        statement = select(ETLProfileActivationEvent).order_by(
            ETLProfileActivationEvent.id
        )
        if profile_id is not None:
            statement = statement.where(
                ETLProfileActivationEvent.profile_id == profile_id
            )
        return list(session.scalars(statement).all())


def _activate(session_factory, *, profile_id=MARKETPLACE_PROFILE_ID, version="1",
              actor_user_id=None, actor_username="operator_user"):
    with session_factory() as session:
        return set_etl_profile_activation(
            session,
            profile_id=profile_id,
            active_version=version,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
        )


def _deactivate(session_factory, *, profile_id=MARKETPLACE_PROFILE_ID,
                actor_user_id=None, actor_username="operator_user"):
    return _activate(
        session_factory,
        profile_id=profile_id,
        version=None,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
    )


def _reset(session_factory, *, profile_id=MARKETPLACE_PROFILE_ID,
           actor_user_id=None, actor_username="operator_user"):
    with session_factory() as session:
        return reset_etl_profile_activation(
            session,
            profile_id=profile_id,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
        )


# ---- 성공한 명령 하나 = event 하나 --------------------------------------------


def test_activate_records_one_event_with_the_resulting_state(
    session_factory, clean_history
):
    _activate(session_factory, version="1")

    [event] = _events(session_factory)
    assert event.profile_id == MARKETPLACE_PROFILE_ID
    assert event.action == "activate"
    assert event.deployment_active_version == "2"
    assert event.runtime_override_exists is True
    assert event.runtime_active_version == "1"
    assert event.effective_active_version == "1"
    assert event.actor_username == "operator_user"
    assert event.created_at is not None


def test_deactivate_records_one_event(session_factory, clean_history):
    _deactivate(session_factory)

    [event] = _events(session_factory)
    assert event.action == "deactivate"
    # 명시적 비활성입니다. override는 있고, 실제 적용 버전은 없습니다.
    assert event.runtime_override_exists is True
    assert event.runtime_active_version is None
    assert event.effective_active_version is None


def test_reset_records_one_event(session_factory, clean_history):
    _activate(session_factory, version="1")
    _reset(session_factory)

    events = _events(session_factory)
    assert [event.action for event in events] == ["activate", "reset"]


def test_reset_event_shows_the_deployment_default_as_what_actually_applies(
    session_factory, clean_history
):
    """reset을 "비활성화"로 읽으면 안 됩니다.

    override가 사라졌을 뿐이고, 배포 기본값이 활성이면 그 프로필은 reset과 동시에
    실행 가능해집니다. event가 그 사실을 담지 못하면 화면이 정반대로 설명합니다.
    """
    _deactivate(session_factory)
    _reset(session_factory)

    reset_event = _events(session_factory)[-1]
    assert reset_event.action == "reset"
    assert reset_event.runtime_override_exists is False
    assert reset_event.runtime_active_version is None
    assert reset_event.deployment_active_version == "2"
    assert reset_event.effective_active_version == "2"


# ---- state idempotency != audit idempotency ----------------------------------


def test_activating_the_same_version_again_records_another_event(
    session_factory, clean_history
):
    """상태는 그대로지만 운영자가 실제로 내린 명령이 둘입니다."""
    _activate(session_factory, version="1", actor_username="first_operator")
    _activate(session_factory, version="1", actor_username="second_operator")

    events = _events(session_factory)
    assert [event.action for event in events] == ["activate", "activate"]
    assert [event.actor_username for event in events] == [
        "first_operator",
        "second_operator",
    ]


def test_deactivating_an_already_inactive_profile_records_another_event(
    session_factory, clean_history
):
    _deactivate(session_factory)
    _deactivate(session_factory)

    assert [event.action for event in _events(session_factory)] == [
        "deactivate",
        "deactivate",
    ]


def test_resetting_a_profile_without_an_override_records_an_event(
    session_factory, clean_history
):
    """지운 row가 0건이어도 성공한 운영 명령입니다.

    API는 idempotent 200이지만 이 표가 기록하는 단위는 상태 변화가 아니라 명령입니다.
    """
    with session_factory() as session:
        assert (
            session.scalars(
                select(ETLProfileActivation).where(
                    ETLProfileActivation.profile_id == MARKETPLACE_PROFILE_ID
                )
            ).one_or_none()
            is None
        )

    _reset(session_factory)

    [event] = _events(session_factory)
    assert event.action == "reset"
    assert event.runtime_override_exists is False
    assert event.effective_active_version == "2"


# ---- 실패한 요청은 흔적을 남기지 않는다 ---------------------------------------


@pytest.mark.parametrize("unknown_profile_id", ["nope", "sample_fashion_vendor", ""])
def test_an_unknown_profile_records_nothing(
    session_factory, clean_history, unknown_profile_id
):
    with session_factory() as session:
        with pytest.raises(ETLProfileNotFoundError):
            set_etl_profile_activation(
                session,
                profile_id=unknown_profile_id,
                active_version="1",
                actor_user_id=None,
                actor_username="operator_user",
            )
    with session_factory() as session:
        with pytest.raises(ETLProfileNotFoundError):
            reset_etl_profile_activation(
                session,
                profile_id=unknown_profile_id,
                actor_user_id=None,
                actor_username="operator_user",
            )

    assert _events(session_factory) == []


@pytest.mark.parametrize("unknown_version", ["999", "", "   "])
def test_an_unknown_version_records_nothing(
    session_factory, clean_history, unknown_version
):
    with session_factory() as session:
        with pytest.raises(ETLProfileVersionNotFoundError):
            set_etl_profile_activation(
                session,
                profile_id=MARKETPLACE_PROFILE_ID,
                active_version=unknown_version,
                actor_user_id=None,
                actor_username="operator_user",
            )

    assert _events(session_factory) == []


# ---- 상태 변경과 기록은 같은 트랜잭션이다 -------------------------------------


def test_a_failed_event_insert_rolls_back_the_activation_change(
    session_factory, clean_history, monkeypatch
):
    """audit이 실패하면 상태 변경도 없던 일이 되어야 합니다.

    반대(상태만 바뀌고 기록이 없음)를 허용하면, 이력을 믿을 수 없게 됩니다. "기록에
    없으니 아무도 안 했다"가 참이 아니게 되기 때문입니다.

    실제 flush 실패로 확인합니다. helper가 예외를 던지는 것만 보면 트랜잭션이 아니라
    호출 순서만 검증하게 되므로, DB가 거부하는 event를 넣어 commit 시점에 실패시킵니다.
    """
    import db.etl_profile_activation_service as service

    def broken_record(session, *, action, activation, actor_user_id, actor_username):
        session.add(
            ETLProfileActivationEvent(
                profile_id=activation.profile_id,
                # action CHECK 제약이 거부하는 값입니다.
                action="bogus",
                deployment_active_version=activation.deployment_active_version,
                runtime_override_exists=activation.runtime_override_exists,
                runtime_active_version=activation.runtime_active_version,
                effective_active_version=activation.effective_active_version,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
            )
        )

    monkeypatch.setattr(service, "_record_activation_event", broken_record)

    with session_factory() as session:
        with pytest.raises(IntegrityError):
            set_etl_profile_activation(
                session,
                profile_id=MARKETPLACE_PROFILE_ID,
                active_version="1",
                actor_user_id=None,
                actor_username="operator_user",
            )

    with session_factory() as session:
        assert (
            session.scalars(
                select(ETLProfileActivation).where(
                    ETLProfileActivation.profile_id == MARKETPLACE_PROFILE_ID
                )
            ).one_or_none()
            is None
        )
    assert _events(session_factory) == []


def test_a_failed_event_insert_rolls_back_a_reset(
    session_factory, clean_history, monkeypatch
):
    """reset도 같습니다. override가 지워졌는데 기록이 없는 상태가 생기면 안 됩니다."""
    import db.etl_profile_activation_service as service

    _activate(session_factory, version="1")

    def raising_record(session, **kwargs):
        raise RuntimeError("history insert failed")

    monkeypatch.setattr(service, "_record_activation_event", raising_record)

    with session_factory() as session:
        with pytest.raises(RuntimeError):
            reset_etl_profile_activation(
                session,
                profile_id=MARKETPLACE_PROFILE_ID,
                actor_user_id=None,
                actor_username="operator_user",
            )

    with session_factory() as session:
        row = session.scalars(
            select(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == MARKETPLACE_PROFILE_ID
            )
        ).one_or_none()
    # override는 그대로 남아 있어야 합니다.
    assert row is not None
    assert row.active_version == "1"
    # reset event도 생기지 않았습니다. 남은 것은 앞선 activate 하나뿐입니다.
    assert [event.action for event in _events(session_factory)] == ["activate"]


# ---- 조회 --------------------------------------------------------------------


def test_history_is_newest_first(session_factory, clean_history):
    _activate(session_factory, version="1")
    _deactivate(session_factory)
    _reset(session_factory)

    with session_factory() as session:
        history = list_etl_profile_activation_history(
            session, profile_id=MARKETPLACE_PROFILE_ID, limit=20, offset=0
        )

    assert [item.action for item in history.items] == [
        "reset",
        "deactivate",
        "activate",
    ]
    # created_at이 같은 트랜잭션 시각으로 겹쳐도 id가 tie를 끊어 순서가 결정적입니다.
    assert [item.event_id for item in history.items] == sorted(
        (item.event_id for item in history.items), reverse=True
    )


def test_history_paginates_and_reports_the_total(session_factory, clean_history):
    for _ in range(3):
        _activate(session_factory, version="1")

    with session_factory() as session:
        first = list_etl_profile_activation_history(
            session, profile_id=MARKETPLACE_PROFILE_ID, limit=2, offset=0
        )
        second = list_etl_profile_activation_history(
            session, profile_id=MARKETPLACE_PROFILE_ID, limit=2, offset=2
        )

    assert first.total == 3
    assert first.limit == 2
    assert first.offset == 0
    assert len(first.items) == 2
    assert second.total == 3
    assert second.offset == 2
    assert len(second.items) == 1
    # 페이지가 겹치지 않습니다.
    assert not {item.event_id for item in first.items} & {
        item.event_id for item in second.items
    }


def test_history_only_returns_the_requested_profile(session_factory, clean_history):
    _activate(session_factory, profile_id=MARKETPLACE_PROFILE_ID, version="1")
    _activate(session_factory, profile_id=FASHION_PROFILE_ID, version="1")

    with session_factory() as session:
        history = list_etl_profile_activation_history(
            session, profile_id=FASHION_PROFILE_ID, limit=20, offset=0
        )

    assert history.total == 1
    assert [item.profile_id for item in history.items] == [FASHION_PROFILE_ID]


def test_history_of_a_profile_without_events_is_empty_not_an_error(
    session_factory, clean_history
):
    """빈 이력은 정상입니다. 이 기능 이전의 조작은 애초에 남아 있지 않습니다."""
    with session_factory() as session:
        history = list_etl_profile_activation_history(
            session, profile_id=MARKETPLACE_PROFILE_ID, limit=20, offset=0
        )

    assert history.items == []
    assert history.total == 0


@pytest.mark.parametrize("unknown_profile_id", ["nope", "sample_fashion_vendor", ""])
def test_history_of_an_unknown_profile_is_rejected(
    session_factory, clean_history, unknown_profile_id
):
    with session_factory() as session:
        with pytest.raises(ETLProfileNotFoundError):
            list_etl_profile_activation_history(
                session, profile_id=unknown_profile_id, limit=20, offset=0
            )


# ---- actor snapshot ----------------------------------------------------------


def test_the_actor_is_recorded_as_both_a_reference_and_a_snapshot(
    session_factory, clean_history, operator_account
):
    user_id, username = operator_account
    _activate(session_factory, actor_user_id=user_id, actor_username=username)

    [event] = _events(session_factory)
    assert event.actor_user_id == user_id
    assert event.actor_username == username


def test_deleting_the_user_keeps_the_recorded_username(
    session_factory, clean_history, operator_account
):
    """사용자를 지워도 "누가 했는가"는 남아야 합니다.

    FK만 NULL이 되고 snapshot은 그대로입니다. CASCADE였다면 계정 정리 한 번으로 운영
    기록이 통째로 사라집니다.
    """
    user_id, username = operator_account
    _reset(session_factory, actor_user_id=user_id, actor_username=username)

    with session_factory() as session:
        session.execute(delete(User).where(User.id == user_id))
        session.commit()

    [event] = _events(session_factory)
    assert event.actor_user_id is None
    assert event.actor_username == username


def test_the_history_view_does_not_expose_the_actor_user_id(
    session_factory, clean_history, operator_account
):
    """화면 운영자에게 필요한 것은 DB 관계용 ID가 아니라 사용자 이름입니다."""
    user_id, username = operator_account
    _activate(session_factory, actor_user_id=user_id, actor_username=username)

    with session_factory() as session:
        history = list_etl_profile_activation_history(
            session, profile_id=MARKETPLACE_PROFILE_ID, limit=20, offset=0
        )

    [item] = history.items
    assert item.actor_username == username
    assert not hasattr(item, "actor_user_id")


# ---- DB 제약: API를 우회한 잘못된 row도 막는다 --------------------------------


def _insert_event(session_factory, **values):
    defaults = {
        "profile_id": MARKETPLACE_PROFILE_ID,
        "action": "activate",
        "deployment_active_version": "2",
        "runtime_override_exists": True,
        "runtime_active_version": "1",
        "effective_active_version": "1",
        "actor_user_id": None,
        "actor_username": "operator_user",
    }
    defaults.update(values)
    with session_factory() as session:
        session.add(ETLProfileActivationEvent(**defaults))
        session.commit()


@pytest.mark.parametrize("action", ["bogus", "delete", "ACTIVATE", ""])
def test_an_unknown_action_is_rejected_by_the_database(
    session_factory, clean_history, action
):
    with pytest.raises(IntegrityError):
        _insert_event(session_factory, action=action)


@pytest.mark.parametrize("profile_id", ["", "   "])
def test_a_blank_profile_id_is_rejected_by_the_database(
    session_factory, clean_history, profile_id
):
    with pytest.raises(IntegrityError):
        _insert_event(session_factory, profile_id=profile_id)


@pytest.mark.parametrize("blank_version", ["", "   "])
def test_a_blank_version_is_rejected_by_the_database(
    session_factory, clean_history, blank_version
):
    """비활성을 뜻하는 값은 NULL 하나뿐입니다. ''는 "비어 있는 pointer"가 아닙니다."""
    with pytest.raises(IntegrityError):
        _insert_event(
            session_factory,
            runtime_active_version=blank_version,
            effective_active_version=blank_version,
        )
    with pytest.raises(IntegrityError):
        _insert_event(session_factory, deployment_active_version=blank_version)


def test_an_event_contradicting_its_own_action_is_rejected(
    session_factory, clean_history
):
    """모순된 기록은 없는 기록보다 나쁩니다. 나중에 읽는 사람이 그것을 믿습니다."""
    # activate인데 override가 없다
    with pytest.raises(IntegrityError):
        _insert_event(
            session_factory,
            action="activate",
            runtime_override_exists=False,
            runtime_active_version=None,
            effective_active_version=None,
        )
    # deactivate인데 실제 적용 버전이 있다
    with pytest.raises(IntegrityError):
        _insert_event(
            session_factory,
            action="deactivate",
            runtime_active_version=None,
            effective_active_version="2",
        )
    # reset인데 override가 남아 있다
    with pytest.raises(IntegrityError):
        _insert_event(
            session_factory,
            action="reset",
            runtime_override_exists=True,
            runtime_active_version=None,
            effective_active_version="2",
        )
    # reset인데 실제 적용 버전이 배포 기본값과 다르다
    with pytest.raises(IntegrityError):
        _insert_event(
            session_factory,
            action="reset",
            runtime_override_exists=False,
            runtime_active_version=None,
            deployment_active_version="2",
            effective_active_version="1",
        )


def test_a_reset_event_with_no_deployment_default_is_allowed(
    session_factory, clean_history
):
    """배포 기본값 자체가 비활성이면 reset 뒤에도 비활성입니다.

    NULL = NULL이 참이 아닌 PostgreSQL에서 이 경우를 '='로 검사했다면 제약이 조용히
    통과시키거나(또는 정반대로 막아) 실제 상태를 기록할 수 없게 됩니다.
    """
    _insert_event(
        session_factory,
        action="reset",
        runtime_override_exists=False,
        runtime_active_version=None,
        deployment_active_version=None,
        effective_active_version=None,
    )

    [event] = _events(session_factory)
    assert event.action == "reset"
    assert event.effective_active_version is None
