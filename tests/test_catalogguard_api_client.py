import importlib
from datetime import date

import pytest
import requests

from config import settings


LIST_RESPONSE = {
    "items": [
        {
            "inspection_run_id": 11,
            "source_filename": "products_dev.csv",
            "created_at": "2026-07-04T13:42:39.495949+09:00",
            "total_products": 5,
            "total_issues": 6,
            "error_count": 6,
            "warning_count": 0,
        }
    ],
    "total": 1,
    "limit": 20,
    "offset": 0,
}

DETAIL_RESPONSE = {
    "inspection_run_id": 11,
    "source_filename": "products_dev.csv",
    "created_at": "2026-07-04T13:42:39.495949+09:00",
    "summary": {
        "total_products": 5,
        "total_issues": 6,
        "error_count": 6,
        "warning_count": 0,
    },
    "results": [],
}

CREATE_RESPONSE = {
    "inspection_run_id": 12,
    "created": True,
    "summary": {
        "total_products": 5,
        "total_issues": 6,
        "error_count": 6,
        "warning_count": 0,
    },
    "results": [],
}

CREATE_RESPONSE_WITHOUT_CREATED = {
    "inspection_run_id": 12,
    "summary": {
        "total_products": 5,
        "total_issues": 6,
        "error_count": 6,
        "warning_count": 0,
    },
    "results": [],
}

CREATE_DUPLICATE_RESPONSE = {
    "inspection_run_id": 11,
    "created": False,
    "summary": {
        "total_products": 5,
        "total_issues": 6,
        "error_count": 6,
        "warning_count": 0,
    },
    "results": [],
}

JOB_ID = "12345678-1234-5678-1234-567812345678"
JOB_SUBMISSION_RESPONSE = {
    "job_id": JOB_ID,
    "status": "queued",
    "status_url": f"/api/v1/inspection-jobs/{JOB_ID}",
}


def make_job_status_response(status):
    response = {
        "job_id": JOB_ID,
        "status": status,
        "created": None,
        "inspection_run_id": None,
        "summary": None,
        "error_code": None,
        "message": None,
        "created_at": "2026-07-22T10:00:00+09:00",
        "updated_at": "2026-07-22T10:00:01+09:00",
    }
    if status == "succeeded":
        response.update(
            created=True,
            inspection_run_id=12,
            summary=CREATE_RESPONSE["summary"],
        )
    if status == "failed":
        response.update(
            error_code="inspection_failed",
            message="검수 처리 중 오류가 발생했습니다.",
        )
    return response

VALID_REQUEST_ID = "a29ae9a1c62f4152bb96f6513c323d96"


class FakeResponse:
    def __init__(
        self,
        *,
        payload=None,
        status_code=200,
        json_error=None,
        text="",
        headers=None,
    ):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("HTTP error", response=self)

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.headers = {}

    def get(self, url, *, params=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "timeout": timeout,
            }
        )
        if self.error is not None:
            raise self.error
        return self.response

    def post(self, url, *, files=None, data=None, json=None, timeout=None):
        call = {
            "url": url,
            "files": files,
            "timeout": timeout,
        }
        if data is not None:
            call["data"] = data
        if json is not None:
            call["json"] = json
        self.calls.append(call)
        if self.error is not None:
            raise self.error
        return self.response


def import_client_module():
    return importlib.import_module("clients.catalogguard_api")


def make_client(*, response=None, error=None, timeout_seconds=5.0):
    client_module = import_client_module()
    session = FakeSession(response=response, error=error)
    client = client_module.CatalogGuardApiClient(
        "https://api.example.com/",
        timeout_seconds=timeout_seconds,
        session=session,
    )
    return client, session


def test_get_catalogguard_api_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_API_BASE_URL", "https://api.example.com/")

    assert settings.get_catalogguard_api_base_url() == "https://api.example.com"


def test_create_client_requires_base_url(monkeypatch):
    client_module = import_client_module()
    monkeypatch.delenv("CATALOGGUARD_API_BASE_URL", raising=False)

    with pytest.raises(client_module.CatalogGuardApiConfigurationError) as error:
        client_module.create_catalogguard_api_client()

    assert "검수 이력 API 주소가 설정되지 않았습니다." in str(error.value)
    assert "localhost" not in str(error.value)
    assert "http://" not in str(error.value)


def test_get_catalogguard_api_timeout_seconds_uses_default_for_missing_value(
    monkeypatch,
):
    monkeypatch.delenv("CATALOGGUARD_API_TIMEOUT_SECONDS", raising=False)

    assert settings.get_catalogguard_api_timeout_seconds() == 5.0


def test_get_catalogguard_api_timeout_seconds_uses_default_for_invalid_value(
    monkeypatch,
):
    monkeypatch.setenv("CATALOGGUARD_API_TIMEOUT_SECONDS", "-1")

    assert settings.get_catalogguard_api_timeout_seconds() == 5.0


def test_list_inspections_calls_expected_endpoint_with_pagination_and_timeout():
    client, session = make_client(
        response=FakeResponse(payload=LIST_RESPONSE),
        timeout_seconds=7.5,
    )

    data = client.list_inspections(limit=20, offset=0)

    assert data == LIST_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections",
            "params": {"limit": 20, "offset": 0},
            "timeout": 7.5,
        }
    ]


def test_list_inspections_includes_trimmed_filename_when_provided():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    data = client.list_inspections(
        limit=10,
        offset=0,
        filename="  products  ",
    )

    assert data == LIST_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections",
            "params": {"limit": 10, "offset": 0, "filename": "products"},
            "timeout": 5.0,
        }
    ]


def test_list_inspections_omits_blank_filename():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    client.list_inspections(filename="   ")

    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections",
            "params": {"limit": 20, "offset": 0},
            "timeout": 5.0,
        }
    ]


def test_list_inspections_includes_iso_start_and_end_dates_when_provided():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    data = client.list_inspections(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
    )

    assert data == LIST_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections",
            "params": {
                "limit": 20,
                "offset": 0,
                "start_date": "2026-07-01",
                "end_date": "2026-07-05",
            },
            "timeout": 5.0,
        }
    ]


def test_list_inspections_includes_filename_and_date_filters_together():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    client.list_inspections(
        limit=10,
        offset=20,
        filename=" products ",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
    )

    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections",
            "params": {
                "limit": 10,
                "offset": 20,
                "filename": "products",
                "start_date": "2026-07-01",
                "end_date": "2026-07-05",
            },
            "timeout": 5.0,
        }
    ]


@pytest.mark.parametrize("status_value", ["error", "warning", "normal"])
def test_list_inspections_includes_status_when_provided(status_value):
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    data = client.list_inspections(status=status_value)

    assert data == LIST_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections",
            "params": {"limit": 20, "offset": 0, "status": status_value},
            "timeout": 5.0,
        }
    ]


