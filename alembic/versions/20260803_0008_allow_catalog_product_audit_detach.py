"""allow operational products to be deleted while retaining audit history

Revision ID: 20260803_0008
Revises: 20260803_0007
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260803_0008"
down_revision: str | None = "20260803_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "catalog_product_changes_catalog_product_id_fkey",
        "catalog_product_changes",
        type_="foreignkey",
    )
    op.drop_constraint(
        "catalog_promotion_rollback_changes_catalog_product_id_fkey",
        "catalog_promotion_rollback_changes",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "catalog_promotion_rollback_changes_catalog_product_id_fkey",
        "catalog_promotion_rollback_changes",
        "catalog_products",
        ["catalog_product_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "catalog_product_changes_catalog_product_id_fkey",
        "catalog_product_changes",
        "catalog_products",
        ["catalog_product_id"],
        ["id"],
        ondelete="RESTRICT",
    )
