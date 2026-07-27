"""store validated and masked ETL reject rows

Revision ID: 20260728_0005
Revises: 20260727_0004
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260728_0005"
down_revision: str | None = "20260727_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "etl_load_runs",
        sa.Column(
            "reject_details_stored",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "etl_load_runs",
        sa.Column("rejects_file_sha256", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_etl_load_runs_reject_details_state",
        "etl_load_runs",
        """
        (
            reject_details_stored = false
            AND rejects_file_sha256 IS NULL
        )
        OR
        (
            reject_details_stored = true
            AND rejects_file_sha256 IS NOT NULL
            AND length(rejects_file_sha256) = 64
        )
        """,
    )

    op.create_table(
        "etl_rejected_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("etl_load_run_id", sa.BigInteger(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("errors", postgresql.JSONB(), nullable=False),
        sa.Column("masked_source_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_row_number >= 2",
            name="ck_etl_rejected_rows_source_row_number_min",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(errors) = 'array'",
            name="ck_etl_rejected_rows_errors_array",
        ),
        sa.CheckConstraint(
            "jsonb_array_length(errors) > 0",
            name="ck_etl_rejected_rows_errors_non_empty",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(masked_source_data) = 'object'",
            name="ck_etl_rejected_rows_masked_source_data_object",
        ),
        sa.ForeignKeyConstraint(
            ["etl_load_run_id"],
            ["etl_load_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_etl_rejected_rows_etl_load_run_id",
        "etl_rejected_rows",
        ["etl_load_run_id"],
        unique=False,
    )
    op.create_index(
        "ux_etl_rejected_rows_load_run_source_row",
        "etl_rejected_rows",
        ["etl_load_run_id", "source_row_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_etl_rejected_rows_load_run_source_row",
        table_name="etl_rejected_rows",
    )
    op.drop_index(
        "ix_etl_rejected_rows_etl_load_run_id",
        table_name="etl_rejected_rows",
    )
    op.drop_table("etl_rejected_rows")
    op.drop_constraint(
        "ck_etl_load_runs_reject_details_state",
        "etl_load_runs",
        type_="check",
    )
    op.drop_column("etl_load_runs", "rejects_file_sha256")
    op.drop_column("etl_load_runs", "reject_details_stored")
