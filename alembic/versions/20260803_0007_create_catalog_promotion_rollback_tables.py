"""create catalog promotion rollback tables

Revision ID: 20260803_0007
Revises: 20260728_0006
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260803_0007"
down_revision: str | None = "20260728_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_promotion_rollbacks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("target_promotion_run_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("preview_hash", sa.String(length=64), nullable=True),
        sa.Column("preview_schema_version", sa.String(length=20), nullable=True),
        sa.Column("restored_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("deleted_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("conflict_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("safe_failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('applying', 'succeeded', 'failed', 'blocked')", name="ck_catalog_promotion_rollbacks_status"),
        sa.CheckConstraint("preview_hash IS NULL OR length(preview_hash) = 64", name="ck_catalog_promotion_rollbacks_preview_hash_length"),
        sa.CheckConstraint("restored_count >= 0", name="ck_catalog_promotion_rollbacks_restored_count_non_negative"),
        sa.CheckConstraint("deleted_count >= 0", name="ck_catalog_promotion_rollbacks_deleted_count_non_negative"),
        sa.CheckConstraint("conflict_count >= 0", name="ck_catalog_promotion_rollbacks_conflict_count_non_negative"),
        sa.CheckConstraint("(status = 'applying' AND completed_at IS NULL) OR (status IN ('succeeded', 'failed', 'blocked') AND completed_at IS NOT NULL)", name="ck_catalog_promotion_rollbacks_completed_at_matches_status"),
        sa.ForeignKeyConstraint(["target_promotion_run_id"], ["catalog_promotion_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_catalog_promotion_rollbacks_target_promotion_run", "catalog_promotion_rollbacks", ["target_promotion_run_id"], unique=True, postgresql_where=sa.text("status = 'succeeded'"))
    op.create_index("ix_catalog_promotion_rollbacks_status", "catalog_promotion_rollbacks", ["status"], unique=False)

    op.create_table(
        "catalog_promotion_rollback_changes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rollback_run_id", sa.BigInteger(), nullable=False),
        sa.Column("original_audit_id", sa.BigInteger(), nullable=False),
        sa.Column("catalog_product_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(), nullable=False),
        sa.Column("before_data", postgresql.JSONB(), nullable=False),
        sa.Column("after_data", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("action IN ('delete', 'restore')", name="ck_catalog_promotion_rollback_changes_action"),
        sa.CheckConstraint("jsonb_typeof(changed_fields) = 'object'", name="ck_catalog_promotion_rollback_changes_changed_fields_object"),
        sa.CheckConstraint("changed_fields <> '{}'::jsonb", name="ck_catalog_promotion_rollback_changes_changed_fields_non_empty"),
        sa.CheckConstraint("jsonb_typeof(before_data) = 'object'", name="ck_catalog_promotion_rollback_changes_before_data_object"),
        sa.CheckConstraint("after_data IS NULL OR jsonb_typeof(after_data) = 'object'", name="ck_catalog_promotion_rollback_changes_after_data_object"),
        sa.CheckConstraint("(action = 'delete' AND after_data IS NULL) OR (action = 'restore' AND after_data IS NOT NULL)", name="ck_catalog_promotion_rollback_changes_after_data_matches_action"),
        sa.ForeignKeyConstraint(["rollback_run_id"], ["catalog_promotion_rollbacks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["original_audit_id"], ["catalog_product_changes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["catalog_product_id"], ["catalog_products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_promotion_rollback_changes_rollback_run_id", "catalog_promotion_rollback_changes", ["rollback_run_id"], unique=False)
    op.create_index("ix_catalog_promotion_rollback_changes_catalog_product_id", "catalog_promotion_rollback_changes", ["catalog_product_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_catalog_promotion_rollback_changes_catalog_product_id", table_name="catalog_promotion_rollback_changes")
    op.drop_index("ix_catalog_promotion_rollback_changes_rollback_run_id", table_name="catalog_promotion_rollback_changes")
    op.drop_table("catalog_promotion_rollback_changes")
    op.drop_index("ix_catalog_promotion_rollbacks_status", table_name="catalog_promotion_rollbacks")
    op.drop_index("ux_catalog_promotion_rollbacks_target_promotion_run", table_name="catalog_promotion_rollbacks")
    op.drop_table("catalog_promotion_rollbacks")
