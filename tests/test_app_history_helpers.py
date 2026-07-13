import copy
import importlib
import sys
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
import streamlit as st


VALID_REQUEST_ID = "a29ae9a1c62f4152bb96f6513c323d96"


@pytest.fixture()
def app_module(monkeypatch):
    sys.modules.pop("app", None)
    monkeypatch.setattr(st, "stop", lambda: None)
    return importlib.import_module("app")


class FakeHistoryApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def list_inspections(self, **params):
        self.calls.append(params)
        if not self.responses:
            raise AssertionError("unexpected list_inspections call")

        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeStreamlitColumn:
    def __init__(self, streamlit, index):
        self.streamlit = streamlit
        self.index = index

    def __enter__(self):
        self.streamlit.active_column = self.index
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.streamlit.active_column = None

    def metric(self, label, value):
        self.streamlit.metrics.append((self.index, label, value))


class FakeAppStreamlit:
    def __init__(
        self,
        *,
        uploaded_file=None,
        session_state=None,
        selectbox_values=None,
        text_input_values=None,
    ):
        self.uploaded_file = uploaded_file
        self.session_state = session_state or SimpleNamespace()
        self.selectbox_values = selectbox_values or {}
        self.text_input_values = text_input_values or {}
        self.active_column = None
        self.call_log = []
        self.subheaders = []
        self.captions = []
        self.errors = []
        self.infos = []
        self.warnings = []
        self.successes = []
        self.markdowns = []
        self.dataframes = []
        self.columns_calls = []
        self.metrics = []
        self.downloads = []

    def subheader(self, message):
        self.subheaders.append(message)
        self.call_log.append(("subheader", message))

    def write(self, message):
        self.call_log.append(("write", message))

    def caption(self, message):
        self.captions.append(message)
        self.call_log.append(("caption", message))

    def error(self, message):
        self.errors.append(message)
        self.call_log.append(("error", message))

    def info(self, message):
        self.infos.append(message)
        self.call_log.append(("info", message))

    def warning(self, message):
        self.warnings.append(message)
        self.call_log.append(("warning", message))

    def success(self, message):
        self.successes.append(message)
        self.call_log.append(("success", message))

    def markdown(self, message):
        self.markdowns.append((self.active_column, message))
        self.call_log.append(("markdown", self.active_column, message))

    def columns(self, specification):
        count = specification if isinstance(specification, int) else len(specification)
        self.columns_calls.append(specification)
        return tuple(FakeStreamlitColumn(self, index) for index in range(count))

    def dataframe(self, dataframe, **kwargs):
        self.dataframes.append(
            (self.active_column, dataframe.copy(deep=True), kwargs.copy())
        )
        self.call_log.append(("dataframe", self.active_column))

    def download_button(self, label, **kwargs):
        self.downloads.append((label, kwargs.copy()))

    def file_uploader(self, *args, **kwargs):
        return self.uploaded_file

    def selectbox(self, label, options, **kwargs):
        return self.selectbox_values.get(label, options[0])

    def text_input(self, label, **kwargs):
        return self.text_input_values.get(label, "")

    def button(self, *args, **kwargs):
        return False


def make_statistics_dataframes():
    return {
        "issue_counts": pd.DataFrame(
            {
                "오류 항목": ["가격 오류", "필수 값 누락"],
                "문제 수": [4, 2],
            }
        ),
        "risk_counts": pd.DataFrame(
            {
                "위험 수준": ["높음", "중간", "낮음"],
                "문제 수": [3, 2, 1],
            }
        ),
        "product_counts": pd.DataFrame(
            {
                "상품 ID": ["P001", "P002", "P003", "P004", "P005", "P006"],
                "문제 수": [6, 5, 4, 3, 2, 1],
            }
        ),
        "total_issues": 6,
    }


def make_history_item(
    inspection_run_id: int,
    *,
    error_count: int = 0,
    warning_count: int = 0,
) -> dict:
    return {
        "inspection_run_id": inspection_run_id,
        "source_filename": f"products_{inspection_run_id}.csv",
        "created_at": "2026-07-04T13:42:39.495949+09:00",
        "total_products": 5,
        "total_issues": error_count + warning_count,
        "error_count": error_count,
        "warning_count": warning_count,
    }


def make_history_response(items: list[dict], *, total: int) -> dict:
    return {
        "items": items,
        "total": total,
        "limit": 100,
        "offset": 0,
    }


def make_prepared_history_summary_download_state(app_module) -> dict:
    return {
        app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY: {
            "cache_key": (("status", "error"),),
            "csv_bytes": b"old-csv",
            "file_name": "old.csv",
            "total": 10,
        },
        app_module.HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY: "old error",
    }


