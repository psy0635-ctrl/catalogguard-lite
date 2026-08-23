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

    def put(self, url, *, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return self.response

    def delete(self, url, *, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
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

ETL_LOAD_QUALITY_SUMMARY_RESPONSE = {
    "batch_count": 3,
    "quality_available_batch_count": 2,
    "quality_unavailable_batch_count": 1,
    "total_rows": 300,
    "loaded_rows": 280,
    "rejected_rows": 20,
    "rejection_rate": 6.67,
}

ETL_LOAD_QUALITY_TREND_RESPONSE = {
    "items": [
        {
            "etl_load_run_id": 12,
            "created_at": "2026-07-25T12:00:00Z",
            "total_rows": 30,
            "loaded_rows": 25,
            "rejected_rows": 5,
            "rejection_rate": 16.67,
        }
    ]
}

ETL_QUALITY_OBSERVABILITY_RESPONSE = {
    "profile_name": "sample_fashion_vendor",
    "limit": 10,
    "batch_count": 2,
    "latest_batch": {
        "etl_load_run_id": 12,
        "created_at": "2026-08-20T12:00:00Z",
        "total_rows": 100,
        "loaded_rows": 91,
        "rejected_rows": 9,
        "rejection_rate": 9.0,
    },
    "previous_batch": {
        "etl_load_run_id": 11,
        "created_at": "2026-08-19T12:00:00Z",
        "total_rows": 100,
        "loaded_rows": 96,
        "rejected_rows": 4,
        "rejection_rate": 4.0,
    },
    "rejection_rate_delta": 5.0,
    "direction": "worsened",
    "error_codes": [
        {"error_code": "INVALID_PRICE", "total_count": 8, "affected_batch_count": 2}
    ],
    "recent_batches": [
        {
            "etl_load_run_id": 11,
            "created_at": "2026-08-19T12:00:00Z",
            "total_rows": 100,
            "loaded_rows": 96,
            "rejected_rows": 4,
            "rejection_rate": 4.0,
        },
        {
            "etl_load_run_id": 12,
            "created_at": "2026-08-20T12:00:00Z",
            "total_rows": 100,
            "loaded_rows": 91,
            "rejected_rows": 9,
            "rejection_rate": 9.0,
        },
    ],
}

ETL_QUALITY_OBSERVABILITY_EMPTY_RESPONSE = {
    "profile_name": "sample_fashion_vendor",
    "limit": 10,
    "batch_count": 0,
    "latest_batch": None,
    "previous_batch": None,
    "rejection_rate_delta": None,
    "direction": "no_baseline",
    "error_codes": [],
    "recent_batches": [],
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


def test_get_etl_load_quality_summary_calls_endpoint_and_trims_profile_filter():
    client, session = make_client(
        response=FakeResponse(payload=ETL_LOAD_QUALITY_SUMMARY_RESPONSE),
    )

    data = client.get_etl_load_quality_summary(profile_name="  fashion  ")

    assert data == ETL_LOAD_QUALITY_SUMMARY_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-loads/quality-summary",
            "params": {"profile_name": "fashion"},
            "timeout": 5.0,
        }
    ]


def test_get_etl_load_quality_trend_calls_endpoint_with_trimmed_profile_and_limit():
    client, session = make_client(
        response=FakeResponse(payload=ETL_LOAD_QUALITY_TREND_RESPONSE),
    )

    data = client.get_etl_load_quality_trend(profile_name="  fashion  ", limit=3)

    assert data == ETL_LOAD_QUALITY_TREND_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-loads/quality-trend",
            "params": {"profile_name": "fashion", "limit": 3},
            "timeout": 5.0,
        }
    ]


def test_get_etl_load_quality_trend_omits_blank_profile_filter():
    client, session = make_client(
        response=FakeResponse(payload=ETL_LOAD_QUALITY_TREND_RESPONSE),
    )

    client.get_etl_load_quality_trend(profile_name="   ", limit=10)

    assert session.calls[0]["params"] == {"limit": 10}


