"""Bounded S3 CSV source adapter for the existing Web ETL pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from config.logging import LOGGER_NAME, log_event
from config.settings import (
    MAX_UPLOAD_SIZE_BYTES,
    get_catalogguard_etl_s3_bucket,
    get_catalogguard_etl_s3_prefix,
)
from core.upload_validator import (
    CsvUploadValidationError,
    validate_csv_filename,
    validate_csv_size_bytes_count,
)


class S3Client(Protocol):
    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class S3SourceObject:
    source_filename: str
    content: bytes


class S3NotConfiguredError(RuntimeError):
    """Raised when the server-side S3 bucket is not configured."""


class S3ObjectNotFoundError(RuntimeError):
    """Raised when S3 reports the configured object is absent."""


class S3KeyNotAllowedError(RuntimeError):
    """Raised when an object key is outside the configured prefix."""


class S3ReadError(RuntimeError):
    """Raised for safe S3 SDK, protocol, and stream-read failures."""


_LOGGER = logging.getLogger(LOGGER_NAME)
_NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}


def _log_s3_failure(code: str) -> None:
    log_event(
        _LOGGER,
        logging.WARNING,
        event="etl_s3_source_failed",
        code=code,
    )


def _raise_read_error(error: Exception) -> None:
    response = getattr(error, "response", None)
    error_info = response.get("Error", {}) if isinstance(response, dict) else {}
    error_code = str(error_info.get("Code", ""))
    if error_code in _NOT_FOUND_CODES:
        _log_s3_failure("s3_object_not_found")
        raise S3ObjectNotFoundError("S3 object was not found") from error

    _log_s3_failure("s3_read_failed")
    raise S3ReadError("S3 object could not be read") from error


def _require_configured_bucket() -> str:
    bucket = get_catalogguard_etl_s3_bucket()
    if bucket is None:
        _log_s3_failure("s3_not_configured")
        raise S3NotConfiguredError("S3 source is not configured")
    return bucket


def _validated_source_filename(object_key: str) -> str:
    validate_csv_filename(object_key)

    return str(object_key).replace("\\", "/").split("/")[-1].strip()


def _validate_configured_prefix(object_key: str) -> None:
    prefix = get_catalogguard_etl_s3_prefix()
    if prefix is not None and not object_key.startswith(prefix):
        _log_s3_failure("s3_key_not_allowed")
        raise S3KeyNotAllowedError("S3 object key is not allowed")


def sanitized_object_ref(object_key: str) -> str:
    """Return a lineage-safe locator for one S3 object key.

    The bucket name is never included, and the configured prefix is removed because it is
    server configuration rather than per-batch provenance. What remains is the object's
    position inside the allowed area, which is what identifies the batch later.
    """
    key = str(object_key).replace("\\", "/").strip()
    prefix = get_catalogguard_etl_s3_prefix()
    if prefix is not None and key.startswith(prefix):
        key = key[len(prefix) :]
    return key.lstrip("/")


def _content_length(response: object) -> int:
    if not isinstance(response, dict):
        _log_s3_failure("s3_read_failed")
        raise S3ReadError("S3 response was invalid")

    size = response.get("ContentLength")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        _log_s3_failure("s3_read_failed")
        raise S3ReadError("S3 response was invalid")
    return size


def _validate_csv_size(size_bytes: int) -> None:
    try:
        validate_csv_size_bytes_count(size_bytes)
    except CsvUploadValidationError:
        _log_s3_failure("s3_read_failed")
        raise


def _response_body(response: object) -> Any:
    if not isinstance(response, dict) or "Body" not in response:
        _log_s3_failure("s3_read_failed")
        raise S3ReadError("S3 response was invalid")
    body = response["Body"]
    if not callable(getattr(body, "read", None)) or not callable(
        getattr(body, "close", None)
    ):
        _log_s3_failure("s3_read_failed")
        raise S3ReadError("S3 response was invalid")
    return body


def _create_s3_client() -> S3Client:
    try:
        import boto3

        return boto3.client("s3")
    except Exception as error:
        _raise_read_error(error)


def read_s3_csv_object(
    object_key: str,
    *,
    client: S3Client | None = None,
) -> S3SourceObject:
    """Read one configured S3 CSV object after bounded metadata validation."""
    bucket = _require_configured_bucket()
    source_filename = _validated_source_filename(object_key)
    _validate_configured_prefix(object_key)
    s3_client = _create_s3_client() if client is None else client

    try:
        head_response = s3_client.head_object(Bucket=bucket, Key=object_key)
    except Exception as error:
        _raise_read_error(error)
    _validate_csv_size(_content_length(head_response))

    try:
        response = s3_client.get_object(Bucket=bucket, Key=object_key)
    except Exception as error:
        _raise_read_error(error)

    body = _response_body(response)
    try:
        _validate_csv_size(_content_length(response))
        try:
            content = body.read(MAX_UPLOAD_SIZE_BYTES + 1)
        except Exception as error:
            _raise_read_error(error)
    finally:
        try:
            body.close()
        except Exception:  # noqa: BLE001 - 정리 실패가 이미 읽은 본문 결과를 가리지 않게 합니다.
            _log_s3_failure("s3_read_failed")

    if not isinstance(content, bytes):
        _log_s3_failure("s3_read_failed")
        raise S3ReadError("S3 response was invalid")

    _validate_csv_size(len(content))
    return S3SourceObject(source_filename=source_filename, content=content)
