"""create ETL load and catalog staging tables

Revision ID: 20260725_0003
Revises: 20260705_0002
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260725_0003"
down_revision: str | None = "20260705_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "etl_load_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("profile_name", sa.String(length=100), nullable=False),
        sa.Column("profile_version", sa.String(length=20), nullable=False),
        sa.Column("input_file_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_file_sha256", sa.String(length=64), nullable=False),
        sa.Column("loaded_rows", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "loaded_rows >= 0",
            name="ck_etl_load_runs_loaded_rows_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_etl_load_runs_input_profile_version",
        "etl_load_runs",
        ["input_file_sha256", "profile_name", "profile_version"],
        unique=True,
    )

    op.create_table(
        "catalog_products_staging",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("etl_load_run_id", sa.BigInteger(), nullable=False),
        sa.Column("product_group_id", sa.String(length=100), nullable=False),
        sa.Column("product_id", sa.String(length=100), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=100), nullable=False),
        sa.Column("size", sa.String(length=100), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("sale_price", sa.BigInteger(), nullable=True),
        sa.Column("image_path", sa.String(length=2048), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("seller", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stock >= 0",
            name="ck_catalog_products_staging_stock_non_negative",
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_catalog_products_staging_price_non_negative",
        ),
        sa.CheckConstraint(
            "sale_price IS NULL OR sale_price >= 0",
            name="ck_catalog_products_staging_sale_price_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["etl_load_run_id"],
            ["etl_load_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalog_products_staging_etl_load_run_id",
        "catalog_products_staging",
        ["etl_load_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalog_products_staging_etl_load_run_id",
        table_name="catalog_products_staging",
    )
    op.drop_table("catalog_products_staging")
    op.drop_index(
        "ux_etl_load_runs_input_profile_version",
        table_name="etl_load_runs",
    )
    op.drop_table("etl_load_runs")
