import importlib
import io
import sys
from datetime import datetime

import pandas as pd
import pytest
import streamlit as st


@pytest.fixture()
def app_module(monkeypatch):
    sys.modules.pop("app", None)
    monkeypatch.setattr(st, "stop", lambda: None)
    return importlib.import_module("app")


def make_detail_dataframe(app_module):
    return pd.DataFrame(
        [
            {
                "검수 상태": "오류",
                "오류 항목": "상품 ID 중복",
                "상품 그룹 ID": "G002",
                "상품 ID": "P003",
                "오류 이유": "동일한 상품 ID가 여러 상품에 사용되었습니다.",
                "수정 권장사항": "각 상품에 고유한 상품 ID를 입력하십시오.",
                "위험 수준": "높음",
            }
        ],
        columns=app_module.HISTORY_DETAIL_DISPLAY_COLUMNS,
    )


def make_summary_item(
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


def make_history_response(items: list[dict], *, total: int) -> dict:
    return {
        "items": items,
        "total": total,
        "limit": 100,
        "offset": 0,
    }


def put_prepared_summary_download(app_module, session_state, *, total: int) -> None:
    session_state[app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY] = {
        "cache_key": app_module.build_history_summary_download_cache_key(
            session_state,
            total=total,
        ),
        "csv_bytes": b"prepared-csv",
        "file_name": "prepared.csv",
        "total": total,
    }
    session_state[app_module.HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY] = "old error"


def test_build_history_detail_csv_returns_bytes(app_module):
    csv_bytes = app_module.build_history_detail_csv(make_detail_dataframe(app_module))

    assert isinstance(csv_bytes, bytes)
    assert len(csv_bytes) > 0


def test_build_history_detail_csv_includes_utf8_bom(app_module):
    csv_bytes = app_module.build_history_detail_csv(make_detail_dataframe(app_module))

    assert csv_bytes.startswith(b"\xef\xbb\xbf")


def test_build_history_detail_csv_keeps_display_column_order(app_module):
    csv_bytes = app_module.build_history_detail_csv(make_detail_dataframe(app_module))
    csv_text = csv_bytes.decode("utf-8-sig")
    header = csv_text.splitlines()[0]

    assert header.split(",") == app_module.HISTORY_DETAIL_DISPLAY_COLUMNS


def test_build_history_detail_csv_excludes_dataframe_index(app_module):
    dataframe = make_detail_dataframe(app_module)
    dataframe.index = [99]

    csv_text = app_module.build_history_detail_csv(dataframe).decode("utf-8-sig")

    assert not csv_text.startswith(",")
    assert "99," not in csv_text


def test_build_history_detail_csv_preserves_korean_values(app_module):
    csv_text = app_module.build_history_detail_csv(
        make_detail_dataframe(app_module)
    ).decode("utf-8-sig")

    assert "상품 ID 중복" in csv_text
    assert "동일한 상품 ID가 여러 상품에 사용되었습니다." in csv_text


def test_build_history_download_filename_avoids_duplicate_csv_extension(app_module):
    filename = app_module.build_history_download_filename(3, "products_dev.csv")

    assert filename == "inspection_3_products_dev_results.csv"
    assert not filename.endswith(".csv.csv")


def test_build_history_download_filename_replaces_windows_reserved_characters(
    app_module,
):
    filename = app_module.build_history_download_filename(
        7,
        'bad/name\\with:chars*?"<>|.csv',
    )

    assert filename == "inspection_7_bad_name_with_chars_results.csv"
    assert all(character not in filename for character in '/\\:*?"<>|')


def test_build_history_download_filename_uses_safe_default_for_empty_source(
    app_module,
):
    filename = app_module.build_history_download_filename(8, "")

    assert filename == "inspection_8_inspection_results.csv"


def test_should_show_history_detail_download_is_false_for_empty_dataframe(
    app_module,
):
    dataframe = pd.DataFrame(columns=app_module.HISTORY_DETAIL_DISPLAY_COLUMNS)

    assert app_module.should_show_history_detail_download(dataframe) is False
    assert app_module.should_show_history_detail_download(
        make_detail_dataframe(app_module)
    ) is True


def test_build_history_summary_dataframe_maps_columns_and_status(app_module):
    dataframe = app_module.build_history_summary_dataframe(
        [
            make_summary_item(1, error_count=2, warning_count=1),
            make_summary_item(2, error_count=0, warning_count=3),
            make_summary_item(3, error_count=0, warning_count=0),
        ]
    )

    assert list(dataframe.columns) == app_module.HISTORY_SUMMARY_DOWNLOAD_COLUMNS
    assert dataframe["검수 상태"].tolist() == ["오류", "주의", "정상"]
    assert dataframe.iloc[0].to_dict() == {
        "실행 ID": 1,
        "파일명": "products_1.csv",
        "검수 시간": "2026-07-04 13:42:39",
        "전체 상품": 5,
        "전체 문제": 3,
        "오류": 2,
        "주의": 1,
        "검수 상태": "오류",
    }


def test_build_history_summary_csv_uses_bom_header_and_no_index(app_module):
    csv_bytes = app_module.build_history_summary_csv([make_summary_item(1)])
    csv_text = csv_bytes.decode("utf-8-sig")
    header = csv_text.splitlines()[0]

    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert header.split(",") == app_module.HISTORY_SUMMARY_DOWNLOAD_COLUMNS
    assert not csv_text.startswith(",")
    assert csv_text.splitlines()[1].split(",")[0] == "1"


def test_build_history_summary_csv_preserves_order_and_includes_over_100_rows(
    app_module,
):
    items = [make_summary_item(index) for index in range(1, 126)]

    csv_bytes = app_module.build_history_summary_csv(items)
    dataframe = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")

    assert len(dataframe) == 125
    assert dataframe["실행 ID"].tolist() == list(range(1, 126))


@pytest.mark.parametrize(
    "filename",
    ["=cmd.csv", "+cmd.csv", "-cmd.csv", "@cmd.csv"],
)
def test_build_history_summary_csv_escapes_formula_like_filename(
    app_module,
    filename,
):
    item = make_summary_item(1)
    item["source_filename"] = filename

    csv_text = app_module.build_history_summary_csv([item]).decode("utf-8-sig")

    assert f"'{filename}" in csv_text


def test_build_history_summary_csv_handles_empty_items(app_module):
    csv_text = app_module.build_history_summary_csv([]).decode("utf-8-sig")

    assert csv_text.splitlines() == [
        ",".join(app_module.HISTORY_SUMMARY_DOWNLOAD_COLUMNS)
    ]


def test_build_history_summary_download_filename_uses_timestamp(app_module):
    filename = app_module.build_history_summary_download_filename(
        datetime(2026, 7, 7, 15, 30, 0)
    )

    assert filename == "inspection_history_20260707_153000.csv"


def test_render_history_summary_download_shows_button_with_applied_query(
    app_module,
    monkeypatch,
):
    item = make_summary_item(1)
    api_client = FakeHistoryApiClient([make_history_response([item], total=1)])
    session_state = {
        "history_filename_input": "not-applied",
        "history_filename_query": "products",
        "history_status_query": "normal",
        "history_offset": 20,
    }
    captions = []
    prepare_buttons = []
    download_buttons = []
    monkeypatch.setattr(app_module.st, "caption", captions.append)
    monkeypatch.setattr(app_module.st, "info", lambda message: None)
    monkeypatch.setattr(app_module.st, "error", lambda message: None)

    def fake_button(label, *, key):
        prepare_buttons.append({"label": label, "key": key})
        return key == app_module.HISTORY_SUMMARY_DOWNLOAD_PREPARE_BUTTON_KEY

    monkeypatch.setattr(app_module.st, "button", fake_button)

    def fake_download_button(label, *, data, file_name, mime, key):
        download_buttons.append(
            {
                "label": label,
                "data": data,
                "file_name": file_name,
                "mime": mime,
                "key": key,
            }
        )

    monkeypatch.setattr(app_module.st, "download_button", fake_download_button)

    app_module.render_history_summary_download(api_client, session_state, total=1)

    assert captions == [
        "현재 검색 조건에 맞는 전체 1건을 다운로드할 수 있습니다.",
        "준비된 전체 1건을 다운로드합니다.",
    ]
    assert prepare_buttons == [
        {
            "label": "CSV 다운로드 준비",
            "key": app_module.HISTORY_SUMMARY_DOWNLOAD_PREPARE_BUTTON_KEY,
        }
    ]
    assert len(download_buttons) == 1
    assert download_buttons[0]["label"] == "전체 검수 이력 요약 CSV 다운로드"
    assert download_buttons[0]["mime"] == "text/csv"
    assert download_buttons[0]["key"] == "history_summary_download"
    assert download_buttons[0]["data"].startswith(b"\xef\xbb\xbf")
    assert download_buttons[0]["file_name"].startswith("inspection_history_")
    assert api_client.calls == [
        {
            "limit": app_module.HISTORY_SUMMARY_DOWNLOAD_LIMIT,
            "offset": 0,
            "filename": "products",
            "status": "normal",
        }
    ]
    assert session_state["history_offset"] == 20
    assert (
        session_state[app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY]["total"]
        == 1
    )


def test_render_history_summary_download_waits_for_prepare_click(
    app_module,
    monkeypatch,
):
    item = make_summary_item(1)
    api_client = FakeHistoryApiClient([make_history_response([item], total=1)])
    captions = []
    monkeypatch.setattr(app_module.st, "caption", captions.append)
    monkeypatch.setattr(app_module.st, "info", lambda message: None)
    monkeypatch.setattr(app_module.st, "error", lambda message: None)
    monkeypatch.setattr(app_module.st, "button", lambda label, *, key: False)
    monkeypatch.setattr(
        app_module.st,
        "download_button",
        lambda *args, **kwargs: pytest.fail("download button should be hidden"),
    )

    app_module.render_history_summary_download(api_client, {}, total=1)

    assert captions == ["현재 검색 조건에 맞는 전체 1건을 다운로드할 수 있습니다."]
    assert api_client.calls == []


def test_render_history_summary_download_keeps_prepared_csv_for_page_move(
    app_module,
    monkeypatch,
):
    api_client = FakeHistoryApiClient([])
    session_state = {
        "history_filename_query": "products",
        "history_status_query": "error",
        "history_offset": 0,
    }
    put_prepared_summary_download(app_module, session_state, total=120)
    session_state["history_offset"] = 100
    download_buttons = []
    monkeypatch.setattr(app_module.st, "caption", lambda message: None)
    monkeypatch.setattr(app_module.st, "info", lambda message: None)
    monkeypatch.setattr(app_module.st, "error", lambda message: None)
    monkeypatch.setattr(app_module.st, "button", lambda label, *, key: False)
    monkeypatch.setattr(
        app_module.st,
        "download_button",
        lambda *args, **kwargs: download_buttons.append(kwargs),
    )

    app_module.render_history_summary_download(api_client, session_state, total=120)

    assert len(download_buttons) == 1
    assert download_buttons[0]["data"] == b"prepared-csv"
    assert api_client.calls == []
    assert app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY in session_state
    assert app_module.HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY in session_state


def test_render_history_summary_download_keeps_prepared_csv_for_unapplied_input(
    app_module,
    monkeypatch,
):
    api_client = FakeHistoryApiClient([])
    session_state = {
        "history_filename_input": "normal-products",
        "history_filename_query": "error-products",
        "history_status_query": "error",
    }
    put_prepared_summary_download(app_module, session_state, total=10)
    session_state["history_filename_input"] = "changed-but-not-searched"
    download_buttons = []
    monkeypatch.setattr(app_module.st, "caption", lambda message: None)
    monkeypatch.setattr(app_module.st, "info", lambda message: None)
    monkeypatch.setattr(app_module.st, "error", lambda message: None)
    monkeypatch.setattr(app_module.st, "button", lambda label, *, key: False)
    monkeypatch.setattr(
        app_module.st,
        "download_button",
        lambda *args, **kwargs: download_buttons.append(kwargs),
    )

    app_module.render_history_summary_download(api_client, session_state, total=10)

    assert len(download_buttons) == 1
    assert download_buttons[0]["file_name"] == "prepared.csv"
    assert api_client.calls == []
    assert app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY in session_state
    assert app_module.HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY in session_state


def test_render_history_summary_download_hides_button_for_empty_result(
    app_module,
    monkeypatch,
):
    api_client = FakeHistoryApiClient([])
    session_state = {
        app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY: {"cache_key": "old"}
    }
    infos = []
    monkeypatch.setattr(app_module.st, "info", infos.append)
    monkeypatch.setattr(app_module.st, "caption", lambda message: None)
    monkeypatch.setattr(app_module.st, "error", lambda message: None)
    monkeypatch.setattr(
        app_module.st,
        "button",
        lambda *args, **kwargs: pytest.fail("prepare button should be hidden"),
    )
    monkeypatch.setattr(
        app_module.st,
        "download_button",
        lambda *args, **kwargs: pytest.fail("download button should be hidden"),
    )

    app_module.render_history_summary_download(api_client, session_state, total=0)

    assert infos == ["다운로드할 검수 이력이 없습니다."]
    assert api_client.calls == []
    assert app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY not in session_state


def test_render_history_summary_download_shows_error_when_later_fetch_fails(
    app_module,
    monkeypatch,
):
    first_page = [make_summary_item(index) for index in range(1, 101)]
    api_client = FakeHistoryApiClient(
        [
            make_history_response(first_page, total=150),
            app_module.CatalogGuardApiConnectionError("connection failed"),
        ]
    )
    session_state = {}
    errors = []
    monkeypatch.setattr(app_module.st, "error", errors.append)
    monkeypatch.setattr(app_module.st, "info", lambda message: None)
    monkeypatch.setattr(app_module.st, "caption", lambda message: None)
    monkeypatch.setattr(
        app_module.st,
        "button",
        lambda label, *, key: key
        == app_module.HISTORY_SUMMARY_DOWNLOAD_PREPARE_BUTTON_KEY,
    )
    monkeypatch.setattr(
        app_module.st,
        "download_button",
        lambda *args, **kwargs: pytest.fail("partial CSV should not be exposed"),
    )

    app_module.render_history_summary_download(api_client, session_state, total=150)

    assert errors == ["전체 검수 이력 CSV를 준비하는 중 서버에 연결할 수 없습니다."]
    assert [call["offset"] for call in api_client.calls] == [0, 100]
    assert app_module.HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY not in session_state
