# 역할: 비밀번호 hashing/검증과 JWT access token 발급/검증을 테스트합니다.
import time

import jwt
import pytest

from config.settings import JWTConfigurationError, get_jwt_secret
from core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")
    monkeypatch.delenv("CATALOGGUARD_JWT_ACCESS_TOKEN_TTL_SECONDS", raising=False)


def test_hash_password_does_not_return_plain_password():
    password_hash = hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert "correct horse battery staple" not in password_hash


def test_hash_password_uses_bcrypt_format():
    password_hash = hash_password("some-password")

    # bcrypt hash 문자열은 $2b$ 계열 접두사로 시작합니다. 고정 hash 값 자체는 확인하지 않습니다.
    assert password_hash.startswith(("$2a$", "$2b$", "$2y$"))


def test_verify_password_succeeds_for_correct_password():
    password_hash = hash_password("correct-password")

    assert verify_password("correct-password", password_hash) is True


def test_verify_password_fails_for_incorrect_password():
    password_hash = hash_password("correct-password")

    assert verify_password("wrong-password", password_hash) is False


def test_verify_password_fails_safely_for_malformed_hash():
    assert verify_password("any-password", "not-a-real-bcrypt-hash") is False


def test_create_access_token_returns_token_and_positive_ttl():
    token, expires_in = create_access_token(subject="viewer_user", role="viewer")

    assert isinstance(token, str) and token
    assert expires_in > 0


def test_decode_access_token_round_trips_subject_and_role():
    token, _ = create_access_token(subject="operator_user", role="operator")

    payload = decode_access_token(token)

    assert payload["sub"] == "operator_user"
    assert payload["role"] == "operator"


def test_decode_access_token_does_not_include_password_hash_field():
    token, _ = create_access_token(subject="viewer_user", role="viewer")

    payload = decode_access_token(token)

    assert "password_hash" not in payload
    assert "password" not in payload


def test_decode_access_token_rejects_expired_token(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_ACCESS_TOKEN_TTL_SECONDS", "1")
    token, _ = create_access_token(subject="viewer_user", role="viewer")
    time.sleep(2)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_bad_signature():
    token = jwt.encode(
        {"sub": "attacker", "role": "operator"},
        "a-completely-different-secret",
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_garbage_token():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.jwt")


def test_get_jwt_secret_raises_clear_error_when_missing(monkeypatch):
    monkeypatch.delenv("CATALOGGUARD_JWT_SECRET", raising=False)

    with pytest.raises(JWTConfigurationError):
        get_jwt_secret()


@pytest.mark.parametrize("configured_secret", ["CHANGE_ME", "  CHANGE_ME  "])
def test_get_jwt_secret_rejects_example_placeholder(monkeypatch, configured_secret):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", configured_secret)

    with pytest.raises(JWTConfigurationError) as exc_info:
        get_jwt_secret()

    error_message = str(exc_info.value)
    assert "CATALOGGUARD_JWT_SECRET" in error_message
    assert "placeholder" in error_message
    assert "CHANGE_ME" not in error_message


@pytest.mark.parametrize(
    "configured_secret", ["test-only-secret-value", "MY_CHANGE_ME_SECRET"]
)
def test_get_jwt_secret_accepts_non_placeholder_secret(monkeypatch, configured_secret):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", configured_secret)

    assert get_jwt_secret() == configured_secret
