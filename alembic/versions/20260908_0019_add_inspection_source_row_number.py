"""add inspection result source row number

Revision ID: 20260908_0019
Revises: 20260826_0018
"""

from alembic import op
import sqlalchemy as sa


revision = "20260908_0019"
down_revision = "20260826_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspection_results",
        sa.Column("source_row_number", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_inspection_results_source_row_number_minimum",
        "inspection_results",
        "source_row_number IS NULL OR source_row_number >= 2",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_inspection_results_source_row_number_minimum",
        "inspection_results",
        type_="check",
    )
    op.drop_column("inspection_results", "source_row_number")
