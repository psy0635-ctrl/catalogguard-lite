"""create users table

Revision ID: 20260805_0009
Revises: 20260803_0008
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260805_0009"
down_revision: str | None = "20260803_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('viewer', 'operator')",
            name="ck_users_role",
        ),
        sa.CheckConstraint(
            "length(trim(username)) > 0",
            name="ck_users_username_not_blank",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_users_username",
        "users",
        ["username"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_users_username", table_name="users")
    op.drop_table("users")