def test_list_inspections_includes_filename_date_and_status_filters_together():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    client.list_inspections(
        limit=10,
        offset=20,
        filename=" products ",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        status="warning",
    )

    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections",
            "params": {
                "limit": 10,
                "offset": 20,
                "filename": "products",
                "start_date": "2026-07-01",
                "end_date": "2026-07-05",
                "status": "warning",
            },
            "timeout": 5.0,
        }
    ]


def test_list_inspections_rejects_invalid_status_without_request():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    with pytest.raises(ValueError, match="status"):
        client.list_inspections(status="all")

    assert session.calls == []


def test_get_inspection_detail_calls_expected_endpoint_with_timeout():
    client, session = make_client(
        response=FakeResponse(payload=DETAIL_RESPONSE),
        timeout_seconds=3.0,
    )

    data = client.get_inspection_detail(11)

    assert data == DETAIL_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections/11",
            "params": None,
            "timeout": 3.0,
        }
    ]


def test_create_inspection_posts_multipart_file_with_timeout():
    client, session = make_client(
        response=FakeResponse(payload=CREATE_RESPONSE),
        timeout_seconds=8.5,
    )

    data = client.create_inspection(
        source_filename="products_dev.csv",
        file_content=b"product_id,price\nP001,1000\n",
        content_type="text/csv",
    )

    assert data == CREATE_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspections",
            "files": {
                "file": (
                    "products_dev.csv",
                    b"product_id,price\nP001,1000\n",
                    "text/csv",
                )
            },
            "timeout": 8.5,
        }
    ]


def test_submit_inspection_job_posts_multipart_file_and_accepts_202_response():
    client, session = make_client(
        response=FakeResponse(payload=JOB_SUBMISSION_RESPONSE, status_code=202),
        timeout_seconds=7.5,
    )

    data = client.submit_inspection_job(
        source_filename="products_dev.csv",
        file_content=b"product_id,price\nP001,1000\n",
        content_type="text/csv",
    )

    assert data == JOB_SUBMISSION_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/inspection-jobs",
            "files": {
                "file": (
                    "products_dev.csv",
                    b"product_id,price\nP001,1000\n",
                    "text/csv",
                )
            },
            "timeout": 7.5,
        }
    ]


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "failed"])
def test_get_inspection_job_returns_supported_statuses(status):
    response = make_job_status_response(status)
    client, session = make_client(
        response=FakeResponse(payload=response),
        timeout_seconds=4.0,
    )

    data = client.get_inspection_job(JOB_ID)

    assert data == response
    assert session.calls == [
        {
            "url": f"https://api.example.com/api/v1/inspection-jobs/{JOB_ID}",
            "params": None,
            "timeout": 4.0,
        }
    ]


def test_submit_inspection_job_converts_connection_error():
    client_module = import_client_module()
    client, _ = make_client(error=requests.ConnectionError("redis.internal:6379"))

    with pytest.raises(client_module.CatalogGuardApiConnectionError) as error:
        client.submit_inspection_job(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert str(error.value) == "검수 이력 서버에 연결할 수 없습니다."
    assert "redis.internal" not in str(error.value)


def test_get_inspection_job_converts_timeout_error():
    client_module = import_client_module()
    client, _ = make_client(error=requests.Timeout("too slow"))

    with pytest.raises(client_module.CatalogGuardApiTimeoutError):
        client.get_inspection_job(JOB_ID)


def test_get_inspection_job_converts_404_to_not_found():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(status_code=404))

    with pytest.raises(client_module.InspectionNotFoundError):
        client.get_inspection_job(JOB_ID)


def test_submit_inspection_job_rejects_invalid_json():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(json_error=requests.JSONDecodeError("bad json", "", 0))
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.submit_inspection_job(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )


@pytest.mark.parametrize(
    "method_name,payload",
    [
        ("submit_inspection_job", {"job_id": JOB_ID, "status": "queued"}),
        ("get_inspection_job", {"job_id": JOB_ID}),
    ],
)
def test_inspection_job_methods_reject_missing_required_fields(method_name, payload):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        if method_name == "submit_inspection_job":
            client.submit_inspection_job(
                source_filename="products_dev.csv",
                file_content=b"product_id,price\nP001,1000\n",
            )
        else:
            client.get_inspection_job(JOB_ID)


@pytest.mark.parametrize(
    "method_name,payload",
    [
        (
            "submit_inspection_job",
            {**JOB_SUBMISSION_RESPONSE, "status": "running"},
        ),
        (
            "get_inspection_job",
            {**make_job_status_response("queued"), "status": "unknown"},
        ),
    ],
)
def test_inspection_job_methods_reject_invalid_status(method_name, payload):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        if method_name == "submit_inspection_job":
            client.submit_inspection_job(
                source_filename="products_dev.csv",
                file_content=b"product_id,price\nP001,1000\n",
            )
        else:
            client.get_inspection_job(JOB_ID)


def test_get_inspection_job_rejects_invalid_job_id_without_request():
    client, session = make_client(
        response=FakeResponse(payload=make_job_status_response("queued"))
    )

    with pytest.raises(ValueError, match="job_id"):
        client.get_inspection_job("../internal")

    assert session.calls == []


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("inspection_run_id", None),
        ("inspection_run_id", "12"),
        ("inspection_run_id", 0),
        ("inspection_run_id", True),
        ("created", None),
        ("created", "true"),
        ("created", 1),
    ],
)
def test_get_inspection_job_rejects_invalid_succeeded_completion_fields(
    field,
    invalid_value,
):
    client_module = import_client_module()
    payload = {
        **make_job_status_response("succeeded"),
        field: invalid_value,
    }
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.get_inspection_job(JOB_ID)


def test_get_inspection_job_rejects_non_object_json_response():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=[]))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.get_inspection_job(JOB_ID)


@pytest.mark.parametrize(
    "status_url",
    [
        "https://internal.example/api/v1/inspection-jobs/secret",
        "/api/v1/inspection-jobs/87654321-4321-8765-4321-876543218765",
        "/api/v1/inspection-jobs",
    ],
)
def test_submit_inspection_job_rejects_mismatched_status_url(status_url):
    client_module = import_client_module()
    payload = {**JOB_SUBMISSION_RESPONSE, "status_url": status_url}
    client, _ = make_client(response=FakeResponse(payload=payload, status_code=202))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.submit_inspection_job(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )


def test_create_inspection_defaults_missing_created_to_true():
    client, _ = make_client(
        response=FakeResponse(payload=CREATE_RESPONSE_WITHOUT_CREATED),
    )

    data = client.create_inspection(
        source_filename="products_dev.csv",
        file_content=b"product_id,price\nP001,1000\n",
    )

    assert data == {**CREATE_RESPONSE_WITHOUT_CREATED, "created": True}


