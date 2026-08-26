"""add ETL application commit lineage

Revision ID: 20260826_0017
Revises: 20260825_0016
"""

from alembic import op
import sqlalchemy as sa


revision = "20260826_0017"
down_revision = "20260825_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "etl_load_runs",
        sa.Column("application_commit_sha", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("etl_load_runs", "application_commit_sha")
