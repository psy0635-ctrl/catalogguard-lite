"""add ETL profile definition snapshot lineage

Revision ID: 20260826_0018
Revises: 20260826_0017
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260826_0018"
down_revision = "20260826_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "etl_load_runs",
        sa.Column(
            "profile_definition_snapshot",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("etl_load_runs", "profile_definition_snapshot")
