# 역할: 같은 프로세스에서 Alembic migration을 실행해도 애플리케이션 logger가 살아 있는지 검증합니다.
from __future__ import annotations

import logging

import pytest
from alembic import command
from alembic.config import Config

from config.database import get_optional_database_url
from config.logging import LOGGER_NAME, configure_logging, log_event


ALEMBIC_LOGGER_NAME = "alembic"


@pytest.fixture()
def restored_logging_state():
    """logging은 프로세스 전역 상태라, 이 테스트가 바꾼 값을 반드시 되돌립니다.

    통과시키려고 disabled=False를 남겨 두는 것이 아니라, 테스트 시작 시점의 값을
    그대로 복원해 다른 테스트가 보는 상태를 바꾸지 않는 것이 목적입니다.
    """
    logger = configure_logging()
    alembic_logger = logging.getLogger(ALEMBIC_LOGGER_NAME)
    original = {
        logger: (logger.disabled, logger.level),
        alembic_logger: (alembic_logger.disabled, alembic_logger.level),
    }
    try:
        yield logger
    finally:
        for target, (disabled, level) in original.items():
            target.disabled = disabled
            target.setLevel(level)


@pytest.fixture()
def alembic_config(monkeypatch):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 Alembic 통합 테스트를 건너뜁니다.")

    # env.py가 get_database_url()로 읽는 값입니다.
    monkeypatch.setenv("DATABASE_URL", database_url)
    return Config("alembic.ini")


def test_in_process_migration_keeps_the_application_logger_working(
    restored_logging_state,
    alembic_config,
) -> None:
    """Alembic을 같은 프로세스에서 돌려도 catalogguard logger가 죽으면 안 됩니다.

    env.py의 fileConfig()는 disable_existing_loggers 기본값이 True라, alembic.ini에
    선언되지 않은 logger를 전부 disabled로 만듭니다. 그러면 migration을 in-process로
    실행한 뒤에 오는 로그 검증 테스트가 실행 순서에 따라 실패합니다.
    """
    logger = restored_logging_state
    assert not logger.disabled

    command.upgrade(alembic_config, "head")

    # flag만 보지 않고 실제로 로그가 나오는지까지 확인합니다.
    records: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = CaptureHandler()
    logger.addHandler(handler)
    try:
        log_event(logger, logging.INFO, event="alembic_logging_probe")
    finally:
        logger.removeHandler(handler)

    # logging.config는 자신이 설정한 logger에 bool이 아닌 0을 넣기도 하므로
    # 정체성(is False)이 아니라 "꺼져 있지 않다"만 확인합니다.
    assert not logger.disabled
    assert len(records) == 1
    assert "alembic_logging_probe" in records[0]


def test_migration_still_applies_alembic_ini_logging_configuration(
    restored_logging_state,
    alembic_config,
) -> None:
    """애플리케이션 logger를 지키느라 Alembic 자체 로깅 설정이 깨지면 안 됩니다.

    alembic.ini의 [logger_alembic] level = INFO가 그대로 적용되는지만 확인하고,
    출력 문자열 전체를 고정하지는 않습니다.
    """
    command.upgrade(alembic_config, "head")

    alembic_logger = logging.getLogger(ALEMBIC_LOGGER_NAME)
    assert not alembic_logger.disabled
    assert alembic_logger.level == logging.INFO


def test_repeated_in_process_migrations_do_not_disable_the_logger(
    restored_logging_state,
    alembic_config,
) -> None:
    """env.py는 alembic command마다 다시 실행되므로 반복 호출도 확인합니다."""
    logger = restored_logging_state

    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")

    assert not logger.disabled
    assert not logging.getLogger(LOGGER_NAME).disabled