def assert_prepared_history_summary_download_is_cleared(
    app_module,
    session_state,
) -> None:
    assert app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY not in session_state
    assert app_module.HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY not in session_state


def test_build_api_error_display_message_appends_request_id_once(app_module):
    error = app_module.CatalogGuardApiResponseError(
        "private upstream error",
        request_id=VALID_REQUEST_ID,
    )

    message = app_module.build_api_error_display_message(
        "검수 이력을 불러오는 중 오류가 발생했습니다.",
        error,
    )

    assert "검수 이력을 불러오는 중 오류가 발생했습니다." in message
    assert f"요청 ID: {VALID_REQUEST_ID}" in message
    assert message.count(VALID_REQUEST_ID) == 1


def test_build_api_error_display_message_omits_missing_request_id(app_module):
    error = app_module.CatalogGuardApiTimeoutError(
        "private timeout detail",
        request_id=None,
    )

    message = app_module.build_api_error_display_message(
        "검수 이력 서버 응답 시간이 초과되었습니다.",
        error,
    )

    assert message == "검수 이력 서버 응답 시간이 초과되었습니다."
    assert "요청 ID:" not in message


def test_build_api_error_display_message_omits_invalid_request_id(app_module):
    invalid_request_id = "not-valid\ninternal-host.example"
    error = app_module.CatalogGuardApiResponseError(
        "private upstream error",
        request_id=invalid_request_id,
    )

    message = app_module.build_api_error_display_message(
        "검수 이력을 불러오는 중 오류가 발생했습니다.",
        error,
    )

    assert message == "검수 이력을 불러오는 중 오류가 발생했습니다."
    assert "요청 ID:" not in message
    assert invalid_request_id not in message


def test_build_api_error_display_message_does_not_expose_private_error(app_module):
    private_details = [
        "Traceback: private stack trace",
        "postgresql://catalog:fake-password@internal-db.example/catalog",
        "fake-password",
        "internal-db.example",
    ]
    error = app_module.CatalogGuardApiResponseError(
        " ".join(private_details),
        request_id=VALID_REQUEST_ID,
    )

    message = app_module.build_api_error_display_message(
        "전체 검수 이력 CSV를 준비하는 중 오류가 발생했습니다.",
        error,
    )

    assert "전체 검수 이력 CSV를 준비하는 중 오류가 발생했습니다." in message
    assert all(detail not in message for detail in private_details)


def test_build_api_error_display_message_does_not_duplicate_request_id(app_module):
    error = app_module.CatalogGuardApiResponseError(
        "private upstream error",
        request_id=VALID_REQUEST_ID,
    )
    existing_message = (
        "검수 상세 결과를 불러오는 중 오류가 발생했습니다."
        f"\n\n요청 ID: {VALID_REQUEST_ID}"
    )

    message = app_module.build_api_error_display_message(existing_message, error)

    assert message == existing_message
    assert message.count(VALID_REQUEST_ID) == 1


@pytest.mark.parametrize(
    ("total", "limit", "offset", "expected"),
    [
        (25, 10, 0, (1, 3, False, True)),
        (25, 10, 10, (2, 3, True, True)),
        (25, 10, 20, (3, 3, True, False)),
        (0, 10, 0, (1, 1, False, False)),
    ],
)
def test_calculate_history_pagination(app_module, total, limit, offset, expected):
    assert (
        app_module.calculate_history_pagination(
            total=total,
            limit=limit,
            offset=offset,
        )
        == expected
    )


def test_build_history_dataframe_maps_items_without_changing_input(app_module):
    items = [
        {
            "inspection_run_id": 11,
            "source_filename": "products_dev.csv",
            "created_at": "2026-07-04T13:42:39.495949+09:00",
            "total_products": 5,
            "total_issues": 6,
            "error_count": 6,
            "warning_count": 0,
        }
    ]
    original_items = copy.deepcopy(items)

    dataframe = app_module.build_history_dataframe(items)

    assert list(dataframe.columns) == app_module.HISTORY_DISPLAY_COLUMNS
    assert len(dataframe) == 1
    assert dataframe.iloc[0].to_dict() == {
        "실행 ID": 11,
        "파일명": "products_dev.csv",
        "검수 시간": "2026-07-04 13:42:39",
        "전체 상품": 5,
        "전체 문제": 6,
        "오류": 6,
        "주의": 0,
    }
    assert items == original_items


def test_build_history_dataframe_keeps_original_datetime_when_parse_fails(
    app_module,
):
    dataframe = app_module.build_history_dataframe(
        [
            {
                "inspection_run_id": 12,
                "source_filename": "invalid_time.csv",
                "created_at": "not-a-date",
                "total_products": 1,
                "total_issues": 0,
                "error_count": 0,
                "warning_count": 0,
            }
        ]
    )

    assert dataframe.iloc[0]["검수 시간"] == "not-a-date"


