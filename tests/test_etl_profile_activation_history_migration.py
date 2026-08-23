"""Migration 20260823_0015: the append-only activation history table.

Phase 5B.4 of docs/etl_profile_lifecycle.md.

이 migration이 지켜야 할 가장 중요한 계약은 스키마 모양이 아니라 **기존 상태로 과거
이력을 만들어 내지 않는다**는 것입니다. current-state row 하나만으로는 누가 처음
활성화했는지, 몇 번 바꿨는지 알 수 없으므로, 추측해 채우면 없는 기록보다 나쁜 틀린
기록이 남습니다.
"""
from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import BigInteger, Boolean, String, text

from config.database import get_optional_database_url
from db.models import ETLProfileActivationEvent
from db.session import create_database_engine


EVENTS_TABLE = "etl_profile_activation_events"
HISTORY_INDEX = "ix_etl_profile_activation_events_profile_created_at_id"
PREVIOUS_REVISION = "20260822_0014"
REVISION = "20260823_0015"


# ---- 스크립트 그래프: DB 없이도 확인할 수 있는 것 ----------------------------


def test_activation_history_migration_is_the_single_alembic_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert list(script.get_heads()) == [REVISION]
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION


def test_event_model_columns_match_the_audit_contract() -> None:
    columns = ETLProfileActivationEvent.__table__.columns

    assert isinstance(columns["id"].type, BigInteger)
    assert columns["id"].primary_key is True
    assert isinstance(columns["profile_id"].type, String)
    assert columns["profile_id"].nullable is False
    assert isinstance(columns["action"].type, String)
    assert columns["action"].nullable is False
    assert isinstance(columns["runtime_override_exists"].type, Boolean)
    assert columns["runtime_override_exists"].nullable is False
    # 세 버전 값은 모두 NULL일 수 있습니다. 비활성 상태를 기록할 수 없으면 audit이
    # 표현할 수 있는 상태가 실제 상태보다 좁아집니다.
    for name in (
        "deployment_active_version",
        "runtime_active_version",
        "effective_active_version",
    ):
        assert columns[name].nullable is True
    assert columns["created_at"].nullable is False

    # profile_id에는 FK가 없습니다. 프로필은 아직 DB entity가 아니라 코드 registry의
    # key이므로, 존재하지 않는 대상을 가리키는 FK를 만들 수 없습니다.
    assert not columns["profile_id"].foreign_keys

    [actor_fk] = list(columns["actor_user_id"].foreign_keys)
    assert actor_fk.target_fullname == "users.id"
    # 사용자를 지워도 기록은 남아야 하므로 CASCADE가 아니라 SET NULL입니다.
    assert actor_fk.ondelete == "SET NULL"
    assert columns["actor_user_id"].nullable is True
    assert columns["actor_username"].nullable is True


# ---- 실제 PostgreSQL에서의 upgrade / downgrade -------------------------------


@pytest.fixture(name="alembic_config")
def fixture_alembic_config(monkeypatch):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 Alembic 통합 테스트를 건너뜁니다.")

    # env.py가 get_database_url()로 읽는 값입니다.
    monkeypatch.setenv("DATABASE_URL", database_url)
    return Config("alembic.ini")


@pytest.fixture(name="engine")
def fixture_engine():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(name="head_restored")
def fixture_head_restored(alembic_config):
    """이 파일이 downgrade한 상태를 다른 테스트에 물려주지 않습니다."""
    yield
    command.upgrade(alembic_config, "head")


def _table_exists(connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"public.{table_name}"},
        ).scalar()
    )


