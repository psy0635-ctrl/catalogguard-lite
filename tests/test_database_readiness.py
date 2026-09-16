"""Schema readiness contracts and isolated PostgreSQL migration checks."""

import uuid
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import api.main as api_main
import db.session as db_session
from config.database import get_optional_database_url
from config.settings import BASE_DIR


@pytest.fixture
def migration_config():
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "alembic"))
    return config


@pytest.fixture(autouse=True)
def clear_head_cache():
    db_session.get_expected_alembic_head.cache_clear()
    yield
    db_session.get_expected_alembic_head.cache_clear()


def test_expected_head_uses_real_repository_from_another_directory(
    monkeypatch, tmp_path, migration_config,
):
    heads = ScriptDirectory.from_config(migration_config).get_heads()
    assert len(heads) == 1
    monkeypatch.chdir(tmp_path)
    assert db_session.get_expected_alembic_head() == heads[0]
    assert db_session.get_expected_alembic_head() == heads[0]
    assert db_session.get_expected_alembic_head.cache_info().misses == 1
    assert db_session.get_expected_alembic_head.cache_info().hits == 1


@pytest.mark.parametrize("heads", [[], ["branch_a", "branch_b"]])
def test_repository_without_single_head_fails_closed(monkeypatch, heads):
    script = Mock()
    script.get_heads.return_value = heads
    monkeypatch.setattr(db_session.ScriptDirectory, "from_config", lambda config: script)
    with pytest.raises(db_session.DatabaseSchemaNotReadyError):
        db_session.get_expected_alembic_head()


def test_unreadable_repository_fails_closed(monkeypatch):
    def unreadable(config):
        raise OSError("private filesystem detail")

    monkeypatch.setattr(db_session.ScriptDirectory, "from_config", unreadable)
    with pytest.raises(db_session.DatabaseSchemaNotReadyError):
        db_session.get_expected_alembic_head()


@pytest.mark.parametrize("state", ["current", "stale", "future", "empty", "multiple", "missing"])
def test_readiness_checks_real_version_rows(monkeypatch, state):
    engine = create_engine("sqlite://")
    head = db_session.get_expected_alembic_head()
    rows = {
        "current": [head], "stale": ["old_revision"], "future": ["unknown_revision"],
        "empty": [], "multiple": [head, "other_branch"], "missing": [],
    }[state]
    try:
        with engine.begin() as connection:
            if state != "missing":
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
                for revision in rows:
                    connection.execute(
                        text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                        {"revision": revision},
                    )
        monkeypatch.setattr(db_session, "get_engine", lambda: engine)
        if state == "current":
            db_session.check_database_readiness()
        else:
            with pytest.raises(db_session.DatabaseSchemaNotReadyError):
                db_session.check_database_readiness()
    finally:
        engine.dispose()


def test_connection_failure_does_not_attempt_schema_check(monkeypatch):
    def connection_failed():
        raise RuntimeError("connection failed")

    schema_check = Mock()
    monkeypatch.setattr(db_session, "check_database_connection", connection_failed)
    monkeypatch.setattr(db_session, "check_database_schema", schema_check)
    with pytest.raises(RuntimeError):
        db_session.check_database_readiness()
    schema_check.assert_not_called()


@pytest.mark.parametrize("state,expected_status", [("current", 200), ("stale", 503), ("empty", 503)])
def test_postgresql_readiness_with_isolated_migrations(
    monkeypatch, migration_config, state, expected_status,
):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")
    # Only a generated disposable schema in the explicitly configured test DB is touched.
    schema = f"readiness_{uuid.uuid4().hex}"
    admin_engine = create_engine(database_url)
    url = make_url(database_url).update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(url)
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        script = ScriptDirectory.from_config(migration_config)
        head = script.get_current_head()
        if state != "empty":
            target = head if state == "current" else script.get_revision(head).down_revision
            command.upgrade(migration_config, target)
        monkeypatch.setattr(db_session, "get_engine", lambda: engine)
        response = TestClient(api_main.app).get("/ready")
        assert response.status_code == expected_status
        assert response.json() == (
            {"status": "ready", "service": "catalogguard-lite-api", "database": "ok"}
            if expected_status == 200 else
            {"detail": {"status": "not_ready", "service": "catalogguard-lite-api", "database": "unavailable"}}
        )
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
