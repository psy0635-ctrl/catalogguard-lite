from __future__ import annotations

import logging
import socket
from urllib.error import HTTPError, URLError

import pytest

from config.logging import LOGGER_NAME
from config.settings import (
    MAX_UPLOAD_SIZE_BYTES,
    get_catalogguard_etl_http_feed_filename,
    get_catalogguard_etl_http_feed_url,
)
from core.upload_validator import CsvUploadValidationError
from etl.http_source import (
    DEFAULT_HTTP_FEED_FILENAME,
    HTTPFeedNotConfiguredError,
    HTTPFeedPermanentError,
    HTTPFeedReadError,
    HTTPFeedTransientError,
    read_http_feed_csv,
)


FEED_URL = "https://supplier.example.invalid/catalog.csv"
CSV_BYTES = b"vendor_sku,item_name\nSKU-1,shirt\n"


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        *,
        content_length: str | None = None,
        read_error: Exception | None = None,
    ) -> None:
        self.content = content
        self.headers = {} if content_length is None else {"Content-Length": content_length}
        self.read_error = read_error
        self.read_sizes: list[int] = []
        self.closed = False

    def read(self, amount: int) -> bytes:
        self.read_sizes.append(amount)
        if self.read_error is not None:
            raise self.read_error
        return self.content[:amount]

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, *, timeout: float):
        self.calls.append((url, timeout))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture(autouse=True)
