"""create catalog promotion tables

Revision ID: 20260728_0006
Revises: 20260728_0005
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260728_0006"
down_revision: str | None = "20260728_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("supplier_key", sa.String(length=100), nullable=False),
        sa.Column("external_product_id", sa.String(length=100), nullable=False),
        sa.Column("product_group_id", sa.String(length=100), nullable=False),
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
        sa.Column("source_etl_load_run_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stock >= 0",
            name="ck_catalog_products_stock_non_negative",
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_catalog_products_price_non_negative",
        ),
        sa.CheckConstraint(
            "sale_price IS NULL OR sale_price >= 0",
            name="ck_catalog_products_sale_price_non_negative",
        ),
        sa.CheckConstraint(
            "length(trim(supplier_key)) > 0",
            name="ck_catalog_products_supplier_key_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(external_product_id)) > 0",
            name="ck_catalog_products_external_product_id_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["source_etl_load_run_id"],
            ["etl_load_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_catalog_products_supplier_external_product",
        "catalog_products",
        ["supplier_key", "external_product_id"],
        unique=True,
    )
    op.create_index(
        "ix_catalog_products_source_etl_load_run_id",
        "catalog_products",
        ["source_etl_load_run_id"],
        unique=False,
    )

    op.create_table(
        "catalog_promotion_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("etl_load_run_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("preview_hash", sa.String(length=64), nullable=True),
        sa.Column("preview_schema_version", sa.String(length=20), nullable=True),
        sa.Column("inspection_version", sa.String(length=20), nullable=True),
        sa.Column(
            "inserted_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "updated_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "unchanged_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "blocked_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "error_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "warning_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("safe_failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('applying', 'succeeded', 'failed', 'blocked')",
            name="ck_catalog_promotion_runs_status",
        ),
        sa.CheckConstraint(
            "preview_hash IS NULL OR length(preview_hash) = 64",
            name="ck_catalog_promotion_runs_preview_hash_length",
        ),
        sa.CheckConstraint(
            "inserted_count >= 0",
            name="ck_catalog_promotion_runs_inserted_count_non_negative",
        ),
        sa.CheckConstraint(
            "updated_count >= 0",
            name="ck_catalog_promotion_runs_updated_count_non_negative",
        ),
        sa.CheckConstraint(
            "unchanged_count >= 0",
            name="ck_catalog_promotion_runs_unchanged_count_non_negative",
        ),
        sa.CheckConstraint(
            "blocked_count >= 0",
            name="ck_catalog_promotion_runs_blocked_count_non_negative",
        ),
        sa.CheckConstraint(
            "error_count >= 0",
            name="ck_catalog_promotion_runs_error_count_non_negative",
        ),
        sa.CheckConstraint(
            "warning_count >= 0",
            name="ck_catalog_promotion_runs_warning_count_non_negative",
        ),
        sa.CheckConstraint(
            """
            (status = 'applying' AND completed_at IS NULL)
            OR
            (status IN ('succeeded', 'failed', 'blocked') AND completed_at IS NOT NULL)
            """,
            name="ck_catalog_promotion_runs_completed_at_matches_status",
        ),
        sa.ForeignKeyConstraint(
            ["etl_load_run_id"],
            ["etl_load_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalog_promotion_runs_etl_load_run_id",
        "catalog_promotion_runs",
        ["etl_load_run_id"],
        unique=False,
    )
    op.create_index(
        "ux_catalog_promotion_runs_succeeded_etl_load_run",
        "catalog_promotion_runs",
        ["etl_load_run_id"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
    )

    op.create_table(
        "catalog_product_changes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("promotion_run_id", sa.BigInteger(), nullable=False),
        sa.Column("catalog_product_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(), nullable=False),
        sa.Column(
            "before_data",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
        ),
        sa.Column("after_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('insert', 'update')",
            name="ck_catalog_product_changes_action",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(changed_fields) = 'object'",
            name="ck_catalog_product_changes_changed_fields_object",
        ),
        sa.CheckConstraint(
            "changed_fields <> '{}'::jsonb",
            name="ck_catalog_product_changes_changed_fields_non_empty",
        ),
        sa.CheckConstraint(
            "before_data IS NULL OR jsonb_typeof(before_data) = 'object'",
            name="ck_catalog_product_changes_before_data_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(after_data) = 'object'",
            name="ck_catalog_product_changes_after_data_object",
        ),
        sa.CheckConstraint(
            """
            (action = 'insert' AND before_data IS NULL)
            OR
            (action = 'update' AND before_data IS NOT NULL)
            """,
            name="ck_catalog_product_changes_before_data_matches_action",
        ),
        sa.ForeignKeyConstraint(
            ["promotion_run_id"],
            ["catalog_promotion_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_product_id"],
            ["catalog_products.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalog_product_changes_promotion_run_id",
        "catalog_product_changes",
        ["promotion_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_product_changes_catalog_product_id",
        "catalog_product_changes",
        ["catalog_product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalog_product_changes_catalog_product_id",
        table_name="catalog_product_changes",
    )
    op.drop_index(
        "ix_catalog_product_changes_promotion_run_id",
        table_name="catalog_product_changes",
    )
    op.drop_table("catalog_product_changes")

    op.drop_index(
        "ux_catalog_promotion_runs_succeeded_etl_load_run",
        table_name="catalog_promotion_runs",
    )
    op.drop_index(
        "ix_catalog_promotion_runs_etl_load_run_id",
        table_name="catalog_promotion_runs",
    )
    op.drop_table("catalog_promotion_runs")

    op.drop_index(
        "ix_catalog_products_source_etl_load_run_id",
        table_name="catalog_products",
    )
    op.drop_index(
        "ux_catalog_products_supplier_external_product",
        table_name="catalog_products",
    )
    op.drop_table("catalog_products")
