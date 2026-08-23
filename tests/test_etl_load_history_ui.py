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
    ETL_QUALITY_OBSERVABILITY_ERROR_COLUMNS,
    ETL_QUALITY_OBSERVABILITY_NO_BATCH_MESSAGE,
    ETL_QUALITY_OBSERVABILITY_NO_ERROR_MESSAGE,
    ETL_QUALITY_OBSERVABILITY_SINGLE_BATCH_MESSAGE,
    build_etl_quality_error_code_dataframe,
    build_etl_quality_observability_notice,
    build_etl_quality_observability_profile_options,
    build_etl_quality_recent_batch_dataframe,
    resolve_etl_quality_observability_selection,
    format_etl_batch_rejection_rate,
    format_etl_quality_direction,
    format_etl_rejection_rate_delta,
    invalidate_etl_quality_observability,
)
from conftest import build_authenticated_app_test


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


def make_quality_observability_batch(
    run_id=12,
    created_at="2026-08-20T12:00:00Z",
    total_rows=100,
    rejected_rows=9,
    rejection_rate=9.0,
):
    return {
        "etl_load_run_id": run_id,
        "created_at": created_at,
        "total_rows": total_rows,
        "loaded_rows": total_rows - rejected_rows,
        "rejected_rows": rejected_rows,
        "rejection_rate": rejection_rate,
    }


