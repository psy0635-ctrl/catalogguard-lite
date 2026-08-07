"""add actor audit columns to etl/promotion/rollback runs

Revision ID: 20260806_0010
Revises: 20260805_0009
Create Date: 2026-08-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260806_0010"
down_revision: str | None = "20260805_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES = ("etl_load_runs", "catalog_promotion_runs", "catalog_promotion_rollbacks")


def upgrade() -> None:
    # 세 실행 이력 테이블 모두 nullable로 추가합니다. 기존 row는 이 마이그레이션이
    # 실행되기 전에 생성됐으므로 실행한 사용자를 알 수 없고(actor_user_id/actor_username
    # 모두 NULL), 임의 사용자에게 backfill하지 않습니다. 새로 생성되는 row는
    # 애플리케이션 계층이 JWT current_user에서 가져온 값을 반드시 채웁니다.
    for table_name in _TABLES:
        op.add_column(
            table_name,
            sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("actor_username", sa.String(length=50), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_actor_user_id",
            table_name,
            "users",
            ["actor_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table_name in _TABLES:
        op.drop_constraint(
            f"fk_{table_name}_actor_user_id", table_name, type_="foreignkey"
        )
        op.drop_column(table_name, "actor_username")
        op.drop_column(table_name, "actor_user_id")
