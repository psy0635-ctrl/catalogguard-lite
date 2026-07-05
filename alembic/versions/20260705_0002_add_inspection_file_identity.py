# Role: store inspection file identity and prevent duplicate saves in the DB.
"""add inspection file identity

Revision ID: 20260705_0002
Revises: 20260703_0001
Create Date: 2026-07-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260705_0002"
down_revision: str | None = "20260703_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # file_sha256은 기존 원본 CSV bytes가 없어서 과거 데이터에는 채울 수 없습니다.
    # 그래서 nullable 컬럼으로 추가하고, 신규 저장분부터 해시를 기록합니다.
    op.add_column(
        "inspection_runs",
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
    )
    # 기존 행이 있는 DB에서도 안전하게 적용하려고 처음에는 nullable로 추가합니다.
    op.add_column(
        "inspection_runs",
        sa.Column("inspection_version", sa.String(length=20), nullable=True),
    )
    # 과거 이력은 현재 규칙 버전인 "1"로 표시하되, DB server_default는 남기지 않습니다.
    op.execute(
        sa.text(
            "UPDATE inspection_runs "
            "SET inspection_version = '1' "
            "WHERE inspection_version IS NULL"
        )
    )
    op.alter_column(
        "inspection_runs",
        "inspection_version",
        existing_type=sa.String(length=20),
        nullable=False,
    )
    # 이후부터는 DB 레벨에서도 잘못된 해시 길이와 빈 버전을 막습니다.
    op.create_check_constraint(
        "ck_inspection_runs_file_sha256_length",
        "inspection_runs",
        "file_sha256 IS NULL OR length(file_sha256) = 64",
    )
    op.create_check_constraint(
        "ck_inspection_runs_inspection_version_not_blank",
        "inspection_runs",
        "length(trim(inspection_version)) > 0",
    )
    op.create_index(
        # NULL 해시는 unique 비교에서 제외해 migration 이전 이력이 여러 개 있어도 허용합니다.
        "ux_inspection_runs_file_sha256_inspection_version",
        "inspection_runs",
        ["file_sha256", "inspection_version"],
        unique=True,
        postgresql_where=sa.text("file_sha256 IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_inspection_runs_file_sha256_inspection_version",
        table_name="inspection_runs",
    )
    op.drop_constraint(
        "ck_inspection_runs_inspection_version_not_blank",
        "inspection_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_inspection_runs_file_sha256_length",
        "inspection_runs",
        type_="check",
    )
    op.drop_column("inspection_runs", "inspection_version")
    op.drop_column("inspection_runs", "file_sha256")
