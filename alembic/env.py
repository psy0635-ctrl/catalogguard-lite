# 역할: Alembic이 SQLAlchemy 모델 정보를 읽어 마이그레이션을 실행하도록 설정합니다.
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config.database import get_database_url
from db.base import Base
from db import models  # noqa: F401


config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers 기본값은 True라, alembic.ini에 선언되지 않은 logger를 전부
    # disabled로 바꿉니다. alembic.ini는 root/sqlalchemy/alembic만 선언하므로 기본값으로 두면
    # 같은 프로세스에서 migration을 실행할 때 catalogguard 애플리케이션 logger가 조용히 죽습니다.
    # False로 두어도 alembic.ini가 선언한 logger 설정은 그대로 적용됩니다.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    # 오프라인 모드는 DB에 접속하지 않고 SQL 스크립트 생성용으로 설정합니다.
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 일반적인 마이그레이션 실행은 실제 DB에 연결한 뒤 트랜잭션 안에서 진행합니다.
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
