from datetime import datetime

import pandas as pd
from streamlit.testing.v1 import AppTest

from clients import catalogguard_api
from clients.catalogguard_api import ETLLoadNotFoundError
from ui import etl_load_history

from ui.etl_load_history import (
    ETL_LOAD_DISPLAY_COLUMNS,
    ETL_PRODUCT_DISPLAY_COLUMNS,
    ETL_REJECT_DISPLAY_COLUMNS,
    build_etl_load_dataframe,
    build_etl_product_dataframe,
    build_etl_load_option_label,
    calculate_etl_pagination,
    format_etl_datetime,
    build_etl_api_error_display_message,
    build_etl_error_counts_dataframe,
    build_etl_rejection_dataframe,
    format_etl_quality_rate,
)


def make_load(run_id=12):
    return {
        "etl_load_run_id": run_id,
        "source_filename": "vendor_products.csv",
        "profile_name": "sample_fashion_vendor_v2",
        "profile_version": "1",
        "loaded_rows": 25,
        "total_rows": 30,
        "rejected_rows": 5,
        "created_at": "2026-07-25T12:00:00Z",
    }


def make_product():
    return {
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


def test_build_etl_load_dataframe_maps_contract_to_display_columns():
    dataframe = build_etl_load_dataframe([make_load()])

    assert isinstance(dataframe, pd.DataFrame)
    assert list(dataframe.columns) == ETL_LOAD_DISPLAY_COLUMNS
    assert dataframe.iloc[0].to_dict() == {
        "적재 배치 ID": 12,
        "원본 파일명": "vendor_products.csv",
        "공급사 프로필": "sample_fashion_vendor_v2",
        "프로필 버전": "1",
        "적재 상품 수": 25,
        "전체 행": 30,
        "변환 거부": 5,
        "적재 시간": "2026-07-25 12:00:00",
    }


def test_build_etl_product_dataframe_keeps_order_and_renders_nullable_values_as_blank():
    dataframe = build_etl_product_dataframe([make_product()])

    assert list(dataframe.columns) == ETL_PRODUCT_DISPLAY_COLUMNS
    assert dataframe.iloc[0]["할인가"] == ""
    assert dataframe.iloc[0]["설명"] == ""
    assert dataframe.iloc[0]["판매자"] == ""
    assert dataframe.iloc[0]["재고"] == 10
    assert dataframe.iloc[0]["정상가"] == 19900


def test_etl_pagination_uses_total_and_limit():
    assert calculate_etl_pagination(total=25, limit=10, offset=10) == (
        2,
        3,
        True,
        True,
    )


def test_etl_pagination_disables_buttons_for_empty_and_edges():
    assert calculate_etl_pagination(total=0, limit=10, offset=0) == (
        1,
        1,
        False,
        False,
    )
    assert calculate_etl_pagination(total=25, limit=10, offset=20)[2:] == (
        True,
        False,
    )


def test_etl_datetime_preserves_unparseable_value_and_formats_iso_value():
    assert format_etl_datetime("2026-07-25T12:00:00Z") == "2026-07-25 12:00:00"
    assert format_etl_datetime("not-a-date") == "not-a-date"
    assert format_etl_datetime(None) == ""
    assert format_etl_datetime(datetime(2026, 7, 25, 12)) == "2026-07-25 12:00:00"


def test_etl_quality_rate_formats_percent_and_handles_zero_or_missing_total():
    assert format_etl_quality_rate(3, 2) == "66.7%"
    assert format_etl_quality_rate(3, 3) == "100.0%"
    assert format_etl_quality_rate(0, 0) == "—"
    assert format_etl_quality_rate(None, 2) == "—"


def test_etl_error_counts_dataframe_sorts_by_count_then_code():
    dataframe = build_etl_error_counts_dataframe(
        {"Z_ERROR": 1, "A_ERROR": 2, "B_ERROR": 2}
    )

    assert dataframe.to_dict(orient="records") == [
        {"오류 코드": "A_ERROR", "발생 건수": 2},
        {"오류 코드": "B_ERROR", "발생 건수": 2},
        {"오류 코드": "Z_ERROR", "발생 건수": 1},
    ]
    assert list(build_etl_error_counts_dataframe({}).columns) == [
        "오류 코드",
        "발생 건수",
    ]


def test_build_etl_rejection_dataframe_flattens_errors_and_keeps_masked_source_values():
    dataframe = build_etl_rejection_dataframe(
        [
            {
                "rejected_row_id": 301,
                "source_row_number": 4,
                "errors": [
                    {"code": "INVALID_PRICE", "field": "price", "message": "bad price"},
                    {"code": "NEGATIVE_STOCK", "field": "stock", "message": "negative"},
                ],
                "masked_source_data": {"description": "010-****-5678"},
                "created_at": "2026-07-25T12:00:00Z",
            }
        ]
    )

    assert list(dataframe.columns) == ETL_REJECT_DISPLAY_COLUMNS
    assert dataframe.iloc[0].to_dict() == {
        "원본 행": 4,
        "오류 코드": "INVALID_PRICE, NEGATIVE_STOCK",
        "오류 필드": "price, stock",
        "오류 메시지": "bad price, negative",
    }


def test_build_etl_load_option_label_contains_identity_fields():
    label = build_etl_load_option_label(make_load())

    assert "12" in label
    assert "vendor_products.csv" in label
    assert "sample_fashion_vendor_v2" in label


def test_etl_api_error_display_message_only_exposes_valid_request_id():
    from clients.catalogguard_api import CatalogGuardApiResponseError

    request_id = "a29ae9a1c62f4152bb96f6513c323d96"
    error = CatalogGuardApiResponseError(
        "private internal error",
        request_id=request_id,
    )
    message = build_etl_api_error_display_message("조회 실패", error)

    assert message == f"조회 실패\n\n요청 ID: {request_id}"
    assert "private internal error" not in message


class FakeEtlApiClient:
    def __init__(
        self,
        *,
        detail_error=None,
        list_items=None,
        list_total=None,
        product_total=1,
        rejection_items=None,
        rejection_total=None,
        reject_details_stored=False,
    ):
        self.list_calls = []
        self.detail_calls = []
        self.rejection_calls = []
        self.detail_error = detail_error
        self.list_items = [make_load()] if list_items is None else list_items
        self.list_total = (
            len(self.list_items) if list_total is None else list_total
        )
        self.product_total = product_total
        self.rejection_items = rejection_items or []
        self.rejection_total = (
            len(self.rejection_items) if rejection_total is None else rejection_total
        )
        self.reject_details_stored = reject_details_stored

    def list_etl_loads(self, **params):
        self.list_calls.append(params)
        return {
            "items": self.list_items,
            "total": self.list_total,
            "limit": params["limit"],
            "offset": params["offset"],
        }

    def list_inspections(self, **params):
        return {
            "items": [],
            "total": 0,
            "limit": params["limit"],
            "offset": params["offset"],
        }

    def get_etl_load_detail(self, run_id, **params):
        self.detail_calls.append((run_id, params))
        if self.detail_error is not None:
            raise self.detail_error
        product = {**make_product(), "product_id": f"SKU-{run_id}"}
        return {
            **make_load(run_id),
            "input_file_sha256": "a" * 64,
            "output_file_sha256": "b" * 64,
            "error_counts": {"INVALID_PRICE": 3, "NEGATIVE_STOCK": 2},
            "reject_details_stored": self.reject_details_stored,
            "products": {
                "items": [product],
                "total": self.product_total,
                "limit": params["product_limit"],
                "offset": params["product_offset"],
            },
        }

    def list_etl_rejections(self, run_id, **params):
        self.rejection_calls.append((run_id, params))
        return {
            "available": bool(self.rejection_items),
            "items": self.rejection_items,
            "total": self.rejection_total,
            "limit": params["limit"],
            "offset": params["offset"],
        }


def test_etl_load_history_shows_rejection_rows_and_paginates(monkeypatch):
    rejection_items = [
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
    ]
    api_client = FakeEtlApiClient(
        rejection_items=rejection_items,
        rejection_total=25,
        reject_details_stored=True,
    )
    monkeypatch.setattr(etl_load_history, "create_catalogguard_api_client", lambda: api_client)
    monkeypatch.setattr(catalogguard_api, "create_catalogguard_api_client", lambda: api_client)

    app = AppTest.from_file("app.py").run(timeout=10)
    next(widget for widget in app.button if widget.label == "상세 조회").click().run(
        timeout=10
    )

    assert len(app.exception) == 0
    assert api_client.rejection_calls == [(12, {"limit": 20, "offset": 0})]
    assert any(
        set(dataframe.value.columns) == set(ETL_REJECT_DISPLAY_COLUMNS)
        for dataframe in app.dataframe
    )
    next(widget for widget in app.button if widget.key == "etl_reject_next").click().run(
        timeout=10
    )
    assert api_client.rejection_calls[-1] == (12, {"limit": 20, "offset": 20})


def test_etl_load_history_apptest_queries_once_and_shows_detail(monkeypatch):
    api_client = FakeEtlApiClient()
    monkeypatch.setattr(
        etl_load_history,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = AppTest.from_file("app.py").run(timeout=10)

    assert len(app.exception) == 0
    assert "ETL 적재 이력" in [subheader.value for subheader in app.subheader]
    assert len(api_client.list_calls) == 1
    assert api_client.list_calls[0] == {
        "limit": 10,
        "offset": 0,
    }
    assert any(
        set(dataframe.value.columns) == set(ETL_LOAD_DISPLAY_COLUMNS)
        for dataframe in app.dataframe
    )

    next(widget for widget in app.button if widget.label == "상세 조회").click().run(
        timeout=10
    )

    assert len(app.exception) == 0
    assert api_client.detail_calls == [
        (12, {"product_limit": 20, "product_offset": 0})
    ]
    assert any(
        set(dataframe.value.columns) == set(ETL_PRODUCT_DISPLAY_COLUMNS)
        for dataframe in app.dataframe
    )
    assert any("a" * 64 in code.value for code in app.code)


def test_etl_load_history_does_not_retry_failed_detail_within_one_click(
    monkeypatch,
):
    api_client = FakeEtlApiClient(
        detail_error=ETLLoadNotFoundError("missing", request_id="a" * 32)
    )
    monkeypatch.setattr(
        etl_load_history,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = AppTest.from_file("app.py").run(timeout=10)
    next(widget for widget in app.button if widget.label == "상세 조회").click().run(
        timeout=10
    )

    assert len(app.exception) == 0
    assert len(api_client.detail_calls) == 1
    assert any("요청 ID: " + "a" * 32 in error.value for error in app.error)


def test_etl_load_history_apptest_applies_filters_and_product_pagination(
    monkeypatch,
):
    api_client = FakeEtlApiClient(
        list_items=[make_load(run_id) for run_id in range(12, 22)],
        list_total=25,
        product_total=45,
    )
    monkeypatch.setattr(
        etl_load_history,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = AppTest.from_file("app.py").run(timeout=10)
    next(widget for widget in app.text_input if widget.label == "원본 파일명").set_value(
        "  vendor_products.csv  "
    ).run(timeout=10)
    next(widget for widget in app.text_input if widget.label == "공급사 프로필").set_value(
        "  sample_fashion_vendor_v2  "
    ).run(timeout=10)
    next(widget for widget in app.button if widget.label == "조회").click().run(
        timeout=10
    )

    assert api_client.list_calls[-1] == {
        "limit": 10,
        "offset": 0,
        "filename": "vendor_products.csv",
        "profile_name": "sample_fashion_vendor_v2",
    }
    next(widget for widget in app.button if widget.key == "etl_load_next").click().run(
        timeout=10
    )
    assert api_client.list_calls[-1]["offset"] == 10

    next(widget for widget in app.button if widget.key == "etl_load_show_detail").click().run(
        timeout=10
    )
    assert api_client.detail_calls[-1] == (
        12,
        {"product_limit": 20, "product_offset": 0},
    )
    next(widget for widget in app.button if widget.key == "etl_product_next").click().run(
        timeout=10
    )
    assert api_client.detail_calls[-1] == (
        12,
        {"product_limit": 20, "product_offset": 20},
    )


def test_etl_load_history_clears_previous_products_when_batch_changes(monkeypatch):
    api_client = FakeEtlApiClient(
        list_items=[make_load(12), make_load(13)],
    )
    monkeypatch.setattr(
        etl_load_history,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = AppTest.from_file("app.py").run(timeout=10)
    next(widget for widget in app.button if widget.key == "etl_load_show_detail").click().run(
        timeout=10
    )
    assert any(
        "SKU-12" in dataframe.value["상품 ID"].tolist()
        for dataframe in app.dataframe
        if "상품 ID" in dataframe.value.columns
    )

    next(widget for widget in app.selectbox if widget.label == "적재 배치 선택").select(
        13
    ).run(timeout=10)
    assert not any(
        "상품 ID" in dataframe.value.columns for dataframe in app.dataframe
    )

    next(widget for widget in app.button if widget.key == "etl_load_show_detail").click().run(
        timeout=10
    )
    assert api_client.detail_calls[-1][0] == 13
    assert any(
        "SKU-13" in dataframe.value["상품 ID"].tolist()
        for dataframe in app.dataframe
        if "상품 ID" in dataframe.value.columns
    )


def test_etl_load_history_shows_empty_result_message(monkeypatch):
    api_client = FakeEtlApiClient(list_items=[], list_total=0)
    monkeypatch.setattr(
        etl_load_history,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = AppTest.from_file("app.py").run(timeout=10)

    assert len(app.exception) == 0
    assert "조건에 맞는 ETL 적재 이력이 없습니다." in [
        info.value for info in app.info
    ]
