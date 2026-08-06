# 역할: 비밀번호 hashing/검증과 JWT access token 발급/검증을 담당하는 순수 유틸리티입니다.
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config.settings import (
    CATALOGGUARD_JWT_ALGORITHM,
    get_jwt_access_token_ttl_seconds,
    get_jwt_secret,
)


class InvalidTokenError(ValueError):
    """Raised when an access token is missing, malformed, expired, or has a bad signature."""


def hash_password(password: str) -> str:
    """Hash a plain password with bcrypt. Never store the plain password."""
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plain password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        # bcrypt는 72바이트를 넘는 입력이나 잘못된 hash 형식에 ValueError를 던집니다.
        # 이 경우도 안전하게 "검증 실패"로 처리합니다.
        return False


def create_access_token(*, subject: str, role: str) -> tuple[str, int]:
    """Issue a short-lived JWT access token. Returns (token, expires_in_seconds)."""
    ttl_seconds = get_jwt_access_token_ttl_seconds()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    token = jwt.encode(payload, get_jwt_secret(), algorithm=CATALOGGUARD_JWT_ALGORITHM)
    return token, ttl_seconds


def decode_access_token(token: str) -> dict[str, object]:
    """Decode and verify a JWT access token. Raises InvalidTokenError on any failure."""
    try:
        return jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[CATALOGGUARD_JWT_ALGORITHM],
        )
    except jwt.PyJWTError as error:
        raise InvalidTokenError("access token is invalid or expired") from error