def test_build_history_dataframe_returns_empty_dataframe_with_display_columns(
    app_module,
):
    dataframe = app_module.build_history_dataframe([])

    assert isinstance(dataframe, pd.DataFrame)
    assert dataframe.empty
    assert list(dataframe.columns) == app_module.HISTORY_DISPLAY_COLUMNS


def test_apply_history_filename_search_trims_query_and_resets_offset(app_module):
    session_state = {
        "history_filename_input": "  products  ",
        "history_filename_query": "",
        "history_offset": 20,
    }

    app_module.apply_history_filename_search(session_state)

    assert session_state["history_filename_input"] == "products"
    assert session_state["history_filename_query"] == "products"
    assert session_state["history_offset"] == 0


def test_apply_history_search_applies_filename_and_dates_and_resets_offset(
    app_module,
):
    session_state = {
        "history_filename_input": "  products  ",
        "history_filename_query": "",
        "history_start_date_input": date(2026, 7, 1),
        "history_end_date_input": date(2026, 7, 5),
        "history_start_date_query": None,
        "history_end_date_query": None,
        "history_filter_error": "old error",
        "history_offset": 20,
    }

    app_module.apply_history_search(session_state)

    assert session_state["history_filename_input"] == "products"
    assert session_state["history_filename_query"] == "products"
    assert session_state["history_start_date_query"] == date(2026, 7, 1)
    assert session_state["history_end_date_query"] == date(2026, 7, 5)
    assert session_state["history_filter_error"] is None
    assert session_state["history_offset"] == 0


def test_apply_history_search_applies_status_and_resets_offset(app_module):
    session_state = {
        "history_filename_input": "",
        "history_filename_query": "",
        "history_start_date_input": None,
        "history_end_date_input": None,
        "history_start_date_query": None,
        "history_end_date_query": None,
        "history_status_input": "오류",
        "history_status_query": None,
        "history_filter_error": None,
        "history_offset": 20,
    }

    app_module.apply_history_search(session_state)

    assert session_state["history_status_input"] == "오류"
    assert session_state["history_status_query"] == "error"
    assert session_state["history_filter_error"] is None
    assert session_state["history_offset"] == 0


def test_apply_history_search_clears_prepared_csv_when_filename_query_changes(
    app_module,
):
    session_state = {
        **make_prepared_history_summary_download_state(app_module),
        "history_filename_input": "normal-products",
        "history_filename_query": "error-products",
        "history_start_date_input": None,
        "history_end_date_input": None,
        "history_status_input": "전체",
        "history_filter_error": None,
        "history_offset": 20,
    }

    app_module.apply_history_search(session_state)

    assert session_state["history_filename_query"] == "normal-products"
    assert_prepared_history_summary_download_is_cleared(app_module, session_state)


def test_apply_history_search_clears_prepared_csv_when_date_query_changes(
    app_module,
):
    session_state = {
        **make_prepared_history_summary_download_state(app_module),
        "history_filename_input": "",
        "history_filename_query": "",
        "history_start_date_input": date(2026, 7, 2),
        "history_end_date_input": date(2026, 7, 5),
        "history_start_date_query": date(2026, 7, 1),
        "history_end_date_query": date(2026, 7, 5),
        "history_status_input": "전체",
        "history_filter_error": None,
        "history_offset": 20,
    }

    app_module.apply_history_search(session_state)

    assert session_state["history_start_date_query"] == date(2026, 7, 2)
    assert session_state["history_end_date_query"] == date(2026, 7, 5)
    assert_prepared_history_summary_download_is_cleared(app_module, session_state)


def test_apply_history_search_clears_prepared_csv_when_status_query_changes(
    app_module,
):
    session_state = {
        **make_prepared_history_summary_download_state(app_module),
        "history_filename_input": "",
        "history_filename_query": "",
        "history_start_date_input": None,
        "history_end_date_input": None,
        "history_status_input": app_module.HISTORY_STATUS_QUERY_TO_LABEL["normal"],
        "history_status_query": "error",
        "history_filter_error": None,
        "history_offset": 20,
    }

    app_module.apply_history_search(session_state)

    assert session_state["history_status_query"] == "normal"
    assert_prepared_history_summary_download_is_cleared(app_module, session_state)


def test_apply_history_search_keeps_status_query_none_for_all(app_module):
    session_state = {
        "history_filename_input": "",
        "history_filename_query": "products",
        "history_start_date_input": None,
        "history_end_date_input": None,
        "history_start_date_query": None,
        "history_end_date_query": None,
        "history_status_input": "전체",
        "history_status_query": "warning",
        "history_filter_error": None,
        "history_offset": 10,
    }

    app_module.apply_history_search(session_state)

    assert session_state["history_status_input"] == "전체"
    assert session_state["history_status_query"] is None
    assert session_state["history_offset"] == 0


