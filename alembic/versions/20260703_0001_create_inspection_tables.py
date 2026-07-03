# 역할: 검수 실행과 상세 결과를 저장할 초기 PostgreSQL 테이블을 생성합니다.
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
    # 먼저 검수 실행 요약을 담는 부모 테이블을 만듭니다.
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
    # 최신 실행 기록을 빠르게 정렬/조회할 수 있도록 생성 시각 인덱스를 둡니다.
    op.create_index(
        "ix_inspection_runs_created_at",
        "inspection_runs",
        ["created_at"],
        unique=False,
    )

    # 그다음 실행 기록에 연결되는 상세 문제 테이블을 만듭니다.
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
    # 조회 조건으로 자주 쓰일 수 있는 컬럼들에 인덱스를 만듭니다.
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
    # 되돌릴 때는 외래키를 가진 자식 테이블부터 제거해야 안전합니다.
    op.drop_index("ix_inspection_results_status", table_name="inspection_results")
    op.drop_index("ix_inspection_results_product_id", table_name="inspection_results")
    op.drop_index(
        "ix_inspection_results_inspection_run_id",
        table_name="inspection_results",
    )
    op.drop_table("inspection_results")
    op.drop_index("ix_inspection_runs_created_at", table_name="inspection_runs")
    op.drop_table("inspection_runs")