def test_get_etl_load_quality_trend_rejects_missing_item_field():
    client, _ = make_client(
        response=FakeResponse(
            payload={
                "items": [
                    {
                        "etl_load_run_id": 12,
                        "created_at": "2026-07-25T12:00:00Z",
                        "total_rows": 30,
                        "loaded_rows": 25,
                        "rejected_rows": 5,
                    }
                ]
            }
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_load_quality_trend()


ETL_QUALITY_OBSERVABILITY_PROFILES_RESPONSE = {
    "items": [
        {"profile_name": "sample_fashion_vendor"},
        {"profile_name": "sample_marketplace_vendor"},
    ]
}


def test_get_etl_quality_observability_profiles_calls_endpoint():
    client, session = make_client(
        response=FakeResponse(payload=ETL_QUALITY_OBSERVABILITY_PROFILES_RESPONSE),
    )

    data = client.get_etl_quality_observability_profiles()

    assert data == ETL_QUALITY_OBSERVABILITY_PROFILES_RESPONSE
    assert session.calls == [
        {
            "url": (
                "https://api.example.com"
                "/api/v1/etl-loads/quality-observability/profiles"
            ),
            "params": None,
            "timeout": 5.0,
        }
    ]


def test_get_etl_quality_observability_profiles_accepts_empty_items():
    client, _ = make_client(response=FakeResponse(payload={"items": []}))

    assert client.get_etl_quality_observability_profiles() == {"items": []}


@pytest.mark.parametrize(
    "payload",
    [
        # profile_name이 비어 있으면 정확 일치 비교 조회에 넣을 수 없습니다.
        {"items": [{"profile_name": ""}]},
        {"items": [{"profile_name": "   "}]},
        {"items": [{"profile_name": None}]},
        # 같은 공급사가 두 번 보이면 선택 목록이 망가집니다.
        {
            "items": [
                {"profile_name": "sample_fashion_vendor"},
                {"profile_name": "sample_fashion_vendor"},
            ]
        },
        # 서버 계약은 profile_name ASC입니다.
        {
            "items": [
                {"profile_name": "sample_marketplace_vendor"},
                {"profile_name": "sample_fashion_vendor"},
            ]
        },
        {"items": {}},
        {"items": None},
        {"items": ["sample_fashion_vendor"]},
        {"items": [{"name": "sample_fashion_vendor"}]},
        {},
    ],
)
def test_get_etl_quality_observability_profiles_rejects_broken_payload(payload):
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability_profiles()


def test_get_etl_quality_observability_calls_endpoint_with_trimmed_profile():
    client, session = make_client(
        response=FakeResponse(payload=ETL_QUALITY_OBSERVABILITY_RESPONSE),
    )

    data = client.get_etl_quality_observability(
        profile_name="  sample_fashion_vendor  ",
        limit=3,
    )

    assert data == ETL_QUALITY_OBSERVABILITY_RESPONSE
    assert session.calls == [
        {
            "url": (
                "https://api.example.com/api/v1/etl-loads/quality-observability"
            ),
            "params": {"profile_name": "sample_fashion_vendor", "limit": 3},
            "timeout": 5.0,
        }
    ]


def test_get_etl_quality_observability_accepts_empty_no_baseline_response():
    client, _ = make_client(
        response=FakeResponse(payload=ETL_QUALITY_OBSERVABILITY_EMPTY_RESPONSE),
    )

    data = client.get_etl_quality_observability(profile_name="sample_fashion_vendor")

    assert data["direction"] == "no_baseline"
    assert data["latest_batch"] is None
    assert data["rejection_rate_delta"] is None


@pytest.mark.parametrize("profile_name", ["", "   "])
def test_get_etl_quality_observability_rejects_blank_profile_without_request(
    profile_name,
):
    client, session = make_client(
        response=FakeResponse(payload=ETL_QUALITY_OBSERVABILITY_RESPONSE),
    )

    with pytest.raises(ValueError):
        client.get_etl_quality_observability(profile_name=profile_name)

    assert session.calls == []


@pytest.mark.parametrize("limit", [0, 51, True, 2.0, "3"])
def test_get_etl_quality_observability_rejects_invalid_limit_without_request(limit):
    client, session = make_client(
        response=FakeResponse(payload=ETL_QUALITY_OBSERVABILITY_RESPONSE),
    )

    with pytest.raises(ValueError):
        client.get_etl_quality_observability(
            profile_name="sample_fashion_vendor",
            limit=limit,
        )

    assert session.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        # 방향과 변화량의 부호가 서로 반대인 응답입니다.
        {"direction": "improved"},
        # 비교 대상이 없다면서 변화량은 남아 있는 응답입니다.
        {"previous_batch": None},
        # 변화량이 두 배치의 rejection_rate 차이와 맞지 않는 응답입니다.
        {"rejection_rate_delta": 1.0},
        # batch_count가 실제 목록 길이와 다른 응답입니다.
        {"batch_count": 5},
        # 관찰한 배치 수보다 많은 배치에서 나왔다고 주장하는 오류 코드입니다.
        {
            "error_codes": [
                {
                    "error_code": "INVALID_PRICE",
                    "total_count": 8,
                    "affected_batch_count": 7,
                }
            ]
        },
        # 합계보다 배치 수가 큰, 산술적으로 불가능한 오류 코드입니다.
        {
            "error_codes": [
                {
                    "error_code": "INVALID_PRICE",
                    "total_count": 1,
                    "affected_batch_count": 2,
                }
            ]
        },
        {"direction": "degraded"},
        {"limit": 0},
        {"profile_name": "   "},
        {"recent_batches": [{"etl_load_run_id": 12}]},
    ],
)
def test_get_etl_quality_observability_rejects_inconsistent_server_response(changes):
    client, _ = make_client(
        response=FakeResponse(
            payload={**ETL_QUALITY_OBSERVABILITY_RESPONSE, **changes}
        ),
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability(profile_name="sample_fashion_vendor")


def _observability_batch(**overrides):
    values = {
        "etl_load_run_id": 20,
        "created_at": "2026-08-21T12:00:00Z",
        "total_rows": 100,
        "loaded_rows": 99,
        "rejected_rows": 1,
        "rejection_rate": 1.0,
    }
    values.update(overrides)
    return values


def test_get_etl_quality_observability_rejects_latest_batch_not_matching_last_item():
    # 요약 지표와 아래 목록이 서로 다른 배치를 가리키면 화면 전체가 거짓말이 됩니다.
    client, _ = make_client(
        response=FakeResponse(
            payload={
                **ETL_QUALITY_OBSERVABILITY_RESPONSE,
                "latest_batch": _observability_batch(
                    etl_load_run_id=99,
                    rejected_rows=9,
                    loaded_rows=91,
                    rejection_rate=9.0,
                ),
            }
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability(profile_name="sample_fashion_vendor")


def test_get_etl_quality_observability_rejects_previous_batch_not_matching_second_last():
    client, _ = make_client(
        response=FakeResponse(
            payload={
                **ETL_QUALITY_OBSERVABILITY_RESPONSE,
                "previous_batch": _observability_batch(
                    etl_load_run_id=98,
                    rejected_rows=4,
                    loaded_rows=96,
                    rejection_rate=4.0,
                ),
            }
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability(profile_name="sample_fashion_vendor")


def test_get_etl_quality_observability_accepts_single_batch_matching_latest():
    only_batch = _observability_batch()
    payload = {
        "profile_name": "sample_fashion_vendor",
        "limit": 10,
        "batch_count": 1,
        "latest_batch": dict(only_batch),
        "previous_batch": None,
        "rejection_rate_delta": None,
        "direction": "no_baseline",
        "error_codes": [],
        "recent_batches": [dict(only_batch)],
    }
    client, _ = make_client(response=FakeResponse(payload=payload))

    data = client.get_etl_quality_observability(profile_name="sample_fashion_vendor")

    assert data["batch_count"] == 1
    assert data["latest_batch"] == data["recent_batches"][-1]
    assert data["previous_batch"] is None


def test_get_etl_quality_observability_rejects_single_batch_with_a_previous_batch():
    only_batch = _observability_batch()
    payload = {
        "profile_name": "sample_fashion_vendor",
        "limit": 10,
        "batch_count": 1,
        "latest_batch": dict(only_batch),
        # 목록에 배치가 하나뿐인데 비교 대상이 따로 있다고 주장하는 응답입니다.
        "previous_batch": _observability_batch(etl_load_run_id=19, rejection_rate=0.5),
        "rejection_rate_delta": 0.5,
        "direction": "worsened",
        "error_codes": [],
        "recent_batches": [dict(only_batch)],
    }
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability(profile_name="sample_fashion_vendor")


def test_get_etl_quality_observability_rejects_batches_not_in_chronological_order():
    # 서버는 과거 -> 최신 순서로 보냅니다. 뒤집힌 목록은 "직전"과 "최신"이 바뀐 화면이 됩니다.
    reversed_batches = list(
        reversed(ETL_QUALITY_OBSERVABILITY_RESPONSE["recent_batches"])
    )
    client, _ = make_client(
        response=FakeResponse(
            payload={
                **ETL_QUALITY_OBSERVABILITY_RESPONSE,
                "recent_batches": reversed_batches,
                "latest_batch": reversed_batches[-1],
                "previous_batch": reversed_batches[-2],
                "rejection_rate_delta": -5.0,
                "direction": "improved",
            }
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability(profile_name="sample_fashion_vendor")


def test_get_etl_quality_observability_rejects_same_timestamp_batches_out_of_id_order():
    same_moment = "2026-08-21T12:00:00Z"
    newer = _observability_batch(
        etl_load_run_id=30,
        created_at=same_moment,
        rejected_rows=9,
        loaded_rows=91,
        rejection_rate=9.0,
    )
    older = _observability_batch(
        etl_load_run_id=29,
        created_at=same_moment,
        rejected_rows=4,
        loaded_rows=96,
        rejection_rate=4.0,
    )
    payload = {
        "profile_name": "sample_fashion_vendor",
        "limit": 10,
        "batch_count": 2,
        # created_at이 같으면 id 오름차순이어야 하는데 뒤집혀 있습니다.
        "recent_batches": [newer, older],
        "latest_batch": older,
        "previous_batch": newer,
        "rejection_rate_delta": -5.0,
        "direction": "improved",
        "error_codes": [],
    }
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability(profile_name="sample_fashion_vendor")


def test_get_etl_quality_observability_rejects_unparsable_created_at():
    broken = list(ETL_QUALITY_OBSERVABILITY_RESPONSE["recent_batches"])
    broken[0] = {**broken[0], "created_at": "not-a-timestamp"}
    client, _ = make_client(
        response=FakeResponse(
            payload={**ETL_QUALITY_OBSERVABILITY_RESPONSE, "recent_batches": broken}
        )
    )

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability(profile_name="sample_fashion_vendor")


def test_get_etl_quality_observability_rejects_missing_top_level_field():
    payload = {
        key: value
        for key, value in ETL_QUALITY_OBSERVABILITY_RESPONSE.items()
        if key != "direction"
    }
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(import_client_module().CatalogGuardApiResponseError):
        client.get_etl_quality_observability(profile_name="sample_fashion_vendor")


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

UNKNOWN_SIZE_TOKEN_REPORT_RESPONSE = {
    "items": [
        {"token": "4XL", "count": 8},
        {"token": "OS", "count": 3},
    ]
}


def test_list_unknown_size_tokens_calls_get_with_limit_and_validates_contract():
    client, session = make_client(
        response=FakeResponse(payload=UNKNOWN_SIZE_TOKEN_REPORT_RESPONSE),
        timeout_seconds=4.0,
    )

    data = client.list_unknown_size_tokens(limit=7)

    assert data == UNKNOWN_SIZE_TOKEN_REPORT_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/catalog/unknown-size-tokens",
            "params": {"limit": 7},
            "timeout": 4.0,
        }
    ]


@pytest.mark.parametrize("limit", [0, 101])
def test_list_unknown_size_tokens_rejects_invalid_limits_without_request(limit):
    client, session = make_client(
        response=FakeResponse(payload=UNKNOWN_SIZE_TOKEN_REPORT_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.list_unknown_size_tokens(limit=limit)

    assert session.calls == []


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
        {"id": "sample_fashion_vendor_v1", "display_name": "패션 공급사 샘플"},
        {"id": "sample_marketplace_vendor_v1", "display_name": "마켓플레이스 공급사 샘플"},
    ]
}
ETL_PROFILE_DETAIL_RESPONSE = {
    "id": "sample_fashion_vendor_v1",
    "display_name": "패션 공급사 샘플",
    "profile_name": "sample_fashion_vendor",
    "profile_version": "2",
    "source_columns": {"vendor_sku": ["product_group_id", "product_id"]},
    "required_source_columns": ["vendor_sku"],
    "defaults": {"stock": "0"},
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
CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM = {
    "rollback_change_id": 101,
    "rollback_run_id": 71,
    "original_audit_id": 41,
    "catalog_product_id": 25,
    "action": "delete",
    "changed_fields": {
        "product_name": {"before": "Product A", "after": None}
    },
    "before_data": {
        "external_product_id": "P-25",
        "product_name": "Product A",
    },
    "after_data": None,
    "created_at": "2026-08-11T05:20:01Z",
}
CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE = {
    "items": [CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM],
    "total": 1,
    "limit": 20,
    "offset": 0,
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


def test_catalog_promotion_rollback_changes_calls_default_endpoint():
    client, session = make_client(
        response=FakeResponse(
            payload=CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE
        ),
        timeout_seconds=4.0,
    )

    data = client.list_catalog_promotion_rollback_changes(71)

    assert data == CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE
    assert session.calls == [
        {
            "url": (
                "https://api.example.com/api/v1/"
                "catalog-promotion-rollbacks/71/changes"
            ),
            "params": {"limit": 20, "offset": 0},
            "timeout": 4.0,
        }
    ]


def test_catalog_promotion_rollback_changes_forwards_pagination():
    response = {
        **CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE,
        "limit": 10,
        "offset": 20,
    }
    client, session = make_client(response=FakeResponse(payload=response))

    client.list_catalog_promotion_rollback_changes(71, limit=10, offset=20)

    assert session.calls[0]["params"] == {"limit": 10, "offset": 20}


@pytest.mark.parametrize(
    ("rollback_run_id", "kwargs"),
    [
        (0, {}),
        (71, {"limit": 0}),
        (71, {"limit": 101}),
        (71, {"offset": -1}),
    ],
)
def test_catalog_promotion_rollback_changes_rejects_invalid_arguments_without_request(
    rollback_run_id,
    kwargs,
):
    client, session = make_client(
        response=FakeResponse(
            payload=CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE
        )
    )

    with pytest.raises(ValueError):
        client.list_catalog_promotion_rollback_changes(rollback_run_id, **kwargs)

    assert session.calls == []


def test_catalog_promotion_rollback_changes_maps_404_to_not_found():
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
        client.list_catalog_promotion_rollback_changes(71)

    assert error.value.request_id == VALID_REQUEST_ID
    assert str(error.value) == "Rollback 실행 이력을 찾을 수 없습니다."
    assert "postgresql" not in str(error.value).lower()


@pytest.mark.parametrize(
    "payload",
    [
        {
            **CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE,
            "items": [
                {
                    **CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM,
                    "rollback_change_id": 0,
                }
            ],
        },
        {
            **CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE,
            "items": [
                {**CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM, "action": "unknown"}
            ],
        },
        {
            **CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE,
            "items": [
                {**CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM, "after_data": {}}
            ],
        },
        {
            **CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE,
            "items": [
                {
                    **CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM,
                    "action": "restore",
                    "after_data": None,
                }
            ],
        },
        {
            **CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE,
            "items": [
                {**CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM, "changed_fields": {}}
            ],
        },
        {**CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_RESPONSE, "total": -1},
    ],
)
def test_catalog_promotion_rollback_changes_rejects_invalid_response(payload):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.list_catalog_promotion_rollback_changes(71)


def test_catalog_promotion_rollback_changes_accepts_empty_page():
    response = {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }
    client, _ = make_client(response=FakeResponse(payload=response))

    assert client.list_catalog_promotion_rollback_changes(71) == response


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


def test_get_etl_profile_detail_returns_validated_response_and_escapes_path_id():
    client, session = make_client(
        response=FakeResponse(payload=ETL_PROFILE_DETAIL_RESPONSE),
        timeout_seconds=6.0,
    )

    data = client.get_etl_profile_detail(" sample_fashion_vendor_v1 ")

    assert data == ETL_PROFILE_DETAIL_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-profiles/sample_fashion_vendor_v1",
            "params": None,
            "timeout": 6.0,
        }
    ]


def test_get_etl_profile_detail_percent_encodes_path_separator():
    client, session = make_client(response=FakeResponse(payload=ETL_PROFILE_DETAIL_RESPONSE))

    client.get_etl_profile_detail("../secret")

    assert session.calls[0]["url"].endswith("/api/v1/etl-profiles/..%2Fsecret")


@pytest.mark.parametrize(
    "response",
    [
        {key: value for key, value in ETL_PROFILE_DETAIL_RESPONSE.items() if key != "defaults"},
        {**ETL_PROFILE_DETAIL_RESPONSE, "source_columns": {"vendor_sku": "product_id"}},
    ],
)
def test_get_etl_profile_detail_rejects_missing_or_invalid_response_fields(response):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=response))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.get_etl_profile_detail("sample_fashion_vendor_v1")


def test_get_etl_profile_detail_maps_404_to_profile_not_found_error():
    client_module = import_client_module()
    response = FakeResponse(status_code=404, payload={"detail": "missing"})
    client, _ = make_client(response=response)

    with pytest.raises(client_module.ETLProfileNotFoundError):
        client.get_etl_profile_detail("unknown")


INACTIVE_PROFILE_PAYLOAD = {
    "detail": {
        "code": "inactive_profile",
        "message": "internal server supplied message",
    }
}


def test_run_etl_load_maps_inactive_profile_with_a_client_owned_message():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=409, payload=INACTIVE_PROFILE_PAYLOAD)
    )

    with pytest.raises(client_module.ETLProfileInactiveError) as error:
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )

    assert error.value.code == "inactive_profile"
    assert str(error.value) == client_module.ETL_INACTIVE_PROFILE_MESSAGE
    # 서버 원문이 사용자 메시지로 새면 안 됩니다.
    assert "internal server supplied message" not in str(error.value)