def test_create_inspection_preserves_created_false():
    client, _ = make_client(response=FakeResponse(payload=CREATE_DUPLICATE_RESPONSE))

    data = client.create_inspection(
        source_filename="products_dev.csv",
        file_content=b"product_id,price\nP001,1000\n",
    )

    assert data == CREATE_DUPLICATE_RESPONSE


@pytest.mark.parametrize("created_value", ["false", 0, 1, None])
def test_create_inspection_rejects_non_bool_created(created_value):
    client_module = import_client_module()
    payload = {**CREATE_RESPONSE, "created": created_value}
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert "검수 이력 서버의 응답 형식이 올바르지 않습니다." in str(error.value)


def test_list_inspections_converts_connection_error_without_leaking_url():
    client_module = import_client_module()
    client, _ = make_client(
        error=requests.ConnectionError("failed to reach http://internal.example")
    )

    with pytest.raises(client_module.CatalogGuardApiConnectionError) as error:
        client.list_inspections()

    message = str(error.value)
    assert "검수 이력 서버에 연결할 수 없습니다." in message
    assert "http://internal.example" not in message
    assert error.value.request_id is None


def test_list_inspections_converts_timeout_error():
    client_module = import_client_module()
    client, _ = make_client(error=requests.Timeout("too slow"))

    with pytest.raises(client_module.CatalogGuardApiTimeoutError) as error:
        client.list_inspections()

    assert "검수 이력 서버 응답 시간이 초과되었습니다." in str(error.value)
    assert error.value.request_id is None


def test_create_inspection_converts_connection_error_without_leaking_url():
    client_module = import_client_module()
    client, _ = make_client(
        error=requests.ConnectionError("failed to reach http://internal.example")
    )

    with pytest.raises(client_module.CatalogGuardApiConnectionError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    message = str(error.value)
    assert "검수 이력 서버에 연결할 수 없습니다." in message
    assert "http://internal.example" not in message
    assert error.value.request_id is None


def test_create_inspection_converts_timeout_error():
    client_module = import_client_module()
    client, _ = make_client(error=requests.Timeout("too slow"))

    with pytest.raises(client_module.CatalogGuardApiTimeoutError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert "검수 이력 서버 응답 시간이 초과되었습니다." in str(error.value)
    assert error.value.request_id is None


def test_get_inspection_detail_converts_404_to_not_found():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(status_code=404, text="not found"))

    with pytest.raises(client_module.InspectionNotFoundError) as error:
        client.get_inspection_detail(11)

    assert "검수 실행 결과를 찾을 수 없습니다." in str(error.value)


def test_get_inspection_detail_preserves_valid_request_id_for_404():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=404,
            text="not found",
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.InspectionNotFoundError) as error:
        client.get_inspection_detail(11)

    assert error.value.request_id == VALID_REQUEST_ID


def test_list_inspections_converts_server_error_without_leaking_body():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=500, text="Traceback: secret stack trace")
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    message = str(error.value)
    assert "검수 이력 서버에서 오류가 발생했습니다." in message
    assert "Traceback" not in message
    assert "secret" not in message


def test_list_inspections_preserves_valid_request_id_for_server_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    assert error.value.request_id == VALID_REQUEST_ID


def test_list_inspections_uses_none_request_id_when_header_is_missing():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(status_code=500))

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    assert error.value.request_id is None


def test_list_inspections_trims_valid_request_id_header():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            headers={"X-Request-ID": f"  {VALID_REQUEST_ID}  "},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    assert error.value.request_id == VALID_REQUEST_ID


@pytest.mark.parametrize(
    "header_value",
    [
        "",
        "   ",
        VALID_REQUEST_ID.upper(),
        "a" * 31,
        "a" * 33,
        f"{VALID_REQUEST_ID[:-1]}-",
        "a" * 10000,
    ],
)
def test_list_inspections_rejects_invalid_request_id_header(header_value):
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            headers={"X-Request-ID": header_value},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    assert error.value.request_id is None


def test_create_inspection_converts_server_error_without_leaking_body():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=500, text="Traceback: secret stack trace")
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    message = str(error.value)
    assert "검수 이력 서버에서 오류가 발생했습니다." in message
    assert "Traceback" not in message
    assert "secret" not in message


def test_create_inspection_preserves_valid_request_id_for_server_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert error.value.request_id == VALID_REQUEST_ID


def test_server_error_does_not_leak_sensitive_response_body_values():
    client_module = import_client_module()
    sensitive_values = [
        "postgresql://catalog:fake-password@internal-db.example:5432/catalog",
        "fake-password",
        "internal-db.example",
    ]
    client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            text=" ".join(sensitive_values),
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    message = str(error.value)
    assert message == "검수 이력 서버에서 오류가 발생했습니다."
    assert all(value not in message for value in sensitive_values)


def test_list_inspections_converts_invalid_json():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            json_error=requests.JSONDecodeError("bad json", "", 0),
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    assert "검수 이력 서버의 응답 형식이 올바르지 않습니다." in str(error.value)


def test_list_inspections_preserves_request_id_for_invalid_json():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            json_error=requests.JSONDecodeError("bad json", "", 0),
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    assert error.value.request_id == VALID_REQUEST_ID


def test_create_inspection_converts_invalid_json():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            json_error=requests.JSONDecodeError("bad json", "", 0),
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert "검수 이력 서버의 응답 형식이 올바르지 않습니다." in str(error.value)


def test_create_inspection_preserves_request_id_for_invalid_json():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            json_error=requests.JSONDecodeError("bad json", "", 0),
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert error.value.request_id == VALID_REQUEST_ID


def test_list_inspections_rejects_missing_required_keys():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload={"items": []}))

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_inspections()

    assert "검수 이력 서버의 응답 형식이 올바르지 않습니다." in str(error.value)


def test_create_inspection_rejects_missing_required_keys():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload={"inspection_run_id": 12}))

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert "검수 이력 서버의 응답 형식이 올바르지 않습니다." in str(error.value)


def test_get_inspection_detail_rejects_missing_required_keys():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload={"inspection_run_id": 11}))

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.get_inspection_detail(11)

    assert "검수 이력 서버의 응답 형식이 올바르지 않습니다." in str(error.value)


@pytest.mark.parametrize(
    ("limit", "offset"),
    [
        (0, 0),
        (101, 0),
        (20, -1),
    ],
)
def test_list_inspections_rejects_invalid_pagination_without_request(limit, offset):
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    with pytest.raises(ValueError):
        client.list_inspections(limit=limit, offset=offset)

    assert session.calls == []


def test_list_inspections_rejects_too_long_filename_without_request():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    with pytest.raises(ValueError):
        client.list_inspections(filename="a" * 101)

    assert session.calls == []


