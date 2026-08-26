"""Phase 5C.2 migration and ORM contract for application commit lineage."""

from __future__ import annotations

import hashlib

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import String, text

from config.database import get_optional_database_url
from db.models import ETLLoadRun
from db.session import create_database_engine


REVISION = "20260826_0017"
PREVIOUS_REVISION = "20260825_0016"
HEAD_REVISION = "20260826_0018"
COLUMN = "application_commit_sha"


def test_application_commit_lineage_migration_is_the_single_alembic_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert list(script.get_heads()) == [HEAD_REVISION]
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION


def test_application_commit_model_column_is_nullable_commit_text() -> None:
    column = ETLLoadRun.__table__.columns[COLUMN]
    assert isinstance(column.type, String)
    assert column.type.length == 40
    assert column.nullable is True
    assert column.server_default is None


@pytest.fixture(name="alembic_config")
def fixture_alembic_config(monkeypatch):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 Alembic 통합 테스트를 건너뜁니다.")
    monkeypatch.setenv("DATABASE_URL", database_url)
    return Config("alembic.ini")


@pytest.fixture(name="engine")
def fixture_engine():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 Alembic 통합 테스트를 건너뜁니다.")
    engine = create_database_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


def test_upgrade_adds_nullable_column_without_backfilling_legacy_rows(alembic_config, engine) -> None:
    marker = hashlib.sha256(b"application-commit-migration-test").hexdigest()
    command.downgrade(alembic_config, PREVIOUS_REVISION)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO etl_load_runs ("
                    "source_filename, profile_name, profile_version, "
                    "input_file_sha256, output_file_sha256, loaded_rows, "
                    "initial_source_type) VALUES ("
                    "'legacy.csv', 'migration_application_commit_profile', '1', "
                    ":input_hash, :output_hash, 0, 'unknown')"
                ),
                {"input_hash": marker, "output_hash": marker},
            )
        command.upgrade(alembic_config, REVISION)
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT application_commit_sha FROM etl_load_runs "
                    "WHERE input_file_sha256 = :input_hash"
                ),
                {"input_hash": marker},
            ).scalar() is None
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM etl_load_runs WHERE input_file_sha256 = :input_hash"),
                {"input_hash": marker},
            )
