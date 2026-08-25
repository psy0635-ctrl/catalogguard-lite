"""add ETL profile definition fingerprint

Revision ID: 20260825_0016
Revises: 20260823_0015
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0016"
down_revision = "20260823_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "etl_load_runs",
        sa.Column("profile_definition_sha256", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("etl_load_runs", "profile_definition_sha256")
