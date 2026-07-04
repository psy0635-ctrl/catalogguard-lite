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
