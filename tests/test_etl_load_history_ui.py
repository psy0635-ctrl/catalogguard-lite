from datetime import datetime

import pandas as pd

from clients import catalogguard_api
from clients.catalogguard_api import ETLLoadNotFoundError
from conftest import run_authenticated_app_test
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
        "actor_username": "operator_user",
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


def make_promotion_preview(
    *,
    run_id=12,
    eligible=True,
    preview_hash=None,
    blocked_reasons=None,
):
    return {
        "etl_load_run_id": run_id,
        "supplier_key": "sample_fashion_vendor_v2",
        "inspection_version": "2026.07",
        "preview_schema_version": 1,
        "preview_hash": ("a" * 64 if preview_hash is None else preview_hash),
        "promotion_eligible": eligible,
        "blocked_reasons": blocked_reasons or [],
        "insert_count": 1,
        "update_count": 1,
        "unchanged_count": 1,
        "error_count": 0,
        "warning_count": 1,
        "items": [
            {
                "supplier_key": "sample_fashion_vendor_v2",
                "external_product_id": "SKU-NEW",
                "action": "insert",
                "changed_fields": {},
                "before_data": None,
                "after_data": {
                    "external_product_id": "SKU-NEW",
                    "product_group_id": "GROUP-NEW",
                    "product_name": "New shirt",
                    "category": "TOP",
                    "color": "WHITE",
                    "size": "M",
                    "stock": 5,
                    "price": 15900,
                    "sale_price": None,
                    "image_path": "new.jpg",
                    "description": None,
                    "seller": "supplier-a",
                },
            },
            {
                "supplier_key": "sample_fashion_vendor_v2",
                "external_product_id": "SKU-UPDATE",
                "action": "update",
                "changed_fields": {
                    "price": {"before": 19900, "after": 20900},
                    "stock": {"before": 10, "after": 8},
                },
                "before_data": {
                    "external_product_id": "SKU-UPDATE",
                    "product_group_id": "GROUP-UPDATE",
                    "product_name": "Basic shirt",
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
                    "external_product_id": "SKU-UPDATE",
                    "product_group_id": "GROUP-UPDATE",
                    "product_name": "Basic shirt",
                    "category": "TOP",
                    "color": "BLACK",
                    "size": "M",
                    "stock": 8,
                    "price": 20900,
                    "sale_price": None,
                    "image_path": "before.jpg",
                    "description": None,
                    "seller": "supplier-a",
                },
            },
            {
                "supplier_key": "sample_fashion_vendor_v2",
                "external_product_id": "SKU-SAME",
                "action": "unchanged",
                "changed_fields": {},
                "before_data": {
                    "external_product_id": "SKU-SAME",
                    "product_group_id": "GROUP-SAME",
                    "product_name": "Same shirt",
                    "category": "TOP",
                    "color": "NAVY",
                    "size": "L",
                    "stock": 4,
                    "price": 25900,
                    "sale_price": None,
                    "image_path": "same.jpg",
                    "description": None,
                    "seller": "supplier-a",
                },
                "after_data": {
                    "external_product_id": "SKU-SAME",
                    "product_group_id": "GROUP-SAME",
                    "product_name": "Same shirt",
                    "category": "TOP",
                    "color": "NAVY",
                    "size": "L",
                    "stock": 4,
                    "price": 25900,
                    "sale_price": None,
                    "image_path": "same.jpg",
                    "description": None,
                    "seller": "supplier-a",
                },
            },
        ],
    }