ETL_LOAD_LIST_RESPONSE = {
    "items": [
        {
            "etl_load_run_id": 12,
            "source_filename": "vendor_products.csv",
            "profile_name": "sample_fashion_vendor_v2",
            "profile_version": "1",
            "loaded_rows": 25,
            "total_rows": 30,
            "rejected_rows": 5,
            "created_at": "2026-07-25T12:00:00Z",
        }
    ],
    "total": 1,
    "limit": 10,
    "offset": 0,
}

ETL_LOAD_DETAIL_RESPONSE = {
    "etl_load_run_id": 12,
    "source_filename": "vendor_products.csv",
    "profile_name": "sample_fashion_vendor_v2",
    "profile_version": "1",
    "input_file_sha256": "a" * 64,
    "output_file_sha256": "b" * 64,
    "loaded_rows": 25,
    "total_rows": 30,
    "rejected_rows": 5,
    "error_counts": {"INVALID_PRICE": 5},
    "reject_details_stored": True,
    "created_at": "2026-07-25T12:00:00Z",
    "products": {
        "items": [
            {
                "staging_product_id": 101,
                "product_group_id": "GROUP-001",
                "product_id": "SKU-001",
                "product_name": "Basic T-shirt",
                "category": "TOP",
                "color": "BLACK",
                "size": "M",
                "stock": 10,
                "price": 19900,
                "sale_price": None,
                "image_path": "image.jpg",
                "description": None,
                "seller": None,
                "created_at": "2026-07-25T12:00:00Z",
            }
        ],
        "total": 25,
        "limit": 20,
        "offset": 0,
    },
}

ETL_REJECTIONS_RESPONSE = {
    "available": True,
    "items": [
        {
            "rejected_row_id": 301,
            "source_row_number": 4,
            "errors": [
                {
                    "code": "INVALID_PRICE",
                    "field": "price",
                    "message": "bad price",
                }
            ],
            "masked_source_data": {"description": "010-****-5678"},
            "created_at": "2026-07-25T12:00:00Z",
        }
    ],
    "total": 1,
    "limit": 20,
    "offset": 0,
}


