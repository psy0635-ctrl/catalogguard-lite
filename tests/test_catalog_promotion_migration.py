from alembic.config import Config
from alembic.script import ScriptDirectory


def test_catalog_promotion_migration_is_the_single_alembic_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert list(script.get_heads()) == ["20260826_0018"]
    revision = script.get_revision("20260728_0006")
    assert revision is not None
    assert revision.down_revision == "20260728_0005"