def test_run_etl_load_inactive_profile_preserves_request_id():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=409,
            payload=INACTIVE_PROFILE_PAYLOAD,
            headers={"X-Request-ID": "b" * 32},
        )
    )

    with pytest.raises(client_module.ETLProfileInactiveError) as error:
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )

    assert error.value.request_id == "b" * 32


def test_inactive_profile_error_is_not_an_unsupported_profile_error():
    # 없는 프로필과 비활성 프로필이 상속으로 묶이면 호출자가 둘을 구분할 수 없습니다.
    client_module = import_client_module()

    assert not issubclass(
        client_module.ETLProfileInactiveError,
        client_module.ETLUnsupportedProfileError,
    )
    assert not issubclass(
        client_module.ETLUnsupportedProfileError,
        client_module.ETLProfileInactiveError,
    )
    assert issubclass(
        client_module.ETLProfileInactiveError,
        client_module.CatalogGuardApiResponseError,
    )


def test_get_etl_profile_detail_maps_409_to_inactive_profile_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=409,
            payload=INACTIVE_PROFILE_PAYLOAD,
            headers={"X-Request-ID": "c" * 32},
        )
    )

    with pytest.raises(client_module.ETLProfileInactiveError) as error:
        client.get_etl_profile_detail("sample_fashion_vendor_v1")

    assert error.value.code == "inactive_profile"
    assert error.value.request_id == "c" * 32
    assert str(error.value) == client_module.ETL_INACTIVE_PROFILE_MESSAGE
    assert "internal server supplied message" not in str(error.value)


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status_code=409, json_error=ValueError("not json")),
        FakeResponse(status_code=409, payload={"message": "no detail key"}),
        FakeResponse(status_code=409, payload={"detail": "not a dict"}),
        FakeResponse(
            status_code=409,
            payload={"detail": {"code": "something_else", "message": "other"}},
        ),
    ],
)
def test_profile_detail_409_without_the_inactive_code_stays_a_generic_error(response):
    # 409를 무조건 비활성으로 해석하면 관계없는 상태 충돌까지 잘못 분류됩니다.
    client_module = import_client_module()
    client, _ = make_client(response=response)

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.get_etl_profile_detail("sample_fashion_vendor_v1")

    assert not isinstance(error.value, client_module.ETLProfileInactiveError)


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status_code=409, json_error=ValueError("not json")),
        FakeResponse(
            status_code=409,
            payload={"detail": {"code": "something_else", "message": "other"}},
        ),
    ],
)
def test_run_etl_load_409_without_the_inactive_code_stays_a_generic_error(response):
    client_module = import_client_module()
    client, _ = make_client(response=response)

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.run_etl_load(
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            file_content=b"a,b\n1,2\n",
        )

    assert not isinstance(error.value, client_module.ETLProfileInactiveError)