def test_list_etl_loads_calls_etl_endpoint_and_trims_filters():
    client, session = make_client(
        response=FakeResponse(payload=ETL_LOAD_LIST_RESPONSE),
        timeout_seconds=7.5,
    )

    data = client.list_etl_loads(
        limit=10,
        offset=20,
        filename="  vendor_products.csv  ",
        profile_name="  fashion  ",
    )

    assert data == ETL_LOAD_LIST_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-loads",
            "params": {
                "limit": 10,
                "offset": 20,
                "filename": "vendor_products.csv",
                "profile_name": "fashion",
            },
            "timeout": 7.5,
        }
    ]


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (10, -1), (True, 0), (10, False)],
)
def test_list_etl_loads_rejects_invalid_pagination_without_request(limit, offset):
    client, session = make_client(
        response=FakeResponse(payload=ETL_LOAD_LIST_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.list_etl_loads(limit=limit, offset=offset)

    assert session.calls == []


def test_list_etl_loads_validates_item_shape():
    client, _ = make_client(
        response=FakeResponse(
            payload={**ETL_LOAD_LIST_RESPONSE, "items": [{"etl_load_run_id": 12}]}
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.list_etl_loads()


def test_get_etl_load_detail_calls_detail_endpoint_and_preserves_nullable_fields():
    client, session = make_client(
        response=FakeResponse(payload=ETL_LOAD_DETAIL_RESPONSE),
        timeout_seconds=3.0,
    )

    data = client.get_etl_load_detail(
        12,
        product_limit=20,
        product_offset=40,
    )

    assert data == ETL_LOAD_DETAIL_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-loads/12",
            "params": {"product_limit": 20, "product_offset": 40},
            "timeout": 3.0,
        }
    ]


@pytest.mark.parametrize(
    "run_id",
    [0, -1, True, "12"],
)
def test_get_etl_load_detail_rejects_invalid_run_id_without_request(run_id):
    client, session = make_client(
        response=FakeResponse(payload=ETL_LOAD_DETAIL_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.get_etl_load_detail(run_id)

    assert session.calls == []


def test_get_etl_load_detail_maps_404_to_etl_load_not_found_and_keeps_request_id():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=404,
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.ETLLoadNotFoundError) as error:
        client.get_etl_load_detail(12)

    assert error.value.request_id == VALID_REQUEST_ID


def test_get_etl_load_detail_rejects_invalid_hash_and_product_shape():
    client, _ = make_client(
        response=FakeResponse(
            payload={
                **ETL_LOAD_DETAIL_RESPONSE,
                "input_file_sha256": "not-a-sha",
            }
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_load_detail(12)


@pytest.mark.parametrize(
    "changes",
    [
        {"total_rows": True},
        {"total_rows": 31},
        {"rejected_rows": -1},
        {"error_counts": []},
        {"error_counts": {"": 1}},
        {"error_counts": {"INVALID_PRICE": True}},
        {"error_counts": {"INVALID_PRICE": 0}},
        {"error_counts": None, "total_rows": 30, "rejected_rows": 5},
    ],
)
def test_get_etl_load_detail_rejects_invalid_quality_summary(changes):
    client, _ = make_client(
        response=FakeResponse(
            payload={**ETL_LOAD_DETAIL_RESPONSE, **changes}
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_load_detail(12)


def test_get_etl_load_detail_accepts_nullable_quality_summary_for_legacy_batch():
    client, _ = make_client(
        response=FakeResponse(
            payload={
                **ETL_LOAD_DETAIL_RESPONSE,
                "total_rows": None,
                "rejected_rows": None,
                "error_counts": None,
            }
        )
    )

    assert client.get_etl_load_detail(12)["error_counts"] is None


def test_list_etl_rejections_calls_endpoint_and_validates_contract():
    client, session = make_client(
        response=FakeResponse(payload=ETL_REJECTIONS_RESPONSE),
        timeout_seconds=3.0,
    )

    data = client.list_etl_rejections(12, limit=20, offset=40)

    assert data == ETL_REJECTIONS_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-loads/12/rejections",
            "params": {"limit": 20, "offset": 40},
            "timeout": 3.0,
        }
    ]


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (20, -1), (True, 0), (20, False)],
)
def test_list_etl_rejections_rejects_invalid_pagination_without_request(limit, offset):
    client, session = make_client(
        response=FakeResponse(payload=ETL_REJECTIONS_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.list_etl_rejections(12, limit=limit, offset=offset)

    assert session.calls == []


def test_list_etl_rejections_maps_404_to_etl_load_not_found():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(status_code=404))

    with pytest.raises(client_module.ETLLoadNotFoundError):
        client.list_etl_rejections(12)


def test_list_etl_rejections_rejects_raw_source_values_and_invalid_error_shape():
    client, _ = make_client(
        response=FakeResponse(
            payload={
                **ETL_REJECTIONS_RESPONSE,
                "items": [
                    {
                        **ETL_REJECTIONS_RESPONSE["items"][0],
                        "errors": [],
                    }
                ],
            }
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.list_etl_rejections(12)


def test_get_inspection_detail_rejects_invalid_id_without_request():
    client, session = make_client(response=FakeResponse(payload=DETAIL_RESPONSE))

    with pytest.raises(ValueError):
        client.get_inspection_detail(0)

    assert session.calls == []


def test_create_inspection_rejects_empty_filename_without_request():
    client, session = make_client(response=FakeResponse(payload=CREATE_RESPONSE))

    with pytest.raises(ValueError):
        client.create_inspection(
            source_filename="",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert session.calls == []


def test_create_inspection_rejects_empty_file_content_without_request():
    client, session = make_client(response=FakeResponse(payload=CREATE_RESPONSE))

    with pytest.raises(ValueError):
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"",
        )

    assert session.calls == []


CATALOG_PROMOTION_PREVIEW_RESPONSE = {
    "etl_load_run_id": 12,
    "supplier_key": "sample_fashion_vendor_v2",
    "inspection_version": "2026.07",
    "preview_schema_version": 1,
    "preview_hash": "a" * 64,
    "promotion_eligible": True,
    "blocked_reasons": [],
    "insert_count": 0,
    "update_count": 1,
    "unchanged_count": 0,
    "error_count": 0,
    "warning_count": 1,
    "items": [
        {
            "supplier_key": "sample_fashion_vendor_v2",
            "external_product_id": "SKU-001",
            "action": "update",
            "changed_fields": {
                "price": {"before": 19900, "after": 20900},
            },
            "before_data": {
                "external_product_id": "SKU-001",
                "product_group_id": "GROUP-001",
                "product_name": "Basic T-shirt",
                "category": "TOP",
                "color": "BLACK",
                "size": "M",
                "stock": 10,
                "price": 19900,
                "sale_price": None,
                "image_path": "before.jpg",
                "description": None,
                "seller": "supplier-a",
            },
            "after_data": {
                "external_product_id": "SKU-001",
                "product_group_id": "GROUP-001",
                "product_name": "Basic T-shirt",
                "category": "TOP",
                "color": "BLACK",
                "size": "M",
                "stock": 10,
                "price": 20900,
                "sale_price": None,
                "image_path": "after.jpg",
                "description": None,
                "seller": "supplier-a",
            },
        }
    ],
}

CATALOG_PROMOTION_RESPONSE = {
    "promotion_run_id": 31,
    "etl_load_run_id": 12,
    "status": "succeeded",
    "created": True,
    "preview_hash": "a" * 64,
    "preview_schema_version": 1,
    "inspection_version": "2026.07",
    "inserted_count": 1,
    "updated_count": 1,
    "unchanged_count": 1,
    "blocked_count": 0,
    "error_count": 0,
    "warning_count": 1,
    "started_at": "2026-07-30T10:00:00Z",
    "completed_at": "2026-07-30T10:00:01Z",
}

CATALOG_PROMOTION_RUN_ITEM = {
    "promotion_run_id": 31,
    "etl_load_run_id": 12,
    "source_filename": "vendor.csv",
    "profile_name": "sample_vendor",
    "status": "succeeded",
    "inserted_count": 1,
    "updated_count": 1,
    "unchanged_count": 1,
    "blocked_count": 0,
    "error_count": 0,
    "warning_count": 1,
    "failure_code": None,
    "safe_failure_message": None,
    "started_at": "2026-07-30T10:00:00Z",
    "completed_at": "2026-07-30T10:00:01Z",
    "created_at": "2026-07-30T10:00:00Z",
}
CATALOG_PROMOTION_RUN_LIST_RESPONSE = {
    "items": [CATALOG_PROMOTION_RUN_ITEM],
    "total": 1,
    "limit": 20,
    "offset": 0,
}
CATALOG_PROMOTION_RUN_DETAIL_RESPONSE = {
    **CATALOG_PROMOTION_RUN_ITEM,
    "preview_hash": "a" * 64,
    "preview_schema_version": "1",
    "inspection_version": "2026.07",
}
CATALOG_PROMOTION_AUDIT_RESPONSE = {
    "items": [
        {
            "audit_id": 41,
            "promotion_run_id": 31,
            "catalog_product_id": 51,
            "action": "update",
            "changed_fields": {"stock": {"before": 1, "after": 2}},
            "before_data": {"external_product_id": "SKU-001", "stock": 1},
            "after_data": {"external_product_id": "SKU-001", "stock": 2},
            "created_at": "2026-07-30T10:00:00Z",
        }
    ],
    "total": 1,
    "limit": 20,
    "offset": 0,
}


def test_list_catalog_promotions_calls_get_with_filters_and_validates_contract():
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_RUN_LIST_RESPONSE),
        timeout_seconds=4.0,
    )

    data = client.list_catalog_promotions(
        limit=20,
        offset=0,
        status="succeeded",
        etl_load_run_id=12,
        filename="  vendor  ",
    )

    assert data == CATALOG_PROMOTION_RUN_LIST_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/catalog-promotions",
            "params": {
                "limit": 20,
                "offset": 0,
                "status": "succeeded",
                "etl_load_run_id": 12,
                "filename": "vendor",
            },
            "timeout": 4.0,
        }
    ]


def test_get_catalog_promotion_detail_and_audits_validate_contracts():
    detail_client, detail_session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_RUN_DETAIL_RESPONSE)
    )
    audit_client, audit_session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_AUDIT_RESPONSE)
    )

    assert detail_client.get_catalog_promotion_detail(31) == (
        CATALOG_PROMOTION_RUN_DETAIL_RESPONSE
    )
    assert audit_client.list_catalog_promotion_audits(
        31,
        limit=20,
        offset=0,
    ) == CATALOG_PROMOTION_AUDIT_RESPONSE
    assert detail_session.calls[0]["url"].endswith("/api/v1/catalog-promotions/31")
    assert audit_session.calls[0] == {
        "url": "https://api.example.com/api/v1/catalog-promotions/31/audits",
        "params": {"limit": 20, "offset": 0},
        "timeout": 5.0,
    }


@pytest.mark.parametrize(
    ("method_name", "args", "kwargs"),
    [
        ("list_catalog_promotions", (), {"limit": 0}),
        ("list_catalog_promotions", (), {"offset": -1}),
        ("list_catalog_promotions", (), {"status": "unknown"}),
        ("list_catalog_promotions", (), {"etl_load_run_id": 0}),
        ("get_catalog_promotion_detail", (0,), {}),
        ("list_catalog_promotion_audits", (31,), {"limit": 101}),
    ],
)
def test_catalog_promotion_history_rejects_invalid_arguments_without_request(
    method_name,
    args,
    kwargs,
):
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_RUN_LIST_RESPONSE)
    )

    with pytest.raises(ValueError):
        getattr(client, method_name)(*args, **kwargs)

    assert session.calls == []