def test_apply_history_search_rejects_start_after_end_without_changing_query(
    app_module,
):
    session_state = {
        "history_filename_input": "products",
        "history_filename_query": "",
        "history_start_date_input": date(2026, 7, 6),
        "history_end_date_input": date(2026, 7, 5),
        "history_start_date_query": None,
        "history_end_date_query": None,
        "history_status_input": "오류",
        "history_status_query": "warning",
        "history_offset": 20,
    }

    app_module.apply_history_search(session_state)

    assert session_state["history_filter_error"] == "시작일은 종료일보다 늦을 수 없습니다."
    assert session_state["history_filename_query"] == ""
    assert session_state["history_start_date_query"] is None
    assert session_state["history_end_date_query"] is None
    assert session_state["history_status_query"] == "warning"
    assert session_state["history_offset"] == 20


def test_build_history_list_request_params_includes_filename_query(app_module):
    session_state = {"history_filename_query": "products"}

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=20,
    )

    assert params == {"limit": 10, "offset": 20, "filename": "products"}


def test_build_history_list_request_params_includes_date_queries(app_module):
    session_state = {
        "history_filename_query": "",
        "history_start_date_query": date(2026, 7, 1),
        "history_end_date_query": date(2026, 7, 5),
    }

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=0,
    )

    assert params == {
        "limit": 10,
        "offset": 0,
        "start_date": "2026-07-01",
        "end_date": "2026-07-05",
    }


def test_build_history_list_request_params_includes_status_query(app_module):
    session_state = {
        "history_filename_query": "",
        "history_status_query": "normal",
    }

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=0,
    )

    assert params == {"limit": 10, "offset": 0, "status": "normal"}


def test_build_history_list_request_params_omits_status_for_all(app_module):
    session_state = {
        "history_filename_query": "",
        "history_status_query": None,
    }

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=0,
    )

    assert params == {"limit": 10, "offset": 0}


def test_build_history_list_request_params_omits_blank_filename_query(app_module):
    session_state = {"history_filename_query": "   "}

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=0,
    )

    assert params == {"limit": 10, "offset": 0}


def test_history_filename_query_is_kept_for_pagination_offsets(app_module):
    session_state = {
        "history_filename_query": "products",
        "history_status_query": "warning",
    }

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=10,
    )

    assert params["filename"] == "products"
    assert params["status"] == "warning"
    assert params["offset"] == 10


def test_fetch_all_history_summary_items_fetches_single_page_under_limit(app_module):
    items = [make_history_item(index) for index in range(1, 51)]
    api_client = FakeHistoryApiClient([make_history_response(items, total=50)])

    fetched_items, total = app_module.fetch_all_history_summary_items(api_client, {})

    assert fetched_items == items
    assert total == 50
    assert api_client.calls == [
        {"limit": app_module.HISTORY_SUMMARY_DOWNLOAD_LIMIT, "offset": 0}
    ]


def test_fetch_all_history_summary_items_fetches_multiple_pages(app_module):
    first_page = [make_history_item(index) for index in range(1, 101)]
    second_page = [make_history_item(index) for index in range(101, 126)]
    api_client = FakeHistoryApiClient(
        [
            make_history_response(first_page, total=125),
            make_history_response(second_page, total=125),
        ]
    )

    fetched_items, total = app_module.fetch_all_history_summary_items(api_client, {})

    assert fetched_items == first_page + second_page
    assert total == 125
    assert [call["offset"] for call in api_client.calls] == [0, 100]


def test_fetch_all_history_summary_items_stops_at_exactly_100_results(app_module):
    items = [make_history_item(index) for index in range(1, 101)]
    api_client = FakeHistoryApiClient([make_history_response(items, total=100)])

    fetched_items, total = app_module.fetch_all_history_summary_items(api_client, {})

    assert fetched_items == items
    assert total == 100
    assert len(api_client.calls) == 1


def test_fetch_all_history_summary_items_returns_empty_result(app_module):
    api_client = FakeHistoryApiClient([make_history_response([], total=0)])

    fetched_items, total = app_module.fetch_all_history_summary_items(api_client, {})

    assert fetched_items == []
    assert total == 0
    assert len(api_client.calls) == 1