def make_quality_observability(
    *,
    profile_name="sample_fashion_vendor",
    batches=None,
    error_codes=None,
):
    """Default payload: 4% -> 9% (worsened, +5.00%p) for one supplier."""
    if batches is None:
        batches = [
            make_quality_observability_batch(
                run_id=11,
                created_at="2026-08-19T12:00:00Z",
                rejected_rows=4,
                rejection_rate=4.0,
            ),
            make_quality_observability_batch(),
        ]
    latest = batches[-1] if batches else None
    previous = batches[-2] if len(batches) >= 2 else None
    if previous is None:
        delta, direction = None, "no_baseline"
    else:
        delta = round(latest["rejection_rate"] - previous["rejection_rate"], 2)
        direction = (
            "worsened" if delta > 0 else "improved" if delta < 0 else "unchanged"
        )
    return {
        "profile_name": profile_name,
        "limit": 10,
        "batch_count": len(batches),
        "latest_batch": latest,
        "previous_batch": previous,
        "rejection_rate_delta": delta,
        "direction": direction,
        "error_codes": (
            [
                {
                    "error_code": "INVALID_PRICE",
                    "total_count": 8,
                    "affected_batch_count": 2,
                },
                {
                    "error_code": "MISSING_CATEGORY",
                    "total_count": 3,
                    "affected_batch_count": 1,
                },
            ]
            if error_codes is None
            else error_codes
        ),
        "recent_batches": batches,
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


def make_activation(
    profile_id="sample_fashion_vendor_v1",
    *,
    display_name="패션 공급사 샘플",
    deployment_active_version="2",
    runtime_override_exists=False,
    runtime_active_version=None,
    available_versions=("1", "2"),
    actor_username=None,
    updated_at=None,
):
    """Build one activation payload the way the server would.

    effective/is_active는 계약대로 파생시킵니다. 테스트가 서로 어긋난 값을 만들면
    화면이 실제로는 생기지 않는 상태를 그리게 됩니다.
    """
    effective = (
        runtime_active_version if runtime_override_exists else deployment_active_version
    )
    return {
        "profile_id": profile_id,
        "display_name": display_name,
        "deployment_active_version": deployment_active_version,
        "runtime_override_exists": runtime_override_exists,
        "runtime_active_version": runtime_active_version,
        "effective_active_version": effective,
        "is_active": effective is not None,
        "available_versions": list(available_versions),
        "actor_username": actor_username,
        "updated_at": updated_at,
    }


def make_activation_event(
    event_id=1,
    *,
    profile_id="sample_fashion_vendor_v1",
    action="activate",
    deployment_active_version="2",
    runtime_active_version="2",
    actor_username="operator_user",
    created_at="2026-08-23T09:00:00Z",
):
    """Build one history item the way the server records it.

    action과 상태의 관계를 계약대로 파생시킵니다. 테스트가 어긋난 event를 만들면
    화면이 실제로는 생기지 않는 기록을 그리게 됩니다.
    """
    if action == "reset":
        override_exists = False
        runtime_version = None
        effective = deployment_active_version
    elif action == "deactivate":
        override_exists = True
        runtime_version = None
        effective = None
    else:
        override_exists = True
        runtime_version = runtime_active_version
        effective = runtime_active_version
    return {
        "event_id": event_id,
        "profile_id": profile_id,
        "action": action,
        "deployment_active_version": deployment_active_version,
        "runtime_override_exists": override_exists,
        "runtime_active_version": runtime_version,
        "effective_active_version": effective,
        "actor_username": actor_username,
        "created_at": created_at,
    }


DEFAULT_ACTIVATIONS = {
    "sample_fashion_vendor_v1": make_activation(),
    "sample_marketplace_vendor_v1": make_activation(
        "sample_marketplace_vendor_v1",
        display_name="마켓플레이스 공급사 샘플",
    ),
}


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
        admin_profiles=None,
        activation_responses=None,
        activation_error=None,
        activation_update_error=None,
        activation_reset_error=None,
        activation_reset_responses=None,
        activation_history=None,
        activation_history_error=None,
        etl_profiles_error=None,
        etl_profile_details=None,
        etl_profile_detail_error=None,
        etl_run_response=None,
        etl_run_error=None,
        unknown_size_tokens=None,
        unknown_size_token_error=None,
        quality_summary=None,
        quality_trend=None,
        quality_trend_error=None,
        observability_response=None,
        observability_error=None,
        observability_profiles=None,
        observability_profiles_error=None,
        reconciliation_response=None,
        reconciliation_error=None,
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
        self.etl_profile_detail_calls = []
        self.etl_run_calls = []
        self.unknown_size_token_calls = []
        self.quality_summary_calls = []
        self.quality_trend_calls = []
        self.observability_calls = []
        self.observability_profile_calls = 0
        self.etl_profiles = (
            [
                {"id": "sample_fashion_vendor_v1", "display_name": "패션 공급사 샘플"},
                {"id": "sample_marketplace_vendor_v1", "display_name": "마켓플레이스 공급사 샘플"},
            ]
            if etl_profiles is None
            else etl_profiles
        )
        self.etl_profiles_error = etl_profiles_error
        # 관리 화면은 include_inactive=True로 비활성 프로필까지 받습니다. 기본값은
        # 실행 목록과 같게 두고, 필요한 테스트만 다르게 지정합니다.
        self.admin_profiles = admin_profiles
        self.activation_responses = (
            DEFAULT_ACTIVATIONS if activation_responses is None else activation_responses
        )
        self.activation_error = activation_error
        self.activation_update_error = activation_update_error
        self.activation_reset_error = activation_reset_error
        # reset 응답은 override를 지운 뒤의 상태라 조회 응답과 다릅니다. 지정하지 않으면
        # 서버가 하는 것과 같은 방식(배포 기본값 복귀)으로 계산합니다.
        self.activation_reset_responses = activation_reset_responses
        self.activation_calls = []
        self.activation_update_calls = []
        self.activation_reset_calls = []
        # profile_id -> 최신순 event 목록입니다. 서버처럼 offset/limit으로 잘라
        # 돌려주므로 pagination도 실제와 같은 모양으로 검증할 수 있습니다.
        self.activation_history = activation_history or {}
        self.activation_history_error = activation_history_error
        self.activation_history_calls = []
        self.etl_profile_details = etl_profile_details or {
            "sample_fashion_vendor_v1": {
                "id": "sample_fashion_vendor_v1",
                "display_name": "패션 공급사 샘플",
                "profile_name": "sample_fashion_vendor",
                "profile_version": "2",
                "source_columns": {"vendor_sku": ["product_group_id", "product_id"]},
                "required_source_columns": ["vendor_sku"],
                "defaults": {"stock": "0"},
            },
            "sample_marketplace_vendor_v1": {
                "id": "sample_marketplace_vendor_v1",
                "display_name": "마켓플레이스 공급사 샘플",
                "profile_name": "sample_marketplace_vendor",
                "profile_version": "2",
                "source_columns": {"market_sku": ["product_group_id", "product_id"]},
                "required_source_columns": ["market_sku"],
                "defaults": {"stock": "0"},
            },
        }
        self.etl_profile_detail_error = etl_profile_detail_error
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
        self.reconciliation_response = reconciliation_response
        self.reconciliation_error = reconciliation_error
        self.reconciliation_calls = []
        self.unknown_size_tokens = (
            [{"token": "4XL", "count": 8}, {"token": "OS", "count": 3}]
            if unknown_size_tokens is None
            else unknown_size_tokens
        )
        self.unknown_size_token_error = unknown_size_token_error
        self.quality_summary = quality_summary or {
            "batch_count": 3,
            "quality_available_batch_count": 2,
            "quality_unavailable_batch_count": 0,
            "total_rows": 300,
            "loaded_rows": 280,
            "rejected_rows": 20,
            "rejection_rate": 6.67,
        }
        self.quality_trend = (
            [
                {
                    "etl_load_run_id": 12,
                    "created_at": "2026-07-25T12:00:00Z",
                    "total_rows": 30,
                    "loaded_rows": 25,
                    "rejected_rows": 5,
                    "rejection_rate": 16.67,
                }
            ]
            if quality_trend is None
            else quality_trend
        )
        self.quality_trend_error = quality_trend_error
        self.observability_response = (
            make_quality_observability()
            if observability_response is None
            else observability_response
        )
        self.observability_error = observability_error
        self.observability_profiles = (
            ["sample_fashion_vendor", "sample_marketplace_vendor"]
            if observability_profiles is None
            else observability_profiles
        )
        self.observability_profiles_error = observability_profiles_error
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

    def list_etl_profiles(self, *, include_inactive=False):
        self.etl_profiles_calls.append({"include_inactive": include_inactive})
        if self.etl_profiles_error is not None:
            raise self.etl_profiles_error
        if include_inactive and self.admin_profiles is not None:
            return {"items": self.admin_profiles}
        return {"items": self.etl_profiles}

    def get_etl_profile_activation(self, profile_id):
        self.activation_calls.append(profile_id)
        if self.activation_error is not None:
            raise self.activation_error
        return self.activation_responses[profile_id]

    def reset_etl_profile_activation(self, profile_id):
        self.activation_reset_calls.append(profile_id)
        if self.activation_reset_error is not None:
            raise self.activation_reset_error
        if self.activation_reset_responses is not None:
            return self.activation_reset_responses[profile_id]
        current = self.activation_responses[profile_id]
        return make_activation(
            profile_id,
            display_name=current["display_name"],
            deployment_active_version=current["deployment_active_version"],
            available_versions=current["available_versions"],
        )

    def list_etl_profile_activation_history(self, profile_id, *, limit=20, offset=0):
        self.activation_history_calls.append(
            {"profile_id": profile_id, "limit": limit, "offset": offset}
        )
        if self.activation_history_error is not None:
            raise self.activation_history_error
        items = self.activation_history.get(profile_id, [])
        return {
            "items": items[offset : offset + limit],
            "total": len(items),
            "limit": limit,
            "offset": offset,
        }

    def update_etl_profile_activation(self, profile_id, *, active_version):
        self.activation_update_calls.append(
            {"profile_id": profile_id, "active_version": active_version}
        )
        if self.activation_update_error is not None:
            raise self.activation_update_error
        return self.activation_responses[profile_id]

    def get_etl_profile_detail(self, profile_id):
        self.etl_profile_detail_calls.append(profile_id)
        if self.etl_profile_detail_error is not None:
            raise self.etl_profile_detail_error
        return self.etl_profile_details[profile_id]

    def run_etl_load(self, **params):
        self.etl_run_calls.append(params)
        if self.etl_run_error is not None:
            raise self.etl_run_error
        return self.etl_run_response

    def get_catalog_reconciliation(self, etl_load_run_id, *, limit=50, offset=0):
        self.reconciliation_calls.append(
            {"etl_load_run_id": etl_load_run_id, "limit": limit, "offset": offset}
        )
        if self.reconciliation_error is not None:
            raise self.reconciliation_error
        return self.reconciliation_response

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

    def list_unknown_size_tokens(self, *, limit):
        self.unknown_size_token_calls.append(limit)
        if self.unknown_size_token_error is not None:
            raise self.unknown_size_token_error
        return {"items": self.unknown_size_tokens}

    def get_etl_load_quality_summary(self, *, profile_name=None):
        self.quality_summary_calls.append(profile_name)
        return self.quality_summary

    def get_etl_load_quality_trend(self, *, profile_name=None, limit=10):
        self.quality_trend_calls.append(
            {"profile_name": profile_name, "limit": limit}
        )
        if self.quality_trend_error is not None:
            raise self.quality_trend_error
        return {"items": self.quality_trend}

    def get_etl_quality_observability_profiles(self):
        self.observability_profile_calls += 1
        if self.observability_profiles_error is not None:
            raise self.observability_profiles_error
        return {
            "items": [
                {"profile_name": profile_name}
                for profile_name in self.observability_profiles
            ]
        }

    def get_etl_quality_observability(self, *, profile_name, limit=10):
        self.observability_calls.append(
            {"profile_name": profile_name, "limit": limit}
        )
        if self.observability_error is not None:
            raise self.observability_error
        return self.observability_response

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


def test_etl_load_history_shows_quality_summary_for_applied_profile(monkeypatch):
    api_client = FakeEtlApiClient(
        quality_summary={
            "batch_count": 3,
            "quality_available_batch_count": 2,
            "quality_unavailable_batch_count": 1,
            "total_rows": 300,
            "loaded_rows": 280,
            "rejected_rows": 20,
            "rejection_rate": 6.67,
        }
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(widget for widget in app.text_input if widget.label == "공급사 프로필").set_value(
        "  sample_fashion_vendor_v2  "
    ).run(timeout=10)
    next(widget for widget in app.button if widget.label == "조회").click().run(timeout=10)

    assert len(app.exception) == 0
    assert api_client.quality_summary_calls[-1] == "sample_fashion_vendor_v2"
    assert "ETL 품질 요약" in [subheader.value for subheader in app.subheader]
    assert {metric.label for metric in app.metric} >= {
        "실행 배치",
        "품질 집계 가능 배치",
        "전체 입력",
        "정상 적재",
        "Reject",
        "Reject 비율",
    }
    assert "과거 일부 배치는 품질 요약 정보가 없어 집계에서 제외되었습니다." in [
        info.value for info in app.info
    ]


def test_etl_load_history_shows_quality_trend_for_applied_profile_without_filename(
    monkeypatch,
):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(widget for widget in app.text_input if widget.label == "원본 파일명").set_value(
        "vendor_products.csv"
    ).run(timeout=10)
    next(widget for widget in app.text_input if widget.label == "공급사 프로필").set_value(
        "  sample_fashion_vendor_v2  "
    ).run(timeout=10)
    next(widget for widget in app.button if widget.label == "조회").click().run(timeout=10)

    assert len(app.exception) == 0
    assert api_client.quality_trend_calls[-1] == {
        "profile_name": "sample_fashion_vendor_v2",
        "limit": 10,
    }
    assert "최근 ETL 품질 추이" in [subheader.value for subheader in app.subheader]
    assert app.get("vega_lite_chart")


def test_etl_load_history_shows_empty_quality_trend_message(monkeypatch):
    api_client = FakeEtlApiClient(quality_trend=[])
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert "표시할 품질 추이 데이터가 없습니다." in [info.value for info in app.info]


def test_etl_load_history_shows_quality_trend_api_error(monkeypatch):
    api_client = FakeEtlApiClient(
        quality_trend_error=catalogguard_api.CatalogGuardApiResponseError("invalid")
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert "ETL 품질 추이를 불러오지 못했습니다." in [error.value for error in app.error]


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


def test_unknown_size_token_dataframe_uses_operator_facing_columns():
    dataframe = etl_load_history.build_unknown_size_token_dataframe(
        [{"token": "4XL", "count": 8}, {"token": "OS", "count": 3}]
    )

    assert list(dataframe.columns) == etl_load_history.UNKNOWN_SIZE_TOKEN_DISPLAY_COLUMNS
    assert dataframe.to_dict("records") == [
        {"사이즈 토큰": "4XL", "개수": 8},
        {"사이즈 토큰": "OS", "개수": 3},
    ]


def test_etl_load_history_shows_unknown_size_token_report(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert api_client.unknown_size_token_calls == [20]
    assert "미판정 사이즈 토큰" in [subheader.value for subheader in app.subheader]
    assert any(
        set(dataframe.value.columns)
        == set(etl_load_history.UNKNOWN_SIZE_TOKEN_DISPLAY_COLUMNS)
        for dataframe in app.dataframe
    )


def test_etl_load_history_shows_empty_unknown_size_token_report(monkeypatch):
    api_client = FakeEtlApiClient(unknown_size_tokens=[])
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert "현재 운영 카탈로그에 미판정 사이즈 토큰이 없습니다." in [
        info.value for info in app.info
    ]


def test_unknown_size_token_report_failure_does_not_block_etl_history(monkeypatch):
    api_client = FakeEtlApiClient(
        unknown_size_token_error=catalogguard_api.CatalogGuardApiResponseError(
            "upstream failure"
        )
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert api_client.unknown_size_token_calls == [20]
    assert "ETL 적재 이력" in [subheader.value for subheader in app.subheader]
    assert any("미판정 사이즈 토큰을 불러오지 못했습니다." in error.value for error in app.error)


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
        "패션 공급사 샘플",
        "마켓플레이스 공급사 샘플",
    ]
    # 실행 selector는 반드시 활성 목록만 씁니다. 관리 화면이 같은 rerun에서
    # include_inactive=True로 한 번 더 부르는 것과 구분됩니다.
    assert {"include_inactive": False} in api_client.etl_profiles_calls
    assert api_client.etl_profiles_calls.count({"include_inactive": False}) == 1


def test_etl_web_run_shows_selected_profile_detail_before_upload(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert "선택한 ETL 프로필" in [subheader.value for subheader in app.subheader]
    assert any("패션 공급사 샘플" in markdown.value for markdown in app.markdown)
    assert any("필수 원본 컬럼" in markdown.value for markdown in app.markdown)
    assert any("기본값" in markdown.value for markdown in app.markdown)
    assert any(
        {"공급사 원본 컬럼", "CatalogGuard 컬럼"} == set(dataframe.value.columns)
        for dataframe in app.dataframe
    )
    assert any(
        {"CatalogGuard 컬럼", "기본값"} == set(dataframe.value.columns)
        for dataframe in app.dataframe
    )
    assert api_client.etl_profile_detail_calls == ["sample_fashion_vendor_v1"]


def test_etl_web_run_profile_change_replaces_detail_without_clearing_upload_state(
    monkeypatch,
):
    from ui.etl_load_history import _on_etl_web_run_profile_change

    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(
        widget
        for widget in app.selectbox
        if widget.key == "etl_web_run_selected_profile_id"
    ).select("sample_marketplace_vendor_v1").run(timeout=10)

    assert api_client.etl_profile_detail_calls == [
        "sample_fashion_vendor_v1",
        "sample_marketplace_vendor_v1",
    ]
    assert any("마켓플레이스 공급사 샘플" in markdown.value for markdown in app.markdown)
    assert not any("sample_fashion_vendor" in markdown.value for markdown in app.markdown)

    state = {
        "etl_web_run_upload_file": object(),
        "etl_web_run_result": {"etl_load_run_id": 1},
        "etl_web_run_error": ValueError("stale"),
        "etl_web_run_profile_detail_id": "sample_fashion_vendor_v1",
        "etl_web_run_profile_detail_response": {"id": "sample_fashion_vendor_v1"},
        "etl_web_run_profile_detail_error": ValueError("stale"),
    }
    upload = state["etl_web_run_upload_file"]
    _on_etl_web_run_profile_change(state)

    assert state["etl_web_run_upload_file"] is upload
    assert state["etl_web_run_profile_detail_response"] is None


def test_etl_web_run_shows_profile_detail_api_error(monkeypatch):
    api_client = FakeEtlApiClient(
        etl_profile_detail_error=catalogguard_api.CatalogGuardApiResponseError(
            "private", request_id="a" * 32
        )
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert "ETL 프로필 상세 정보를 불러오지 못했습니다.\n\n요청 ID: " + "a" * 32 in [
        error.value for error in app.error
    ]


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


RECONCILIATION_RESPONSE = {
    "etl_load_run_id": 42,
    "supplier_key": "sample_fashion_vendor",
    "total_rows": 15,
    "loaded_rows": 13,
    "rejected_rows": 2,
    "new_count": 1,
    "changed_count": 2,
    "unchanged_count": 10,
    "not_observed_in_batch_count": 1,
    "field_change_counts": {"stock": 15, "price": 3, "sale_price": 2, "category": 1},
    "items": [
        {"external_product_id": "P002", "status": "new", "changed_fields": {}},
        {
            "external_product_id": "P001",
            "status": "changed",
            "changed_fields": {
                "stock": {"before": 10, "after": 7},
                "price": {"before": 1000, "after": 900},
            },
        },
        {
            "external_product_id": "P900",
            "status": "not_observed_in_batch",
            "changed_fields": {},
        },
    ],
    "total": 14,
    "limit": 50,
    "offset": 0,
}


def test_build_catalog_reconciliation_field_dataframe_orders_by_count_then_name():
    from ui.etl_load_history import build_catalog_reconciliation_field_dataframe

    frame = build_catalog_reconciliation_field_dataframe(
        RECONCILIATION_RESPONSE["field_change_counts"]
    )

    assert list(frame.columns) == ["변경 필드", "변경 건수"]
    assert frame.to_dict("records") == [
        {"변경 필드": "stock", "변경 건수": 15},
        {"변경 필드": "price", "변경 건수": 3},
        {"변경 필드": "sale_price", "변경 건수": 2},
        {"변경 필드": "category", "변경 건수": 1},
    ]


def test_build_catalog_reconciliation_field_dataframe_handles_no_changes():
    from ui.etl_load_history import build_catalog_reconciliation_field_dataframe

    frame = build_catalog_reconciliation_field_dataframe({})

    assert list(frame.columns) == ["변경 필드", "변경 건수"]
    assert frame.empty


def test_build_catalog_reconciliation_item_dataframe_labels_status_in_korean():
    from ui.etl_load_history import build_catalog_reconciliation_item_dataframe

    frame = build_catalog_reconciliation_item_dataframe(
        RECONCILIATION_RESPONSE["items"]
    )

    assert list(frame.columns) == ["상품 ID", "상태", "변경 필드"]
    # 서버가 준 순서를 그대로 유지합니다.
    assert frame.to_dict("records") == [
        {"상품 ID": "P002", "상태": "신규", "변경 필드": "-"},
        {"상품 ID": "P001", "상태": "변경", "변경 필드": "price, stock"},
        {"상품 ID": "P900", "상태": "이번 배치 미관측", "변경 필드": "-"},
    ]


def test_catalog_reconciliation_not_observed_notice_rejects_deletion_reading():
    from ui.etl_load_history import CATALOG_RECONCILIATION_NOT_OBSERVED_NOTICE

    notice = CATALOG_RECONCILIATION_NOT_OBSERVED_NOTICE

    assert "관측되지 않은" in notice
    assert "삭제 또는 판매 종료를 의미하지 않" in notice
    assert "자동 삭제 대상으로 판단하지 않습니다" in notice


def test_reject_notice_warns_that_rejected_rows_were_never_compared():
    from ui.etl_load_history import build_catalog_reconciliation_reject_notice

    notice = build_catalog_reconciliation_reject_notice(2)

    assert notice is not None
    assert "2개 행" in notice
    assert "제외" in notice
    # 미관측에 reject 상품이 섞일 수 있다는 점이 드러나야 합니다.
    assert "이번 배치 미관측" in notice


def test_reject_notice_is_absent_when_nothing_was_rejected():
    from ui.etl_load_history import build_catalog_reconciliation_reject_notice

    assert build_catalog_reconciliation_reject_notice(0) is None


def test_reject_notice_for_a_legacy_batch_says_the_scope_is_unknown():
    from ui.etl_load_history import (
        CATALOG_RECONCILIATION_LEGACY_QUALITY_NOTICE,
        build_catalog_reconciliation_reject_notice,
    )

    notice = build_catalog_reconciliation_reject_notice(None)

    # None을 0으로 바꿔 "거부 행이 없었다"고 말하지 않습니다.
    assert notice == CATALOG_RECONCILIATION_LEGACY_QUALITY_NOTICE
    assert "확인할 수 없습니다" in notice
    assert "0개" not in notice


def test_not_observed_notice_is_independent_of_the_reject_notice():
    # reject 경고가 생겨도 삭제/판매 종료가 아니라는 기존 경고는 그대로 유지됩니다.
    from ui.etl_load_history import (
        CATALOG_RECONCILIATION_NOT_OBSERVED_NOTICE,
        build_catalog_reconciliation_reject_notice,
    )

    assert build_catalog_reconciliation_reject_notice(5) != (
        CATALOG_RECONCILIATION_NOT_OBSERVED_NOTICE
    )
    assert "자동 삭제 대상으로 판단하지 않습니다" in (
        CATALOG_RECONCILIATION_NOT_OBSERVED_NOTICE
    )


def test_fetch_catalog_reconciliation_caches_the_report_per_batch():
    from ui.etl_load_history import _fetch_catalog_reconciliation

    api_client = FakeEtlApiClient(reconciliation_response=RECONCILIATION_RESPONSE)
    state = {"etl_load_selected_run_id": 42, "catalog_reconciliation_offset": 0}

    first = _fetch_catalog_reconciliation(api_client, state)
    second = _fetch_catalog_reconciliation(api_client, state)

    assert first == RECONCILIATION_RESPONSE
    assert second == RECONCILIATION_RESPONSE
    assert api_client.reconciliation_calls == [
        {"etl_load_run_id": 42, "limit": 50, "offset": 0}
    ]
    assert state["catalog_reconciliation_batch_id"] == 42


def test_fetch_catalog_reconciliation_stores_api_errors_without_raising():
    from clients.catalogguard_api import CatalogGuardApiResponseError
    from ui.etl_load_history import _fetch_catalog_reconciliation

    error = CatalogGuardApiResponseError("boom")
    api_client = FakeEtlApiClient(reconciliation_error=error)
    state = {"etl_load_selected_run_id": 42, "catalog_reconciliation_offset": 0}

    assert _fetch_catalog_reconciliation(api_client, state) is None
    assert state["catalog_reconciliation_error"] is error
    # 오류를 캐시해 rerun마다 같은 실패 요청을 반복하지 않습니다.
    assert _fetch_catalog_reconciliation(api_client, state) is None
    assert len(api_client.reconciliation_calls) == 1


def test_synchronize_catalog_reconciliation_batch_drops_a_stale_report():
    from ui.etl_load_history import synchronize_catalog_reconciliation_batch

    state = {
        "etl_load_selected_run_id": 43,
        "catalog_reconciliation_batch_id": 42,
        "catalog_reconciliation_offset": 50,
        "catalog_reconciliation_response": RECONCILIATION_RESPONSE,
        "catalog_reconciliation_error": None,
    }

    synchronize_catalog_reconciliation_batch(state)

    assert state["catalog_reconciliation_response"] is None
    assert state["catalog_reconciliation_batch_id"] is None
    assert state["catalog_reconciliation_offset"] == 0


def test_synchronize_catalog_reconciliation_batch_keeps_a_matching_report():
    from ui.etl_load_history import synchronize_catalog_reconciliation_batch

    state = {
        "etl_load_selected_run_id": 42,
        "catalog_reconciliation_batch_id": 42,
        "catalog_reconciliation_offset": 50,
        "catalog_reconciliation_response": RECONCILIATION_RESPONSE,
        "catalog_reconciliation_error": None,
    }

    synchronize_catalog_reconciliation_batch(state)

    assert state["catalog_reconciliation_response"] == RECONCILIATION_RESPONSE
    assert state["catalog_reconciliation_offset"] == 50


def test_etl_web_run_error_message_names_the_inactive_profile_cause():
    from clients.catalogguard_api import (
        ETLProfileInactiveError,
        ETLUnsupportedProfileError,
    )
    from ui.etl_load_history import (
        ETL_INACTIVE_PROFILE_RUN_MESSAGE,
        _etl_web_run_error_message,
    )

    message = _etl_web_run_error_message(
        ETLProfileInactiveError("server text", code="inactive_profile")
    )

    assert message == ETL_INACTIVE_PROFILE_RUN_MESSAGE
    assert "비활성화" in message
    # 서버 원문을 그대로 보여 주지 않습니다.
    assert "server text" not in message
    # 없는 프로필 문구와 섞이지 않습니다.
    assert message != _etl_web_run_error_message(
        ETLUnsupportedProfileError("no", code="unsupported_profile")
    )


def test_submit_etl_web_run_inactive_profile_refreshes_the_profile_list_cache():
    from unittest.mock import Mock

    from clients.catalogguard_api import ETLProfileInactiveError
    from ui.etl_load_history import _submit_etl_web_run

    error = ETLProfileInactiveError("server text", code="inactive_profile")
    api_client = FakeEtlApiClient(etl_run_error=error)
    uploaded_file = Mock(name="vendor.csv")
    uploaded_file.name = "vendor.csv"
    uploaded_file.getvalue.return_value = b"a,b\n1,2\n"

    state = {
        # 목록을 받은 뒤 배포로 프로필이 내려간 race 상황입니다.
        "etl_web_run_profiles_response": {
            "items": [{"id": "sample_fashion_vendor_v1", "display_name": "패션"}]
        },
        "etl_web_run_profiles_error": None,
        "etl_web_run_profile_detail_id": "sample_fashion_vendor_v1",
        "etl_web_run_profile_detail_response": {"id": "sample_fashion_vendor_v1"},
        "etl_load_list_response": {"items": [], "total": 0},
        "etl_load_initialized": True,
    }

    import streamlit as st

    original_session_state = st.session_state
    try:
        st.session_state = state
        _submit_etl_web_run(
            api_client,
            profile_id="sample_fashion_vendor_v1",
            uploaded_file=uploaded_file,
        )
    finally:
        st.session_state = original_session_state

    assert state["etl_web_run_error"] is error
    assert state["etl_web_run_result"] is None
    assert state["etl_web_run_in_flight"] is False
    # 다음 rerun이 GET /api/v1/etl-profiles를 다시 호출하도록 캐시를 비웁니다.
    assert state["etl_web_run_profiles_response"] is None
    assert state["etl_web_run_profiles_error"] is None
    assert state["etl_web_run_profile_detail_id"] is None
    assert state["etl_web_run_profile_detail_response"] is None
    # 실행이 성사되지 않았으므로 ETL 이력 캐시는 건드리지 않습니다.
    assert state["etl_load_list_response"] == {"items": [], "total": 0}
    assert state["etl_load_initialized"] is True


def test_fetch_etl_profile_detail_inactive_error_refreshes_the_profile_list_cache():
    from clients.catalogguard_api import ETLProfileInactiveError
    from ui.etl_load_history import _fetch_etl_profile_detail

    error = ETLProfileInactiveError("server text", code="inactive_profile")
    api_client = FakeEtlApiClient(etl_profile_detail_error=error)
    state = {
        "etl_web_run_profiles_response": {
            "items": [{"id": "sample_fashion_vendor_v1", "display_name": "패션"}]
        },
        "etl_web_run_profiles_error": None,
    }

    detail = _fetch_etl_profile_detail(api_client, state, "sample_fashion_vendor_v1")

    assert detail is None
    # 일반 서버 오류가 아니라 비활성 상태로 구분돼야 화면이 원인을 말할 수 있습니다.
    assert state["etl_web_run_profile_detail_error"] is error
    assert state["etl_web_run_profiles_response"] is None
    assert state["etl_web_run_profiles_error"] is None
    # detail_id는 남겨 두어 같은 rerun/재조회에서 409를 반복 호출하지 않습니다.
    assert state["etl_web_run_profile_detail_id"] == "sample_fashion_vendor_v1"

    _fetch_etl_profile_detail(api_client, state, "sample_fashion_vendor_v1")

    assert api_client.etl_profile_detail_calls == ["sample_fashion_vendor_v1"]


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


# ---- ETL 품질 관찰: 순수 helper 단위 테스트 --------------------------------


def test_format_etl_quality_direction_maps_every_api_value_to_korean():
    assert format_etl_quality_direction("improved") == "개선"
    assert format_etl_quality_direction("unchanged") == "동일"
    assert format_etl_quality_direction("worsened") == "악화"
    assert format_etl_quality_direction("no_baseline") == "비교 데이터 없음"
    # API 계약에 없는 값이 들어와도 화면이 깨지지 않아야 합니다.
    assert format_etl_quality_direction("degraded") == "알 수 없음"
    assert format_etl_quality_direction(None) == "알 수 없음"


def test_format_etl_rejection_rate_delta_uses_percentage_points():
    # 4% -> 9%는 "125% 증가"가 아니라 +5.00%p입니다.
    assert format_etl_rejection_rate_delta(5.0) == "+5.00%p"
    assert format_etl_rejection_rate_delta(-2.3) == "-2.30%p"
    assert format_etl_rejection_rate_delta(0.0) == "0.00%p"


def test_format_etl_rejection_rate_delta_shows_dash_without_baseline():
    assert format_etl_rejection_rate_delta(None) == "—"
    assert format_etl_rejection_rate_delta("5.0") == "—"
    assert format_etl_rejection_rate_delta(True) == "—"


def test_format_etl_batch_rejection_rate_handles_missing_batch():
    assert format_etl_batch_rejection_rate(make_quality_observability_batch()) == "9.00%"
    assert format_etl_batch_rejection_rate(None) == "—"
    assert format_etl_batch_rejection_rate({"rejection_rate": None}) == "—"


def test_build_etl_quality_error_code_dataframe_keeps_the_api_order():
    error_codes = [
        {"error_code": "INVALID_PRICE", "total_count": 8, "affected_batch_count": 2},
        {"error_code": "AAA_TIE", "total_count": 3, "affected_batch_count": 1},
        {"error_code": "MISSING_CATEGORY", "total_count": 3, "affected_batch_count": 2},
    ]

    dataframe = build_etl_quality_error_code_dataframe(error_codes)

    assert list(dataframe.columns) == ETL_QUALITY_OBSERVABILITY_ERROR_COLUMNS
    # API가 이미 total_count DESC, error_code ASC로 보내므로 다시 정렬하지 않습니다.
    assert list(dataframe["오류 코드"]) == [
        "INVALID_PRICE",
        "AAA_TIE",
        "MISSING_CATEGORY",
    ]
    assert list(dataframe["발생 건수"]) == [8, 3, 3]
    assert list(dataframe["발생 배치 수"]) == [2, 1, 2]


def test_build_etl_quality_error_code_dataframe_returns_empty_frame():
    for empty in ([], None):
        dataframe = build_etl_quality_error_code_dataframe(empty)
        assert list(dataframe.columns) == ETL_QUALITY_OBSERVABILITY_ERROR_COLUMNS
        assert dataframe.empty


def test_build_etl_quality_recent_batch_dataframe_formats_rows():
    dataframe = build_etl_quality_recent_batch_dataframe(
        make_quality_observability()["recent_batches"]
    )

    assert list(dataframe["적재 배치 ID"]) == [11, 12]
    assert list(dataframe["Reject 비율"]) == ["4.00%", "9.00%"]
    assert list(dataframe["적재 시간"]) == [
        "2026-08-19 12:00:00",
        "2026-08-20 12:00:00",
    ]
    assert build_etl_quality_recent_batch_dataframe([]).empty


def test_build_etl_quality_observability_notice_separates_zero_and_one_batch():
    empty = make_quality_observability(batches=[])
    assert (
        build_etl_quality_observability_notice(empty)
        == ETL_QUALITY_OBSERVABILITY_NO_BATCH_MESSAGE
    )

    single = make_quality_observability(
        batches=[make_quality_observability_batch()],
        error_codes=[],
    )
    assert single["direction"] == "no_baseline"
    assert (
        build_etl_quality_observability_notice(single)
        == ETL_QUALITY_OBSERVABILITY_SINGLE_BATCH_MESSAGE
    )

    assert build_etl_quality_observability_notice(make_quality_observability()) is None
    assert build_etl_quality_observability_notice(None) is None


def test_build_etl_quality_observability_profile_options_reads_the_profile_endpoint():
    response = {
        "items": [
            {"profile_name": "sample_fashion_vendor"},
            {"profile_name": "sample_marketplace_vendor"},
        ]
    }

    # 서버가 이미 중복 제거와 정렬을 마쳤으므로 화면에서 다시 손대지 않습니다.
    assert build_etl_quality_observability_profile_options(response) == [
        "sample_fashion_vendor",
        "sample_marketplace_vendor",
    ]


def test_build_etl_quality_observability_profile_options_handles_empty_and_missing():
    assert build_etl_quality_observability_profile_options({"items": []}) == []
    assert build_etl_quality_observability_profile_options(None) == []
    assert build_etl_quality_observability_profile_options({}) == []


def test_resolve_etl_quality_observability_selection_keeps_a_still_listed_profile():
    options = ["sample_fashion_vendor", "sample_marketplace_vendor"]

    assert (
        resolve_etl_quality_observability_selection(options, "sample_marketplace_vendor")
        == "sample_marketplace_vendor"
    )


def test_resolve_etl_quality_observability_selection_clears_a_vanished_profile():
    # 사라진 공급사를 첫 항목으로 바꾸면 이전 숫자가 다른 이름 아래 남을 수 있습니다.
    assert resolve_etl_quality_observability_selection(
        ["sample_fashion_vendor"], "retired_vendor"
    ) is None
    assert resolve_etl_quality_observability_selection([], "sample_fashion_vendor") is None
    assert resolve_etl_quality_observability_selection(["a"], None) is None


def test_invalidate_etl_quality_observability_drops_the_cached_comparison():
    state = {
        "etl_quality_observability_initialized": True,
        "etl_quality_observability_response": make_quality_observability(),
        "etl_quality_observability_error": ValueError("boom"),
    }

    invalidate_etl_quality_observability(state)

    assert state == {
        "etl_quality_observability_initialized": False,
        "etl_quality_observability_response": None,
        "etl_quality_observability_error": None,
    }


# ---- ETL 품질 관찰: fetch/state 단위 테스트 --------------------------------


def test_fetch_etl_quality_observability_sends_the_exact_selected_profile():
    api_client = FakeEtlApiClient()
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)
    state["etl_quality_observability_selected_profile"] = "sample_fashion_vendor"

    response = etl_load_history._fetch_etl_quality_observability(api_client, state)

    assert api_client.observability_calls == [
        {"profile_name": "sample_fashion_vendor", "limit": 10}
    ]
    assert response["direction"] == "worsened"
    assert state["etl_quality_observability_initialized"] is True
    assert state["etl_quality_observability_error"] is None


def test_fetch_etl_quality_observability_skips_request_without_a_selection():
    api_client = FakeEtlApiClient()
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)

    assert etl_load_history._fetch_etl_quality_observability(api_client, state) is None
    # 부분 검색어가 남아 있어도 그것으로 조회하지 않습니다.
    state["etl_load_applied_profile"] = "sample"
    assert etl_load_history._fetch_etl_quality_observability(api_client, state) is None
    assert api_client.observability_calls == []


def test_fetch_etl_quality_observability_stores_api_error_without_response():
    api_client = FakeEtlApiClient(
        observability_error=catalogguard_api.CatalogGuardApiResponseError("invalid")
    )
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)
    state["etl_quality_observability_selected_profile"] = "sample_fashion_vendor"

    response = etl_load_history._fetch_etl_quality_observability(api_client, state)

    assert response is None
    assert isinstance(
        state["etl_quality_observability_error"],
        catalogguard_api.CatalogGuardApiResponseError,
    )
    # 실패한 조회를 같은 화면에서 계속 재시도하지 않습니다.
    assert etl_load_history._fetch_etl_quality_observability(api_client, state) is None
    assert len(api_client.observability_calls) == 1


def test_changing_the_supplier_clears_the_previous_supplier_response():
    api_client = FakeEtlApiClient()
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)
    state["etl_quality_observability_selected_profile"] = "sample_fashion_vendor"
    etl_load_history._fetch_etl_quality_observability(api_client, state)

    state["etl_quality_observability_selected_profile"] = "sample_marketplace_vendor"
    etl_load_history._on_etl_quality_observability_profile_change(state)

    # 공급사를 바꾼 직후에는 이전 공급사의 숫자가 화면에 남아 있으면 안 됩니다.
    assert state["etl_quality_observability_response"] is None
    api_client.observability_response = make_quality_observability(
        profile_name="sample_marketplace_vendor"
    )
    etl_load_history._fetch_etl_quality_observability(api_client, state)
    assert api_client.observability_calls == [
        {"profile_name": "sample_fashion_vendor", "limit": 10},
        {"profile_name": "sample_marketplace_vendor", "limit": 10},
    ]


# ---- ETL 품질 관찰: 화면 통합 테스트 ---------------------------------------


def _select_observability_profile(app, profile_name):
    return next(
        widget
        for widget in app.selectbox
        if widget.key == "etl_quality_observability_selected_profile"
    ).select(profile_name).run(timeout=10)


def test_etl_load_history_renders_quality_observability_section(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert "ETL 품질 관찰" in [subheader.value for subheader in app.subheader]
    # 공급사를 고르기 전에는 조회하지 않습니다.
    assert api_client.observability_calls == []
    assert any(
        widget.key == "etl_quality_observability_selected_profile"
        for widget in app.selectbox
    )


def test_etl_load_history_observability_uses_exact_profile_not_search_text(
    monkeypatch,
):
    api_client = FakeEtlApiClient(
        list_items=[make_load(12) | {"profile_name": "sample_fashion_vendor"}]
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(widget for widget in app.text_input if widget.label == "공급사 프로필").set_value(
        "sample"
    ).run(timeout=10)
    next(widget for widget in app.button if widget.label == "조회").click().run(timeout=10)
    app = _select_observability_profile(app, "sample_fashion_vendor")

    assert len(app.exception) == 0
    # 부분 검색어 "sample"이 아니라 적재 이력의 정확한 profile_name을 보냅니다.
    assert api_client.observability_calls == [
        {"profile_name": "sample_fashion_vendor", "limit": 10}
    ]
    assert "sample" not in [
        call["profile_name"] for call in api_client.observability_calls
    ]


def test_etl_load_history_shows_comparison_metrics_and_error_codes(monkeypatch):
    api_client = FakeEtlApiClient(
        list_items=[make_load(12) | {"profile_name": "sample_fashion_vendor"}]
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app = _select_observability_profile(app, "sample_fashion_vendor")

    assert len(app.exception) == 0
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["최신 Reject 비율"] == "9.00%"
    assert metrics["직전 Reject 비율"] == "4.00%"
    assert metrics["변화량"] == "+5.00%p"
    assert metrics["방향"] == "악화"
    assert "Reject 비율이 직전 배치보다 높아졌습니다." in [
        warning.value for warning in app.warning
    ]
    assert any(
        list(dataframe.value.columns) == ETL_QUALITY_OBSERVABILITY_ERROR_COLUMNS
        for dataframe in app.dataframe
    )


def test_etl_load_history_shows_improved_direction_as_success(monkeypatch):
    improved = make_quality_observability(
        batches=[
            make_quality_observability_batch(
                run_id=11,
                created_at="2026-08-19T12:00:00Z",
                rejected_rows=9,
                rejection_rate=9.0,
            ),
            make_quality_observability_batch(
                run_id=12,
                rejected_rows=4,
                rejection_rate=4.0,
            ),
        ]
    )
    api_client = FakeEtlApiClient(
        list_items=[make_load(12) | {"profile_name": "sample_fashion_vendor"}],
        observability_response=improved,
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app = _select_observability_profile(app, "sample_fashion_vendor")

    assert len(app.exception) == 0
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["변화량"] == "-5.00%p"
    assert metrics["방향"] == "개선"
    assert "Reject 비율이 직전 배치보다 낮아졌습니다." in [
        success.value for success in app.success
    ]


def test_etl_load_history_shows_single_batch_no_baseline_notice(monkeypatch):
    api_client = FakeEtlApiClient(
        list_items=[make_load(12) | {"profile_name": "sample_fashion_vendor"}],
        observability_response=make_quality_observability(
            batches=[make_quality_observability_batch()],
            error_codes=[],
        ),
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app = _select_observability_profile(app, "sample_fashion_vendor")

    assert len(app.exception) == 0
    infos = [info.value for info in app.info]
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["직전 Reject 비율"] == "—"
    assert metrics["변화량"] == "—"
    assert metrics["방향"] == "비교 데이터 없음"
    assert ETL_QUALITY_OBSERVABILITY_SINGLE_BATCH_MESSAGE in infos
    assert ETL_QUALITY_OBSERVABILITY_NO_BATCH_MESSAGE not in infos
    assert ETL_QUALITY_OBSERVABILITY_NO_ERROR_MESSAGE in infos


def test_etl_load_history_shows_zero_batch_notice_without_metrics(monkeypatch):
    api_client = FakeEtlApiClient(
        list_items=[make_load(12) | {"profile_name": "sample_fashion_vendor"}],
        observability_response=make_quality_observability(batches=[], error_codes=[]),
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app = _select_observability_profile(app, "sample_fashion_vendor")

    assert len(app.exception) == 0
    infos = [info.value for info in app.info]
    assert ETL_QUALITY_OBSERVABILITY_NO_BATCH_MESSAGE in infos
    assert ETL_QUALITY_OBSERVABILITY_SINGLE_BATCH_MESSAGE not in infos
    assert "최신 Reject 비율" not in {metric.label for metric in app.metric}


def test_etl_load_history_shows_observability_api_error(monkeypatch):
    api_client = FakeEtlApiClient(
        list_items=[make_load(12) | {"profile_name": "sample_fashion_vendor"}],
        observability_error=catalogguard_api.CatalogGuardApiResponseError("invalid"),
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app = _select_observability_profile(app, "sample_fashion_vendor")

    assert len(app.exception) == 0
    assert "ETL 품질 관찰 정보를 불러오지 못했습니다." in [
        error.value for error in app.error
    ]


def test_etl_load_history_observability_is_readable_by_viewer_and_operator(monkeypatch):
    for role in ("viewer", "operator"):
        api_client = FakeEtlApiClient(
            list_items=[make_load(12) | {"profile_name": "sample_fashion_vendor"}]
        )
        _patch_etl_api_client(monkeypatch, api_client)

        app = build_authenticated_app_test("app.py", role=role).run(timeout=10)
        app = _select_observability_profile(app, "sample_fashion_vendor")

        assert len(app.exception) == 0
        assert "ETL 품질 관찰" in [subheader.value for subheader in app.subheader]
        assert {metric.label for metric in app.metric} >= {"방향", "변화량"}
        assert api_client.observability_calls == [
            {"profile_name": "sample_fashion_vendor", "limit": 10}
        ]


# ---- ETL 품질 관찰: 공급사 목록 전용 조회 -----------------------------------


def test_fetch_observability_profiles_caches_within_one_render():
    api_client = FakeEtlApiClient()
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)

    first = etl_load_history._fetch_etl_quality_observability_profiles(
        api_client, state
    )
    second = etl_load_history._fetch_etl_quality_observability_profiles(
        api_client, state
    )

    assert first == second
    assert [item["profile_name"] for item in first["items"]] == [
        "sample_fashion_vendor",
        "sample_marketplace_vendor",
    ]
    assert api_client.observability_profile_calls == 1
    assert state["etl_quality_observability_profiles_error"] is None


def test_fetch_observability_profiles_stores_error_without_retrying():
    api_client = FakeEtlApiClient(
        observability_profiles_error=catalogguard_api.CatalogGuardApiResponseError(
            "invalid"
        )
    )
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)

    assert (
        etl_load_history._fetch_etl_quality_observability_profiles(api_client, state)
        is None
    )
    assert isinstance(
        state["etl_quality_observability_profiles_error"],
        catalogguard_api.CatalogGuardApiResponseError,
    )
    etl_load_history._fetch_etl_quality_observability_profiles(api_client, state)
    assert api_client.observability_profile_calls == 1


def test_observability_offers_a_supplier_absent_from_the_current_history_page(
    monkeypatch,
):
    # 이번 작업의 핵심: 최근 10건에 배치가 없는 공급사도 고를 수 있어야 합니다.
    api_client = FakeEtlApiClient(
        list_items=[make_load(12) | {"profile_name": "sample_fashion_vendor"}],
        observability_profiles=[
            "sample_fashion_vendor",
            "sample_marketplace_vendor",
        ],
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    selectbox = next(
        widget
        for widget in app.selectbox
        if widget.key == "etl_quality_observability_selected_profile"
    )

    assert len(app.exception) == 0
    assert api_client.observability_profile_calls >= 1
    # ETL 이력 페이지에는 sample_fashion_vendor 배치만 있습니다.
    assert [item["profile_name"] for item in api_client.list_items] == [
        "sample_fashion_vendor"
    ]
    assert "sample_marketplace_vendor" in selectbox.options

    app = _select_observability_profile(app, "sample_marketplace_vendor")
    assert len(app.exception) == 0
    assert api_client.observability_calls == [
        {"profile_name": "sample_marketplace_vendor", "limit": 10}
    ]


def test_observability_profile_list_ignores_the_etl_history_search_text(monkeypatch):
    api_client = FakeEtlApiClient(
        observability_profiles=["sample_fashion_vendor", "sample_marketplace_vendor"]
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    next(widget for widget in app.text_input if widget.label == "공급사 프로필").set_value(
        "sample"
    ).run(timeout=10)
    next(widget for widget in app.button if widget.label == "조회").click().run(timeout=10)
    app = _select_observability_profile(app, "sample_marketplace_vendor")

    assert len(app.exception) == 0
    # 부분 검색어 "sample"은 비교 조회로 흘러가지 않습니다.
    assert api_client.observability_calls == [
        {"profile_name": "sample_marketplace_vendor", "limit": 10}
    ]
    assert app.session_state["etl_load_applied_profile"] == "sample"


def test_observability_shows_no_quality_data_notice_and_skips_detail_call(monkeypatch):
    api_client = FakeEtlApiClient(observability_profiles=[])
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert etl_load_history.ETL_QUALITY_OBSERVABILITY_NO_PROFILE_MESSAGE in [
        info.value for info in app.info
    ]
    # 고를 공급사가 없으면 비교 조회를 보내지 않습니다.
    assert api_client.observability_calls == []
    assert not any(
        widget.key == "etl_quality_observability_selected_profile"
        for widget in app.selectbox
    )


def test_observability_shows_profile_list_error_without_detail_call(monkeypatch):
    api_client = FakeEtlApiClient(
        observability_profiles_error=catalogguard_api.CatalogGuardApiResponseError(
            "invalid"
        )
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert etl_load_history.ETL_QUALITY_OBSERVABILITY_PROFILE_ERROR_MESSAGE in [
        error.value for error in app.error
    ]
    assert api_client.observability_calls == []


def test_observability_keeps_a_selection_that_is_still_listed(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app = _select_observability_profile(app, "sample_marketplace_vendor")
    app = app.run(timeout=10)

    assert len(app.exception) == 0
    assert (
        app.session_state["etl_quality_observability_selected_profile"]
        == "sample_marketplace_vendor"
    )
    # 다시 그려도 같은 공급사 결과를 캐시에서 씁니다.
    assert api_client.observability_calls == [
        {"profile_name": "sample_marketplace_vendor", "limit": 10}
    ]


def test_observability_clears_a_selection_that_left_the_profile_list(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app = _select_observability_profile(app, "sample_marketplace_vendor")
    assert app.session_state["etl_quality_observability_response"] is not None

    # 그 공급사가 더 이상 목록에 없는 상태로 다시 그립니다.
    api_client.observability_profiles = ["sample_fashion_vendor"]
    app.session_state["etl_quality_observability_profiles_initialized"] = False
    app = app.run(timeout=10)

    assert len(app.exception) == 0
    assert app.session_state["etl_quality_observability_selected_profile"] is None
    # 이전 공급사의 숫자가 남아 다른 이름 아래 보이면 안 됩니다.
    assert app.session_state["etl_quality_observability_response"] is None
    assert etl_load_history.ETL_QUALITY_OBSERVABILITY_SELECT_PROFILE_MESSAGE in [
        info.value for info in app.info
    ]


def test_observability_invalidates_detail_cache_when_supplier_changes(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app = _select_observability_profile(app, "sample_fashion_vendor")
    app = _select_observability_profile(app, "sample_marketplace_vendor")

    assert len(app.exception) == 0
    assert api_client.observability_calls == [
        {"profile_name": "sample_fashion_vendor", "limit": 10},
        {"profile_name": "sample_marketplace_vendor", "limit": 10},
    ]


def test_observability_profile_list_works_for_viewer_and_operator(monkeypatch):
    for role in ("viewer", "operator"):
        api_client = FakeEtlApiClient()
        _patch_etl_api_client(monkeypatch, api_client)

        app = build_authenticated_app_test("app.py", role=role).run(timeout=10)
        app = _select_observability_profile(app, "sample_marketplace_vendor")

        assert len(app.exception) == 0
        assert api_client.observability_profile_calls >= 1
        assert api_client.observability_calls == [
            {"profile_name": "sample_marketplace_vendor", "limit": 10}
        ]


# ---- Phase 5B.2: ETL 프로필 운영 관리 화면 -----------------------------------


INACTIVE_ACTIVATION = make_activation(
    "sample_marketplace_vendor_v1",
    display_name="마켓플레이스 공급사 샘플",
    runtime_override_exists=True,
    runtime_active_version=None,
)
OVERRIDE_ACTIVATION = make_activation(
    runtime_override_exists=True,
    runtime_active_version="1",
    actor_username="operator_user",
    updated_at="2026-08-22T04:00:00Z",
)


def _admin_client(**overrides):
    """Fake client whose management list keeps a deactivated profile selectable."""
    defaults = {
        "etl_profiles": [
            {"id": "sample_fashion_vendor_v1", "display_name": "패션 공급사 샘플"},
        ],
        "admin_profiles": [
            {"id": "sample_fashion_vendor_v1", "display_name": "패션 공급사 샘플"},
            {
                "id": "sample_marketplace_vendor_v1",
                "display_name": "마켓플레이스 공급사 샘플",
            },
        ],
    }
    defaults.update(overrides)
    return FakeEtlApiClient(**defaults)


def _admin_selectbox(app, key):
    return next((widget for widget in app.selectbox if widget.key == key), None)


def _admin_button(app, key):
    return next((widget for widget in app.button if widget.key == key), None)


def _body_text(app) -> str:
    parts = []
    for elements in (app.markdown, app.caption, app.info, app.warning):
        parts.extend(str(getattr(element, "value", "")) for element in elements)
    return " ".join(parts)


# --- 세 상태 표현 ---


def test_management_shows_deployment_default_state_without_an_override(monkeypatch):
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    body = _body_text(app)
    assert etl_load_history.ETL_PROFILE_ADMIN_RUNTIME_NO_OVERRIDE in body
    # override가 없으면 actor 정보를 억지로 보여 주지 않습니다.
    assert etl_load_history.ETL_PROFILE_ADMIN_ACTOR_CAPTION not in body


def test_management_distinguishes_no_override_from_explicit_inactive():
    """이 둘을 같은 문구로 보이면 배포 기본값을 자기가 내린 것으로 착각합니다."""
    no_override = etl_load_history.format_etl_profile_admin_runtime_state(
        make_activation()
    )
    inactive = etl_load_history.format_etl_profile_admin_runtime_state(
        INACTIVE_ACTIVATION
    )
    explicit_active = etl_load_history.format_etl_profile_admin_runtime_state(
        OVERRIDE_ACTIVATION
    )

    assert no_override == etl_load_history.ETL_PROFILE_ADMIN_RUNTIME_NO_OVERRIDE
    assert inactive == etl_load_history.ETL_PROFILE_ADMIN_RUNTIME_INACTIVE
    assert explicit_active == "런타임에서 v1 활성으로 지정"
    assert len({no_override, inactive, explicit_active}) == 3


def test_management_shows_actor_only_when_a_runtime_override_exists(monkeypatch):
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    body = _body_text(app)
    assert "operator_user" in body
    assert etl_load_history.ETL_PROFILE_ADMIN_ACTOR_CAPTION in body


def test_management_says_there_is_nothing_to_reset_without_an_override(monkeypatch):
    """지울 것이 없는데 버튼을 보여 주면 "무언가 남아 있다"고 잘못 말합니다."""
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert (
        etl_load_history.ETL_PROFILE_ADMIN_NO_OVERRIDE_RESET_CAPTION in _body_text(app)
    )
    assert _admin_button(app, "etl_profile_admin_reset") is None


# --- 목록 분리 ---


def test_management_list_keeps_a_deactivated_profile_selectable(monkeypatch):
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    admin_select = _admin_selectbox(app, "etl_profile_admin_selected_profile_id")
    run_select = _admin_selectbox(app, "etl_web_run_selected_profile_id")
    # 관리 목록에는 비활성 프로필이 남고, 실행 selector에서는 사라집니다.
    assert admin_select.options == ["패션 공급사 샘플", "마켓플레이스 공급사 샘플"]
    assert run_select.options == ["패션 공급사 샘플"]


def test_management_and_run_selectors_use_separate_state_keys(monkeypatch):
    """관리 화면 조작이 실행할 프로필 선택을 바꾸면 안 됩니다."""
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert app.session_state["etl_web_run_selected_profile_id"] == (
        "sample_fashion_vendor_v1"
    )
    app.session_state["etl_profile_admin_selected_profile_id"] = (
        "sample_marketplace_vendor_v1"
    )
    app.run(timeout=10)

    assert app.session_state["etl_web_run_selected_profile_id"] == (
        "sample_fashion_vendor_v1"
    )


def test_management_requests_the_inactive_inclusive_list(monkeypatch):
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    run_authenticated_app_test(timeout=10)

    assert {"include_inactive": True} in api_client.etl_profiles_calls
    assert {"include_inactive": False} in api_client.etl_profiles_calls


# --- RBAC ---


def test_operator_sees_the_activation_write_controls(monkeypatch):
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(role="operator", timeout=10)

    assert _admin_selectbox(app, "etl_profile_admin_selected_version") is not None
    assert _admin_button(app, "etl_profile_admin_activate") is not None
    assert _admin_button(app, "etl_profile_admin_deactivate") is not None


def test_viewer_reads_the_state_but_gets_no_write_controls(monkeypatch):
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(role="viewer", timeout=10)

    # 상태와 사용 가능한 버전은 볼 수 있습니다.
    body = _body_text(app)
    assert "사용 가능한 버전" in body
    # 쓰기 control은 노출하지 않습니다.
    assert _admin_selectbox(app, "etl_profile_admin_selected_version") is None
    assert _admin_button(app, "etl_profile_admin_activate") is None
    assert _admin_button(app, "etl_profile_admin_deactivate") is None


# --- 활성화 ---


def test_available_versions_come_from_the_activation_response(monkeypatch):
    """UI가 버전을 하드코딩하지 않습니다."""
    api_client = _admin_client(
        activation_responses={
            "sample_fashion_vendor_v1": make_activation(
                available_versions=("1", "2", "7")
            )
        }
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    version_select = _admin_selectbox(app, "etl_profile_admin_selected_version")
    assert version_select.options == ["v1", "v2", "v7"]


def test_activating_sends_the_selected_version(monkeypatch):
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app.session_state["etl_profile_admin_selected_version"] = "1"
    app.run(timeout=10)
    _admin_button(app, "etl_profile_admin_activate").click().run(timeout=10)

    assert api_client.activation_update_calls == [
        {"profile_id": "sample_fashion_vendor_v1", "active_version": "1"}
    ]


def test_activating_an_inactive_profile_is_possible(monkeypatch):
    """한 번 내린 프로필을 관리 화면에서 다시 올릴 수 있어야 합니다."""
    api_client = _admin_client(
        activation_responses={
            "sample_fashion_vendor_v1": make_activation(),
            "sample_marketplace_vendor_v1": INACTIVE_ACTIVATION,
        }
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app.session_state["etl_profile_admin_selected_profile_id"] = (
        "sample_marketplace_vendor_v1"
    )
    app.run(timeout=10)
    app.session_state["etl_profile_admin_selected_version"] = "2"
    app.run(timeout=10)
    _admin_button(app, "etl_profile_admin_activate").click().run(timeout=10)

    assert api_client.activation_update_calls == [
        {"profile_id": "sample_marketplace_vendor_v1", "active_version": "2"}
    ]


def test_deactivate_button_is_hidden_for_an_already_inactive_profile(monkeypatch):
    api_client = _admin_client(
        activation_responses={
            "sample_fashion_vendor_v1": make_activation(),
            "sample_marketplace_vendor_v1": INACTIVE_ACTIVATION,
        }
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app.session_state["etl_profile_admin_selected_profile_id"] = (
        "sample_marketplace_vendor_v1"
    )
    app.run(timeout=10)

    assert _admin_button(app, "etl_profile_admin_deactivate") is None
    # 대신 다시 활성화는 가능해야 합니다.
    assert _admin_button(app, "etl_profile_admin_activate") is not None


# --- 활성화 버튼 활성 조건 (deployment default vs explicit override) ---


def test_activate_stays_available_when_only_the_deployment_default_matches():
    """override가 없으면 같은 버전이라도 의미가 다른 조작입니다.

    누르면 배포 기본값을 따르던 상태가 그 버전으로 고정되어, 나중에 배포 기본값이
    바뀌어도 따라가지 않습니다.
    """
    can_activate, note = etl_load_history.build_etl_profile_admin_activate_state(
        make_activation(deployment_active_version="2"),
        "2",
    )

    assert can_activate is True
    assert "명시적으로 고정" in note


def test_activate_is_blocked_only_for_a_real_no_op():
    can_activate, note = etl_load_history.build_etl_profile_admin_activate_state(
        OVERRIDE_ACTIVATION,
        "1",
    )

    assert can_activate is False
    assert "이미 런타임에서 적용 중" in note


def test_activate_is_available_for_a_different_version_than_the_override():
    can_activate, _ = etl_load_history.build_etl_profile_admin_activate_state(
        OVERRIDE_ACTIVATION,
        "2",
    )

    assert can_activate is True


def test_activate_is_available_for_an_inactive_profile():
    can_activate, _ = etl_load_history.build_etl_profile_admin_activate_state(
        INACTIVE_ACTIVATION,
        "2",
    )

    assert can_activate is True


# --- 비활성화 확인 절차 ---


def test_deactivate_needs_an_explicit_confirmation(monkeypatch):
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    deactivate = _admin_button(app, "etl_profile_admin_deactivate")
    assert deactivate.disabled is True

    deactivate.click().run(timeout=10)
    assert api_client.activation_update_calls == []


def test_deactivate_sends_null_after_confirmation(monkeypatch):
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    confirmation = next(
        widget
        for widget in app.checkbox
        if widget.key == "etl_profile_admin_deactivate_confirmed"
    )
    confirmation.check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_deactivate").click().run(timeout=10)

    assert api_client.activation_update_calls == [
        {"profile_id": "sample_fashion_vendor_v1", "active_version": None}
    ]


# --- 성공 후 캐시 / 오류 처리 ---


def test_successful_update_invalidates_the_run_selector_cache():
    api_client = _admin_client()
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)
    state["etl_web_run_profiles_response"] = {"items": [{"id": "x", "display_name": "x"}]}
    state["etl_profile_admin_profiles_response"] = {"items": []}
    state["etl_web_run_profile_detail_response"] = {"id": "x"}

    applied = etl_load_history._apply_etl_profile_activation(
        api_client,
        state,
        "sample_fashion_vendor_v1",
        None,
    )

    assert applied is True
    # 실행 selector가 방금 내린 프로필을 계속 보여 주지 않도록 캐시를 비웁니다.
    assert state["etl_web_run_profiles_response"] is None
    assert state["etl_profile_admin_profiles_response"] is None
    assert state["etl_web_run_profile_detail_response"] is None
    assert state["etl_profile_admin_update_error"] is None
    assert state["etl_profile_admin_update_success"]


def test_failed_update_does_not_report_success():
    """서버가 거절했는데 화면만 바뀌면 내리지 않은 프로필을 내렸다고 믿게 됩니다."""
    api_client = _admin_client(
        activation_update_error=catalogguard_api.CatalogGuardApiResponseError("boom")
    )
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)
    state["etl_web_run_profiles_response"] = {"items": [{"id": "x", "display_name": "x"}]}

    applied = etl_load_history._apply_etl_profile_activation(
        api_client,
        state,
        "sample_fashion_vendor_v1",
        None,
    )

    assert applied is False
    assert state["etl_profile_admin_update_success"] is None
    assert state["etl_profile_admin_update_error"] is not None
    # 실패했으므로 실행 목록 캐시는 그대로 둡니다.
    assert state["etl_web_run_profiles_response"] is not None


def test_stale_version_error_is_shown_with_a_refresh_hint(monkeypatch):
    api_client = _admin_client(
        activation_update_error=catalogguard_api.ETLProfileActivationVersionError(
            catalogguard_api.UNKNOWN_PROFILE_VERSION_MESSAGE,
            code="unknown_profile_version",
            available_versions=("1", "2"),
        )
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    confirmation = next(
        widget
        for widget in app.checkbox
        if widget.key == "etl_profile_admin_deactivate_confirmed"
    )
    confirmation.check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_deactivate").click().run(timeout=10)

    assert any("새로고침" in str(element.value) for element in app.error)


def test_management_section_renders_without_a_rerun_loop(monkeypatch):
    """렌더링 도중 rerun을 걸면 같은 상태로 다시 들어와 무한 rerun이 됩니다."""
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert not app.exception
    # 프로필당 한 번씩만 조회하고 반복 호출하지 않습니다.
    assert api_client.activation_calls == ["sample_fashion_vendor_v1"]


def test_activation_error_is_surfaced_without_write_controls(monkeypatch):
    api_client = _admin_client(
        activation_error=catalogguard_api.CatalogGuardApiResponseError("boom")
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert any("활성화 상태를 불러오지 못했습니다" in str(e.value) for e in app.error)
    assert _admin_button(app, "etl_profile_admin_activate") is None


# ---- Phase 5B.3: 런타임 설정 초기화 (배포 기본값으로 되돌리기) ----------------


INACTIVE_DEPLOYMENT_ACTIVATION = make_activation(
    "sample_fashion_vendor_v1",
    deployment_active_version=None,
    runtime_override_exists=True,
    runtime_active_version="1",
)


def _reset_confirmation(app):
    return next(
        widget
        for widget in app.checkbox
        if widget.key == "etl_profile_admin_reset_confirmed"
    )


def _select_marketplace_profile(app):
    app.session_state["etl_profile_admin_selected_profile_id"] = (
        "sample_marketplace_vendor_v1"
    )
    app.run(timeout=10)
    return app


# --- 표시 조건 ---


def test_reset_control_appears_only_when_a_runtime_override_exists(monkeypatch):
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert _admin_button(app, "etl_profile_admin_reset") is not None
    assert (
        etl_load_history.ETL_PROFILE_ADMIN_NO_OVERRIDE_RESET_CAPTION
        not in _body_text(app)
    )


def test_viewer_gets_no_reset_control(monkeypatch):
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(role="viewer", timeout=10)

    assert _admin_button(app, "etl_profile_admin_reset") is None


# --- 결과 미리보기: reset은 되살릴 수 있다 ---


def test_reset_preview_names_the_version_that_will_apply():
    preview = etl_load_history.build_etl_profile_admin_reset_preview(
        OVERRIDE_ACTIVATION
    )

    assert "v2" in preview


def test_reset_preview_warns_that_an_inactive_profile_comes_back():
    """이 경고가 없으면 운영자가 정리라고 생각하고 프로필을 되살립니다."""
    preview = etl_load_history.build_etl_profile_admin_reset_preview(
        INACTIVE_ACTIVATION
    )

    assert "v2" in preview
    assert "다시 활성화" in preview


def test_reset_preview_says_an_inactive_deployment_default_stays_inactive():
    preview = etl_load_history.build_etl_profile_admin_reset_preview(
        INACTIVE_DEPLOYMENT_ACTIVATION
    )

    assert "계속 비활성" in preview
    assert "다시 활성화" not in preview


def test_reset_preview_is_shown_before_the_button(monkeypatch):
    api_client = _admin_client(
        activation_responses={
            "sample_fashion_vendor_v1": make_activation(),
            "sample_marketplace_vendor_v1": INACTIVE_ACTIVATION,
        }
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = _select_marketplace_profile(run_authenticated_app_test(timeout=10))

    body = _body_text(app)
    assert etl_load_history.ETL_PROFILE_ADMIN_RESET_CAPTION in body
    assert "다시 활성화" in body


# --- 확인 절차 ---


def test_reset_needs_an_explicit_confirmation(monkeypatch):
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    reset_button = _admin_button(app, "etl_profile_admin_reset")
    assert reset_button.disabled is True

    reset_button.click().run(timeout=10)
    assert api_client.activation_reset_calls == []


def test_reset_sends_the_delete_after_confirmation(monkeypatch):
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    _reset_confirmation(app).check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_reset").click().run(timeout=10)

    assert api_client.activation_reset_calls == ["sample_fashion_vendor_v1"]
    # reset은 PUT이 아닙니다. 여기서 PUT이 나가면 override가 남습니다.
    assert api_client.activation_update_calls == []


def test_reset_of_an_explicit_inactive_override_is_possible(monkeypatch):
    api_client = _admin_client(
        activation_responses={
            "sample_fashion_vendor_v1": make_activation(),
            "sample_marketplace_vendor_v1": INACTIVE_ACTIVATION,
        }
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = _select_marketplace_profile(run_authenticated_app_test(timeout=10))
    _reset_confirmation(app).check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_reset").click().run(timeout=10)

    assert api_client.activation_reset_calls == ["sample_marketplace_vendor_v1"]


# --- 성공 후 상태 ---


def test_reset_success_message_reports_the_state_the_server_returned():
    message = etl_load_history.build_etl_profile_admin_reset_success_message(
        "sample_fashion_vendor_v1",
        make_activation(),
    )

    assert "v2" in message


def test_reset_success_message_says_so_when_the_default_is_also_inactive():
    message = etl_load_history.build_etl_profile_admin_reset_success_message(
        "sample_fashion_vendor_v1",
        make_activation(deployment_active_version=None),
    )

    assert "계속 비활성" in message


def test_successful_reset_invalidates_the_same_caches_as_an_update():
    """관리 화면에서 reset했는데 실행 selector가 옛 상태를 보여 주면 안 됩니다."""
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)
    state["etl_web_run_profiles_response"] = {"items": [{"id": "x", "display_name": "x"}]}
    state["etl_profile_admin_profiles_response"] = {"items": []}
    state["etl_web_run_profile_detail_response"] = {"id": "x"}
    state["etl_profile_admin_activation_response"] = OVERRIDE_ACTIVATION
    state["etl_profile_admin_reset_confirmed"] = True

    applied = etl_load_history._reset_etl_profile_activation(
        api_client,
        state,
        "sample_fashion_vendor_v1",
    )

    assert applied is True
    assert state["etl_web_run_profiles_response"] is None
    assert state["etl_profile_admin_profiles_response"] is None
    assert state["etl_web_run_profile_detail_response"] is None
    assert state["etl_profile_admin_activation_response"] is None
    # 성공한 조작의 확인 표시는 지웁니다(대입이 아니라 삭제여야 Streamlit이 허용합니다).
    assert not state.get("etl_profile_admin_reset_confirmed")
    assert state["etl_profile_admin_update_error"] is None
    assert "v2" in state["etl_profile_admin_update_success"]


def test_failed_reset_does_not_report_success():
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION},
        activation_reset_error=catalogguard_api.CatalogGuardApiResponseError("boom"),
    )
    state = dict(etl_load_history.ETL_LOAD_STATE_DEFAULTS)
    state["etl_web_run_profiles_response"] = {"items": [{"id": "x", "display_name": "x"}]}

    applied = etl_load_history._reset_etl_profile_activation(
        api_client,
        state,
        "sample_fashion_vendor_v1",
    )

    assert applied is False
    assert state["etl_profile_admin_update_success"] is None
    assert state["etl_profile_admin_update_error"] is not None
    # 실패했으므로 실행 목록 캐시는 그대로 둡니다.
    assert state["etl_web_run_profiles_response"] is not None


def test_reset_error_uses_the_existing_error_ui(monkeypatch):
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION},
        activation_reset_error=catalogguard_api.ETLProfileNotFoundError("gone"),
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    _reset_confirmation(app).check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_reset").click().run(timeout=10)

    assert any(
        "활성화 상태를 변경하지 못했습니다" in str(element.value) for element in app.error
    )


def test_reset_refreshes_the_management_state_to_the_deployment_default(monkeypatch):
    """reset 뒤 화면이 계속 override를 말하면 사용자가 지워지지 않았다고 믿습니다."""
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    _reset_confirmation(app).check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_reset").click().run(timeout=10)

    # 캐시를 비웠으므로 상태를 다시 조회합니다.
    assert api_client.activation_calls.count("sample_fashion_vendor_v1") == 2


# --- 격리: reset이 다른 화면 상태를 건드리지 않는다 ---


def test_reset_does_not_change_the_run_selector_choice(monkeypatch):
    api_client = _admin_client(
        activation_responses={
            "sample_fashion_vendor_v1": make_activation(),
            "sample_marketplace_vendor_v1": INACTIVE_ACTIVATION,
        }
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = _select_marketplace_profile(run_authenticated_app_test(timeout=10))
    _reset_confirmation(app).check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_reset").click().run(timeout=10)

    # 관리 화면 조작이 "지금 실행할 프로필" 선택을 옮기면 안 됩니다.
    assert app.session_state["etl_web_run_selected_profile_id"] == (
        "sample_fashion_vendor_v1"
    )
    assert app.session_state["etl_profile_admin_selected_profile_id"] == (
        "sample_marketplace_vendor_v1"
    )


def test_reset_does_not_clear_past_etl_history_state(monkeypatch):
    """override를 지우는 것이지 조회 중인 이력을 지우는 것이 아닙니다."""
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    app.session_state["etl_selected_run_id"] = 42
    app.session_state["etl_page"] = 3
    app.run(timeout=10)

    _reset_confirmation(app).check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_reset").click().run(timeout=10)

    assert app.session_state["etl_selected_run_id"] == 42
    assert app.session_state["etl_page"] == 3


def test_reset_section_renders_without_a_rerun_loop(monkeypatch):
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert not app.exception
    assert api_client.activation_calls == ["sample_fashion_vendor_v1"]
    assert api_client.activation_reset_calls == []


# --- 확인 checkbox 초기화는 대입이 아니라 삭제여야 한다 -----------------------


def test_a_successful_deactivate_does_not_crash_the_page(monkeypatch):
    """성공 처리에서 이미 그려진 checkbox key에 대입하면 화면이 예외로 끝납니다.

    checkbox는 실행 버튼보다 먼저 그려지므로 성공 처리는 항상 그 뒤에 옵니다.
    """
    api_client = _admin_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    confirmation = next(
        widget
        for widget in app.checkbox
        if widget.key == "etl_profile_admin_deactivate_confirmed"
    )
    confirmation.check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_deactivate").click().run(timeout=10)

    assert not app.exception
    assert api_client.activation_update_calls == [
        {"profile_id": "sample_fashion_vendor_v1", "active_version": None}
    ]


def test_a_successful_reset_does_not_crash_the_page(monkeypatch):
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    _reset_confirmation(app).check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_reset").click().run(timeout=10)

    assert not app.exception
    assert api_client.activation_reset_calls == ["sample_fashion_vendor_v1"]


def test_a_successful_reset_clears_the_confirmation_checkbox(monkeypatch):
    """확인 표시가 남으면 다음 reset이 확인 없이 버튼 한 번으로 나갑니다."""
    api_client = _admin_client(
        activation_responses={"sample_fashion_vendor_v1": OVERRIDE_ACTIVATION}
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    _reset_confirmation(app).check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_reset").click().run(timeout=10)

    assert _reset_confirmation(app).value is False
    assert _admin_button(app, "etl_profile_admin_reset").disabled is True


# --- Phase 5B.4: Activation 운영 이력 ------------------------------------------


FASHION_HISTORY = [
    make_activation_event(
        3,
        action="reset",
        created_at="2026-08-23T12:00:00Z",
        actor_username="reset_operator",
    ),
    make_activation_event(
        2,
        action="deactivate",
        created_at="2026-08-23T11:00:00Z",
        actor_username="deactivate_operator",
    ),
    make_activation_event(
        1,
        action="activate",
        runtime_active_version="1",
        created_at="2026-08-23T10:00:00Z",
        actor_username="activate_operator",
    ),
]


def _history_client(history=None, **overrides):
    # 빈 목록도 뜻이 있는 값입니다(기록 없음). `or`로 기본값을 채우면 그 상태를
    # 테스트할 수 없습니다.
    return _admin_client(
        activation_history={
            "sample_fashion_vendor_v1": FASHION_HISTORY if history is None else history
        },
        **overrides,
    )


def _dataframe_text(app) -> str:
    return " ".join(str(element.value) for element in app.dataframe)


def test_history_section_is_shown_with_its_scope_explained(monkeypatch):
    api_client = _history_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    body = _body_text(app)
    assert "Activation 운영 이력" in body
    # 과거 기록이 backfill된 것처럼 보이게 쓰지 않습니다.
    assert etl_load_history.ETL_PROFILE_ADMIN_HISTORY_CAPTION in body
    assert not app.exception


def test_history_shows_every_recorded_command(monkeypatch):
    api_client = _history_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    table = _dataframe_text(app)
    for label in ("버전 활성화", "비활성화", "배포 기본값으로 되돌리기"):
        assert label in table
    assert api_client.activation_history_calls == [
        {"profile_id": "sample_fashion_vendor_v1", "limit": 10, "offset": 0}
    ]


def test_history_does_not_describe_a_reset_as_a_deactivation():
    """reset은 override 제거입니다. 배포 기본값이 활성이면 오히려 되살아납니다."""
    frame = etl_load_history.build_etl_profile_admin_history_dataframe(FASHION_HISTORY)
    rows = {row["동작"]: row for _, row in frame.iterrows()}

    reset_row = rows["배포 기본값으로 되돌리기"]
    assert reset_row["런타임 결과"] == (
        etl_load_history.ETL_PROFILE_ADMIN_RUNTIME_NO_OVERRIDE
    )
    # 되돌린 뒤 실제로는 배포 기본값 v2가 적용됩니다.
    assert reset_row["실제 적용 버전"] == "v2"
    assert reset_row["배포 기본 버전"] == "v2"

    deactivate_row = rows["비활성화"]
    assert deactivate_row["런타임 결과"] == (
        etl_load_history.ETL_PROFILE_ADMIN_RUNTIME_INACTIVE
    )
    assert deactivate_row["실제 적용 버전"] == "없음"


def test_history_action_labels_cover_only_the_recorded_commands():
    assert etl_load_history.format_etl_profile_admin_history_action("activate") == (
        "버전 활성화"
    )
    assert etl_load_history.format_etl_profile_admin_history_action("deactivate") == (
        "비활성화"
    )
    assert etl_load_history.format_etl_profile_admin_history_action("reset") == (
        "배포 기본값으로 되돌리기"
    )
    # 계약에 없는 값은 그럴듯한 문구로 바꾸지 않습니다.
    for unknown in ("promote", "", None, 3):
        assert etl_load_history.format_etl_profile_admin_history_action(unknown) == (
            etl_load_history.ETL_PROFILE_ADMIN_HISTORY_UNKNOWN_ACTION_LABEL
        )


def test_history_shows_the_actor_of_each_command(monkeypatch):
    api_client = _history_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    table = _dataframe_text(app)
    for actor in ("reset_operator", "deactivate_operator", "activate_operator"):
        assert actor in table


def test_history_handles_a_missing_actor(monkeypatch):
    """사용자가 삭제되면 이름 없이 남을 수 있습니다. 화면이 깨지면 안 됩니다."""
    api_client = _history_client(
        [make_activation_event(1, actor_username=None, runtime_active_version="1")]
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert not app.exception
    assert "버전 활성화" in _dataframe_text(app)


def test_history_empty_state_is_information_not_an_error(monkeypatch):
    api_client = _history_client([])
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert etl_load_history.ETL_PROFILE_ADMIN_HISTORY_EMPTY_MESSAGE in _body_text(app)
    assert not app.error
    assert not app.exception


def test_history_paginates(monkeypatch):
    events = [
        make_activation_event(index, runtime_active_version="1")
        for index in range(15, 0, -1)
    ]
    api_client = _history_client(events)
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    _admin_button(app, "etl_profile_admin_history_next").click().run(timeout=10)

    assert app.session_state["etl_profile_admin_history_offset"] == 10
    assert api_client.activation_history_calls[-1] == {
        "profile_id": "sample_fashion_vendor_v1",
        "limit": 10,
        "offset": 10,
    }
    assert not app.exception


def test_changing_the_profile_resets_the_history_page(monkeypatch):
    """다른 프로필의 이력을 남의 페이지 번호로 이어 보면 빈 화면이 보입니다."""
    events = [
        make_activation_event(index, runtime_active_version="1")
        for index in range(15, 0, -1)
    ]
    api_client = _history_client(events)
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    _admin_button(app, "etl_profile_admin_history_next").click().run(timeout=10)
    assert app.session_state["etl_profile_admin_history_offset"] == 10

    _admin_selectbox(app, "etl_profile_admin_selected_profile_id").select(
        "마켓플레이스 공급사 샘플"
    ).run(timeout=10)

    assert app.session_state["etl_profile_admin_history_offset"] == 0
    # 캐시는 새 프로필의 첫 페이지로 교체됩니다. 이전 프로필의 3페이지가 남아 있으면
    # 화면이 남의 이력을 그대로 보여 줍니다.
    assert app.session_state["etl_profile_admin_history_profile_id"] == (
        "sample_marketplace_vendor_v1"
    )
    assert api_client.activation_history_calls[-1] == {
        "profile_id": "sample_marketplace_vendor_v1",
        "limit": 10,
        "offset": 0,
    }


def test_viewer_can_read_the_history_without_write_controls(monkeypatch):
    api_client = _history_client()
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(role="viewer", timeout=10)

    assert "Activation 운영 이력" in _body_text(app)
    assert "버전 활성화" in _dataframe_text(app)
    # 이력을 읽을 수 있다고 조작 권한이 생기지는 않습니다.
    assert _admin_button(app, "etl_profile_admin_activate") is None
    assert _admin_button(app, "etl_profile_admin_deactivate") is None
    assert _admin_button(app, "etl_profile_admin_reset") is None
    # 이력에도 수정·삭제 조작은 없습니다.
    assert _admin_button(app, "etl_profile_admin_history_delete") is None


def test_a_successful_mutation_refreshes_the_history(monkeypatch):
    """이력만 옛 화면으로 남으면 방금 한 조작이 기록되지 않은 것처럼 보입니다."""
    api_client = _history_client([])
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)
    assert etl_load_history.ETL_PROFILE_ADMIN_HISTORY_EMPTY_MESSAGE in _body_text(app)

    # 서버가 event를 기록한 것과 같은 상태로 fake를 바꾸고 조작을 보냅니다.
    api_client.activation_history["sample_fashion_vendor_v1"] = [
        make_activation_event(1, action="deactivate")
    ]
    confirmation = next(
        widget
        for widget in app.checkbox
        if widget.key == "etl_profile_admin_deactivate_confirmed"
    )
    confirmation.check().run(timeout=10)
    _admin_button(app, "etl_profile_admin_deactivate").click().run(timeout=10)

    assert not app.exception
    assert "비활성화" in _dataframe_text(app)
    assert app.session_state["etl_profile_admin_history_offset"] == 0


def test_a_history_failure_does_not_break_the_management_screen(monkeypatch):
    """이력 조회 실패가 상태 확인과 조작까지 함께 없애면 안 됩니다."""
    api_client = _history_client(
        activation_history_error=catalogguard_api.CatalogGuardApiResponseError(
            "조회 실패", request_id=None
        )
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert not app.exception
    errors = " ".join(str(element.value) for element in app.error)
    assert etl_load_history.ETL_PROFILE_ADMIN_HISTORY_ERROR_MESSAGE in errors
    # 현재 상태와 조작 control은 그대로 남습니다.
    body = _body_text(app)
    assert "사용 가능한 버전" in body
    assert _admin_button(app, "etl_profile_admin_activate") is not None
    assert _admin_button(app, "etl_profile_admin_deactivate") is not None


def test_a_history_failure_does_not_leak_the_server_message(monkeypatch):
    api_client = _history_client(
        activation_history_error=catalogguard_api.CatalogGuardApiResponseError(
            "postgresql://admin:secret@db.internal/catalog", request_id=None
        )
    )
    _patch_etl_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    errors = " ".join(str(element.value) for element in app.error)
    assert "secret" not in errors
    assert "postgresql" not in errors
