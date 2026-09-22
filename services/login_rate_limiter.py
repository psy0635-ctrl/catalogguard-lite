"""Temporary, shared login request limits using the existing Redis job connection."""

import hashlib
import logging
from typing import Any

from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from config.metrics import record_login_rate_limiter_fail_open
from config.settings import (
    get_login_rate_limit_ip_attempts,
    get_login_rate_limit_user_attempts,
    get_login_rate_limit_window_seconds,
    get_redis_job_url,
)


KEY_PREFIX = "catalogguard:auth-rate:"
MISSING_CLIENT_PEER = "missing-client-peer"
_logger = logging.getLogger("catalogguard.auth")

# Check both counters before changing either one. Redis executes the entire script atomically.
_LIMIT_SCRIPT = """
local user_count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ip_count = tonumber(redis.call('GET', KEYS[2]) or '0')
if user_count >= tonumber(ARGV[1]) or ip_count >= tonumber(ARGV[2]) then
    return 0
end
user_count = redis.call('INCR', KEYS[1])
if user_count == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
end
ip_count = redis.call('INCR', KEYS[2])
if ip_count == 1 then
    redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3]))
end
return 1
"""


def _key(kind: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"{KEY_PREFIX}{kind}:{digest}"


class LoginRateLimiter:
    def __init__(
        self,
        redis_client: Any,
        *,
        user_attempts: int,
        ip_attempts: int,
        window_seconds: int,
    ) -> None:
        self._redis = redis_client
        self._user_attempts = user_attempts
        self._ip_attempts = ip_attempts
        self._window_seconds = window_seconds

    def allow_attempt(self, *, username: str, client_ip: str | None) -> bool:
        # Authentication strips only; case changes would alter its username identity.
        user_key = _key("user", username.strip())
        ip_key = _key("ip", client_ip if client_ip is not None else MISSING_CLIENT_PEER)
        try:
            result = self._redis.eval(
                _LIMIT_SCRIPT,
                2,
                user_key,
                ip_key,
                self._user_attempts,
                self._ip_attempts,
                self._window_seconds,
            )
        except (RedisConnectionError, RedisTimeoutError):
            record_login_rate_limiter_fail_open()
            _logger.warning("Login rate limiter Redis connection unavailable; authentication continues.")
            return True
        if type(result) is not int or result not in (0, 1):
            raise ValueError("invalid login rate limiter Redis response")
        return result == 1


_default_limiter: LoginRateLimiter | None = None


def get_login_rate_limiter() -> LoginRateLimiter:
    global _default_limiter
    if _default_limiter is None:
        import redis

        _default_limiter = LoginRateLimiter(
            redis.Redis.from_url(
                get_redis_job_url(),
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            ),
            user_attempts=get_login_rate_limit_user_attempts(),
            ip_attempts=get_login_rate_limit_ip_attempts(),
            window_seconds=get_login_rate_limit_window_seconds(),
        )
    return _default_limiter
