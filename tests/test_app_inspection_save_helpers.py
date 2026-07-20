import importlib
import sys

import pytest
import streamlit as st


VALID_REQUEST_ID = "a29ae9a1c62f4152bb96f6513c323d96"


def make_detail_response(inspection_run_id=42):
    return {
        "inspection_run_id": inspection_run_id,
        "created": True,
        "source_filename": "products.csv",
        "created_at": "2026-07-20T12:00:00+09:00",
        "summary": {
            "total_products": 1,
            "total_issues": 1,
            "error_count": 1,
            "warning_count": 0,
        },
        "results": [
            {
                "status": "오류",
                "product_group_id": "G001",
                "product_id": "P001",
                "error_field": "필수 값 누락",
                "reason": "상품명이 비어 있습니다.",
                "recommendation": "누락된 필수 값을 입력하세요.",
                "risk_level": "높음",
            }
        ],
    }


class FakeInspectionApiClient:
    def __init__(
        self,
        *,
        create_response=None,
        detail_response=None,
        create_error=None,
        detail_error=None,
    ):
        self.create_response = create_response or {
            "inspection_run_id": 42,
            "created": True,
            "summary": make_detail_response()["summary"],
            "results": make_detail_response()["results"],
        }
        self.detail_response = detail_response or make_detail_response()
        self.create_error = create_error
        self.detail_error = detail_error
        self.create_calls = []
        self.detail_calls = []

    def create_inspection(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        return self.create_response

    def get_inspection_detail(self, inspection_run_id):
        self.detail_calls.append(inspection_run_id)
        if self.detail_error is not None:
            raise self.detail_error
        return self.detail_response


class FakeButtonStreamlit:
    def __init__(self, *, session_state=None, clicked=True):
        self.session_state = session_state if session_state is not None else {}
        self.clicked = clicked
        self.button_calls = []
        self.captions = []
        self.errors = []
        self.infos = []
        self.successes = []

    def button(self, label, **kwargs):
        self.button_calls.append((label, kwargs))
        return self.clicked

    def caption(self, message):
        self.captions.append(message)

    def error(self, message):
        self.errors.append(message)

    def info(self, message):
        self.infos.append(message)

    def success(self, message):
        self.successes.append(message)


@pytest.fixture()
def app_module(monkeypatch):
    sys.modules.pop("app", None)
    monkeypatch.setattr(st, "stop", lambda: None)
    return importlib.import_module("app")


def test_build_file_hash_returns_same_hash_for_same_bytes(app_module):
    first_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")
    second_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")

    assert first_hash == second_hash


def test_build_file_hash_returns_different_hash_for_different_bytes(app_module):
    first_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")
    second_hash = app_module.build_file_hash(b"product_id,price\nP002,2000\n")

    assert first_hash != second_hash


def test_apply_inspection_save_response_returns_created_message_and_updates_state(
    app_module,
):
    session_state = {}
    file_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")

    inspection_run_id, created, message = app_module.apply_inspection_save_response(
        session_state,
        file_hash=file_hash,
        response={"inspection_run_id": 42, "created": True},
        detail_response=make_detail_response(),
    )

    assert inspection_run_id == 42
    assert created is True
    assert message == "검수 결과를 새 이력으로 저장했습니다. 실행 ID: 42"
    assert session_state["saved_file_hash"] == file_hash
    assert session_state["saved_inspection_run_id"] == 42
    assert session_state["current_inspection_created"] is True
    assert session_state["current_inspection_detail_response"] == make_detail_response()


def test_apply_inspection_save_response_returns_duplicate_message_and_updates_state(
    app_module,
):
    session_state = {}
    file_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")

    inspection_run_id, created, message = app_module.apply_inspection_save_response(
        session_state,
        file_hash=file_hash,
        response={"inspection_run_id": 42, "created": False},
        detail_response=make_detail_response(),
    )

    assert inspection_run_id == 42
    assert created is False
    assert message == (
        "이미 검수한 동일 파일이므로 기존 검수 결과를 불러왔습니다. "
        "실행 ID: 42"
    )
    assert session_state["saved_file_hash"] == file_hash
    assert session_state["saved_inspection_run_id"] == 42
    assert session_state["current_inspection_created"] is False
    assert session_state["current_inspection_detail_response"] == make_detail_response()


def test_render_inspection_button_posts_once_fetches_detail_and_stores_server_result(
    app_module,
    monkeypatch,
):
    fake_streamlit = FakeButtonStreamlit()
    api_client = FakeInspectionApiClient()
    monkeypatch.setattr(app_module, "st", fake_streamlit)
    monkeypatch.setattr(
        app_module,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    detail_response = app_module.render_inspection_save_button(
        source_filename="products.csv",
        file_bytes=b"synthetic csv bytes",
        content_type="text/csv",
    )

    assert fake_streamlit.button_calls[0][0] == "검수 실행 및 이력 저장"
    assert len(api_client.create_calls) == 1
    assert api_client.create_calls[0]["file_content"] == b"synthetic csv bytes"
    assert api_client.detail_calls == [42]
    assert detail_response == make_detail_response()
    assert fake_streamlit.session_state["current_inspection_detail_response"] == (
        make_detail_response()
    )
    assert fake_streamlit.successes == [
        "검수 결과를 새 이력으로 저장했습니다. 실행 ID: 42"
    ]


def test_render_inspection_button_fetches_existing_detail_for_duplicate(
    app_module,
    monkeypatch,
):
    fake_streamlit = FakeButtonStreamlit()
    api_client = FakeInspectionApiClient(
        create_response={
            "inspection_run_id": 42,
            "created": False,
            "summary": make_detail_response()["summary"],
            "results": make_detail_response()["results"],
        }
    )
    monkeypatch.setattr(app_module, "st", fake_streamlit)
    monkeypatch.setattr(
        app_module,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    detail_response = app_module.render_inspection_save_button(
        source_filename="products.csv",
        file_bytes=b"synthetic csv bytes",
        content_type="text/csv",
    )

    assert len(api_client.create_calls) == 1
    assert api_client.detail_calls == [42]
    assert detail_response == make_detail_response()
    assert fake_streamlit.infos == [
        "이미 검수한 동일 파일이므로 기존 검수 결과를 불러왔습니다. "
        "실행 ID: 42"
    ]


@pytest.mark.parametrize(
    "api_error",
    [
        pytest.param(
            None,
            id="connection-error",
        ),
        pytest.param(
            "response",
            id="create-400-error",
        ),
    ],
)
def test_render_inspection_button_clears_previous_result_on_create_failure(
    app_module,
    monkeypatch,
    api_error,
):
    error = (
        app_module.CatalogGuardApiConnectionError("connection failed")
        if api_error is None
        else app_module.CatalogGuardApiResponseError(
            "bad request",
            request_id=VALID_REQUEST_ID,
        )
    )
    old_hash = app_module.build_file_hash(b"old file")
    session_state = {
        "current_upload_file_hash": old_hash,
        "saved_file_hash": old_hash,
        "saved_inspection_run_id": 7,
        "current_inspection_created": True,
        "current_inspection_detail_response": make_detail_response(7),
    }
    fake_streamlit = FakeButtonStreamlit(session_state=session_state)
    api_client = FakeInspectionApiClient(create_error=error)
    monkeypatch.setattr(app_module, "st", fake_streamlit)
    monkeypatch.setattr(
        app_module,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    detail_response = app_module.render_inspection_save_button(
        source_filename="new.csv",
        file_bytes=b"new file",
        content_type="text/csv",
    )

    assert detail_response is None
    assert len(api_client.create_calls) == 1
    assert api_client.detail_calls == []
    assert "current_inspection_detail_response" not in session_state
    assert "saved_inspection_run_id" not in session_state
    assert fake_streamlit.errors == ["검수를 완료하지 못했습니다."]
    if api_error == "response":
        assert any(VALID_REQUEST_ID in caption for caption in fake_streamlit.captions)


def test_render_inspection_button_does_not_keep_result_when_detail_lookup_fails(
    app_module,
    monkeypatch,
):
    detail_error = app_module.CatalogGuardApiResponseError(
        "invalid detail",
        request_id=VALID_REQUEST_ID,
    )
    fake_streamlit = FakeButtonStreamlit()
    api_client = FakeInspectionApiClient(detail_error=detail_error)
    monkeypatch.setattr(app_module, "st", fake_streamlit)
    monkeypatch.setattr(
        app_module,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    detail_response = app_module.render_inspection_save_button(
        source_filename="products.csv",
        file_bytes=b"synthetic csv bytes",
        content_type="text/csv",
    )

    assert detail_response is None
    assert len(api_client.create_calls) == 1
    assert api_client.detail_calls == [42]
    assert "current_inspection_detail_response" not in fake_streamlit.session_state
    assert fake_streamlit.errors == ["검수를 완료하지 못했습니다."]
    assert any(VALID_REQUEST_ID in caption for caption in fake_streamlit.captions)


@pytest.mark.parametrize(
    "detail_response",
    [
        pytest.param(
            {**make_detail_response(), "summary": []},
            id="summary-not-object",
        ),
        pytest.param(
            {
                **make_detail_response(),
                "summary": {
                    **make_detail_response()["summary"],
                    "total_products": "1",
                },
            },
            id="summary-count-not-integer",
        ),
        pytest.param(
            {**make_detail_response(), "results": None},
            id="results-not-list",
        ),
        pytest.param(
            {**make_detail_response(), "results": [{"status": "오류"}]},
            id="result-missing-required-fields",
        ),
    ],
)
def test_render_inspection_button_rejects_malformed_detail_before_storing_result(
    app_module,
    monkeypatch,
    detail_response,
):
    fake_streamlit = FakeButtonStreamlit()
    api_client = FakeInspectionApiClient(detail_response=detail_response)
    monkeypatch.setattr(app_module, "st", fake_streamlit)
    monkeypatch.setattr(
        app_module,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    result = app_module.render_inspection_save_button(
        source_filename="products.csv",
        file_bytes=b"synthetic csv bytes",
        content_type="text/csv",
    )

    assert result is None
    assert len(api_client.create_calls) == 1
    assert api_client.detail_calls == [42]
    assert "saved_inspection_run_id" not in fake_streamlit.session_state
    assert "current_inspection_detail_response" not in fake_streamlit.session_state
    assert fake_streamlit.errors == ["검수를 완료하지 못했습니다."]


def test_render_inspection_button_clears_previous_file_result_before_new_run(
    app_module,
    monkeypatch,
):
    old_hash = app_module.build_file_hash(b"old file")
    session_state = {
        "current_upload_file_hash": old_hash,
        "saved_file_hash": old_hash,
        "saved_inspection_run_id": 7,
        "current_inspection_created": True,
        "current_inspection_detail_response": make_detail_response(7),
    }
    fake_streamlit = FakeButtonStreamlit(
        session_state=session_state,
        clicked=False,
    )
    monkeypatch.setattr(app_module, "st", fake_streamlit)

    detail_response = app_module.render_inspection_save_button(
        source_filename="new.csv",
        file_bytes=b"new file",
        content_type="text/csv",
    )

    assert detail_response is None
    assert session_state["current_upload_file_hash"] == app_module.build_file_hash(
        b"new file"
    )
    assert "current_inspection_detail_response" not in session_state
    assert "saved_inspection_run_id" not in session_state
