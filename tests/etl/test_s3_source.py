from __future__ import annotations

import json
import logging

import pytest

from config.logging import LOGGER_NAME
from config.settings import (
    MAX_UPLOAD_SIZE_BYTES,
    get_catalogguard_etl_s3_bucket,
    get_catalogguard_etl_s3_prefix,
)
from core.upload_validator import CsvUploadValidationError
from etl.s3_source import (
    S3KeyNotAllowedError,
    S3NotConfiguredError,
    S3ObjectNotFoundError,
    S3ReadError,
    read_s3_csv_object,
    sanitized_object_ref,
)


class FakeBody:
    def __init__(self, content: bytes, *, read_error: Exception | None = None) -> None:
        self.content = content
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


class FakeClientError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.response = {"Error": {"Code": code, "Message": message}}
        super().__init__(message)


class FakeS3Client:
    def __init__(
        self,
        *,
        head_response: dict | Exception,
        object_response: dict | Exception,
    ) -> None:
        self.head_response = head_response
        self.object_response = object_response
        self.calls: list[tuple[str, dict[str, str]]] = []

    def head_object(self, **kwargs):
        self.calls.append(("head_object", kwargs))
        if isinstance(self.head_response, Exception):
            raise self.head_response
        return self.head_response

    def get_object(self, **kwargs):
        self.calls.append(("get_object", kwargs))
        if isinstance(self.object_response, Exception):
            raise self.object_response
        return self.object_response


def _client_for(content: bytes = b"supplier,csv\n") -> tuple[FakeS3Client, FakeBody]:
    body = FakeBody(content)
    client = FakeS3Client(
        head_response={"ContentLength": len(content)},
        object_response={"ContentLength": len(content), "Body": body},
    )
    return client, body


def _client_error(code: str) -> FakeClientError:
    return FakeClientError(code, "raw SDK secret")


def test_s3_settings_getters_read_environment_at_call_time(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "  catalogguard-source  ")
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_PREFIX", " /incoming/vendor/ ")

    assert get_catalogguard_etl_s3_bucket() == "catalogguard-source"
    assert get_catalogguard_etl_s3_prefix() == "incoming/vendor/"