def make_promotion_run(run_id=31, *, status="succeeded"):
    return {
        "promotion_run_id": run_id,
        "etl_load_run_id": 12,
        "source_filename": "vendor_products.csv",
        "profile_name": "sample_fashion_vendor_v2",
        "status": status,
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


def make_promotion_audit(audit_id=41, *, promotion_run_id=31):
    return {
        "audit_id": audit_id,
        "promotion_run_id": promotion_run_id,
        "catalog_product_id": 51,
        "action": "update",
        "changed_fields": {
            "price": {"before": 19900, "after": 20900},
            "stock": {"before": 10, "after": 8},
        },
        "before_data": {"external_product_id": "SKU-UPDATE", "stock": 10},
        "after_data": {"external_product_id": "SKU-UPDATE", "stock": 8},
        "created_at": "2026-07-30T10:00:01Z",
    }


def test_initialize_catalog_promotion_state_is_safe_by_default():
    state = {}

    etl_load_history.initialize_etl_load_state(state)

    assert state["etl_load_selected_run_id"] is None
    assert state["catalog_promotion_preview_response"] is None
    assert state["catalog_promotion_preview_hash"] is None
    assert state["catalog_promotion_confirmation"] is False
    assert state["catalog_promotion_in_flight"] is False
    assert etl_load_history.can_submit_catalog_promotion(state) is False


def test_catalog_promotion_preview_state_requires_matching_batch_hash_and_confirmation():
    state = {"etl_load_selected_run_id": 12}
    etl_load_history.initialize_etl_load_state(state)

    etl_load_history.store_catalog_promotion_preview(
        state,
        make_promotion_preview(),
    )

    assert state["catalog_promotion_preview_hash"] == "a" * 64
    assert etl_load_history.can_submit_catalog_promotion(state) is False
    state["catalog_promotion_confirmation"] = True
    assert etl_load_history.can_submit_catalog_promotion(state) is True
    state["etl_load_selected_run_id"] = 13
    assert etl_load_history.can_submit_catalog_promotion(state) is False


def test_changing_batch_clears_previous_preview_confirmation_and_result():
    state = {
        "etl_load_selected_run_id": 12,
        "catalog_promotion_preview_batch_id": 12,
        "catalog_promotion_preview_response": make_promotion_preview(),
        "catalog_promotion_preview_hash": "a" * 64,
        "catalog_promotion_confirmation": True,
        "catalog_promotion_result": {"status": "succeeded"},
    }
    etl_load_history.initialize_etl_load_state(state)

    state["etl_load_selected_run_id"] = 13
    etl_load_history.synchronize_catalog_promotion_batch(state)

    assert state["catalog_promotion_preview_response"] is None
    assert state["catalog_promotion_preview_hash"] is None
    assert state["catalog_promotion_confirmation"] is False
    assert state["catalog_promotion_result"] is None


def test_new_preview_and_success_invalidate_previous_confirmation_and_hash():
    state = {"etl_load_selected_run_id": 12}
    etl_load_history.initialize_etl_load_state(state)
    state["catalog_promotion_confirmation"] = True
    state["catalog_promotion_result"] = {"status": "old"}

    etl_load_history.store_catalog_promotion_preview(
        state,
        make_promotion_preview(preview_hash="b" * 64),
    )

    assert state["catalog_promotion_confirmation"] is False
    assert state["catalog_promotion_result"] is None
    state["catalog_promotion_confirmation"] = True
    etl_load_history.store_catalog_promotion_success(
        state,
        {
            "promotion_run_id": 31,
            "etl_load_run_id": 12,
            "status": "succeeded",
            "created": True,
        },
    )
    assert state["catalog_promotion_preview_response"] is None
    assert state["catalog_promotion_preview_hash"] is None
    assert state["catalog_promotion_confirmation"] is False
    assert state["catalog_promotion_result"]["promotion_run_id"] == 31


def test_stale_preview_clears_reusable_state_but_keeps_result_kind():
    state = {"etl_load_selected_run_id": 12}
    etl_load_history.initialize_etl_load_state(state)
    etl_load_history.store_catalog_promotion_preview(
        state,
        make_promotion_preview(),
    )
    state["catalog_promotion_confirmation"] = True

    etl_load_history.store_catalog_promotion_failure(
        state,
        kind="preview_stale",
        message="미리보기를 다시 실행하세요.",
    )

    assert state["catalog_promotion_preview_response"] is None
    assert state["catalog_promotion_preview_hash"] is None
    assert state["catalog_promotion_confirmation"] is False
    assert state["catalog_promotion_result"] == {
        "kind": "preview_stale",
        "message": "미리보기를 다시 실행하세요.",
    }


def test_build_catalog_promotion_changes_dataframe_flattens_update_fields():
    dataframe = etl_load_history.build_catalog_promotion_changes_dataframe(
        make_promotion_preview()["items"]
    )

    assert list(dataframe.columns) == etl_load_history.PROMOTION_CHANGE_DISPLAY_COLUMNS
    assert set(dataframe["변경 유형"]) == {"신규 등록", "정보 수정", "변경 없음"}
    update_rows = dataframe[dataframe["외부 상품 ID"] == "SKU-UPDATE"]
    assert update_rows[["변경 필드", "변경 전 값", "변경 후 값"]].to_dict(
        orient="records"
    ) == [
        {"변경 필드": "price", "변경 전 값": 19900, "변경 후 값": 20900},
        {"변경 필드": "stock", "변경 전 값": 10, "변경 후 값": 8},
    ]


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
        "실행 사용자": "operator_user",
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
        promotion_preview_response=None,
        promotion_preview_error=None,
        promotion_response=None,
        promotion_error=None,
        list_pages=None,
        promotion_history_items=None,
        promotion_history_error=None,
        promotion_history_detail_error=None,
        promotion_audit_error=None,
        promotion_audit_pages=None,
        etl_profiles=None,
        etl_profiles_error=None,
        etl_run_response=None,
        etl_run_error=None,
    ):
        self.list_calls = []
        self.detail_calls = []
        self.rejection_calls = []
        self.promotion_preview_calls = []
        self.promotion_calls = []
        self.promotion_history_calls = []
        self.promotion_history_detail_calls = []
        self.promotion_audit_calls = []
        self.rollback_history_calls = []
        self.rollback_detail_calls = []
        self.etl_profiles_calls = []
        self.etl_run_calls = []
        self.etl_profiles = (
            [
                {"id": "sample_fashion_vendor_v1", "display_name": "패션 공급사 샘플 v1"},
                {"id": "sample_marketplace_vendor_v1", "display_name": "마켓플레이스 공급사 샘플 v1"},
            ]
            if etl_profiles is None
            else etl_profiles
        )
        self.etl_profiles_error = etl_profiles_error
        self.etl_run_response = etl_run_response or {
            "etl_load_run_id": 99,
            "created": True,
            "profile_name": "sample_fashion_vendor",
            "profile_version": "1",
            "source_filename": "vendor.csv",
            "total_rows": 2,
            "loaded_rows": 2,
            "rejected_rows": 0,
            "error_counts": {},
        }
        self.etl_run_error = etl_run_error
        self.detail_error = detail_error
        self.list_items = [make_load()] if list_items is None else list_items
        self.list_pages = list_pages
        self.list_total = (
            len(self.list_items) if list_total is None else list_total
        )
        self.product_total = product_total
        self.rejection_items = rejection_items or []
        self.rejection_total = (
            len(self.rejection_items) if rejection_total is None else rejection_total
        )
        self.reject_details_stored = reject_details_stored
        self.promotion_preview_response = (
            make_promotion_preview()
            if promotion_preview_response is None
            else promotion_preview_response
        )
        self.promotion_preview_error = promotion_preview_error
        self.promotion_response = promotion_response or {
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
        self.promotion_error = promotion_error
        self.promotion_history_items = (
            [make_promotion_run()]
            if promotion_history_items is None
            else promotion_history_items
        )
        self.promotion_history_error = promotion_history_error
        self.promotion_history_detail_error = promotion_history_detail_error
        self.promotion_audit_error = promotion_audit_error
        self.promotion_audit_pages = promotion_audit_pages

    def list_etl_profiles(self):
        self.etl_profiles_calls.append(1)
        if self.etl_profiles_error is not None:
            raise self.etl_profiles_error
        return {"items": self.etl_profiles}

    def run_etl_load(self, **params):
        self.etl_run_calls.append(params)
        if self.etl_run_error is not None:
            raise self.etl_run_error
        return self.etl_run_response

    def list_etl_loads(self, **params):
        self.list_calls.append(params)
        items = (
            self.list_pages.get(params["offset"], [])
            if self.list_pages is not None
            else self.list_items
        )
        return {
            "items": items,
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

    def get_catalog_promotion_preview(self, run_id):
        self.promotion_preview_calls.append(run_id)
        if self.promotion_preview_error is not None:
            raise self.promotion_preview_error
        return {
            **self.promotion_preview_response,
            "etl_load_run_id": run_id,
        }

    def create_catalog_promotion(
        self,
        run_id,
        *,
        confirmation,
        expected_preview_hash,
    ):
        self.promotion_calls.append(
            {
                "etl_load_run_id": run_id,
                "confirmation": confirmation,
                "expected_preview_hash": expected_preview_hash,
            }
        )
        if self.promotion_error is not None:
            raise self.promotion_error
        return {
            **self.promotion_response,
            "etl_load_run_id": run_id,
            "preview_hash": expected_preview_hash,
        }

    def list_catalog_promotions(self, **params):
        self.promotion_history_calls.append(params)
        if self.promotion_history_error is not None:
            raise self.promotion_history_error
        return {
            "items": self.promotion_history_items,
            "total": len(self.promotion_history_items),
            "limit": params["limit"],
            "offset": params["offset"],
        }

    def get_catalog_promotion_detail(self, promotion_run_id):
        self.promotion_history_detail_calls.append(promotion_run_id)
        if self.promotion_history_detail_error is not None:
            raise self.promotion_history_detail_error
        matching = next(
            (
                item
                for item in self.promotion_history_items
                if item["promotion_run_id"] == promotion_run_id
            ),
            make_promotion_run(promotion_run_id),
        )
        return {
            **matching,
            "preview_hash": "a" * 64,
            "preview_schema_version": "1",
            "inspection_version": "2026.07",
        }

    def list_catalog_promotion_audits(
        self,
        promotion_run_id,
        *,
        limit,
        offset,
    ):
        self.promotion_audit_calls.append(
            {
                "promotion_run_id": promotion_run_id,
                "limit": limit,
                "offset": offset,
            }
        )
        if self.promotion_audit_error is not None:
            raise self.promotion_audit_error
        items = (
            self.promotion_audit_pages.get(offset, [])
            if self.promotion_audit_pages is not None
            else [make_promotion_audit(promotion_run_id=promotion_run_id)]
        )
        total = (
            sum(len(page) for page in self.promotion_audit_pages.values())
            if self.promotion_audit_pages is not None
            else len(items)
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def list_catalog_promotion_rollbacks(self, **params):
        self.rollback_history_calls.append(params)
        return {
            "items": [],
            "total": 0,
            "limit": params["limit"],
            "offset": params["offset"],
        }

    def get_catalog_promotion_rollback_detail(self, rollback_run_id):
        self.rollback_detail_calls.append(rollback_run_id)
        raise catalogguard_api.CatalogPromotionRollbackNotFoundError(
            "Rollback 실행 이력을 찾을 수 없습니다."
        )


def select_etl_batch(app, run_id):
    return next(
        widget
        for widget in app.selectbox
        if widget.key == "etl_load_selected_run_id"
    ).select(run_id).run(timeout=10)


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
    monkeypatch.setattr(etl_load_history, "get_authenticated_api_client", lambda: api_client)
    monkeypatch.setattr(catalogguard_api, "create_catalogguard_api_client", lambda: api_client)

    app = run_authenticated_app_test(timeout=10)
    select_etl_batch(app, 12)
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
        "get_authenticated_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = run_authenticated_app_test(timeout=10)

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

    select_etl_batch(app, 12)
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
        "get_authenticated_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = run_authenticated_app_test(timeout=10)
    select_etl_batch(app, 12)
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
        "get_authenticated_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = run_authenticated_app_test(timeout=10)
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

    select_etl_batch(app, 12)
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
        "get_authenticated_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = run_authenticated_app_test(timeout=10)
    select_etl_batch(app, 12)
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
        "get_authenticated_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert "조건에 맞는 ETL 적재 이력이 없습니다." in [
        info.value for info in app.info
    ]


def _patch_etl_api_client(monkeypatch, api_client):
    monkeypatch.setattr(
        etl_load_history,
        "get_authenticated_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )


def test_catalog_promotion_apptest_requires_batch_selection(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert app.session_state["etl_load_selected_run_id"] is None
    assert next(
        button for button in app.button if button.key == "catalog_promotion_preview"
    ).disabled
    assert api_client.promotion_preview_calls == []
    assert any(
        "운영 상품 반영 결과를 확인할 ETL 적재 이력을 선택하세요."
        in info.value
        for info in app.info
    )


def test_catalog_promotion_apptest_preview_confirm_and_apply_once(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(
        selectbox
        for selectbox in app.selectbox
        if selectbox.key == "etl_load_selected_run_id"
    ).select(12).run(timeout=10)
    next(
        button for button in app.button if button.key == "catalog_promotion_preview"
    ).click().run(timeout=10)

    assert api_client.promotion_preview_calls == [12]
    assert app.session_state["catalog_promotion_preview_hash"] == "a" * 64
    assert any("반영 가능" in success.value for success in app.success)
    assert any(
        set(dataframe.value.columns)
        == set(etl_load_history.PROMOTION_CHANGE_DISPLAY_COLUMNS)
        for dataframe in app.dataframe
    )
    app.run(timeout=10)
    assert api_client.promotion_preview_calls == [12]
    assert api_client.promotion_calls == []

    confirmation = next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.key == "catalog_promotion_confirmation_input"
    )
    confirmation.check().run(timeout=10)
    assert api_client.promotion_calls == []
    submit_button = next(
        button for button in app.button if button.key == "catalog_promotion_submit"
    )
    assert submit_button.disabled is False
    submit_button.click().run(timeout=10)

    assert api_client.promotion_calls == [
        {
            "etl_load_run_id": 12,
            "confirmation": True,
            "expected_preview_hash": "a" * 64,
        }
    ]
    assert any(
        "운영 상품 반영이 완료되었습니다." in success.value
        for success in app.success
    )
    assert app.session_state["catalog_promotion_preview_hash"] is None
    assert app.session_state["catalog_promotion_confirmation"] is False
    app.run(timeout=10)
    assert len(api_client.promotion_calls) == 1


def test_catalog_promotion_apptest_blocked_preview_shows_reasons(monkeypatch):
    blocked_preview = make_promotion_preview(
        eligible=False,
        blocked_reasons=[
            {
                "code": "inspection_errors_present",
                "message": "상품 검사 오류가 있어 운영 반영을 진행할 수 없습니다.",
                "supplier_key": None,
                "external_product_id": None,
                "staging_product_ids": [],
            }
        ],
    )
    blocked_preview.update(
        insert_count=0,
        update_count=0,
        unchanged_count=0,
        items=[],
    )
    api_client = FakeEtlApiClient(
        promotion_preview_response=blocked_preview,
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(
        selectbox
        for selectbox in app.selectbox
        if selectbox.key == "etl_load_selected_run_id"
    ).select(12).run(timeout=10)
    next(
        button for button in app.button if button.key == "catalog_promotion_preview"
    ).click().run(timeout=10)

    assert any("반영 불가" in error.value for error in app.error)
    assert any(
        "상품 검사 오류가 있어 운영 반영을 진행할 수 없습니다." in warning.value
        for warning in app.warning
    )
    assert next(
        button for button in app.button if button.key == "catalog_promotion_submit"
    ).disabled
    assert api_client.promotion_calls == []


def test_catalog_promotion_apptest_batch_change_clears_preview(monkeypatch):
    api_client = FakeEtlApiClient(list_items=[make_load(12), make_load(13)])
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    batch_select = next(
        selectbox
        for selectbox in app.selectbox
        if selectbox.key == "etl_load_selected_run_id"
    )
    batch_select.select(12).run(timeout=10)
    next(
        button for button in app.button if button.key == "catalog_promotion_preview"
    ).click().run(timeout=10)
    assert app.session_state["catalog_promotion_preview_hash"] == "a" * 64

    next(
        selectbox
        for selectbox in app.selectbox
        if selectbox.key == "etl_load_selected_run_id"
    ).select(13).run(timeout=10)

    assert app.session_state["catalog_promotion_preview_hash"] is None
    assert app.session_state["catalog_promotion_preview_response"] is None
    assert app.session_state["catalog_promotion_confirmation"] is False


def test_catalog_promotion_apptest_page_change_invalidates_missing_batch(
    monkeypatch,
):
    api_client = FakeEtlApiClient(
        list_items=[make_load(12)],
        list_total=11,
        list_pages={
            0: [make_load(12)],
            10: [make_load(13)],
        },
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    select_etl_batch(app, 12)
    next(
        button for button in app.button if button.key == "catalog_promotion_preview"
    ).click().run(timeout=10)
    assert app.session_state["catalog_promotion_preview_hash"] == "a" * 64

    next(
        button for button in app.button if button.key == "etl_load_next"
    ).click().run(timeout=10)

    assert app.session_state["etl_load_selected_run_id"] is None
    assert app.session_state["catalog_promotion_preview_hash"] is None
    assert app.session_state["catalog_promotion_preview_response"] is None


def test_catalog_promotion_apptest_stale_clears_preview_and_prompts_retry(
    monkeypatch,
):
    from clients.catalogguard_api import CatalogPromotionPreviewStaleError

    api_client = FakeEtlApiClient(
        promotion_error=CatalogPromotionPreviewStaleError(
            "미리보기 이후 상품 데이터가 변경되었습니다.",
            code="preview_stale",
        )
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(
        selectbox
        for selectbox in app.selectbox
        if selectbox.key == "etl_load_selected_run_id"
    ).select(12).run(timeout=10)
    next(
        button for button in app.button if button.key == "catalog_promotion_preview"
    ).click().run(timeout=10)
    next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.key == "catalog_promotion_confirmation_input"
    ).check().run(timeout=10)
    next(
        button for button in app.button if button.key == "catalog_promotion_submit"
    ).click().run(timeout=10)

    assert len(api_client.promotion_calls) == 1
    assert app.session_state["catalog_promotion_preview_hash"] is None
    assert app.session_state["catalog_promotion_confirmation"] is False
    assert any("미리보기를 다시 실행" in error.value for error in app.error)


def test_etl_web_run_profile_dropdown_lists_allowlisted_profiles(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    profile_select = next(
        widget
        for widget in app.selectbox
        if widget.key == "etl_web_run_selected_profile_id"
    )
    assert profile_select.options == [
        "패션 공급사 샘플 v1",
        "마켓플레이스 공급사 샘플 v1",
    ]
    assert api_client.etl_profiles_calls == [1]


def test_etl_web_run_submit_button_disabled_without_uploaded_file(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    submit_button = next(
        widget for widget in app.button if widget.key == "etl_web_run_submit"
    )
    assert submit_button.disabled is True
    assert api_client.etl_run_calls == []


def test_etl_web_run_profile_change_does_not_call_run_etl_load(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(
        widget
        for widget in app.selectbox
        if widget.key == "etl_web_run_selected_profile_id"
    ).select("sample_marketplace_vendor_v1").run(timeout=10)

    assert api_client.etl_run_calls == []


def test_etl_web_run_profile_change_clears_stale_result_and_error(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app.session_state["etl_web_run_result"] = {"etl_load_run_id": 1, "created": True}
    app.session_state["etl_web_run_error"] = ValueError("stale")
    app.run(timeout=10)

    next(
        widget
        for widget in app.selectbox
        if widget.key == "etl_web_run_selected_profile_id"
    ).select("sample_marketplace_vendor_v1").run(timeout=10)

    assert app.session_state["etl_web_run_result"] is None
    assert app.session_state["etl_web_run_error"] is None


def test_etl_web_run_shows_error_when_profile_list_fails(monkeypatch):
    from clients.catalogguard_api import CatalogGuardApiConnectionError

    api_client = FakeEtlApiClient(
        etl_profiles_error=CatalogGuardApiConnectionError("no connection")
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert any(
        "ETL 프로필 목록을 불러오지 못했습니다." in error.value for error in app.error
    )
    assert not any(
        widget.key == "etl_web_run_selected_profile_id" for widget in app.selectbox
    )


def test_submit_etl_web_run_success_invalidates_history_cache_but_keeps_promotion_cache():
    from unittest.mock import Mock

    from ui.etl_load_history import _submit_etl_web_run

    api_client = FakeEtlApiClient()
    uploaded_file = Mock(name="vendor.csv")
    uploaded_file.name = "vendor.csv"
    uploaded_file.getvalue.return_value = b"a,b\n1,2\n"

    state = {
        "etl_load_list_response": {"items": [{"etl_load_run_id": 1}], "total": 1},
        "etl_load_initialized": True,
        "etl_load_offset": 20,
        "catalog_promotion_preview_response": {"etl_load_run_id": 1},
        "catalog_promotion_history_response": {"items": []},
    }

    class _Session(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    import streamlit as st

    session_state = _Session(state)
    original_session_state = st.session_state
    try:
        st.session_state = session_state
        _submit_etl_web_run(
            api_client,
            profile_id="sample_fashion_vendor_v1",
            uploaded_file=uploaded_file,
        )
    finally:
        st.session_state = original_session_state

    assert api_client.etl_run_calls == [
        {
            "profile_id": "sample_fashion_vendor_v1",
            "source_filename": "vendor.csv",
            "file_content": b"a,b\n1,2\n",
        }
    ]
    assert session_state["etl_load_list_response"] is None
    assert session_state["etl_load_initialized"] is False
    assert session_state["etl_load_offset"] == 0
    assert session_state["etl_web_run_result"] == api_client.etl_run_response
    assert session_state["etl_web_run_error"] is None
    # Promotion cache must be left untouched by a successful ETL web run.
    assert session_state["catalog_promotion_preview_response"] == {"etl_load_run_id": 1}
    assert session_state["catalog_promotion_history_response"] == {"items": []}


def test_submit_etl_web_run_failure_stores_error_and_leaves_history_cache_alone():
    from unittest.mock import Mock

    from clients.catalogguard_api import ETLUnsupportedProfileError
    from ui.etl_load_history import _submit_etl_web_run

    api_client = FakeEtlApiClient(
        etl_run_error=ETLUnsupportedProfileError("no", code="unsupported_profile")
    )
    uploaded_file = Mock(name="vendor.csv")
    uploaded_file.name = "vendor.csv"
    uploaded_file.getvalue.return_value = b"a,b\n1,2\n"

    state = {
        "etl_load_list_response": {"items": [], "total": 0},
        "etl_load_initialized": True,
        "etl_load_offset": 0,
    }

    import streamlit as st

    original_session_state = st.session_state
    try:
        st.session_state = state
        _submit_etl_web_run(
            api_client,
            profile_id="unknown",
            uploaded_file=uploaded_file,
        )
    finally:
        st.session_state = original_session_state

    assert state["etl_web_run_result"] is None
    assert isinstance(state["etl_web_run_error"], ETLUnsupportedProfileError)
    assert state["etl_load_list_response"] == {"items": [], "total": 0}
    assert state["etl_load_initialized"] is True
