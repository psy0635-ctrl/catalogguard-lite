"""create etl profile activation events table

Revision ID: 20260823_0015
Revises: 20260822_0014
Create Date: 2026-08-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260823_0015"
down_revision: str | None = "20260822_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # current-state 표(etl_profile_activations)는 그대로 둡니다. 이 표는 그 상태를
    # 바꾼 **성공한 operator 명령**의 append-only 기록이고, 둘은 서로를 대체하지
    # 않습니다.
    #
    # **기존 row로 과거 이력을 만들어 내지 않습니다.** current-state row 하나만으로는
    # 누가 처음 활성화했는지, 몇 번 바꿨는지, 언제 내렸다 올렸는지 알 수 없습니다.
    # 모르는 것을 추측해 채우면 없는 기록보다 나쁜, 틀린 기록이 남습니다. 그래서 이
    # 표는 **빈 상태로 시작**하고 이 migration 적용 이후의 명령부터 기록합니다.
    op.create_table(
        "etl_profile_activation_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        # 네 값 모두 "명령이 성공한 직후"의 snapshot입니다. 나중에 registry를 다시
        # 읽어 계산하면 배포 기본값이 바뀔 때 과거 기록의 뜻이 조용히 달라집니다.
        sa.Column("deployment_active_version", sa.String(length=20), nullable=True),
        sa.Column("runtime_override_exists", sa.Boolean(), nullable=False),
        sa.Column("runtime_active_version", sa.String(length=20), nullable=True),
        sa.Column("effective_active_version", sa.String(length=20), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_username", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(profile_id)) > 0",
            name="ck_etl_profile_activation_events_profile_id_not_blank",
        ),
        sa.CheckConstraint(
            "action IN ('activate', 'deactivate', 'reset')",
            name="ck_etl_profile_activation_events_action",
        ),
        # 버전 문자열은 형식만 봅니다. registry의 어떤 key인지는 DB가 알 수 없고,
        # ''나 '  '이 "비활성"으로 읽히지 않게 하는 것이 목적입니다.
        sa.CheckConstraint(
            "deployment_active_version IS NULL"
            " OR length(trim(deployment_active_version)) > 0",
            name="ck_etl_profile_activation_events_deployment_version_not_blank",
        ),
        sa.CheckConstraint(
            "runtime_active_version IS NULL"
            " OR length(trim(runtime_active_version)) > 0",
            name="ck_etl_profile_activation_events_runtime_version_not_blank",
        ),
        sa.CheckConstraint(
            "effective_active_version IS NULL"
            " OR length(trim(effective_active_version)) > 0",
            name="ck_etl_profile_activation_events_effective_version_not_blank",
        ),
        # 명령과 그 직후 상태가 모순되는 event를 남기지 않습니다. reset은 둘 다 NULL일
        # 수 있어 '='이 아니라 IS NOT DISTINCT FROM으로 비교합니다. PostgreSQL에서
        # NULL = NULL은 참이 아니라 NULL이고, CHECK는 NULL을 통과시켜 제약이 조용히
        # 무력화되기 때문입니다.
        sa.CheckConstraint(
            "("
            "action = 'activate'"
            " AND runtime_override_exists"
            " AND runtime_active_version IS NOT NULL"
            " AND effective_active_version = runtime_active_version"
            ") OR ("
            "action = 'deactivate'"
            " AND runtime_override_exists"
            " AND runtime_active_version IS NULL"
            " AND effective_active_version IS NULL"
            ") OR ("
            "action = 'reset'"
            " AND NOT runtime_override_exists"
            " AND runtime_active_version IS NULL"
            " AND effective_active_version IS NOT DISTINCT FROM deployment_active_version"
            ")",
            name="ck_etl_profile_activation_events_state_matches_action",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # 주 조회는 "한 프로필의 최신 event부터"입니다. PostgreSQL은 B-tree를 역방향으로도
    # 훑을 수 있으므로 내림차순 전용 index를 따로 만들지 않습니다.
    op.create_index(
        "ix_etl_profile_activation_events_profile_created_at_id",
        "etl_profile_activation_events",
        ["profile_id", "created_at", "id"],
    )


def downgrade() -> None:
    # history만 지웁니다. current-state 표(etl_profile_activations)는 이 migration이
    # 만든 것이 아니므로 건드리지 않습니다. 지금 적용된 runtime override는 그대로
    # 유지되고, 사라지는 것은 이 표에 쌓인 운영 명령 기록뿐입니다.
    op.drop_index(
        "ix_etl_profile_activation_events_profile_created_at_id",
        table_name="etl_profile_activation_events",
    )
    op.drop_table("etl_profile_activation_events")