def test_other_get_endpoints_do_not_map_409_to_an_inactive_profile_error():
    # map_inactive_profile은 profile detail에서만 켭니다.
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=409, payload=INACTIVE_PROFILE_PAYLOAD)
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.list_etl_profiles()

    assert not isinstance(error.value, client_module.ETLProfileInactiveError)


CATALOG_RECONCILIATION_RESPONSE = {
    "etl_load_run_id": 42,
    "supplier_key": "sample_fashion_vendor",
    "total_rows": 4,
    "loaded_rows": 3,
    "rejected_rows": 1,
    "new_count": 1,
    "changed_count": 1,
    "unchanged_count": 1,
    "not_observed_in_batch_count": 1,
    "field_change_counts": {"stock": 1},
    "items": [
        {"external_product_id": "P002", "status": "new", "changed_fields": {}},
        {
            "external_product_id": "P001",
            "status": "changed",
            "changed_fields": {"stock": {"before": 10, "after": 7}},
        },
        {"external_product_id": "P003", "status": "unchanged", "changed_fields": {}},
        {
            "external_product_id": "P900",
            "status": "not_observed_in_batch",
            "changed_fields": {},
        },
    ],
    "total": 4,
    "limit": 50,
    "offset": 0,
}


def test_get_catalog_reconciliation_returns_validated_response():
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_RECONCILIATION_RESPONSE),
        timeout_seconds=6.0,
    )

    data = client.get_catalog_reconciliation(42)

    assert data == CATALOG_RECONCILIATION_RESPONSE
    assert session.calls == [
        {
            "url": (
                "https://api.example.com/api/v1/etl-loads/42/catalog-reconciliation"
            ),
            "params": {"limit": 50, "offset": 0},
            "timeout": 6.0,
        }
    ]


