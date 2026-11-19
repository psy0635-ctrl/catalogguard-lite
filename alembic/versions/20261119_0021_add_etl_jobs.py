"""Store asynchronous web ETL status alongside its PostgreSQL batch."""

from alembic import op
import sqlalchemy as sa

revision = "20261119_0021"
down_revision = "20260915_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "etl_jobs",
        sa.Column("job_id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("source_filename", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_username", sa.String(50), nullable=False),
        sa.Column("etl_load_run_id", sa.BigInteger(), sa.ForeignKey("etl_load_runs.id")),
        sa.Column("created", sa.Boolean()),
        sa.Column("error_code", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_etl_jobs_status",
        ),
        sa.CheckConstraint(
            "(status = 'succeeded') = (etl_load_run_id IS NOT NULL AND created IS NOT NULL) "
            "AND (etl_load_run_id IS NULL) = (created IS NULL) "
            "AND (status = 'failed') = (error_code IS NOT NULL)",
            name="ck_etl_jobs_result",
        ),
    )


def downgrade() -> None:
    op.drop_table("etl_jobs")