def _column_types(connection, table_name: str) -> dict[str, tuple[str, str]]:
    rows = connection.execute(
        text(
            "SELECT column_name, data_type, is_nullable"
            " FROM information_schema.columns WHERE table_name = :name"
        ),
        {"name": table_name},
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def test_upgrade_creates_the_event_table_with_its_constraints(
    alembic_config, engine
) -> None:
    command.upgrade(alembic_config, "head")

    with engine.connect() as connection:
        assert _table_exists(connection, EVENTS_TABLE)

        columns = _column_types(connection, EVENTS_TABLE)
        assert columns["id"] == ("bigint", "NO")
        assert columns["profile_id"] == ("character varying", "NO")
        assert columns["action"] == ("character varying", "NO")
        assert columns["runtime_override_exists"] == ("boolean", "NO")
        assert columns["deployment_active_version"] == ("character varying", "YES")
        assert columns["runtime_active_version"] == ("character varying", "YES")
        assert columns["effective_active_version"] == ("character varying", "YES")
        assert columns["actor_user_id"] == ("bigint", "YES")
        assert columns["actor_username"] == ("character varying", "YES")
        assert columns["created_at"] == ("timestamp with time zone", "NO")

        primary_key = connection.execute(
            text(
                "SELECT a.attname FROM pg_index i"
                " JOIN pg_attribute a ON a.attrelid = i.indrelid"
                " AND a.attnum = ANY(i.indkey)"
                " WHERE i.indrelid = cast(:table AS regclass) AND i.indisprimary"
            ),
            {"table": EVENTS_TABLE},
        ).scalars().all()
        assert list(primary_key) == ["id"]

        check_names = set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint"
                    " WHERE conrelid = cast(:table AS regclass) AND contype = 'c'"
                ),
                {"table": EVENTS_TABLE},
            ).scalars().all()
        )
        assert {
            "ck_etl_profile_activation_events_profile_id_not_blank",
            "ck_etl_profile_activation_events_action",
            "ck_etl_profile_activation_events_deployment_version_not_blank",
            "ck_etl_profile_activation_events_runtime_version_not_blank",
            "ck_etl_profile_activation_events_effective_version_not_blank",
            "ck_etl_profile_activation_events_state_matches_action",
        } <= check_names

        foreign_key = connection.execute(
            text(
                "SELECT confdeltype FROM pg_constraint"
                " WHERE conrelid = cast(:table AS regclass) AND contype = 'f'"
            ),
            {"table": EVENTS_TABLE},
        ).scalar()
        # 'n' = ON DELETE SET NULL. 사용자를 지워도 기록 자체는 남습니다.
        assert foreign_key == "n"

        index_columns = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": HISTORY_INDEX},
        ).scalar()
        assert index_columns is not None
        assert "profile_id" in index_columns
        assert "created_at" in index_columns


def test_downgrade_removes_only_the_history_table(
    alembic_config, engine, head_restored
) -> None:
    """current-state 표는 이 migration이 만든 것이 아니므로 건드리지 않습니다."""
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, PREVIOUS_REVISION)

    with engine.connect() as connection:
        assert not _table_exists(connection, EVENTS_TABLE)
        assert _table_exists(connection, "etl_profile_activations")
        assert (
            connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE indexname = :name"),
                {"name": HISTORY_INDEX},
            ).scalar()
            is None
        )

    # 다시 올려도 성공해야 합니다. 한 번만 되는 migration은 배포에서 되돌릴 수 없습니다.
    command.upgrade(alembic_config, REVISION)
    with engine.connect() as connection:
        assert _table_exists(connection, EVENTS_TABLE)


def test_upgrade_does_not_invent_history_for_an_existing_activation(
    alembic_config, engine, head_restored
) -> None:
    """0014 상태에 이미 있던 override로 과거 event를 만들어 내지 않습니다.

    이 표 하나로는 "누가 언제 이 상태를 만들었는가" 말고는 아무것도 알 수 없습니다.
    그것으로 activate/deactivate/reset의 순서를 지어내면 나중에 읽는 사람이 그 지어낸
    기록을 사실로 믿습니다. history는 반드시 빈 표에서 시작합니다.
    """
    command.downgrade(alembic_config, PREVIOUS_REVISION)

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM etl_profile_activations WHERE profile_id = :profile_id"),
            {"profile_id": "sample_marketplace_vendor_v1"},
        )
        connection.execute(
            text(
                "INSERT INTO etl_profile_activations"
                " (profile_id, active_version, actor_username)"
                " VALUES (:profile_id, :active_version, :actor_username)"
            ),
            {
                "profile_id": "sample_marketplace_vendor_v1",
                "active_version": "1",
                "actor_username": "before_history_operator",
            },
        )

    command.upgrade(alembic_config, REVISION)

    with engine.connect() as connection:
        assert (
            connection.execute(
                text(f"SELECT count(*) FROM {EVENTS_TABLE}")
            ).scalar()
            == 0
        )
        # 기존 current-state row는 그대로 남습니다. history 도입이 지금 적용 중인
        # runtime override를 바꾸면 안 됩니다.
        row = connection.execute(
            text(
                "SELECT active_version, actor_username FROM etl_profile_activations"
                " WHERE profile_id = :profile_id"
            ),
            {"profile_id": "sample_marketplace_vendor_v1"},
        ).one()
        assert row[0] == "1"
        assert row[1] == "before_history_operator"

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM etl_profile_activations WHERE profile_id = :profile_id"),
            {"profile_id": "sample_marketplace_vendor_v1"},
        )