def test_get_catalog_reconciliation_passes_pagination_params():
    client, session = make_client(
        response=FakeResponse(
            payload={**CATALOG_RECONCILIATION_RESPONSE, "limit": 10, "offset": 2}
        )
    )

    client.get_catalog_reconciliation(42, limit=10, offset=2)

    assert session.calls[0]["params"] == {"limit": 10, "offset": 2}


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (50, -1)],
)
def test_get_catalog_reconciliation_rejects_invalid_pagination(limit, offset):
    client, session = make_client(
        response=FakeResponse(payload=CATALOG_RECONCILIATION_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.get_catalog_reconciliation(42, limit=limit, offset=offset)
    # 잘못된 인자는 요청을 보내기 전에 막습니다.
    assert session.calls == []


@pytest.mark.parametrize("etl_load_run_id", [0, -1, "42"])
def test_get_catalog_reconciliation_rejects_invalid_run_id(etl_load_run_id):
    client, _ = make_client(
        response=FakeResponse(payload=CATALOG_RECONCILIATION_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.get_catalog_reconciliation(etl_load_run_id)


def test_get_catalog_reconciliation_accepts_legacy_null_quality_values():
    # 품질 요약 저장 이전 배치는 total_rows/rejected_rows가 null입니다.
    client, _ = make_client(
        response=FakeResponse(
            payload={
                **CATALOG_RECONCILIATION_RESPONSE,
                "total_rows": None,
                "rejected_rows": None,
            }
        )
    )

    data = client.get_catalog_reconciliation(42)

    assert data["total_rows"] is None
    assert data["rejected_rows"] is None
    assert data["loaded_rows"] == 3


@pytest.mark.parametrize(
    "quality",
    [
        # loaded_rows는 서버에서 NOT NULL이므로 null을 받아들이면 안 됩니다.
        {"loaded_rows": None},
        {"loaded_rows": "3"},
        {"loaded_rows": -1},
        {"total_rows": "4"},
        {"total_rows": -1},
        {"rejected_rows": "1"},
        {"rejected_rows": -1},
        {"rejected_rows": 1.5},
    ],
)
def test_get_catalog_reconciliation_rejects_invalid_quality_metadata(quality):
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(payload={**CATALOG_RECONCILIATION_RESPONSE, **quality})
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.get_catalog_reconciliation(42)


def test_get_catalog_reconciliation_maps_404_to_etl_load_not_found():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=404, payload={"detail": "missing"})
    )

    with pytest.raises(client_module.ETLLoadNotFoundError):
        client.get_catalog_reconciliation(42)


@pytest.mark.parametrize(
    "response",
    [
        # 필수 key 누락
        {
            key: value
            for key, value in CATALOG_RECONCILIATION_RESPONSE.items()
            if key != "field_change_counts"
        },
        # count가 음수
        {**CATALOG_RECONCILIATION_RESPONSE, "new_count": -1},
        # total이 상태 합계와 어긋남
        {**CATALOG_RECONCILIATION_RESPONSE, "total": 99},
        # 알 수 없는 status
        {
            **CATALOG_RECONCILIATION_RESPONSE,
            "items": [
                {"external_product_id": "P001", "status": "deleted", "changed_fields": {}}
            ],
            "total": 1,
            "new_count": 1,
            "changed_count": 0,
            "unchanged_count": 0,
            "not_observed_in_batch_count": 0,
        },
        # changed가 아닌데 변경 필드가 있음
        {
            **CATALOG_RECONCILIATION_RESPONSE,
            "items": [
                {
                    "external_product_id": "P001",
                    "status": "unchanged",
                    "changed_fields": {"stock": {"before": 1, "after": 2}},
                }
            ],
            "total": 1,
            "new_count": 0,
            "changed_count": 0,
            "unchanged_count": 1,
            "not_observed_in_batch_count": 0,
        },
        # changed인데 변경 필드가 없음
        {
            **CATALOG_RECONCILIATION_RESPONSE,
            "items": [
                {"external_product_id": "P001", "status": "changed", "changed_fields": {}}
            ],
            "total": 1,
            "new_count": 0,
            "changed_count": 1,
            "unchanged_count": 0,
            "not_observed_in_batch_count": 0,
        },
        # before/after가 빠진 변경 필드
        {
            **CATALOG_RECONCILIATION_RESPONSE,
            "items": [
                {
                    "external_product_id": "P001",
                    "status": "changed",
                    "changed_fields": {"stock": {"before": 1}},
                }
            ],
            "total": 1,
            "new_count": 0,
            "changed_count": 1,
            "unchanged_count": 0,
            "not_observed_in_batch_count": 0,
        },
        # 한 페이지가 limit보다 많음
        {**CATALOG_RECONCILIATION_RESPONSE, "limit": 1},
    ],
)
def test_get_catalog_reconciliation_rejects_invalid_response(response):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=response))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.get_catalog_reconciliation(42)


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


# ---- Phase 5B.2: activation 조회/변경과 관리용 목록 --------------------------


ETL_PROFILE_ACTIVATION_RESPONSE = {
    "profile_id": "sample_fashion_vendor_v1",
    "display_name": "패션 공급사 샘플",
    "deployment_active_version": "2",
    "runtime_override_exists": False,
    "runtime_active_version": None,
    "effective_active_version": "2",
    "is_active": True,
    "available_versions": ["1", "2"],
    "actor_username": None,
    "updated_at": None,
}


def _activation(**overrides):
    payload = dict(ETL_PROFILE_ACTIVATION_RESPONSE)
    payload.update(overrides)
    return payload


