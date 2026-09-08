from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_migrations_have_a_single_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert list(script.get_heads()) == ["20260908_0019"]
    revision = script.get_revision("20260728_0006")
    assert revision is not None
    assert revision.down_revision == "20260728_0005"
