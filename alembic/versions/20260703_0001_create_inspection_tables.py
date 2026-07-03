"""create inspection tables

Revision ID: 20260703_0001
Revises:
Create Date: 2026-07-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260703_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inspection_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("total_products", sa.Integer(), nullable=False),
        sa.Column("total_issues", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "error_count >= 0",
            name="ck_inspection_runs_error_count_non_negative",
        ),
        sa.CheckConstraint(
            "total_issues >= 0",
            name="ck_inspection_runs_total_issues_non_negative",
        ),
        sa.CheckConstraint(
            "total_products >= 0",
            name="ck_inspection_runs_total_products_non_negative",
        ),
        sa.CheckConstraint(
            "warning_count >= 0",
            name="ck_inspection_runs_warning_count_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inspection_runs_created_at",
        "inspection_runs",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "inspection_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("inspection_run_id", sa.BigInteger(), nullable=False),
        sa.Column("product_group_id", sa.String(length=100), nullable=True),
        sa.Column("product_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_field", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inspection_run_id"],
            ["inspection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inspection_results_inspection_run_id",
        "inspection_results",
        ["inspection_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_inspection_results_product_id",
        "inspection_results",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_inspection_results_status",
        "inspection_results",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_inspection_results_status", table_name="inspection_results")
    op.drop_index("ix_inspection_results_product_id", table_name="inspection_results")
    op.drop_index(
        "ix_inspection_results_inspection_run_id",
        table_name="inspection_results",
    )
    op.drop_table("inspection_results")
    op.drop_index("ix_inspection_runs_created_at", table_name="inspection_runs")
    op.drop_table("inspection_runs")
