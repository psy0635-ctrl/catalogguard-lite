import pytest

from config import settings


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "Yes", " yes "])
def test_login_rate_limit_explicit_true_values(monkeypatch, value):
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_ENABLED", value)
    assert settings.is_login_rate_limit_enabled() is True


@pytest.mark.parametrize("value", [None, "", "false", "on", "0", "unexpected"])
def test_login_rate_limit_other_values_are_disabled(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("CATALOGGUARD_LOGIN_RATE_LIMIT_ENABLED", raising=False)
    else:
        monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_ENABLED", value)
    assert settings.is_login_rate_limit_enabled() is False


def test_login_rate_limit_numeric_defaults_and_overrides(monkeypatch):
    for name in (
        "CATALOGGUARD_LOGIN_RATE_LIMIT_USER_ATTEMPTS",
        "CATALOGGUARD_LOGIN_RATE_LIMIT_IP_ATTEMPTS",
        "CATALOGGUARD_LOGIN_RATE_LIMIT_WINDOW_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert settings.get_login_rate_limit_user_attempts() == 10
    assert settings.get_login_rate_limit_ip_attempts() == 100
    assert settings.get_login_rate_limit_window_seconds() == 300

    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_USER_ATTEMPTS", "4")
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_IP_ATTEMPTS", "40")
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")
    assert settings.get_login_rate_limit_user_attempts() == 4
    assert settings.get_login_rate_limit_ip_attempts() == 40
    assert settings.get_login_rate_limit_window_seconds() == 60


@pytest.mark.parametrize("invalid", ["", "0", "-1", "not-a-number"])
def test_login_rate_limit_invalid_numbers_fall_back(monkeypatch, invalid):
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_USER_ATTEMPTS", invalid)
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_IP_ATTEMPTS", invalid)
    monkeypatch.setenv("CATALOGGUARD_LOGIN_RATE_LIMIT_WINDOW_SECONDS", invalid)
    assert settings.get_login_rate_limit_user_attempts() == 10
    assert settings.get_login_rate_limit_ip_attempts() == 100
    assert settings.get_login_rate_limit_window_seconds() == 300
