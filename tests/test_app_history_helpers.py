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
