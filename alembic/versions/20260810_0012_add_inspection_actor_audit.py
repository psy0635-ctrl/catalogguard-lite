"""add actor audit columns to inspection runs

Revision ID: 20260810_0012
Revises: 20260808_0011
Create Date: 2026-08-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260810_0012"
down_revision: str | None = "20260808_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inspection_runs",
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "inspection_runs",
        sa.Column("actor_username", sa.String(length=50), nullable=True),
    )
    op.create_foreign_key(
        "fk_inspection_runs_actor_user_id",
        "inspection_runs",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inspection_runs_actor_user_id",
        "inspection_runs",
        type_="foreignkey",
    )
    op.drop_column("inspection_runs", "actor_username")
    op.drop_column("inspection_runs", "actor_user_id")