@pytest.mark.parametrize(
    "method_name",
    ["get_catalog_promotion_detail", "list_catalog_promotion_audits"],
)
def test_catalog_promotion_history_maps_404_to_not_found(method_name):
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=404,
            payload={"detail": "postgresql://private"},
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.CatalogPromotionNotFoundError) as error:
        getattr(client, method_name)(31)

    assert error.value.request_id == VALID_REQUEST_ID
    assert "postgresql" not in str(error.value).lower()


@pytest.mark.parametrize(
    ("method_name", "payload"),
    [
        (
            "list_catalog_promotions",
            {
                **CATALOG_PROMOTION_RUN_LIST_RESPONSE,
                "items": [{"promotion_run_id": 31}],
            },
        ),
        (
            "get_catalog_promotion_detail",
            {**CATALOG_PROMOTION_RUN_DETAIL_RESPONSE, "status": "unknown"},
        ),
        (
            "list_catalog_promotion_audits",
            {
                **CATALOG_PROMOTION_AUDIT_RESPONSE,
                "items": [{"audit_id": 41}],
            },
        ),
    ],
)
def test_catalog_promotion_history_rejects_missing_or_invalid_fields(
    method_name,
    payload,
):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        if method_name == "list_catalog_promotions":
            client.list_catalog_promotions()
        else:
            getattr(client, method_name)(31)


def test_catalog_promotion_history_rejects_malformed_json_and_hides_500_body():
    client_module = import_client_module()
    malformed_client, _ = make_client(
        response=FakeResponse(json_error=ValueError("bad json"))
    )
    failed_client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            payload={"detail": "postgresql://private"},
            text="Traceback: secret",
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        malformed_client.list_catalog_promotions()
    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        failed_client.get_catalog_promotion_detail(31)

    assert "postgresql" not in str(error.value).lower()
    assert "traceback" not in str(error.value).lower()


def test_get_catalog_promotion_preview_posts_without_body_and_validates_response():
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_PREVIEW_RESPONSE),
        timeout_seconds=7.5,
    )

    data = client.get_catalog_promotion_preview(12)

    assert data == CATALOG_PROMOTION_PREVIEW_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-loads/12/promotion-preview",
            "files": None,
            "timeout": 7.5,
        }
    ]


def test_create_catalog_promotion_posts_confirmation_and_expected_preview_hash():
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_RESPONSE),
        timeout_seconds=3.0,
    )

    data = client.create_catalog_promotion(
        12,
        confirmation=True,
        expected_preview_hash="a" * 64,
    )

    assert data == CATALOG_PROMOTION_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-loads/12/promotions",
            "files": None,
            "json": {
                "confirmation": True,
                "expected_preview_hash": "a" * 64,
            },
            "timeout": 3.0,
        }
    ]


@pytest.mark.parametrize("run_id", [0, -1, True, "12"])
def test_catalog_promotion_methods_reject_invalid_run_id_without_request(run_id):
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_PREVIEW_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.get_catalog_promotion_preview(run_id)

    with pytest.raises(ValueError):
        client.create_catalog_promotion(
            run_id,
            confirmation=True,
            expected_preview_hash="a" * 64,
        )

    assert session.calls == []


def test_create_catalog_promotion_requires_explicit_confirmation_without_request():
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.create_catalog_promotion(
            12,
            confirmation=False,
            expected_preview_hash="a" * 64,
        )

    assert session.calls == []


@pytest.mark.parametrize("preview_hash", ["", "A" * 64, "a" * 63, "z" * 64, None])
def test_create_catalog_promotion_rejects_invalid_preview_hash_without_request(
    preview_hash,
):
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.create_catalog_promotion(
            12,
            confirmation=True,
            expected_preview_hash=preview_hash,
        )

    assert session.calls == []


def test_catalog_promotion_preview_maps_404_to_etl_load_not_found():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=404,
            payload={"detail": "private database detail"},
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.ETLLoadNotFoundError) as error:
        client.get_catalog_promotion_preview(12)

    assert error.value.request_id == VALID_REQUEST_ID
    assert "private database detail" not in str(error.value)


def test_create_catalog_promotion_maps_preview_stale_conflict():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=409,
            payload={
                "detail": {
                    "code": "preview_stale",
                    "message": "미리보기 이후 상품 데이터가 변경되었습니다.",
                    "promotion_run_id": 31,
                }
            },
        )
    )

    with pytest.raises(client_module.CatalogPromotionPreviewStaleError) as error:
        client.create_catalog_promotion(
            12,
            confirmation=True,
            expected_preview_hash="a" * 64,
        )

    assert error.value.code == "preview_stale"
    assert error.value.promotion_run_id == 31


def test_create_catalog_promotion_maps_blocked_conflict_with_safe_reasons():
    client_module = import_client_module()
    blocked_reasons = [
        {
            "code": "inspection_errors_present",
            "message": "상품 검사 오류가 있어 반영할 수 없습니다.",
            "supplier_key": None,
            "external_product_id": None,
            "staging_product_ids": [],
        }
    ]
    client, _ = make_client(
        response=FakeResponse(
            status_code=409,
            payload={
                "detail": {
                    "code": "promotion_blocked",
                    "message": "현재 ETL 적재 결과를 반영할 수 없습니다.",
                    "promotion_run_id": 32,
                    "blocked_reasons": blocked_reasons,
                }
            },
        )
    )

    with pytest.raises(client_module.CatalogPromotionBlockedError) as error:
        client.create_catalog_promotion(
            12,
            confirmation=True,
            expected_preview_hash="a" * 64,
        )

    assert error.value.code == "promotion_blocked"
    assert error.value.blocked_reasons == blocked_reasons


def test_create_catalog_promotion_maps_known_apply_failure_without_leaking_body():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            payload={
                "detail": {
                    "code": "promotion_failed",
                    "message": "운영 상품 반영 중 오류가 발생했습니다.",
                    "promotion_run_id": 33,
                    "debug": "postgresql://private",
                }
            },
            text="Traceback: postgresql://private",
        )
    )

    with pytest.raises(client_module.CatalogPromotionFailedError) as error:
        client.create_catalog_promotion(
            12,
            confirmation=True,
            expected_preview_hash="a" * 64,
        )

    assert error.value.code == "promotion_failed"
    assert error.value.promotion_run_id == 33
    assert "postgresql" not in str(error.value)
    assert "Traceback" not in str(error.value)


@pytest.mark.parametrize("status_code", [400, 422, 503])
def test_catalog_promotion_http_errors_use_safe_generic_message(status_code):
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=status_code,
            payload={"detail": "postgresql://private"},
            text="Traceback: private stack",
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.create_catalog_promotion(
            12,
            confirmation=True,
            expected_preview_hash="a" * 64,
        )

    assert "postgresql" not in str(error.value)
    assert "Traceback" not in str(error.value)


