# 역할: db/auth_service.py의 사용자 생성, 로그인 인증, 중복/역할 검증을 실제 PostgreSQL로 테스트합니다.
from uuid import uuid4

import pytest
from sqlalchemy import delete

from config.database import get_optional_database_url
from core.security import verify_password
from db.auth_service import (
    InvalidRoleError,
    UserAlreadyExistsError,
    authenticate_user,
    create_user,
    get_user_by_username,
)
from db.models import User
from db.session import create_database_engine, create_session_factory


@pytest.fixture()
def postgres_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session, session_factory
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _cleanup_users(session_factory, usernames: list[str]) -> None:
    if not usernames:
        return
    with session_factory() as cleanup:
        cleanup.execute(delete(User).where(User.username.in_(usernames)))
        cleanup.commit()


def test_create_user_persists_bcrypt_hash_not_plain_password(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("viewer")
    try:
        user = create_user(
            session,
            username=username,
            password="synthetic-test-password-1",
            role="viewer",
        )

        assert user.id is not None
        assert user.username == username
        assert user.role == "viewer"
        assert user.is_active is True
        assert user.password_hash != "synthetic-test-password-1"
        assert verify_password("synthetic-test-password-1", user.password_hash)
    finally:
        _cleanup_users(session_factory, [username])


def test_create_user_rejects_duplicate_username(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("dup")
    try:
        create_user(session, username=username, password="pw-one", role="viewer")

        with pytest.raises(UserAlreadyExistsError):
            create_user(session, username=username, password="pw-two", role="operator")
    finally:
        _cleanup_users(session_factory, [username])


def test_create_user_rejects_invalid_role(postgres_session):
    session, _session_factory = postgres_session
    username = _unique_username("badrole")

    with pytest.raises(InvalidRoleError):
        create_user(session, username=username, password="pw", role="admin")


def test_authenticate_user_succeeds_with_correct_password(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("auth_ok")
    try:
        create_user(session, username=username, password="correct-password", role="operator")

        authenticated = authenticate_user(
            session, username=username, password="correct-password"
        )

        assert authenticated is not None
        assert authenticated.username == username
        assert authenticated.role == "operator"
    finally:
        _cleanup_users(session_factory, [username])


def test_authenticate_user_fails_with_wrong_password(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("auth_bad")
    try:
        create_user(session, username=username, password="correct-password", role="viewer")

        assert (
            authenticate_user(session, username=username, password="wrong-password")
            is None
        )
    finally:
        _cleanup_users(session_factory, [username])


def test_authenticate_user_fails_for_unknown_username(postgres_session):
    session, _session_factory = postgres_session

    assert (
        authenticate_user(
            session, username="no-such-user-exists", password="anything"
        )
        is None
    )


def test_authenticate_user_fails_for_inactive_user(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("inactive")
    try:
        create_user(
            session,
            username=username,
            password="correct-password",
            role="viewer",
            is_active=False,
        )

        assert (
            authenticate_user(session, username=username, password="correct-password")
            is None
        )
    finally:
        _cleanup_users(session_factory, [username])


def test_get_user_by_username_returns_none_for_unknown_username(postgres_session):
    session, _session_factory = postgres_session

    assert get_user_by_username(session, "definitely-not-a-real-username") is None


def test_users_table_rejects_role_outside_allowlist_at_db_level(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("rawrole")
    try:
        user = User(
            username=username,
            password_hash="irrelevant-hash",
            role="superadmin",
        )
        session.add(user)
        with pytest.raises(Exception):
            session.commit()
    finally:
        session.rollback()
        _cleanup_users(session_factory, [username])
