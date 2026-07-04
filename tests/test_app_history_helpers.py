import copy
import importlib
import sys

import pandas as pd
import pytest
import streamlit as st


@pytest.fixture()
def app_module(monkeypatch):
    sys.modules.pop("app", None)
    monkeypatch.setattr(st, "stop", lambda: None)
    return importlib.import_module("app")


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


def test_build_history_list_request_params_includes_filename_query(app_module):
    session_state = {"history_filename_query": "products"}

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=20,
    )

    assert params == {"limit": 10, "offset": 20, "filename": "products"}


def test_build_history_list_request_params_omits_blank_filename_query(app_module):
    session_state = {"history_filename_query": "   "}

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=0,
    )

    assert params == {"limit": 10, "offset": 0}


def test_history_filename_query_is_kept_for_pagination_offsets(app_module):
    session_state = {"history_filename_query": "products"}

    params = app_module.build_history_list_request_params(
        session_state,
        limit=10,
        offset=10,
    )

    assert params["filename"] == "products"
    assert params["offset"] == 10


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