def test_catalog_promotion_methods_convert_connection_and_timeout_errors():
    client_module = import_client_module()
    connection_client, _ = make_client(
        error=requests.ConnectionError("http://private.internal")
    )
    timeout_client, _ = make_client(error=requests.Timeout("too slow"))

    with pytest.raises(client_module.CatalogGuardApiConnectionError):
        connection_client.get_catalog_promotion_preview(12)

    with pytest.raises(client_module.CatalogGuardApiTimeoutError):
        timeout_client.create_catalog_promotion(
            12,
            confirmation=True,
            expected_preview_hash="a" * 64,
        )


@pytest.mark.parametrize(
    ("method_name", "payload"),
    [
        (
            "get_catalog_promotion_preview",
            {**CATALOG_PROMOTION_PREVIEW_RESPONSE, "items": [{"action": "update"}]},
        ),
        (
            "create_catalog_promotion",
            {**CATALOG_PROMOTION_RESPONSE, "status": "blocked"},
        ),
    ],
)
def test_catalog_promotion_methods_reject_malformed_success_response(
    method_name,
    payload,
):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        if method_name == "get_catalog_promotion_preview":
            client.get_catalog_promotion_preview(12)
        else:
            client.create_catalog_promotion(
                12,
                confirmation=True,
                expected_preview_hash="a" * 64,
            )


ETL_WEB_RUN_RESPONSE = {
    "etl_load_run_id": 42,
    "created": True,
    "profile_name": "sample_fashion_vendor",
    "profile_version": "1",
    "source_filename": "vendor.csv",
    "total_rows": 2,
    "loaded_rows": 2,
    "rejected_rows": 0,
    "error_counts": {},
}

ETL_PROFILE_LIST_RESPONSE = {
    "items": [
        {"id": "sample_fashion_vendor_v1", "display_name": "패션 공급사 샘플 v1"},
        {"id": "sample_marketplace_vendor_v1", "display_name": "마켓플레이스 공급사 샘플 v1"},
    ]
}


def test_run_etl_load_posts_multipart_file_and_profile_id_form_field():
    client, session = make_client(
        response=FakeResponse(payload=ETL_WEB_RUN_RESPONSE),
        timeout_seconds=9.0,
    )

    data = client.run_etl_load(
        profile_id="sample_fashion_vendor_v1",
        source_filename="vendor.csv",
        file_content=b"vendor_sku,item_name\nSKU-1,Shirt\n",
    )

    assert data == ETL_WEB_RUN_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-loads",
            "files": {
                "file": (
                    "vendor.csv",
                    b"vendor_sku,item_name\nSKU-1,Shirt\n",
                    "text/csv",
                )
            },
            "data": {"profile_id": "sample_fashion_vendor_v1"},
            "timeout": 9.0,
        }
    ]


def test_run_etl_load_rejects_empty_profile_id_without_request():
    client, session = make_client(response=FakeResponse(payload=ETL_WEB_RUN_RESPONSE))

    with pytest.raises(ValueError):
        client.run_etl_load(
            profile_id="   ",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )
    assert session.calls == []


def test_run_etl_load_rejects_empty_filename_without_request():
    client, session = make_client(response=FakeResponse(payload=ETL_WEB_RUN_RESPONSE))

    with pytest.raises(ValueError):
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="   ",
            file_content=b"a,b\n1,2\n",
        )
    assert session.calls == []


def test_run_etl_load_rejects_empty_file_content_without_request():
    client, session = make_client(response=FakeResponse(payload=ETL_WEB_RUN_RESPONSE))

    with pytest.raises(ValueError):
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            file_content=b"",
        )
    assert session.calls == []


def test_run_etl_load_rejects_missing_required_response_keys():
    client, _ = make_client(
        response=FakeResponse(payload={"etl_load_run_id": 42})
    )
    client_module = import_client_module()

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )


def test_run_etl_load_maps_unsupported_profile_error_without_leaking_body():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=400,
            payload={
                "detail": {
                    "code": "unsupported_profile",
                    "message": "지원하지 않는 공급사 프로필입니다.",
                }
            },
        )
    )

    with pytest.raises(client_module.ETLUnsupportedProfileError) as error:
        client.run_etl_load(
            profile_id="unknown",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )
    assert error.value.code == "unsupported_profile"


def test_run_etl_load_maps_invalid_upload_error_with_server_message():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=400,
            payload={
                "detail": {
                    "code": "invalid_upload",
                    "message": "Input CSV has no product rows",
                }
            },
        )
    )

    with pytest.raises(client_module.ETLInvalidUploadError) as error:
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )
    assert "Input CSV has no product rows" in str(error.value)


def test_run_etl_load_maps_unknown_500_to_generic_server_error_without_leaking_body():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            payload={"detail": {"code": "etl_load_failed", "message": "internal"}},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )
    assert "internal" not in str(error.value)


def test_run_etl_load_preserves_request_id_on_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=400,
            payload={"detail": {"code": "unsupported_profile", "message": "no"}},
            headers={"X-Request-ID": "a" * 32},
        )
    )

    with pytest.raises(client_module.ETLUnsupportedProfileError) as error:
        client.run_etl_load(
            profile_id="unknown",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )
    assert error.value.request_id == "a" * 32


CATALOG_PROMOTION_ROLLBACK_RUN_ITEM = {
    "rollback_run_id": 71,
    "target_promotion_run_id": 31,
    "status": "succeeded",
    "restored_count": 2,
    "deleted_count": 1,
    "conflict_count": 0,
    "failure_code": None,
    "safe_failure_message": None,
    "started_at": "2026-08-11T05:20:00Z",
    "completed_at": "2026-08-11T05:20:01Z",
    "created_at": "2026-08-11T05:20:00Z",
    "actor_username": "operator",
}
CATALOG_PROMOTION_ROLLBACK_RUN_LIST_RESPONSE = {
    "items": [CATALOG_PROMOTION_ROLLBACK_RUN_ITEM],
    "total": 1,
    "limit": 10,
    "offset": 0,
}
CATALOG_PROMOTION_ROLLBACK_RUN_DETAIL_RESPONSE = {
    **CATALOG_PROMOTION_ROLLBACK_RUN_ITEM,
    "preview_hash": "b" * 64,
    "preview_schema_version": "1",
}


def test_catalog_promotion_rollback_history_calls_default_list_endpoint():
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_ROLLBACK_RUN_LIST_RESPONSE),
        timeout_seconds=4.0,
    )

    data = client.list_catalog_promotion_rollbacks()

    assert data == CATALOG_PROMOTION_ROLLBACK_RUN_LIST_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/catalog-promotion-rollbacks",
            "params": {"limit": 10, "offset": 0},
            "timeout": 4.0,
        }
    ]


