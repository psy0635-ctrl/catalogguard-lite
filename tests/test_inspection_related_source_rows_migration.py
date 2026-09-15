"""Migration contract for explicit relationships, including offline SQL."""

from io import StringIO

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


def test_relationship_migration_head_and_reversible_sql(monkeypatch):
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["20260915_0020"]
    revision = script.get_revision("20260915_0020")
    assert revision.down_revision == "20260908_0019"
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.upgrade()
    upgrade = output.getvalue()
    assert "ADD COLUMN related_source_rows JSONB" in upgrade
    assert "jsonb_typeof(related_source_rows) = 'array'" in upgrade
    assert "DEFAULT" not in upgrade
    assert "UPDATE" not in upgrade
    revision.module.downgrade()
    assert "DROP CONSTRAINT ck_inspection_results_related_source_rows_array" in output.getvalue()
    assert "DROP COLUMN related_source_rows" in output.getvalue()