def test_list_etl_profiles_sends_include_inactive_only_when_requested():
    client, session = make_client(response=FakeResponse(payload=ETL_PROFILE_LIST_RESPONSE))

    client.list_etl_profiles()
    client.list_etl_profiles(include_inactive=True)

    # 기본 호출은 query parameter 자체를 보내지 않아 기존 요청과 완전히 같습니다.
    assert session.calls[0]["params"] is None
    assert session.calls[1]["params"] == {"include_inactive": "true"}


def test_get_etl_profile_activation_uses_the_activation_path_and_escapes_the_id():
    client, session = make_client(
        response=FakeResponse(payload=ETL_PROFILE_ACTIVATION_RESPONSE),
        timeout_seconds=6.0,
    )

    data = client.get_etl_profile_activation(" sample_fashion_vendor_v1 ")

    assert data == ETL_PROFILE_ACTIVATION_RESPONSE
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-profiles/sample_fashion_vendor_v1/activation",
            "params": None,
            "timeout": 6.0,
        }
    ]


def test_activation_path_percent_encodes_path_separator():
    client, session = make_client(
        response=FakeResponse(payload=ETL_PROFILE_ACTIVATION_RESPONSE)
    )

    client.get_etl_profile_activation("../secret")

    assert session.calls[0]["url"].endswith("/etl-profiles/..%2Fsecret/activation")


def test_update_etl_profile_activation_puts_the_selected_version():
    client, session = make_client(
        response=FakeResponse(
            payload=_activation(
                runtime_override_exists=True,
                runtime_active_version="1",
                effective_active_version="1",
            )
        ),
        timeout_seconds=6.0,
    )

    client.update_etl_profile_activation("sample_fashion_vendor_v1", active_version="1")

    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-profiles/sample_fashion_vendor_v1/activation",
            "json": {"active_version": "1"},
            "timeout": 6.0,
        }
    ]


def test_update_etl_profile_activation_puts_null_to_deactivate():
    client, session = make_client(
        response=FakeResponse(
            payload=_activation(
                runtime_override_exists=True,
                runtime_active_version=None,
                effective_active_version=None,
                is_active=False,
            )
        )
    )

    client.update_etl_profile_activation("sample_fashion_vendor_v1", active_version=None)

    assert session.calls[0]["json"] == {"active_version": None}


def test_update_etl_profile_activation_rejects_a_blank_version():
    client, session = make_client(
        response=FakeResponse(payload=ETL_PROFILE_ACTIVATION_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.update_etl_profile_activation("sample_fashion_vendor_v1", active_version="   ")

    assert session.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        # available_versions 이상
        _activation(available_versions=[]),
        _activation(available_versions=["1", "1"]),
        _activation(available_versions=["1", ""]),
        _activation(available_versions="1,2"),
        # is_active와 effective가 어긋남
        _activation(is_active=False),
        _activation(
            runtime_override_exists=True,
            runtime_active_version=None,
            effective_active_version=None,
            is_active=True,
        ),
        # override 없음인데 effective가 배포 기본값과 다름
        _activation(effective_active_version="1"),
        # override 없음인데 runtime 값이 붙어 있음
        _activation(runtime_active_version="2"),
        # override 있는데 effective가 runtime과 다름
        _activation(
            runtime_override_exists=True,
            runtime_active_version="1",
            effective_active_version="2",
        ),
        # effective가 available_versions 밖
        _activation(
            runtime_override_exists=True,
            runtime_active_version="9",
            effective_active_version="9",
        ),
        # 식별자 결측
        _activation(profile_id=""),
        _activation(display_name="   "),
    ],
)
def test_activation_response_validation_rejects_inconsistent_payloads(payload):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.get_etl_profile_activation("sample_fashion_vendor_v1")


@pytest.mark.parametrize(
    "payload",
    [
        ETL_PROFILE_ACTIVATION_RESPONSE,
        _activation(
            runtime_override_exists=True,
            runtime_active_version="1",
            effective_active_version="1",
            actor_username="operator_user",
            updated_at="2026-08-22T04:00:00Z",
        ),
        _activation(
            runtime_override_exists=True,
            runtime_active_version=None,
            effective_active_version=None,
            is_active=False,
        ),
        # 배포 기본값이 잘못된 pointer라도 override가 정상이면 받아들입니다.
        _activation(
            deployment_active_version="9",
            runtime_override_exists=True,
            runtime_active_version="2",
            effective_active_version="2",
        ),
    ],
)
def test_activation_response_validation_accepts_every_contract_state(payload):
    client, _ = make_client(response=FakeResponse(payload=payload))

    assert client.get_etl_profile_activation("sample_fashion_vendor_v1") == payload


def test_activation_update_maps_unknown_version_to_a_dedicated_error():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=422,
            payload={
                "detail": {
                    "code": "unknown_profile_version",
                    "message": "요청한 ETL 프로필 버전이 없습니다.",
                    "available_versions": ["1", "2"],
                }
            },
        )
    )

    with pytest.raises(client_module.ETLProfileActivationVersionError) as error:
        client.update_etl_profile_activation("sample_fashion_vendor_v1", active_version="9")

    assert error.value.code == "unknown_profile_version"
    assert error.value.available_versions == ("1", "2")
    # 서버 message 원문이 아니라 클라이언트 문구를 씁니다.
    assert "새로고침" in str(error.value)


def test_activation_update_keeps_a_generic_422_generic():
    """FastAPI의 일반 검증 실패도 422입니다. code를 보지 않으면 잘못 분류됩니다."""
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=422, payload={"detail": [{"loc": ["body"], "msg": "bad"}]}
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.update_etl_profile_activation("sample_fashion_vendor_v1", active_version="1")

    assert not isinstance(error.value, client_module.ETLProfileActivationVersionError)


def test_activation_update_maps_missing_profile_to_not_found():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=404, payload={"detail": "nope"})
    )

    with pytest.raises(client_module.ETLProfileNotFoundError):
        client.update_etl_profile_activation("gone", active_version="1")


@pytest.mark.parametrize(
    ("status_code", "expected_attribute"),
    [
        (401, "CatalogGuardApiAuthenticationError"),
        (403, "CatalogGuardApiAuthorizationError"),
    ],
)
def test_activation_update_reuses_the_existing_auth_errors(status_code, expected_attribute):
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=status_code, payload={"detail": {"code": "x"}})
    )

    with pytest.raises(getattr(client_module, expected_attribute)):
        client.update_etl_profile_activation("sample_fashion_vendor_v1", active_version="1")


def test_activation_update_maps_connection_and_timeout_errors():
    client_module = import_client_module()

    client, _ = make_client(error=requests.ConnectionError("boom"))
    with pytest.raises(client_module.CatalogGuardApiConnectionError):
        client.update_etl_profile_activation("sample_fashion_vendor_v1", active_version="1")

    client, _ = make_client(error=requests.Timeout("slow"))
    with pytest.raises(client_module.CatalogGuardApiTimeoutError):
        client.update_etl_profile_activation("sample_fashion_vendor_v1", active_version="1")