def test_blank_s3_prefix_allows_every_key(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_PREFIX", "   ")
    client, _ = _client_for()

    result = read_s3_csv_object("other/vendor/products.csv", client=client)

    assert result.source_filename == "products.csv"
    assert result.content == b"supplier,csv\n"
    assert [call[0] for call in client.calls] == ["head_object", "get_object"]


def test_unset_prefix_allows_a_csv_anywhere_in_configured_bucket(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.delenv("CATALOGGUARD_ETL_S3_PREFIX", raising=False)
    client, _ = _client_for()

    result = read_s3_csv_object("unrestricted/vendor/products.csv", client=client)

    assert result.source_filename == "products.csv"
    assert result.content == b"supplier,csv\n"


def test_configured_prefix_allows_key_inside_directory(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_PREFIX", "incoming/vendor")
    client, _ = _client_for()

    read_s3_csv_object("incoming/vendor/products.csv", client=client)

    assert [call[0] for call in client.calls] == ["head_object", "get_object"]


def test_prefix_blocks_similar_but_outside_directory_before_s3_calls(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_PREFIX", "incoming/vendor")
    client, _ = _client_for()

    with pytest.raises(S3KeyNotAllowedError):
        read_s3_csv_object("incoming/vendor2/products.csv", client=client)

    assert client.calls == []


@pytest.mark.parametrize("object_key", ["", "incoming/vendor/products.txt"])
def test_invalid_object_key_is_rejected_before_s3_calls(monkeypatch, object_key):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    client, _ = _client_for()

    with pytest.raises(CsvUploadValidationError):
        read_s3_csv_object(object_key, client=client)

    assert client.calls == []


def test_missing_bucket_is_rejected_before_s3_calls(monkeypatch):
    monkeypatch.delenv("CATALOGGUARD_ETL_S3_BUCKET", raising=False)
    client, _ = _client_for()

    with pytest.raises(S3NotConfiguredError):
        read_s3_csv_object("products.csv", client=client)

    assert client.calls == []


def test_missing_s3_object_is_translated_to_not_found(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    client = FakeS3Client(head_response=_client_error("NoSuchKey"), object_response={})

    with pytest.raises(S3ObjectNotFoundError):
        read_s3_csv_object("products.csv", client=client)

    assert [call[0] for call in client.calls] == ["head_object"]


def test_s3_client_failures_are_translated_without_sdk_text(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    client = FakeS3Client(head_response=_client_error("AccessDenied"), object_response={})

    with pytest.raises(S3ReadError) as exc_info:
        read_s3_csv_object("products.csv", client=client)

    assert "raw SDK secret" not in str(exc_info.value)


def test_malformed_head_response_is_translated_to_safe_read_error(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    client = FakeS3Client(head_response={}, object_response={})

    with pytest.raises(S3ReadError):
        read_s3_csv_object("products.csv", client=client)

    assert [call[0] for call in client.calls] == ["head_object"]


@pytest.fixture
def captured_s3_logs(caplog):
    """Capture project logger records regardless of global logging setup order.

    config.logging.configure_logging()은 catalogguard.api의 propagate를 False로 두고,
    이는 tests/test_api_logging.py가 명시적으로 검증하는 계약입니다. caplog의 기본
    handler는 root logger에 붙으므로, api.main을 import한 테스트가 같은 실행에서 먼저
    돌면 이 logger의 record가 root까지 올라오지 않아 caplog.records가 비게 됩니다.
    그래서 tests/test_api_logging.py의 captured_api_logs와 같은 방식으로 handler를
    project logger에 직접 붙이고 끝나면 반드시 떼어 냅니다. propagate 값과 production
    handler는 건드리지 않습니다.
    """
    logger = logging.getLogger(LOGGER_NAME)
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    # propagate가 아직 True인 실행(= configure_logging()이 한 번도 돌지 않은 경우)에는
    # caplog가 root에 붙여 둔 handler가 이 record를 이미 받습니다. 그때 handler를 또
    # 붙이면 같은 record가 두 번 잡히므로, 전파되지 않을 때만 직접 붙입니다. 여기서
    # propagate 값을 읽기만 하고 바꾸지 않는 것이 중요합니다.
    attach_directly = not logger.propagate
    if attach_directly:
        logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        if attach_directly:
            logger.removeHandler(caplog.handler)


def s3_source_failed_events(caplog) -> list[dict[str, object]]:
    """Return parsed etl_s3_source_failed events from the project logger only.

    record 위치(-1)에 기대지 않고 event 이름으로 고릅니다. 다른 library가 같은
    구간에서 로그를 남겨도 검증이 흔들리지 않습니다.
    """
    events = []
    for record in caplog.records:
        if record.name != LOGGER_NAME:
            continue
        try:
            event = json.loads(record.getMessage())
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "etl_s3_source_failed":
            events.append(event)
    return events


@pytest.mark.parametrize("size", [0, MAX_UPLOAD_SIZE_BYTES + 1])
def test_invalid_head_content_length_blocks_get_object_and_logs_safely(
    monkeypatch, captured_s3_logs, size
):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    client = FakeS3Client(head_response={"ContentLength": size}, object_response={})

    with pytest.raises(CsvUploadValidationError):
        read_s3_csv_object("products.csv", client=client)

    assert [call[0] for call in client.calls] == ["head_object"]
    events = s3_source_failed_events(captured_s3_logs)
    assert [event["code"] for event in events] == ["s3_read_failed"]


@pytest.mark.parametrize("size", [0, MAX_UPLOAD_SIZE_BYTES + 1])
def test_invalid_get_content_length_blocks_body_read_closes_body_and_logs_safely(
    monkeypatch, captured_s3_logs, size
):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    body = FakeBody(b"not read")
    client = FakeS3Client(
        head_response={"ContentLength": 1},
        object_response={"ContentLength": size, "Body": body},
    )

    with pytest.raises(CsvUploadValidationError):
        read_s3_csv_object("products.csv", client=client)

    assert body.read_sizes == []
    assert body.closed is True
    events = s3_source_failed_events(captured_s3_logs)
    assert [event["code"] for event in events] == ["s3_read_failed"]


def test_download_reads_at_bounded_size_and_closes_body(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    client, body = _client_for()

    read_s3_csv_object("products.csv", client=client)

    assert body.read_sizes == [MAX_UPLOAD_SIZE_BYTES + 1]
    assert body.closed is True


@pytest.mark.parametrize(
    "content",
    [b"", pytest.param(b"x" * (MAX_UPLOAD_SIZE_BYTES + 1), id="oversized")],
)
def test_bounded_download_rejects_invalid_size_closes_body_and_logs_safely(
    monkeypatch, captured_s3_logs, content
):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    body = FakeBody(content)
    client = FakeS3Client(
        head_response={"ContentLength": 1},
        object_response={"ContentLength": 1, "Body": body},
    )

    with pytest.raises(CsvUploadValidationError):
        read_s3_csv_object("products.csv", client=client)

    assert body.closed is True
    events = s3_source_failed_events(captured_s3_logs)
    assert [event["code"] for event in events] == ["s3_read_failed"]


def test_malformed_get_content_length_is_translated_to_safe_read_error(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    body = FakeBody(b"not read")
    client = FakeS3Client(
        head_response={"ContentLength": 1},
        object_response={"ContentLength": "1", "Body": body},
    )

    with pytest.raises(S3ReadError):
        read_s3_csv_object("products.csv", client=client)

    assert body.closed is True


@pytest.mark.parametrize("response", [{"ContentLength": 1}, {"ContentLength": 1, "Body": object()}])
def test_missing_or_invalid_get_body_is_translated_to_safe_read_error(monkeypatch, response):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    client = FakeS3Client(head_response={"ContentLength": 1}, object_response=response)

    with pytest.raises(S3ReadError):
        read_s3_csv_object("products.csv", client=client)


def test_body_read_failure_is_translated_and_body_is_closed(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    body = FakeBody(b"", read_error=OSError("network details"))
    client = FakeS3Client(
        head_response={"ContentLength": 1},
        object_response={"ContentLength": 1, "Body": body},
    )

    with pytest.raises(S3ReadError) as exc_info:
        read_s3_csv_object("products.csv", client=client)

    assert "network details" not in str(exc_info.value)
    assert body.closed is True


def test_sanitized_object_ref_drops_the_configured_prefix(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_PREFIX", "incoming/catalogguard/")

    ref = sanitized_object_ref("incoming/catalogguard/vendor-a/20260813.csv")

    # 허용 prefix는 서버 설정이라 배치별 provenance가 아닙니다. 남는 것은 허용 구역 안의 위치뿐입니다.
    assert ref == "vendor-a/20260813.csv"


def test_sanitized_object_ref_never_contains_the_bucket(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_PREFIX", "incoming/catalogguard/")

    ref = sanitized_object_ref("incoming/catalogguard/vendor-a/products.csv")

    assert "catalogguard-source" not in ref
    assert not ref.startswith("s3://")


def test_sanitized_object_ref_without_configured_prefix_keeps_the_relative_key(
    monkeypatch,
):
    monkeypatch.delenv("CATALOGGUARD_ETL_S3_PREFIX", raising=False)

    assert sanitized_object_ref("vendor-a/products.csv") == "vendor-a/products.csv"
    # 앞의 구분자는 bucket root를 뜻하므로 저장하지 않습니다.
    assert sanitized_object_ref("/vendor-a/products.csv") == "vendor-a/products.csv"
