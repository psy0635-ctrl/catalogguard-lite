"""add ordered index for promotion audit pagination

Revision ID: 20260808_0011
Revises: 20260806_0010
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260808_0011"
down_revision: str | None = "20260806_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEX_NAME = "ix_catalog_product_changes_promotion_run_created_at_id"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "catalog_product_changes",
        [
            "promotion_run_id",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="catalog_product_changes")