# ---- Phase 5B.3: runtime override reset (DELETE) ------------------------------


def test_reset_etl_profile_activation_deletes_the_activation_path():
    client, session = make_client(
        response=FakeResponse(payload=ETL_PROFILE_ACTIVATION_RESPONSE),
        timeout_seconds=6.0,
    )

    data = client.reset_etl_profile_activation(" sample_fashion_vendor_v1 ")

    assert data == ETL_PROFILE_ACTIVATION_RESPONSE
    # body를 보내지 않습니다. 지울 대상은 경로가 정합니다.
    assert session.calls == [
        {
            "url": "https://api.example.com/api/v1/etl-profiles/sample_fashion_vendor_v1/activation",
            "timeout": 6.0,
        }
    ]


def test_reset_reuses_the_shared_profile_id_validation():
    client, session = make_client(
        response=FakeResponse(payload=ETL_PROFILE_ACTIVATION_RESPONSE)
    )

    with pytest.raises(ValueError):
        client.reset_etl_profile_activation("   ")

    assert session.calls == []


def test_reset_percent_encodes_the_path_separator():
    client, session = make_client(
        response=FakeResponse(payload=ETL_PROFILE_ACTIVATION_RESPONSE)
    )

    client.reset_etl_profile_activation("../secret")

    assert session.calls[0]["url"].endswith("/etl-profiles/..%2Fsecret/activation")


def test_reset_reuses_the_activation_response_validation():
    """새 validator를 만들지 않았습니다. 어긋난 응답은 여기서도 거부돼야 합니다."""
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            # override가 없는데 runtime 값이 붙어 있는, 있을 수 없는 상태입니다.
            payload=_activation(runtime_active_version="2")
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.reset_etl_profile_activation("sample_fashion_vendor_v1")


def test_reset_accepts_the_state_the_server_returns_after_deleting_the_row():
    """reset 직후 응답은 항상 "override 없음"입니다."""
    payload = _activation(
        runtime_override_exists=False,
        runtime_active_version=None,
        effective_active_version="2",
        actor_username=None,
        updated_at=None,
    )
    client, _ = make_client(response=FakeResponse(payload=payload))

    assert client.reset_etl_profile_activation("sample_fashion_vendor_v1") == payload


def test_reset_rejects_a_response_missing_contract_keys():
    client_module = import_client_module()
    payload = dict(ETL_PROFILE_ACTIVATION_RESPONSE)
    payload.pop("available_versions")
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.reset_etl_profile_activation("sample_fashion_vendor_v1")


def test_reset_rejects_a_malformed_body():
    client_module = import_client_module()

    client, _ = make_client(response=FakeResponse(json_error=ValueError("not json")))
    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.reset_etl_profile_activation("sample_fashion_vendor_v1")

    client, _ = make_client(response=FakeResponse(payload=["not", "a", "dict"]))
    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.reset_etl_profile_activation("sample_fashion_vendor_v1")


def test_reset_maps_missing_profile_to_not_found():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=404, payload={"detail": "nope"})
    )

    with pytest.raises(client_module.ETLProfileNotFoundError):
        client.reset_etl_profile_activation("gone")


@pytest.mark.parametrize(
    ("status_code", "expected_attribute"),
    [
        (401, "CatalogGuardApiAuthenticationError"),
        (403, "CatalogGuardApiAuthorizationError"),
    ],
)
def test_reset_reuses_the_existing_auth_errors(status_code, expected_attribute):
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(status_code=status_code, payload={"detail": {"code": "x"}})
    )

    with pytest.raises(getattr(client_module, expected_attribute)):
        client.reset_etl_profile_activation("sample_fashion_vendor_v1")


def test_reset_maps_connection_and_timeout_errors():
    client_module = import_client_module()

    client, _ = make_client(error=requests.ConnectionError("boom"))
    with pytest.raises(client_module.CatalogGuardApiConnectionError):
        client.reset_etl_profile_activation("sample_fashion_vendor_v1")

    client, _ = make_client(error=requests.Timeout("slow"))
    with pytest.raises(client_module.CatalogGuardApiTimeoutError):
        client.reset_etl_profile_activation("sample_fashion_vendor_v1")


def test_reset_passes_the_server_request_id_through_like_the_other_calls():
    """오류 화면이 request ID를 보여 줄 수 있어야 기존 client와 같은 진단이 됩니다."""
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=500,
            payload={"detail": "boom"},
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError) as error:
        client.reset_etl_profile_activation("sample_fashion_vendor_v1")

    assert error.value.request_id == VALID_REQUEST_ID


# ---- Phase 5B.4: activation 운영 이력 조회 ------------------------------------


ETL_PROFILE_ACTIVATION_HISTORY_ITEM = {
    "event_id": 3,
    "profile_id": "sample_fashion_vendor_v1",
    "action": "activate",
    "deployment_active_version": "2",
    "runtime_override_exists": True,
    "runtime_active_version": "1",
    "effective_active_version": "1",
    "actor_username": "operator_user",
    "created_at": "2026-08-23T09:00:00Z",
}


def _history_item(**overrides):
    item = dict(ETL_PROFILE_ACTIVATION_HISTORY_ITEM)
    item.update(overrides)
    return item


def _history_response(items=None, **overrides):
    payload = {
        "items": [ETL_PROFILE_ACTIVATION_HISTORY_ITEM] if items is None else items,
        "total": 1,
        "limit": 20,
        "offset": 0,
    }
    payload.update(overrides)
    return payload


def test_activation_history_uses_the_history_path_and_sends_pagination():
    client, session = make_client(
        response=FakeResponse(payload=_history_response()),
        timeout_seconds=6.0,
    )

    data = client.list_etl_profile_activation_history(
        " sample_fashion_vendor_v1 ", limit=10, offset=20
    )

    assert data == _history_response()
    assert session.calls == [
        {
            "url": (
                "https://api.example.com/api/v1/etl-profiles/"
                "sample_fashion_vendor_v1/activation/history"
            ),
            "params": {"limit": 10, "offset": 20},
            "timeout": 6.0,
        }
    ]


def test_activation_history_defaults_to_the_first_page():
    client, session = make_client(response=FakeResponse(payload=_history_response()))

    client.list_etl_profile_activation_history("sample_fashion_vendor_v1")

    assert session.calls[0]["params"] == {"limit": 20, "offset": 0}


