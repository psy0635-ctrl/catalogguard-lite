"""add ETL quality summary columns

Revision ID: 20260727_0004
Revises: 20260725_0003
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260727_0004"
down_revision: str | None = "20260725_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "etl_load_runs",
        sa.Column("total_rows", sa.Integer(), nullable=True),
    )
    op.add_column(
        "etl_load_runs",
        sa.Column("rejected_rows", sa.Integer(), nullable=True),
    )
    op.add_column(
        "etl_load_runs",
        sa.Column("error_counts", postgresql.JSONB(), nullable=True),
    )
    op.create_check_constraint(
        "ck_etl_load_runs_total_rows_non_negative",
        "etl_load_runs",
        "total_rows IS NULL OR total_rows >= 0",
    )
    op.create_check_constraint(
        "ck_etl_load_runs_rejected_rows_non_negative",
        "etl_load_runs",
        "rejected_rows IS NULL OR rejected_rows >= 0",
    )
    op.create_check_constraint(
        "ck_etl_load_runs_quality_summary_all_or_none",
        "etl_load_runs",
        """
        (
            total_rows IS NULL
            AND rejected_rows IS NULL
            AND error_counts IS NULL
        )
        OR
        (
            total_rows IS NOT NULL
            AND rejected_rows IS NOT NULL
            AND error_counts IS NOT NULL
        )
        """,
    )
    op.create_check_constraint(
        "ck_etl_load_runs_total_rows_matches_loaded_and_rejected",
        "etl_load_runs",
        "total_rows IS NULL OR total_rows = loaded_rows + rejected_rows",
    )
    op.create_check_constraint(
        "ck_etl_load_runs_error_counts_object",
        "etl_load_runs",
        "error_counts IS NULL OR jsonb_typeof(error_counts) = 'object'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_etl_load_runs_error_counts_object",
        "etl_load_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_etl_load_runs_total_rows_matches_loaded_and_rejected",
        "etl_load_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_etl_load_runs_quality_summary_all_or_none",
        "etl_load_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_etl_load_runs_rejected_rows_non_negative",
        "etl_load_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_etl_load_runs_total_rows_non_negative",
        "etl_load_runs",
        type_="check",
    )
    op.drop_column("etl_load_runs", "error_counts")
    op.drop_column("etl_load_runs", "rejected_rows")
    op.drop_column("etl_load_runs", "total_rows")