def configured_feed(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_URL", FEED_URL)
    monkeypatch.delenv("CATALOGGUARD_ETL_HTTP_FEED_FILENAME", raising=False)


@pytest.fixture()
def captured_logs(caplog):
    logger = logging.getLogger(LOGGER_NAME)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def test_http_feed_settings_getters_read_environment_at_call_time(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_URL", "  https://later.example.invalid/a.csv  ")
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_FILENAME", "  later_feed.csv  ")

    assert get_catalogguard_etl_http_feed_url() == "https://later.example.invalid/a.csv"
    assert get_catalogguard_etl_http_feed_filename() == "later_feed.csv"


def test_blank_http_feed_settings_fall_back_to_none_and_default(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_URL", "   ")
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_FILENAME", "   ")

    assert get_catalogguard_etl_http_feed_url() is None
    assert get_catalogguard_etl_http_feed_filename() == DEFAULT_HTTP_FEED_FILENAME


def test_configured_feed_returns_bytes_and_configured_filename():
    opener = FakeOpener(FakeResponse(CSV_BYTES, content_length=str(len(CSV_BYTES))))

    source = read_http_feed_csv(opener=opener)

    assert source.content == CSV_BYTES
    assert source.source_filename == DEFAULT_HTTP_FEED_FILENAME
    assert [url for url, _ in opener.calls] == [FEED_URL]


def test_configured_filename_overrides_the_default(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_FILENAME", "vendor_daily.csv")
    opener = FakeOpener(FakeResponse(CSV_BYTES))

    assert read_http_feed_csv(opener=opener).source_filename == "vendor_daily.csv"


def test_request_uses_a_bounded_timeout():
    opener = FakeOpener(FakeResponse(CSV_BYTES))

    read_http_feed_csv(opener=opener)

    timeout = opener.calls[0][1]
    assert isinstance(timeout, (int, float))
    assert 0 < timeout <= 60


def test_missing_feed_url_is_rejected_before_any_request(monkeypatch):
    monkeypatch.delenv("CATALOGGUARD_ETL_HTTP_FEED_URL", raising=False)
    opener = FakeOpener(FakeResponse(CSV_BYTES))

    with pytest.raises(HTTPFeedNotConfiguredError):
        read_http_feed_csv(opener=opener)

    assert opener.calls == []


@pytest.mark.parametrize(
    "feed_url",
    [
        "file:///etc/passwd",
        "ftp://supplier.example.invalid/catalog.csv",
        "gopher://supplier.example.invalid/catalog.csv",
        "http://supplier.example.invalid/catalog.csv",
        "http://169.254.169.254/latest/meta-data/",
        "not-a-url",
        "https://",
    ],
)
def test_unsafe_feed_url_is_rejected_before_any_request(monkeypatch, feed_url):
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_URL", feed_url)
    opener = FakeOpener(FakeResponse(CSV_BYTES))

    with pytest.raises(HTTPFeedNotConfiguredError):
        read_http_feed_csv(opener=opener)

    assert opener.calls == []


@pytest.mark.parametrize(
    "feed_url",
    [
        "http://127.0.0.1:8009/catalog.csv",
        "http://localhost:8009/catalog.csv",
        "http://[::1]:8009/catalog.csv",
    ],
)
def test_plaintext_http_is_allowed_only_for_loopback_hosts(monkeypatch, feed_url):
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_URL", feed_url)
    opener = FakeOpener(FakeResponse(CSV_BYTES))

    assert read_http_feed_csv(opener=opener).content == CSV_BYTES


def test_invalid_configured_filename_is_rejected_before_any_request(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_HTTP_FEED_FILENAME", "catalog.txt")
    opener = FakeOpener(FakeResponse(CSV_BYTES))

    with pytest.raises(HTTPFeedNotConfiguredError):
        read_http_feed_csv(opener=opener)

    assert opener.calls == []


@pytest.mark.parametrize("status_code", [301, 302, 404, 500, 503])
def test_http_status_failures_are_translated_without_url_text(status_code, captured_logs):
    opener = FakeOpener(
        HTTPError(FEED_URL, status_code, "boom", {}, None)
    )

    with pytest.raises(HTTPFeedReadError) as error:
        read_http_feed_csv(opener=opener)

    assert "supplier.example.invalid" not in str(error.value)
    assert not any("supplier.example.invalid" in record.getMessage() for record in captured_logs.records)


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_retryable_http_statuses_raise_a_safe_transient_error(status_code):
    """A 429/5xx must stay retryable without retaining the configured feed URL."""
    with pytest.raises(HTTPFeedTransientError) as error:
        read_http_feed_csv(
            opener=FakeOpener(HTTPError(FEED_URL, status_code, "boom", {}, None))
        )

    assert error.value.error_code == "http_feed_http_retryable"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "supplier.example.invalid" not in str(error.value)


@pytest.mark.parametrize("status_code", [301, 302, 400, 404])
def test_permanent_http_statuses_raise_a_safe_non_retryable_error(status_code):
    """Redirects and non-429 client errors must not consume an Airflow retry."""
    with pytest.raises(HTTPFeedPermanentError) as error:
        read_http_feed_csv(
            opener=FakeOpener(HTTPError(FEED_URL, status_code, "boom", {}, None))
        )

    expected_code = (
        "http_feed_redirect_rejected"
        if status_code in {301, 302}
        else "http_feed_http_permanent"
    )
    assert error.value.error_code == expected_code
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "supplier.example.invalid" not in str(error.value)


def test_timeout_raises_a_safe_transient_error_without_the_original_cause():
    """A retryable network failure must not expose a URL through Airflow traceback chaining."""
    with pytest.raises(HTTPFeedTransientError) as error:
        read_http_feed_csv(opener=FakeOpener(TimeoutError("timed out")))

    assert error.value.error_code == "http_feed_network_retryable"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@pytest.mark.parametrize(
    "source_error",
    [
        ConnectionResetError("connection reset"),
        URLError(ConnectionError("temporary network failure")),
        URLError(socket.gaierror("temporary DNS failure")),
    ],
)
def test_retryable_network_errors_raise_safe_transient_errors(source_error):
    """Reset, temporary network, and DNS errors must be retryable by Airflow."""
    with pytest.raises(HTTPFeedTransientError) as error:
        read_http_feed_csv(opener=FakeOpener(source_error))

    assert error.value.error_code == "http_feed_network_retryable"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "supplier.example.invalid" not in str(error.value)


def test_network_failures_are_translated_without_url_text(captured_logs):
    opener = FakeOpener(URLError("connection refused to supplier.example.invalid"))

    with pytest.raises(HTTPFeedReadError) as error:
        read_http_feed_csv(opener=opener)

    assert "supplier.example.invalid" not in str(error.value)
    assert not any("supplier.example.invalid" in record.getMessage() for record in captured_logs.records)


def test_timeout_is_translated_to_a_safe_read_error():
    opener = FakeOpener(TimeoutError("timed out"))

    with pytest.raises(HTTPFeedReadError):
        read_http_feed_csv(opener=opener)


def test_oversized_content_length_is_rejected_before_reading_the_body():
    response = FakeResponse(
        b"x" * 10,
        content_length=str(MAX_UPLOAD_SIZE_BYTES + 1),
    )
    opener = FakeOpener(response)

    with pytest.raises(CsvUploadValidationError):
        read_http_feed_csv(opener=opener)

    assert response.read_sizes == []
    assert response.closed is True


def test_oversized_body_is_rejected_even_without_content_length():
    response = FakeResponse(b"x" * (MAX_UPLOAD_SIZE_BYTES + 10))
    opener = FakeOpener(response)

    with pytest.raises(CsvUploadValidationError):
        read_http_feed_csv(opener=opener)

    # 최대 크기 + 1 byte까지만 읽고 전체 응답을 메모리에 담지 않습니다.
    assert response.read_sizes == [MAX_UPLOAD_SIZE_BYTES + 1]
    assert response.closed is True


def test_lying_content_length_does_not_bypass_the_body_limit():
    response = FakeResponse(
        b"x" * (MAX_UPLOAD_SIZE_BYTES + 10),
        content_length="10",
    )
    opener = FakeOpener(response)

    with pytest.raises(CsvUploadValidationError):
        read_http_feed_csv(opener=opener)

    assert response.read_sizes == [MAX_UPLOAD_SIZE_BYTES + 1]
    assert response.closed is True


def test_empty_body_is_rejected_as_an_upload_validation_error():
    response = FakeResponse(b"")
    opener = FakeOpener(response)

    with pytest.raises(CsvUploadValidationError):
        read_http_feed_csv(opener=opener)

    assert response.closed is True


def test_non_bytes_body_is_translated_to_a_safe_read_error():
    response = FakeResponse(b"")
    response.read = lambda amount: "not bytes"  # type: ignore[assignment]
    opener = FakeOpener(response)

    with pytest.raises(HTTPFeedReadError):
        read_http_feed_csv(opener=opener)


def test_body_read_failure_is_translated_and_response_is_closed():
    response = FakeResponse(CSV_BYTES, read_error=URLError("stream broke"))
    opener = FakeOpener(response)

    with pytest.raises(HTTPFeedReadError):
        read_http_feed_csv(opener=opener)

    assert response.closed is True


def test_response_is_closed_on_success():
    response = FakeResponse(CSV_BYTES)
    read_http_feed_csv(opener=FakeOpener(response))

    assert response.closed is True
