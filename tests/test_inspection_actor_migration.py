from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import BigInteger, String

from db.models import InspectionRun


def test_inspection_run_actor_columns_are_nullable_and_user_fk_sets_null() -> None:
    actor_user_id = InspectionRun.__table__.columns["actor_user_id"]
    actor_username = InspectionRun.__table__.columns["actor_username"]

    assert isinstance(actor_user_id.type, BigInteger)
    assert actor_user_id.nullable is True
    assert isinstance(actor_username.type, String)
    assert actor_username.type.length == 50
    assert actor_username.nullable is True

    [foreign_key] = list(actor_user_id.foreign_keys)
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "SET NULL"


def test_inspection_actor_migration_is_the_single_alembic_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert list(script.get_heads()) == ["20260813_0013"]
    revision = script.get_revision("20260810_0012")
    assert revision is not None
    assert revision.down_revision == "20260808_0011"
