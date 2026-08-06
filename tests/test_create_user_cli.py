# 역할: scripts/create_user.py bootstrap CLI의 정상 생성, 중복, 역할 검증, 비밀번호 미노출을 테스트합니다.
from uuid import uuid4

import pytest
from sqlalchemy import delete

from config.database import get_optional_database_url
from db.models import User
from db.session import create_database_engine, create_session_factory
from scripts.create_user import PASSWORD_ENV_VAR, main


@pytest.fixture()
def postgres_env(monkeypatch):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")
    monkeypatch.setenv("DATABASE_URL", database_url)
    return database_url


@pytest.fixture()
def session_factory(postgres_env):
    engine = create_database_engine(postgres_env)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


def _unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _cleanup_users(session_factory, usernames: list[str]) -> None:
    if not usernames:
        return
    with session_factory() as cleanup:
        cleanup.execute(delete(User).where(User.username.in_(usernames)))
        cleanup.commit()


def test_create_user_cli_creates_operator_account(
    postgres_env, session_factory, monkeypatch, capsys
):
    username = _unique_username("cli_operator")
    monkeypatch.setenv(PASSWORD_ENV_VAR, "synthetic-cli-password-1")
    try:
        exit_code = main(["--username", username, "--role", "operator"])

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "계정 생성 완료" in output
        assert username in output
        assert "operator" in output
        assert "synthetic-cli-password-1" not in output

        with session_factory() as verify_session:
            from sqlalchemy import select

            user = verify_session.scalar(select(User).where(User.username == username))
            assert user is not None
            assert user.role == "operator"
            assert user.is_active is True
            assert user.password_hash != "synthetic-cli-password-1"
    finally:
        _cleanup_users(session_factory, [username])


def test_create_user_cli_supports_inactive_flag(
    postgres_env, session_factory, monkeypatch
):
    username = _unique_username("cli_inactive")
    monkeypatch.setenv(PASSWORD_ENV_VAR, "synthetic-cli-password-2")
    try:
        exit_code = main(
            ["--username", username, "--role", "viewer", "--inactive"]
        )

        assert exit_code == 0
        with session_factory() as verify_session:
            from sqlalchemy import select

            user = verify_session.scalar(select(User).where(User.username == username))
            assert user is not None
            assert user.is_active is False
    finally:
        _cleanup_users(session_factory, [username])


def test_create_user_cli_rejects_duplicate_username(
    postgres_env, session_factory, monkeypatch, capsys
):
    username = _unique_username("cli_dup")
    monkeypatch.setenv(PASSWORD_ENV_VAR, "synthetic-cli-password-3")
    try:
        first_exit_code = main(["--username", username, "--role", "viewer"])
        assert first_exit_code == 0

        second_exit_code = main(["--username", username, "--role", "operator"])

        assert second_exit_code == 1
        error_output = capsys.readouterr().err
        assert "이미 존재하는 아이디" in error_output
    finally:
        _cleanup_users(session_factory, [username])


def test_create_user_cli_rejects_invalid_role_via_argparse(postgres_env):
    with pytest.raises(SystemExit) as exc_info:
        main(["--username", "someone", "--role", "admin"])

    assert exc_info.value.code == 2


def test_create_user_cli_requires_password_source(postgres_env, monkeypatch, capsys):
    monkeypatch.delenv(PASSWORD_ENV_VAR, raising=False)
    monkeypatch.setattr(
        "getpass.getpass",
        lambda *_args, **_kwargs: "",
    )

    exit_code = main(["--username", "someone-else", "--role", "viewer"])

    assert exit_code == 1
    assert "비밀번호가 비어 있습니다" in capsys.readouterr().err
