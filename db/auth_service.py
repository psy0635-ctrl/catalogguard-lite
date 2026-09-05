# 역할: users 테이블 조회, 로그인 인증, 초기 계정 생성(bootstrap CLI 전용)을 담당합니다.
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.security import hash_password, verify_password
from db.models import User


VALID_ROLES = ("viewer", "operator")
auth_logger = logging.getLogger("catalogguard.auth")


class UserAlreadyExistsError(ValueError):
    """Raised when a username is already taken."""


class InvalidRoleError(ValueError):
    """Raised when a role is not one of the allowed values."""


def get_user_by_username(session: Session, username: str) -> User | None:
    normalized_username = str(username).strip()
    if not normalized_username:
        return None
    return session.scalar(select(User).where(User.username == normalized_username))


def authenticate_user(
    session: Session,
    *,
    username: str,
    password: str,
) -> User | None:
    """Return the user if username/password match an active account, else None.

    Unknown username, wrong password, and inactive accounts all return None so the
    caller can respond with one generic "invalid credentials" message and avoid
    revealing whether a given username exists or is disabled.
    """
    user = get_user_by_username(session, username)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: str,
    is_active: bool = True,
) -> User:
    """Create a new user. Used only by the bootstrap CLI; there is no signup API."""
    normalized_username = str(username).strip()
    if not normalized_username:
        raise ValueError("username must not be empty")
    if role not in VALID_ROLES:
        raise InvalidRoleError(
            f"role must be one of {VALID_ROLES}, got: {role!r}"
        )
    if not password:
        raise ValueError("password must not be empty")

    password_hash = hash_password(password)
    try:
        with session.begin():
            if get_user_by_username(session, normalized_username) is not None:
                raise UserAlreadyExistsError(
                    f"username already exists: {normalized_username}"
                )
            user = User(
                username=normalized_username,
                password_hash=password_hash,
                role=role,
                is_active=is_active,
            )
            session.add(user)
            session.flush()
            return user
    except IntegrityError as error:
        # A concurrent caller may have won the unique username race.
        try:
            session.rollback()
        except Exception:
            auth_logger.exception("failed to roll back user creation session")
        raise UserAlreadyExistsError(
            f"username already exists: {normalized_username}"
        ) from error