def test_fetch_all_history_summary_items_keeps_filters_for_every_page(app_module):
    first_page = [make_history_item(index) for index in range(1, 101)]
    second_page = [make_history_item(index) for index in range(101, 121)]
    api_client = FakeHistoryApiClient(
        [
            make_history_response(first_page, total=120),
            make_history_response(second_page, total=120),
        ]
    )
    session_state = {
        "history_filename_query": "products",
        "history_start_date_query": date(2026, 7, 1),
        "history_end_date_query": date(2026, 7, 5),
        "history_status_query": "warning",
        "history_offset": 30,
    }

    app_module.fetch_all_history_summary_items(api_client, session_state)

    assert api_client.calls == [
        {
            "limit": app_module.HISTORY_SUMMARY_DOWNLOAD_LIMIT,
            "offset": 0,
            "filename": "products",
            "start_date": "2026-07-01",
            "end_date": "2026-07-05",
            "status": "warning",
        },
        {
            "limit": app_module.HISTORY_SUMMARY_DOWNLOAD_LIMIT,
            "offset": 100,
            "filename": "products",
            "start_date": "2026-07-01",
            "end_date": "2026-07-05",
            "status": "warning",
        },
    ]
    assert session_state["history_offset"] == 30


def test_fetch_all_history_summary_items_fails_when_later_page_fails(app_module):
    first_page = [make_history_item(index) for index in range(1, 101)]
    api_client = FakeHistoryApiClient(
        [
            make_history_response(first_page, total=150),
            app_module.CatalogGuardApiTimeoutError("timeout"),
        ]
    )

    with pytest.raises(app_module.CatalogGuardApiTimeoutError):
        app_module.fetch_all_history_summary_items(api_client, {})

    assert [call["offset"] for call in api_client.calls] == [0, 100]


def test_fetch_all_history_summary_items_rejects_duplicate_run_ids(app_module):
    first_page = [make_history_item(index) for index in range(1, 101)]
    second_page = [make_history_item(100)]
    api_client = FakeHistoryApiClient(
        [
            make_history_response(first_page, total=101),
            make_history_response(second_page, total=101),
        ]
    )

    with pytest.raises(app_module.CatalogGuardApiResponseError):
        app_module.fetch_all_history_summary_items(api_client, {})


def test_fetch_all_history_summary_items_has_max_page_guard(
    app_module,
    monkeypatch,
):
    monkeypatch.setattr(app_module, "HISTORY_SUMMARY_DOWNLOAD_MAX_PAGES", 2)
    first_page = [make_history_item(index) for index in range(1, 101)]
    second_page = [make_history_item(index) for index in range(101, 201)]
    api_client = FakeHistoryApiClient(
        [
            make_history_response(first_page, total=999),
            make_history_response(second_page, total=999),
        ]
    )

    with pytest.raises(app_module.CatalogGuardApiResponseError):
        app_module.fetch_all_history_summary_items(api_client, {})

    assert [call["offset"] for call in api_client.calls] == [0, 100]


@pytest.mark.parametrize(
    "response",
    [
        {"items": "not-a-list", "total": 1, "limit": 100, "offset": 0},
        {"items": [], "total": "1", "limit": 100, "offset": 0},
        {"items": [make_history_item(1)], "total": 0, "limit": 100, "offset": 0},
        {"items": [], "total": 5, "limit": 100, "offset": 0},
    ],
)
def test_fetch_all_history_summary_items_rejects_invalid_response_shape(
    app_module,
    response,
):
    api_client = FakeHistoryApiClient([response])

    with pytest.raises(app_module.CatalogGuardApiResponseError):
        app_module.fetch_all_history_summary_items(api_client, {})


def test_return_history_list_state_keeps_search_query_and_offset(app_module):
    session_state = {
        "history_view_mode": "detail",
        "selected_inspection_run_id": 11,
        "history_filename_query": "products",
        "history_offset": 10,
    }

    app_module.return_history_list_state(session_state)

    assert session_state["history_view_mode"] == "list"
    assert session_state["selected_inspection_run_id"] is None
    assert session_state["history_filename_query"] == "products"
    assert session_state["history_offset"] == 10


def test_reset_history_filename_search_clears_query_and_offset(app_module):
    session_state = {
        "history_filename_input": "products",
        "history_filename_query": "products",
        "history_offset": 20,
    }

    app_module.reset_history_filename_search(session_state)

    assert session_state["history_filename_input"] == ""
    assert session_state["history_filename_query"] == ""
    assert session_state["history_offset"] == 0


def test_reset_history_search_clears_filename_dates_error_and_offset(app_module):
    session_state = {
        **make_prepared_history_summary_download_state(app_module),
        "history_filename_input": "products",
        "history_filename_query": "products",
        "history_start_date_input": date(2026, 7, 1),
        "history_end_date_input": date(2026, 7, 5),
        "history_start_date_query": date(2026, 7, 1),
        "history_end_date_query": date(2026, 7, 5),
        "history_status_input": "오류",
        "history_status_query": "error",
        "history_filter_error": "시작일은 종료일보다 늦을 수 없습니다.",
        "history_offset": 20,
    }

    app_module.reset_history_search(session_state)

    assert session_state["history_filename_input"] == ""
    assert session_state["history_filename_query"] == ""
    assert session_state["history_start_date_input"] is None
    assert session_state["history_end_date_input"] is None
    assert session_state["history_start_date_query"] is None
    assert session_state["history_end_date_query"] is None
    assert session_state["history_status_input"] == "전체"
    assert session_state["history_status_query"] is None
    assert session_state["history_filter_error"] is None
    assert session_state["history_offset"] == 0
    assert_prepared_history_summary_download_is_cleared(app_module, session_state)


