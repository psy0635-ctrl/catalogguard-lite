"""Add explicit inspection duplicate row relationships without backfill."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260915_0020"
down_revision = "20260908_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspection_results",
        sa.Column("related_source_rows", JSONB(none_as_null=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_inspection_results_related_source_rows_array",
        "inspection_results",
        "related_source_rows IS NULL OR jsonb_typeof(related_source_rows) = 'array'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_inspection_results_related_source_rows_array",
        "inspection_results", type_="check",
    )
    op.drop_column("inspection_results", "related_source_rows")
