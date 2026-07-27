import pytest

from scripts.run_etl_browser_e2e import BrowserE2EError, _validate_database_url


def test_browser_runner_accepts_local_test_database_url():
    _validate_database_url(
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/catalogguard_lite_test"
    )


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://user:password@db.example.com/catalogguard_lite_test",
        "postgresql+psycopg://user:password@127.0.0.1/production",
        "postgresql+psycopg://user:password@railway.internal/catalogguard_lite_test",
    ],
)
def test_browser_runner_rejects_unsafe_database_urls(database_url):
    with pytest.raises(BrowserE2EError):
        _validate_database_url(database_url)