def test_get_empty_history_message_distinguishes_search_result(app_module):
    assert (
        app_module.get_empty_history_message("products")
        == "입력한 파일명과 일치하는 검수 이력이 없습니다."
    )
    assert app_module.get_empty_history_message("") == "저장된 검수 이력이 없습니다."


def test_format_history_option_label_uses_run_id_filename_and_time(app_module):
    label = app_module.format_history_option_label(
        {
            "inspection_run_id": 11,
            "source_filename": "products_dev.csv",
            "created_at": "2026-07-04T13:42:39.495949+09:00",
        }
    )

    assert label == "11 · products_dev.csv · 2026-07-04 13:42:39"


def test_build_history_detail_dataframe_maps_results_without_changing_input(
    app_module,
):
    results = [
        {
            "status": "오류",
            "product_group_id": "G002",
            "product_id": "P003",
            "error_field": "상품 ID 중복",
            "reason": "동일한 상품 ID가 여러 상품에 사용되었습니다.",
            "recommendation": "각 상품에 고유한 상품 ID를 입력하십시오.",
            "risk_level": "높음",
        },
        {
            "status": "주의",
            "product_group_id": "G003",
            "product_id": "P004",
            "error_field": "품절 상품",
            "reason": "재고가 0개인 품절 상품입니다.",
            "recommendation": "판매 상태를 확인하세요.",
            "risk_level": "낮음",
        },
    ]
    original_results = copy.deepcopy(results)

    dataframe = app_module.build_history_detail_dataframe(results)

    assert list(dataframe.columns) == app_module.HISTORY_DETAIL_DISPLAY_COLUMNS
    assert len(dataframe) == 2
    assert dataframe.iloc[0].to_dict() == {
        "검수 상태": "오류",
        "오류 항목": "상품 ID 중복",
        "상품 그룹 ID": "G002",
        "상품 ID": "P003",
        "오류 이유": "동일한 상품 ID가 여러 상품에 사용되었습니다.",
        "수정 권장사항": "각 상품에 고유한 상품 ID를 입력하십시오.",
        "위험 수준": "높음",
    }
    assert dataframe.iloc[1]["검수 상태"] == "주의"
    assert results == original_results


def test_build_history_detail_dataframe_handles_empty_results(app_module):
    dataframe = app_module.build_history_detail_dataframe([])

    assert isinstance(dataframe, pd.DataFrame)
    assert dataframe.empty
    assert list(dataframe.columns) == app_module.HISTORY_DETAIL_DISPLAY_COLUMNS


def test_build_history_detail_dataframe_tolerates_missing_values(app_module):
    dataframe = app_module.build_history_detail_dataframe(
        [
            {
                "status": "오류",
                "error_field": "가격 오류",
            }
        ]
    )

    assert dataframe.iloc[0].to_dict() == {
        "검수 상태": "오류",
        "오류 항목": "가격 오류",
        "상품 그룹 ID": None,
        "상품 ID": None,
        "오류 이유": None,
        "수정 권장사항": None,
        "위험 수준": None,
    }


def test_render_inspection_statistics_displays_three_complete_statistics(
    app_module,
    monkeypatch,
):
    fake_st = FakeAppStreamlit()
    statistics = make_statistics_dataframes()
    original_product_counts = statistics["product_counts"].copy(deep=True)
    results_df = pd.DataFrame({"unused": range(6)})
    build_calls = []

    def fake_build_inspection_statistics(dataframe):
        build_calls.append(dataframe)
        return statistics

    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "build_inspection_statistics",
        fake_build_inspection_statistics,
        raising=False,
    )

    app_module.render_inspection_statistics(results_df, expected_total_issues=6)

    assert len(build_calls) == 1
    assert build_calls[0] is results_df
    assert fake_st.subheaders == ["검수 결과 통계"]
    assert fake_st.captions == [
        "아래 통계는 필터 적용 전 전체 검수 결과를 기준으로 합니다."
    ]
    assert fake_st.columns_calls == [3]
    assert [message for _, message in fake_st.markdowns] == [
        "**오류 항목별 발생 건수**",
        "**위험 수준별 발생 건수**",
        "**문제가 많은 상품 TOP 5**",
    ]
    assert len(fake_st.dataframes) == 3
    pd.testing.assert_frame_equal(
        fake_st.dataframes[0][1], statistics["issue_counts"]
    )
    pd.testing.assert_frame_equal(
        fake_st.dataframes[1][1], statistics["risk_counts"]
    )
    pd.testing.assert_frame_equal(
        fake_st.dataframes[2][1], statistics["product_counts"].head(5)
    )
    pd.testing.assert_frame_equal(
        statistics["product_counts"], original_product_counts
    )
    assert all(
        dataframe_kwargs["hide_index"] is True
        and dataframe_kwargs["width"] == "stretch"
        and dataframe_kwargs["height"] <= 420
        for _, _, dataframe_kwargs in fake_st.dataframes
    )


