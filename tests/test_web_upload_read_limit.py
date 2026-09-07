"""웹 업로드 endpoint가 파일 크기 제한을 적용해 읽는지 검증합니다."""

import asyncio

import pytest

from api.routes import etl_loads, inspection_jobs, inspections
from config.settings import MAX_UPLOAD_SIZE_BYTES


class ReadStopped(Exception):
    """업로드 읽기 인자를 기록한 뒤 endpoint 실행을 중단합니다."""


class RecordingUpload:
    filename = "products.csv"

    def __init__(self) -> None:
        self.requested_size: int | None = None

    async def read(self, size: int = -1) -> bytes:
        self.requested_size = size
        raise ReadStopped


def assert_bounded_read(coroutine, upload: RecordingUpload) -> None:
    with pytest.raises(ReadStopped):
        asyncio.run(coroutine)

    assert upload.requested_size == MAX_UPLOAD_SIZE_BYTES + 1


def test_inspection_upload_reads_at_most_one_byte_over_the_limit() -> None:
    upload = RecordingUpload()

    assert_bounded_read(
        inspections.create_inspection(
            file=upload,
            current_user=object(),
            session=object(),
            precheck_session=object(),
        ),
        upload,
    )


def test_async_inspection_upload_reads_at_most_one_byte_over_the_limit() -> None:
    upload = RecordingUpload()

    assert_bounded_read(
        inspection_jobs.submit_inspection_job(
            file=upload,
            service=object(),
            current_user=object(),
        ),
        upload,
    )


def test_web_etl_upload_reads_at_most_one_byte_over_the_limit() -> None:
    upload = RecordingUpload()

    assert_bounded_read(
        etl_loads.create_etl_load_run(
            http_request=object(),
            file=upload,
            profile_id="sample_fashion_vendor_v1",
            current_user=object(),
            session=object(),
        ),
        upload,
    )
