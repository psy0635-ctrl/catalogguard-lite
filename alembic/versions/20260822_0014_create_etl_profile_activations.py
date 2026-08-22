"""create etl profile activations table

Revision ID: 20260822_0014
Revises: 20260813_0013
Create Date: 2026-08-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260822_0014"
down_revision: str | None = "20260813_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 프로필 정의는 옮기지 않습니다. 이 표에는 "어떤 보존된 버전을 신규 실행에 쓸
    # 것인가"라는 runtime 상태만 들어갑니다. row가 없으면 배포 registry의 기본값을
    # 그대로 쓰므로, 이 migration은 기존 동작을 바꾸지 않습니다(빈 표로 시작).
    op.create_table(
        "etl_profile_activations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        # NULL = 비활성. 값이 있으면 registry versions의 정확한 key여야 하며 그
        # 검증은 애플리케이션 쓰기 경로가 합니다. DB는 registry를 모르므로 형식만 봅니다.
        sa.Column("active_version", sa.String(length=20), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_username", sa.String(length=50), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(profile_id)) > 0",
            name="ck_etl_profile_activations_profile_id_not_blank",
        ),
        # 비활성을 뜻하는 값은 NULL 하나뿐입니다. ''나 '  '이 들어오면 "비활성인가
        # 잘못된 pointer인가"가 모호해지므로 DB에서 막습니다.
        sa.CheckConstraint(
            "active_version IS NULL OR length(trim(active_version)) > 0",
            name="ck_etl_profile_activations_active_version_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # 한 프로필의 runtime 상태는 정확히 하나입니다. 동시에 두 operator가 바꿔도
    # 중복 row가 생기지 않아야 어느 것이 진짜인지 코드가 고르지 않아도 됩니다.
    op.create_index(
        "ux_etl_profile_activations_profile_id",
        "etl_profile_activations",
        ["profile_id"],
        unique=True,
    )


def downgrade() -> None:
    # runtime override를 전부 버리고 배포 registry 기본값으로 되돌아갑니다.
    # 프로필 archive와 과거 etl_load_runs는 이 표와 무관하므로 그대로 남습니다.
    op.drop_index(
        "ux_etl_profile_activations_profile_id",
        table_name="etl_profile_activations",
    )
    op.drop_table("etl_profile_activations")