def test_activation_history_path_percent_encodes_path_separator():
    client, session = make_client(response=FakeResponse(payload=_history_response()))

    client.list_etl_profile_activation_history("../secret")

    assert session.calls[0]["url"].endswith("/etl-profiles/..%2Fsecret/activation/history")


def test_activation_history_rejects_a_blank_profile_id():
    client, session = make_client(response=FakeResponse(payload=_history_response()))

    with pytest.raises(ValueError):
        client.list_etl_profile_activation_history("   ")

    assert session.calls == []


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (-1, 0), (20, -1), ("10", 0), (20, "0"), (True, 0)],
)
def test_activation_history_rejects_invalid_pagination(limit, offset):
    client, session = make_client(response=FakeResponse(payload=_history_response()))

    with pytest.raises(ValueError):
        client.list_etl_profile_activation_history(
            "sample_fashion_vendor_v1", limit=limit, offset=offset
        )

    # 잘못된 값으로는 요청 자체를 보내지 않습니다.
    assert session.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        # 목록 metadata가 없거나 형태가 틀린 응답
        {"items": [], "total": 0, "limit": 20},
        _history_response(items="not-a-list"),
        _history_response(total=-1),
        _history_response(limit=0),
        _history_response(offset=-1),
        # item 자체가 깨진 경우
        _history_response(items=[{"event_id": 1}]),
        _history_response(items=[_history_item(event_id=0)]),
        _history_response(items=[_history_item(event_id="3")]),
        _history_response(items=[_history_item(profile_id="   ")]),
        _history_response(items=[_history_item(created_at="")]),
        _history_response(items=[_history_item(actor_username=7)]),
        _history_response(items=[_history_item(runtime_override_exists="yes")]),
        _history_response(items=[_history_item(runtime_active_version="  ")]),
    ],
)
def test_activation_history_rejects_a_malformed_payload(payload):
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=payload))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.list_etl_profile_activation_history("sample_fashion_vendor_v1")


@pytest.mark.parametrize("action", ["bogus", "delete", "ACTIVATE", "", None, 1])
def test_activation_history_rejects_an_unknown_action(action):
    """모르는 action을 통과시키면 화면이 그것을 임의의 문구로 그립니다."""
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(payload=_history_response(items=[_history_item(action=action)]))
    )

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.list_etl_profile_activation_history("sample_fashion_vendor_v1")


@pytest.mark.parametrize(
    "item",
    [
        # activate인데 override가 없다
        _history_item(
            action="activate",
            runtime_override_exists=False,
            runtime_active_version=None,
            effective_active_version=None,
        ),
        # deactivate인데 실제 적용 버전이 있다
        _history_item(
            action="deactivate",
            runtime_active_version=None,
            effective_active_version="2",
        ),
        # reset인데 override가 남아 있다
        _history_item(
            action="reset",
            runtime_override_exists=True,
            runtime_active_version=None,
            effective_active_version="2",
        ),
        # reset인데 실제 적용 버전이 배포 기본값과 다르다
        _history_item(
            action="reset",
            runtime_override_exists=False,
            runtime_active_version=None,
            deployment_active_version="2",
            effective_active_version="1",
        ),
    ],
)
def test_activation_history_rejects_an_item_contradicting_its_own_action(item):
    """action과 상태가 어긋나면 화면이 reset을 비활성화로 보여 주게 됩니다."""
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(payload=_history_response(items=[item])))

    with pytest.raises(client_module.CatalogGuardApiResponseError):
        client.list_etl_profile_activation_history("sample_fashion_vendor_v1")


@pytest.mark.parametrize(
    "item",
    [
        _history_item(),
        _history_item(
            action="deactivate",
            runtime_active_version=None,
            effective_active_version=None,
        ),
        _history_item(
            action="reset",
            runtime_override_exists=False,
            runtime_active_version=None,
            deployment_active_version="2",
            effective_active_version="2",
        ),
        # 배포 기본값 자체가 비활성이면 reset 뒤에도 비활성입니다.
        _history_item(
            action="reset",
            runtime_override_exists=False,
            runtime_active_version=None,
            deployment_active_version=None,
            effective_active_version=None,
        ),
        # 삭제된 사용자의 명령은 이름 없이 남을 수 있습니다.
        _history_item(actor_username=None),
    ],
)
def test_activation_history_accepts_every_contract_state(item):
    client, _ = make_client(response=FakeResponse(payload=_history_response(items=[item])))

    data = client.list_etl_profile_activation_history("sample_fashion_vendor_v1")

    assert data["items"] == [item]


def test_activation_history_accepts_an_empty_page():
    """빈 이력은 오류가 아닙니다. 이 기능 이전의 조작은 남아 있지 않습니다."""
    client, _ = make_client(
        response=FakeResponse(payload=_history_response(items=[], total=0))
    )

    data = client.list_etl_profile_activation_history("sample_fashion_vendor_v1")

    assert data["items"] == []
    assert data["total"] == 0


def test_activation_history_maps_404_to_the_profile_error():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(status_code=404, text="not found"))

    with pytest.raises(client_module.ETLProfileNotFoundError) as error:
        client.list_etl_profile_activation_history("sample_fashion_vendor_v1")

    assert "ETL 프로필을 찾을 수 없습니다." in str(error.value)
    assert "not found" not in str(error.value)


def test_activation_history_preserves_the_request_id_for_404():
    client_module = import_client_module()
    client, _ = make_client(
        response=FakeResponse(
            status_code=404,
            text="not found",
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
    )

    with pytest.raises(client_module.ETLProfileNotFoundError) as error:
        client.list_etl_profile_activation_history("sample_fashion_vendor_v1")

    assert error.value.request_id == VALID_REQUEST_ID


def test_activation_history_maps_connection_and_timeout_errors():
    client_module = import_client_module()

    client, _ = make_client(error=requests.ConnectionError("redis.internal:6379"))
    with pytest.raises(client_module.CatalogGuardApiConnectionError) as connection_error:
        client.list_etl_profile_activation_history("sample_fashion_vendor_v1")
    assert "redis.internal" not in str(connection_error.value)

    client, _ = make_client(error=requests.Timeout("too slow"))
    with pytest.raises(client_module.CatalogGuardApiTimeoutError):
        client.list_etl_profile_activation_history("sample_fashion_vendor_v1")


def test_the_client_has_no_history_write_methods():
    """append-only 기록에는 수정·삭제 경로를 두지 않습니다."""
    client, _ = make_client(response=FakeResponse(payload=_history_response()))

    for name in dir(client):
        assert "activation_history" not in name or name.startswith("list_"), name
