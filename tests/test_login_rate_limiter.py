from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import redis

from config.settings import get_redis_job_url
from config import metrics as metrics_config
from services.login_rate_limiter import LoginRateLimiter, _key


class FakeAtomicRedis:
    """Model the script decision for unit tests; real Redis verifies atomic execution below."""

    def __init__(self):
        self.counts = {}
        self.expirations = {}
        self.calls = []
        self.now = 0

    def eval(self, script, key_count, user_key, ip_key, user_limit, ip_limit, window):
        self.calls.append((script, key_count, user_key, ip_key))
        assert key_count == 2
        for key in (user_key, ip_key):
            if key in self.expirations and self.expirations[key] <= self.now:
                self.counts.pop(key, None)
                self.expirations.pop(key, None)
        if self.counts.get(user_key, 0) >= user_limit or self.counts.get(ip_key, 0) >= ip_limit:
            return 0
        for key in (user_key, ip_key):
            self.counts[key] = self.counts.get(key, 0) + 1
            if self.counts[key] == 1:
                self.expirations[key] = self.now + window
        return 1


def make_limiter(fake, *, user_attempts=2, ip_attempts=3, window_seconds=30):
    return LoginRateLimiter(
        fake,
        user_attempts=user_attempts,
        ip_attempts=ip_attempts,
        window_seconds=window_seconds,
    )


def _metric(name):
    return metrics_config.REGISTRY.get_sample_value(name) or 0.0


BLOCKED_METRIC = "catalogguard_login_rate_limited_total"
FAIL_OPEN_METRIC = "catalogguard_login_rate_limiter_fail_open_total"


def test_keys_are_hashed_and_username_uses_strip_only():
    fake = FakeAtomicRedis()
    limiter = make_limiter(fake)
    assert limiter.allow_attempt(username=" User1 ", client_ip="198.51.100.7")
    _, _, user_key, ip_key = fake.calls[0]
    assert user_key == _key("user", "User1")
    assert ip_key == _key("ip", "198.51.100.7")
    assert "User1" not in user_key
    assert "198.51.100.7" not in ip_key
    assert limiter.allow_attempt(username="User1", client_ip="198.51.100.7")
    assert not limiter.allow_attempt(username=" User1 ", client_ip="198.51.100.7")
    assert limiter.allow_attempt(username="user1", client_ip="203.0.113.9")


def test_user_and_ip_buckets_are_independent_and_block_is_not_counted():
    fake = FakeAtomicRedis()
    limiter = make_limiter(fake, user_attempts=2, ip_attempts=3)
    assert limiter.allow_attempt(username="alice", client_ip="ip-a")
    assert limiter.allow_attempt(username="alice", client_ip="ip-b")
    assert not limiter.allow_attempt(username="alice", client_ip="ip-c")
    assert _key("ip", "ip-c") not in fake.counts
    assert limiter.allow_attempt(username="bob", client_ip="ip-a")
    assert limiter.allow_attempt(username="carol", client_ip="ip-a")
    assert not limiter.allow_attempt(username="dave", client_ip="ip-a")
    assert _key("user", "dave") not in fake.counts


def test_ttl_is_set_once_and_expires():
    fake = FakeAtomicRedis()
    limiter = make_limiter(fake, user_attempts=2, ip_attempts=3, window_seconds=30)
    assert limiter.allow_attempt(username="alice", client_ip=None)
    user_key = _key("user", "alice")
    ip_key = _key("ip", "missing-client-peer")
    assert fake.expirations == {user_key: 30, ip_key: 30}
    fake.now = 20
    assert limiter.allow_attempt(username="alice", client_ip=None)
    assert fake.expirations == {user_key: 30, ip_key: 30}
    assert not limiter.allow_attempt(username="alice", client_ip=None)
    fake.now = 30
    assert limiter.allow_attempt(username="alice", client_ip=None)
    assert fake.expirations == {user_key: 60, ip_key: 60}


@pytest.mark.parametrize("exception", [redis.exceptions.ConnectionError, redis.exceptions.TimeoutError])
def test_connection_failures_fail_open_with_safe_warning(caplog, exception, monkeypatch):
    monkeypatch.setenv(metrics_config.CATALOGGUARD_METRICS_ENABLED_ENV_VAR, "true")
    before_fail_open = _metric(FAIL_OPEN_METRIC)
    before_blocked = _metric(BLOCKED_METRIC)
    class BrokenRedis:
        def eval(self, *args):
            raise exception("redis://secret@example.invalid username=alice ip=198.51.100.7")

    limiter = make_limiter(BrokenRedis())
    with caplog.at_level("WARNING", logger="catalogguard.auth"):
        assert limiter.allow_attempt(username="alice", client_ip="198.51.100.7")
    assert len(caplog.records) == 1
    assert caplog.records[0].message == (
        "Login rate limiter Redis connection unavailable; authentication continues."
    )
    assert "alice" not in caplog.text
    assert "198.51.100.7" not in caplog.text
    assert "redis://" not in caplog.text
    assert _metric(FAIL_OPEN_METRIC) - before_fail_open == 1
    assert _metric(BLOCKED_METRIC) - before_blocked == 0


@pytest.mark.parametrize("failure", [redis.exceptions.ResponseError("bad lua"), "bad", 2, True])
def test_response_errors_and_invalid_results_do_not_fail_open(failure, monkeypatch):
    monkeypatch.setenv(metrics_config.CATALOGGUARD_METRICS_ENABLED_ENV_VAR, "true")
    before = _metric(FAIL_OPEN_METRIC)
    class BrokenRedis:
        def eval(self, *args):
            if isinstance(failure, Exception):
                raise failure
            return failure

    with pytest.raises((redis.exceptions.ResponseError, ValueError)):
        make_limiter(BrokenRedis()).allow_attempt(username="alice", client_ip="ip")
    assert _metric(FAIL_OPEN_METRIC) - before == 0


def test_real_redis_lua_concurrency_and_ttl():
    client = redis.Redis.from_url(get_redis_job_url(), socket_connect_timeout=0.2, socket_timeout=1)
    try:
        client.ping()
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
        pytest.skip("Redis unavailable for integration test")

    username = f"login-limit-test-{uuid4().hex}"
    ip = f"test-ip-{uuid4().hex}"
    user_key, ip_key = _key("user", username), _key("ip", ip)
    limiter = make_limiter(client, user_attempts=5, ip_attempts=100, window_seconds=30)
    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            outcomes = list(pool.map(lambda _: limiter.allow_attempt(username=username, client_ip=ip), range(20)))
        assert outcomes.count(True) == 5
        assert outcomes.count(False) == 15
        assert int(client.get(user_key)) == 5
        assert int(client.get(ip_key)) == 5
        assert 0 < client.ttl(user_key) <= 30
        assert 0 < client.ttl(ip_key) <= 30
        assert not limiter.allow_attempt(username=username, client_ip=ip)
        assert int(client.get(ip_key)) == 5
    finally:
        client.delete(user_key, ip_key)