def test_render_inspection_statistics_limits_only_product_table_to_top_five(
    app_module,
    monkeypatch,
):
    fake_st = FakeAppStreamlit()
    statistics = make_statistics_dataframes()
    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "build_inspection_statistics",
        lambda dataframe: statistics,
        raising=False,
    )

    app_module.render_inspection_statistics(pd.DataFrame(), expected_total_issues=6)

    displayed_products = fake_st.dataframes[2][1]
    assert len(displayed_products) == 5
    assert displayed_products["상품 ID"].tolist() == [
        "P001",
        "P002",
        "P003",
        "P004",
        "P005",
    ]
    assert "P006" not in displayed_products["상품 ID"].tolist()
    assert len(statistics["product_counts"]) == 6


def test_render_inspection_statistics_handles_empty_results_without_tables(
    app_module,
    monkeypatch,
):
    fake_st = FakeAppStreamlit()
    empty_statistics = {
        "issue_counts": pd.DataFrame(columns=["오류 항목", "문제 수"]),
        "risk_counts": pd.DataFrame(columns=["위험 수준", "문제 수"]),
        "product_counts": pd.DataFrame(columns=["상품 ID", "문제 수"]),
        "total_issues": 0,
    }
    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "build_inspection_statistics",
        lambda dataframe: empty_statistics,
        raising=False,
    )

    app_module.render_inspection_statistics(
        pd.DataFrame(columns=app_module.HISTORY_DETAIL_DISPLAY_COLUMNS),
        expected_total_issues=0,
    )

    assert fake_st.subheaders == ["검수 결과 통계"]
    assert fake_st.captions == [
        "아래 통계는 필터 적용 전 전체 검수 결과를 기준으로 합니다."
    ]
    assert fake_st.infos == [
        "발견된 문제가 없어 통계로 표시할 항목이 없습니다."
    ]
    assert fake_st.columns_calls == []
    assert fake_st.dataframes == []
    assert fake_st.errors == []


def test_render_inspection_statistics_hides_value_error_details(
    app_module,
    monkeypatch,
):
    fake_st = FakeAppStreamlit()

    def raise_sensitive_error(dataframe):
        raise ValueError("SENSITIVE_FAKE_ERROR")

    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "build_inspection_statistics",
        raise_sensitive_error,
        raising=False,
    )

    app_module.render_inspection_statistics(pd.DataFrame())

    assert fake_st.errors == ["검수 결과 통계를 표시할 수 없습니다."]
    assert fake_st.columns_calls == []
    assert fake_st.dataframes == []
    visible_text = " ".join(
        [*fake_st.subheaders, *fake_st.captions, *fake_st.errors, *fake_st.infos]
    )
    assert "SENSITIVE_FAKE_ERROR" not in visible_text


def test_render_inspection_statistics_rejects_summary_detail_count_mismatch(
    app_module,
    monkeypatch,
):
    fake_st = FakeAppStreamlit()
    statistics = make_statistics_dataframes()
    statistics["total_issues"] = 5
    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "build_inspection_statistics",
        lambda dataframe: statistics,
        raising=False,
    )

    app_module.render_inspection_statistics(
        pd.DataFrame(),
        expected_total_issues=6,
    )

    assert fake_st.errors == [
        "검수 요약과 상세 결과 수가 일치하지 않아 통계를 표시할 수 없습니다."
    ]
    assert fake_st.columns_calls == []
    assert fake_st.dataframes == []
    assert str(statistics) not in " ".join(fake_st.errors)


@pytest.mark.parametrize("expected_total_issues", [6, None])
def test_render_inspection_statistics_displays_when_count_matches_or_is_not_provided(
    app_module,
    monkeypatch,
    expected_total_issues,
):
    fake_st = FakeAppStreamlit()
    statistics = make_statistics_dataframes()
    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "build_inspection_statistics",
        lambda dataframe: statistics,
        raising=False,
    )

    app_module.render_inspection_statistics(
        pd.DataFrame(),
        expected_total_issues=expected_total_issues,
    )

    assert fake_st.errors == []
    assert fake_st.columns_calls == [3]
    assert len(fake_st.dataframes) == 3


