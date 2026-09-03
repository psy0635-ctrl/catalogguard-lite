"""Bounded trusted HTTP CSV source adapter for the existing Web ETL pipeline."""

from __future__ import annotations

import logging
import socket
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from config.logging import LOGGER_NAME, log_event
from config.settings import (
    DEFAULT_ETL_HTTP_FEED_FILENAME,
    MAX_UPLOAD_SIZE_BYTES,
    get_catalogguard_etl_http_feed_filename,
    get_catalogguard_etl_http_feed_url,
)
from core.upload_validator import (
    CsvUploadValidationError,
    validate_csv_filename,
    validate_csv_size_bytes_count,
)


DEFAULT_HTTP_FEED_FILENAME = DEFAULT_ETL_HTTP_FEED_FILENAME
HTTP_FEED_TIMEOUT_SECONDS = 10.0
# 평문 HTTP는 서버를 떠나지 않는 loopback 주소에서만 허용합니다.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class HTTPFeedOpener(Protocol):
    def __call__(self, url: str, *, timeout: float) -> Any: ...


@dataclass(frozen=True)
class HTTPFeedSourceObject:
    source_filename: str
    content: bytes


class HTTPFeedNotConfiguredError(RuntimeError):
    """Raised when the server-side HTTP feed URL is missing or not allowed."""


class HTTPFeedReadError(RuntimeError):
    """Raised for safe HTTP status, network, and stream-read failures."""

    error_code = "http_feed_read_failed"

    def __init__(self, *_ignored: object) -> None:
        # Callers must never receive or log a configured URL through this exception.
        super().__init__("HTTP feed source could not be read")


class HTTPFeedTransientError(HTTPFeedReadError):
    """A safe HTTP feed failure that an orchestrator may retry."""

    error_code = "http_feed_network_retryable"


class HTTPFeedPermanentError(HTTPFeedReadError):
    """A safe HTTP feed failure that an orchestrator must not retry."""

    error_code = "http_feed_http_permanent"


_LOGGER = logging.getLogger(LOGGER_NAME)


def _log_http_feed_failure(code: str) -> None:
    # feed URL과 응답 본문은 credential을 담을 수 있으므로 코드만 남깁니다.
    log_event(
        _LOGGER,
        logging.WARNING,
        event="etl_http_source_failed",
        code=code,
    )


def _raise_not_configured(code: str) -> None:
    _log_http_feed_failure(code)
    raise HTTPFeedNotConfiguredError("HTTP feed source is not configured")


def _read_error_type(error: Exception | None) -> type[HTTPFeedReadError]:
    if isinstance(error, HTTPError):
        if error.code == 429 or 500 <= error.code <= 599:
            return HTTPFeedTransientError
        return HTTPFeedPermanentError

    if isinstance(error, URLError):
        reason = error.reason
        if isinstance(reason, (TimeoutError, ConnectionError, socket.gaierror)):
            return HTTPFeedTransientError
        return HTTPFeedPermanentError

    if isinstance(error, (TimeoutError, ConnectionError, socket.gaierror)):
        return HTTPFeedTransientError
    return HTTPFeedPermanentError


def _read_error_code(
    error: Exception | None,
    error_type: type[HTTPFeedReadError],
) -> str:
    if isinstance(error, HTTPError):
        if error.code in {301, 302, 303, 307, 308}:
            return "http_feed_redirect_rejected"
        if error_type is HTTPFeedTransientError:
            return "http_feed_http_retryable"
        return "http_feed_http_permanent"
    if error_type is HTTPFeedTransientError:
        return "http_feed_network_retryable"
    return "http_feed_read_failed"


def _new_read_error(error: Exception | None = None) -> HTTPFeedReadError:
    error_type = _read_error_type(error)
    error_code = _read_error_code(error, error_type)
    _log_http_feed_failure(error_code)
    safe_error = error_type()
    safe_error.error_code = error_code
    # Callers raise this after their except block so the URL-bearing urllib error
    # is not retained as either an explicit cause or implicit traceback context.
    return safe_error


def _require_allowed_feed_url() -> str:
    feed_url = get_catalogguard_etl_http_feed_url()
    if feed_url is None:
        _raise_not_configured("http_feed_not_configured")

    parts = urlsplit(feed_url)
    if parts.scheme == "https" and parts.hostname:
        return feed_url
    if parts.scheme == "http" and (parts.hostname or "") in LOOPBACK_HOSTS:
        return feed_url

    _raise_not_configured("http_feed_url_not_allowed")


def _no_redirect_opener() -> HTTPFeedOpener:
    # 신뢰 URL이 다른 host로 redirect되어 내부망으로 이동하는 것을 막습니다.
    class _RejectRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_RejectRedirects)

    def open_url(url: str, *, timeout: float) -> Any:
        return opener.open(url, timeout=timeout)

    return open_url


def _declared_content_length(response: object) -> int | None:
    headers = getattr(response, "headers", None)
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None

    raw_length = getter("Content-Length")
    try:
        size = int(str(raw_length).strip())
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def _validate_csv_size(size_bytes: int) -> None:
    try:
        validate_csv_size_bytes_count(size_bytes)
    except CsvUploadValidationError:
        _log_http_feed_failure("http_feed_read_failed")
        raise


def read_http_feed_csv(
    *,
    opener: HTTPFeedOpener | None = None,
) -> HTTPFeedSourceObject:
    """Read the configured trusted HTTP feed CSV with a bounded response read."""
    feed_url = _require_allowed_feed_url()
    source_filename = get_catalogguard_etl_http_feed_filename()
    try:
        validate_csv_filename(source_filename)
    except CsvUploadValidationError:
        # The filename is server configuration, not client-provided upload input.
        _raise_not_configured("http_feed_filename_invalid")
    open_url = _no_redirect_opener() if opener is None else opener

    try:
        response = open_url(feed_url, timeout=HTTP_FEED_TIMEOUT_SECONDS)
    except Exception as error:
        read_error = _new_read_error(error)
    else:
        read_error = None

    if read_error is not None:
        raise read_error

    body_read_error: HTTPFeedReadError | None = None
    try:
        declared_length = _declared_content_length(response)
        if declared_length is not None:
            # 본문을 읽기 전에 먼저 막을 수 있으면 막습니다.
            _validate_csv_size(declared_length)

        try:
            content = response.read(MAX_UPLOAD_SIZE_BYTES + 1)
        except CsvUploadValidationError:
            raise
        except Exception as error:
            body_read_error = _new_read_error(error)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - 정리 실패가 원래 오류를 가리지 않게 합니다.
                _log_http_feed_failure("http_feed_read_failed")

    if body_read_error is not None:
        raise body_read_error

    if not isinstance(content, bytes):
        raise _new_read_error()

    # Content-Length가 없거나 실제와 달라도 여기서 최종 크기를 다시 확인합니다.
    _validate_csv_size(len(content))
    return HTTPFeedSourceObject(
        source_filename=source_filename,
        content=content,
    )
