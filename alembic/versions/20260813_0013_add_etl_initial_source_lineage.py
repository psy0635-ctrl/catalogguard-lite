"""add initial source lineage columns to etl load runs

Revision ID: 20260813_0013
Revises: 20260810_0012
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_0013"
down_revision: str | None = "20260810_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ALLOWED_SOURCE_TYPES = ("unknown", "upload", "s3", "http_feed", "cli")


def upgrade() -> None:
    # 기존 row에는 실제 출처 정보가 없습니다. source_filename이나 actor로 과거 source를 추측하지 않고
    # 정직하게 'unknown'으로 채웁니다. server_default는 backfill에만 쓰고 곧바로 제거해,
    # 이후 신규 row가 값을 넘기지 않으면 조용히 unknown이 되지 않고 드러나게 합니다.
    op.add_column(
        "etl_load_runs",
        sa.Column(
            "initial_source_type",
            sa.String(length=20),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.alter_column("etl_load_runs", "initial_source_type", server_default=None)
    op.add_column(
        "etl_load_runs",
        sa.Column("initial_source_ref", sa.String(length=255), nullable=True),
    )
    op.create_check_constraint(
        "ck_etl_load_runs_initial_source_type",
        "etl_load_runs",
        "initial_source_type IN ("
        + ", ".join(f"'{value}'" for value in ALLOWED_SOURCE_TYPES)
        + ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_etl_load_runs_initial_source_type",
        "etl_load_runs",
        type_="check",
    )
    op.drop_column("etl_load_runs", "initial_source_ref")
    op.drop_column("etl_load_runs", "initial_source_type")