def test_render_csv_inspection_tab_passes_unfiltered_results_to_statistics(
    app_module,
    monkeypatch,
):
    uploaded_file = SimpleNamespace(
        name="products.csv",
        type="text/csv",
        getvalue=lambda: b"fake csv",
    )
    fake_st = FakeAppStreamlit(
        uploaded_file=uploaded_file,
        selectbox_values={"검수 상태": "오류", "오류 항목": "전체"},
    )
    result_df = pd.DataFrame(
        [
            {
                "검수 상태": "오류",
                "오류 항목": "가격 오류",
                "상품 그룹 ID": "G001",
                "상품 ID": "P001",
                "오류 이유": "fake reason",
                "수정 권장사항": "fake recommendation",
                "위험 수준": "높음",
            },
            {
                "검수 상태": "주의",
                "오류 항목": "품절 상품",
                "상품 그룹 ID": "G002",
                "상품 ID": "P002",
                "오류 이유": "fake reason",
                "수정 권장사항": "fake recommendation",
                "위험 수준": "낮음",
            },
        ]
    )
    inspection_report = SimpleNamespace(
        masked_preview_dataframe=pd.DataFrame({"상품 ID": ["P001", "P002"]}),
        products=[object(), object()],
        issues=[object(), object()],
        summary=SimpleNamespace(error_count=1, warning_count=1, total_issues=2),
        result_dataframe=result_df,
    )
    statistics_calls = []
    events = []
    original_filter = app_module.filter_result_dataframe

    def record_statistics(dataframe, expected_total_issues=None):
        statistics_calls.append((dataframe, expected_total_issues))
        events.append("statistics")

    def record_filter(*args, **kwargs):
        events.append("filter")
        return original_filter(*args, **kwargs)

    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "validate_and_read_uploaded_csv",
        lambda filename, file_bytes: pd.DataFrame(),
    )
    monkeypatch.setattr(
        app_module,
        "inspect_dataframe",
        lambda dataframe: inspection_report,
    )
    monkeypatch.setattr(app_module, "render_inspection_save_button", lambda **kwargs: None)
    monkeypatch.setattr(
        app_module,
        "render_inspection_statistics",
        record_statistics,
        raising=False,
    )
    monkeypatch.setattr(app_module, "filter_result_dataframe", record_filter)

    app_module.render_csv_inspection_tab()

    assert len(statistics_calls) == 1
    assert statistics_calls[0][0] is result_df
    assert statistics_calls[0][1] == 2
    assert len(fake_st.dataframes[-1][1]) == 1
    assert events == ["statistics", "filter"]


def test_render_history_detail_passes_complete_dataframe_to_statistics_before_table(
    app_module,
    monkeypatch,
):
    fake_st = FakeAppStreamlit(
        session_state=SimpleNamespace(selected_inspection_run_id=11)
    )
    detail_response = {
        "inspection_run_id": 11,
        "source_filename": "products.csv",
        "created_at": "2026-07-04T13:42:39.495949+09:00",
        "summary": {
            "total_products": 2,
            "total_issues": 2,
            "error_count": 1,
            "warning_count": 1,
        },
        "results": [
            {
                "status": "오류",
                "error_field": "가격 오류",
                "product_group_id": "G001",
                "product_id": "P001",
                "reason": "fake reason",
                "recommendation": "fake recommendation",
                "risk_level": "높음",
            },
            {
                "status": "주의",
                "error_field": "품절 상품",
                "product_group_id": "G002",
                "product_id": "P002",
                "reason": "fake reason",
                "recommendation": "fake recommendation",
                "risk_level": "낮음",
            },
        ],
    }
    api_client = SimpleNamespace(
        get_inspection_detail=lambda inspection_run_id: detail_response
    )
    statistics_calls = []

    def record_statistics(dataframe, expected_total_issues=None):
        statistics_calls.append((dataframe.copy(deep=True), expected_total_issues))
        fake_st.call_log.append(("statistics",))

    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "render_inspection_statistics",
        record_statistics,
        raising=False,
    )

    app_module.render_inspection_history_detail(api_client)

    expected_dataframe = app_module.build_history_detail_dataframe(
        detail_response["results"]
    )
    assert len(statistics_calls) == 1
    pd.testing.assert_frame_equal(statistics_calls[0][0], expected_dataframe)
    assert statistics_calls[0][1] == 2
    assert fake_st.call_log.index(("statistics",)) < fake_st.call_log.index(
        ("dataframe", None)
    )
    pd.testing.assert_frame_equal(fake_st.dataframes[0][1], expected_dataframe)
