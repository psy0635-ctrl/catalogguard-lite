import importlib

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
    "summary": {
        "total_products": 5,
        "total_issues": 6,
        "error_count": 6,
        "warning_count": 0,
    },
    "results": [],
}


class FakeResponse:
    def __init__(self, *, payload=None, status_code=200, json_error=None, text=""):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error
        self.text = text

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

    def post(self, url, *, files=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "files": files,
                "timeout": timeout,
            }
        )
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


def test_list_inspections_converts_timeout_error():
    client_module = import_client_module()
    client, _ = make_client(error=requests.Timeout("too slow"))

    with pytest.raises(client_module.CatalogGuardApiTimeoutError) as error:
        client.list_inspections()

    assert "검수 이력 서버 응답 시간이 초과되었습니다." in str(error.value)


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


def test_create_inspection_converts_timeout_error():
    client_module = import_client_module()
    client, _ = make_client(error=requests.Timeout("too slow"))

    with pytest.raises(client_module.CatalogGuardApiTimeoutError) as error:
        client.create_inspection(
            source_filename="products_dev.csv",
            file_content=b"product_id,price\nP001,1000\n",
        )

    assert "검수 이력 서버 응답 시간이 초과되었습니다." in str(error.value)


def test_get_inspection_detail_converts_404_to_not_found():
    client_module = import_client_module()
    client, _ = make_client(response=FakeResponse(status_code=404, text="not found"))

    with pytest.raises(client_module.InspectionNotFoundError) as error:
        client.get_inspection_detail(11)

    assert "검수 실행 결과를 찾을 수 없습니다." in str(error.value)


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
