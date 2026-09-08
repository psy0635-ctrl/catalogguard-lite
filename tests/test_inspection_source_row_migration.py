"""Schema contract for persisted inspection source-row identity."""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Integer

from db.models import InspectionResult


REVISION = "20260908_0019"
PREVIOUS_REVISION = "20260826_0018"
COLUMN = "source_row_number"
CHECK_CONSTRAINT = "ck_inspection_results_source_row_number_minimum"


def test_source_row_migration_is_the_single_alembic_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert list(script.get_heads()) == [REVISION]
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION


def test_source_row_column_is_nullable_integer_with_logical_row_check() -> None:
    column = InspectionResult.__table__.columns[COLUMN]

    assert isinstance(column.type, Integer)
    assert column.nullable is True
    assert column.server_default is None
    assert CHECK_CONSTRAINT in {
        constraint.name for constraint in InspectionResult.__table__.constraints
    }