@pytest.mark.parametrize(
    ("kwargs", "expected_params"),
    [
        (
            {"status": "succeeded"},
            {"limit": 10, "offset": 0, "status": "succeeded"},
        ),
        (
            {"target_promotion_run_id": 123},
            {"limit": 10, "offset": 0, "target_promotion_run_id": 123},
        ),
    ],
)
def test_catalog_promotion_rollback_history_forwards_supported_filters(
    kwargs,
    expected_params,
):
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_ROLLBACK_RUN_LIST_RESPONSE)
    )

    client.list_catalog_promotion_rollbacks(**kwargs)

    assert session.calls[0]["params"] == expected_params


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"offset": -1},
        {"status": "unknown"},
        {"target_promotion_run_id": 0},
    ],
)
def test_catalog_promotion_rollback_history_rejects_invalid_arguments_without_request(
    kwargs,
):
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_ROLLBACK_RUN_LIST_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.list_catalog_promotion_rollbacks(**kwargs)

    assert session.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {
            **CATALOG_PROMOTION_ROLLBACK_RUN_LIST_RESPONSE,
            "items": [{"rollback_run_id": 71}],
        },
        {
            **CATALOG_PROMOTION_ROLLBACK_RUN_LIST_RESPONSE,
            "items": [
                {**CATALOG_PROMOTION_ROLLBACK_RUN_ITEM, "status": "unknown"}
            ],
        },
    ],
)
def test_catalog_promotion_rollback_history_rejects_invalid_list_response(payload):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.list_catalog_promotion_rollbacks()


def test_catalog_promotion_rollback_detail_calls_endpoint_and_validates_response():
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_PROMOTION_ROLLBACK_RUN_DETAIL_RESPONSE)
    )

    data = client.get_catalog_promotion_rollback_detail(71)

    assert data == CATALOG_PROMOTION_ROLLBACK_RUN_DETAIL_RESPONSE
    assert session.calls[0]["url"].endswith(
        "/api/v1/catalog-promotion-rollbacks/71"
    )


def test_catalog_promotion_rollback_detail_maps_404_to_not_found():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=404,
            payload={"detail": "postgresql://private"},
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(
        client_module.CatalogPromotionRollbackNotFoundError
    ) as error:
        client.get_catalog_promotion_rollback_detail(71)

    assert error.value.request_id == VALID_REQUEST_ID
    assert str(error.value) == "Rollback 실행 이력을 찾을 수 없습니다."
    assert "postgresql" not in str(error.value).lower()


@pytest.mark.parametrize(
    "payload",
    [
        {**CATALOG_PROMOTION_ROLLBACK_RUN_DETAIL_RESPONSE, "conflict_count": -1},
        {**CATALOG_PROMOTION_ROLLBACK_RUN_DETAIL_RESPONSE, "preview_hash": "B" * 64},
    ],
)
def test_catalog_promotion_rollback_detail_rejects_invalid_response(payload):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.get_catalog_promotion_rollback_detail(71)


def test_list_etl_profiles_returns_validated_response():
    client, session = make_client(
        response=FakeResponse(payload=ETL_PROFILE_LIST_RESPONSE),
        timeout_seconds=6.0,
    )

    data = client.list_etl_profiles()

    assert data == ETL_PROFILE_LIST_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-profiles",
            "params": None,
            "timeout": 6.0,
        }
    ]


def test_list_etl_profiles_rejects_malformed_items():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(payload={"items": [{"id": "x"}]})
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.list_etl_profiles()


LOGIN_RESPONSE = {
    "access_token": "a.b.c",
    "token_type": "bearer",
    "expires_in": 3600,
}
CURRENT_USER_RESPONSE = {"username": "operator_user", "role": "operator"}


def test_login_returns_validated_token_response():
    client, session = make_client(response=FakeResponse(payload=LOGIN_RESPONSE))

    data = client.login(username="operator_user", password="correct-password")

    assert data == LOGIN_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/auth/login",
            "files": None,
            "timeout": 5.0,
            "json": {"username": "operator_user", "password": "correct-password"},
        }
    ]


def test_login_rejects_malformed_response():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload={"access_token": "x"}))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.login(username="someone", password="pw")


def test_login_maps_invalid_credentials_to_typed_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=401,
            payload={"detail": {"code": "invalid_credentials", "message": "no"}},
        )
    )

    with pytest.raises(client_module.InvalidCredentialsError) as error:
        client.login(username="someone", password="wrong")
    assert isinstance(error.value, client_module.CatalogGuardApiAuthenticationError)
    assert error.value.code == "invalid_credentials"


def test_get_current_user_returns_username_and_role():
    client, session = make_client(response=FakeResponse(payload=CURRENT_USER_RESPONSE))

    data = client.get_current_user()

    assert data == CURRENT_USER_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/auth/me",
            "params": None,
            "timeout": 5.0,
        }
    ]


def test_get_current_user_maps_missing_token_to_authentication_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=401,
            payload={
                "detail": {
                    "code": "authentication_required",
                    "message": "login required",
                }
            },
        )
    )

    with pytest.raises(client_module.CatalogGuardApiAuthenticationError) as error:
        client.get_current_user()
    assert error.value.code == "authentication_required"


def test_get_current_user_maps_inactive_user_to_authentication_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=401,
            payload={"detail": {"code": "inactive_user", "message": "disabled"}},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiAuthenticationError) as error:
        client.get_current_user()
    assert error.value.code == "inactive_user"


def test_get_current_user_maps_invalid_token_to_authentication_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=401,
            payload={"detail": {"code": "invalid_token", "message": "bad token"}},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiAuthenticationError) as error:
        client.get_current_user()
    assert error.value.code == "invalid_token"


def test_run_etl_load_maps_forbidden_response_to_authorization_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=403,
            payload={
                "detail": {"code": "insufficient_role", "message": "no permission"}
            },
        )
    )

    with pytest.raises(client_module.CatalogGuardApiAuthorizationError) as error:
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )
    assert error.value.code == "insufficient_role"


def test_set_access_token_adds_authorization_header():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    client.set_access_token("token-value")

    assert session.headers["Authorization"] == "Bearer token-value"


def test_set_access_token_none_removes_authorization_header():
    client, session = make_client(response=FakeResponse(payload=LIST_RESPONSE))

    client.set_access_token("token-value")
    client.set_access_token(None)

    assert "Authorization" not in session.headers


def test_constructor_access_token_sets_authorization_header():
    client_module = import_client_module()
    session = FakeSession(response=FakeResponse(payload=LIST_RESPONSE))

    client_module.CatalogGuardApiClient(
        "https://api.example.com",
        session=session,
        access_token="constructor-token",
    )

    assert session.headers["Authorization"] == "Bearer constructor-token"
