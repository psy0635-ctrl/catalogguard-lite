from datetime import datetime
from math import ceil
from typing import Any

import pandas as pd
import streamlit as st

from clients.catalogguard_api import (
    CatalogGuardApiConfigurationError,
    CatalogGuardApiConnectionError,
    CatalogGuardApiResponseError,
    CatalogGuardApiTimeoutError,
    CatalogPromotionBlockedError,
    CatalogPromotionFailedError,
    CatalogPromotionNotFoundError,
    CatalogPromotionPreviewStaleError,
    ETLInvalidUploadError,
    ETLLoadNotFoundError,
    ETLUnsupportedProfileError,
)
from ui.auth import get_authenticated_api_client, is_operator


ETL_LOAD_LIMIT = 10
ETL_PRODUCT_LIMIT = 20
ETL_REJECT_LIMIT = 20
PROMOTION_HISTORY_LIMIT = 10
PROMOTION_AUDIT_LIMIT = 10
ETL_LOAD_DISPLAY_COLUMNS = [
    "적재 배치 ID",
    "원본 파일명",
    "공급사 프로필",
    "프로필 버전",
    "적재 상품 수",
    "전체 행",
    "변환 거부",
    "적재 시간",
]
ETL_ERROR_DISPLAY_COLUMNS = ["오류 코드", "발생 건수"]
ETL_REJECT_DISPLAY_COLUMNS = ["원본 행", "오류 코드", "오류 필드", "오류 메시지"]
ETL_PRODUCT_DISPLAY_COLUMNS = [
    "staging 상품 ID",
    "상품 그룹 ID",
    "상품 ID",
    "상품명",
    "카테고리",
    "색상",
    "사이즈",
    "재고",
    "정상가",
    "할인가",
    "이미지 경로",
    "설명",
    "판매자",
    "등록 시간",
]
PROMOTION_CHANGE_DISPLAY_COLUMNS = [
    "공급사",
    "외부 상품 ID",
    "변경 유형",
    "변경 필드",
    "변경 전 값",
    "변경 후 값",
]
PROMOTION_ACTION_LABELS = {
    "insert": "신규 등록",
    "update": "정보 수정",
    "unchanged": "변경 없음",
}
PROMOTION_HISTORY_DISPLAY_COLUMNS = [
    "실행 ID",
    "ETL 배치",
    "파일명",
    "상태",
    "신규",
    "수정",
    "변경 없음",
    "실행 시각",
]
PROMOTION_AUDIT_DISPLAY_COLUMNS = [
    "Audit ID",
    "상품 ID",
    "외부 상품 ID",
    "변경 유형",
    "변경 필드",
    "변경 전",
    "변경 후",
    "변경 시각",
]

ETL_LOAD_STATE_DEFAULTS = {
    "etl_load_initialized": False,
    "etl_load_filename_query": "",
    "etl_load_profile_query": "",
    "etl_load_applied_filename": "",
    "etl_load_applied_profile": "",
    "etl_load_offset": 0,
    "etl_load_list_response": None,
    "etl_load_list_error": None,
    "etl_load_selected_run_id": None,
    "etl_load_detail_requested": False,
    "etl_load_detail_response": None,
    "etl_load_detail_error": None,
    "etl_load_product_offset": 0,
    "etl_reject_offset": 0,
    "etl_reject_response": None,
    "etl_reject_error": None,
    "catalog_promotion_preview_batch_id": None,
    "catalog_promotion_preview_response": None,
    "catalog_promotion_preview_hash": None,
    "catalog_promotion_preview_error": None,
    "catalog_promotion_confirmation": False,
    "catalog_promotion_confirmation_input": False,
    "catalog_promotion_in_flight": False,
    "catalog_promotion_result": None,
    "catalog_promotion_history_status": "전체",
    "catalog_promotion_history_offset": 0,
    "catalog_promotion_history_response": None,
    "catalog_promotion_history_error": None,
    "catalog_promotion_history_run_id": None,
    "catalog_promotion_history_detail_requested": False,
    "catalog_promotion_history_detail_response": None,
    "catalog_promotion_history_detail_error": None,
    "catalog_promotion_audit_offset": 0,
    "catalog_promotion_audit_response": None,
    "catalog_promotion_audit_error": None,
    "etl_web_run_profiles_response": None,
    "etl_web_run_profiles_error": None,
    "etl_web_run_selected_profile_id": None,
    "etl_web_run_in_flight": False,
    "etl_web_run_result": None,
    "etl_web_run_error": None,
}


def format_etl_datetime(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    text_value = str(value)
    normalized_value = (
        f"{text_value[:-1]}+00:00" if text_value.endswith("Z") else text_value
    )
    try:
        parsed_datetime = datetime.fromisoformat(normalized_value)
    except ValueError:
        return text_value
    return parsed_datetime.strftime("%Y-%m-%d %H:%M:%S")


def build_etl_load_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "적재 배치 ID": item.get("etl_load_run_id"),
            "원본 파일명": item.get("source_filename"),
            "공급사 프로필": item.get("profile_name"),
            "프로필 버전": item.get("profile_version"),
            "적재 상품 수": item.get("loaded_rows"),
            "전체 행": _display_nullable(item.get("total_rows")),
            "변환 거부": _display_nullable(item.get("rejected_rows")),
            "적재 시간": format_etl_datetime(item.get("created_at")),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=ETL_LOAD_DISPLAY_COLUMNS)


def _display_nullable(value: object) -> object:
    return "" if value is None else value


def format_etl_quality_rate(
    total_rows: int | None,
    loaded_rows: int | None,
) -> str:
    if total_rows is None or loaded_rows is None or total_rows <= 0:
        return "—"
    return f"{loaded_rows / total_rows * 100:.1f}%"


def build_etl_error_counts_dataframe(error_counts: dict[str, int] | None) -> pd.DataFrame:
    if not error_counts:
        return pd.DataFrame(columns=ETL_ERROR_DISPLAY_COLUMNS)
    rows = sorted(
        error_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return pd.DataFrame(
        [
            {"오류 코드": code, "발생 건수": count}
            for code, count in rows
        ],
        columns=ETL_ERROR_DISPLAY_COLUMNS,
    )


def build_etl_rejection_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in items:
        errors = item.get("errors") or []
        rows.append(
            {
                "원본 행": item.get("source_row_number"),
                "오류 코드": ", ".join(str(error.get("code", "")) for error in errors),
                "오류 필드": ", ".join(str(error.get("field", "")) for error in errors),
                "오류 메시지": ", ".join(
                    str(error.get("message", "")) for error in errors
                ),
            }
        )
    return pd.DataFrame(rows, columns=ETL_REJECT_DISPLAY_COLUMNS)


def build_etl_product_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "staging 상품 ID": item.get("staging_product_id"),
            "상품 그룹 ID": item.get("product_group_id"),
            "상품 ID": item.get("product_id"),
            "상품명": item.get("product_name"),
            "카테고리": item.get("category"),
            "색상": item.get("color"),
            "사이즈": item.get("size"),
            "재고": item.get("stock"),
            "정상가": item.get("price"),
            "할인가": _display_nullable(item.get("sale_price")),
            "이미지 경로": item.get("image_path"),
            "설명": _display_nullable(item.get("description")),
            "판매자": _display_nullable(item.get("seller")),
            "등록 시간": format_etl_datetime(item.get("created_at")),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=ETL_PRODUCT_DISPLAY_COLUMNS)


def calculate_etl_pagination(
    *, total: int, limit: int, offset: int
) -> tuple[int, int, bool, bool]:
    safe_total = max(0, int(total))
    safe_limit = max(1, int(limit))
    safe_offset = max(0, int(offset))
    current_page = safe_offset // safe_limit + 1
    total_pages = max(1, ceil(safe_total / safe_limit))
    return (
        current_page,
        total_pages,
        safe_offset > 0,
        safe_offset + safe_limit < safe_total,
    )


def build_etl_load_option_label(item: dict[str, Any]) -> str:
    return (
        f"{item.get('etl_load_run_id')} · "
        f"{item.get('source_filename')} · "
        f"{item.get('profile_name')}"
    )


def build_etl_api_error_display_message(
    message: str, error: Exception | None = None
) -> str:
    request_id = getattr(error, "request_id", None)
    if request_id is None:
        return message
    request_id_message = f"요청 ID: {request_id}"
    if request_id_message in message:
        return message
    return f"{message}\n\n{request_id_message}"


def initialize_etl_load_state(session_state=None) -> None:
    state = st.session_state if session_state is None else session_state
    for key, value in ETL_LOAD_STATE_DEFAULTS.items():
        if key not in state:
            state[key] = value


def clear_catalog_promotion_preview_state(
    session_state,
    *,
    clear_result: bool = True,
) -> None:
    session_state["catalog_promotion_preview_batch_id"] = None
    session_state["catalog_promotion_preview_response"] = None
    session_state["catalog_promotion_preview_hash"] = None
    session_state["catalog_promotion_preview_error"] = None
    session_state["catalog_promotion_confirmation"] = False
    session_state["catalog_promotion_in_flight"] = False
    if clear_result:
        session_state["catalog_promotion_result"] = None


def synchronize_catalog_promotion_batch(session_state) -> None:
    selected_run_id = session_state.get("etl_load_selected_run_id")
    preview_batch_id = session_state.get("catalog_promotion_preview_batch_id")
    if preview_batch_id is None or preview_batch_id == selected_run_id:
        return
    clear_catalog_promotion_preview_state(session_state)


def store_catalog_promotion_preview(session_state, response: dict[str, Any]) -> None:
    selected_run_id = session_state.get("etl_load_selected_run_id")
    response_run_id = response.get("etl_load_run_id")
    if selected_run_id is None or response_run_id != selected_run_id:
        raise ValueError("promotion preview batch does not match selected batch")

    clear_catalog_promotion_preview_state(session_state)
    session_state["catalog_promotion_preview_batch_id"] = response_run_id
    session_state["catalog_promotion_preview_response"] = dict(response)
    preview_hash = response.get("preview_hash")
    session_state["catalog_promotion_preview_hash"] = (
        preview_hash if isinstance(preview_hash, str) else None
    )


def can_submit_catalog_promotion(session_state) -> bool:
    response = session_state.get("catalog_promotion_preview_response")
    selected_run_id = session_state.get("etl_load_selected_run_id")
    preview_batch_id = session_state.get("catalog_promotion_preview_batch_id")
    preview_hash = session_state.get("catalog_promotion_preview_hash")
    return (
        isinstance(response, dict)
        and selected_run_id is not None
        and selected_run_id == preview_batch_id
        and response.get("promotion_eligible") is True
        and isinstance(preview_hash, str)
        and len(preview_hash) == 64
        and session_state.get("catalog_promotion_confirmation") is True
        and session_state.get("catalog_promotion_in_flight") is not True
    )


def store_catalog_promotion_success(
    session_state,
    response: dict[str, Any],
) -> None:
    clear_catalog_promotion_preview_state(session_state, clear_result=False)
    session_state["catalog_promotion_result"] = dict(response)
    session_state["catalog_promotion_history_response"] = None
    session_state["catalog_promotion_history_error"] = None


def store_catalog_promotion_failure(
    session_state,
    *,
    kind: str,
    message: str,
) -> None:
    if kind == "preview_stale":
        clear_catalog_promotion_preview_state(session_state, clear_result=False)
    else:
        session_state["catalog_promotion_in_flight"] = False
    session_state["catalog_promotion_result"] = {
        "kind": kind,
        "message": message,
    }


def build_catalog_promotion_changes_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        supplier_key = item.get("supplier_key", "")
        external_product_id = item.get("external_product_id", "")
        action = str(item.get("action", ""))
        action_label = PROMOTION_ACTION_LABELS.get(action, action)
        changed_fields = item.get("changed_fields")
        if action == "update" and isinstance(changed_fields, dict):
            for field_name, change in changed_fields.items():
                change_data = change if isinstance(change, dict) else {}
                rows.append(
                    {
                        "공급사": supplier_key,
                        "외부 상품 ID": external_product_id,
                        "변경 유형": action_label,
                        "변경 필드": field_name,
                        "변경 전 값": _display_nullable(change_data.get("before")),
                        "변경 후 값": _display_nullable(change_data.get("after")),
                    }
                )
            continue

        rows.append(
            {
                "공급사": supplier_key,
                "외부 상품 ID": external_product_id,
                "변경 유형": action_label,
                "변경 필드": "상품 전체" if action == "insert" else "-",
                "변경 전 값": "-" if action == "insert" else "변경 없음",
                "변경 후 값": "신규 등록" if action == "insert" else "변경 없음",
            }
        )
    return pd.DataFrame(rows, columns=PROMOTION_CHANGE_DISPLAY_COLUMNS)


def build_catalog_promotion_history_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows = [
        {
            "실행 ID": item.get("promotion_run_id"),
            "ETL 배치": item.get("etl_load_run_id"),
            "파일명": item.get("source_filename", ""),
            "상태": item.get("status", ""),
            "신규": item.get("inserted_count", 0),
            "수정": item.get("updated_count", 0),
            "변경 없음": item.get("unchanged_count", 0),
            "실행 시각": format_etl_datetime(
                item.get("started_at") or item.get("created_at")
            ),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=PROMOTION_HISTORY_DISPLAY_COLUMNS)


def build_catalog_promotion_audit_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        after_data = item.get("after_data")
        before_data = item.get("before_data")
        safe_after = after_data if isinstance(after_data, dict) else {}
        safe_before = before_data if isinstance(before_data, dict) else {}
        external_product_id = safe_after.get(
            "external_product_id",
            safe_before.get("external_product_id", ""),
        )
        changed_fields = item.get("changed_fields")
        safe_changes = changed_fields if isinstance(changed_fields, dict) else {}
        for field_name in sorted(safe_changes):
            change = safe_changes.get(field_name)
            safe_change = change if isinstance(change, dict) else {}
            rows.append(
                {
                    "Audit ID": item.get("audit_id"),
                    "상품 ID": item.get("catalog_product_id"),
                    "외부 상품 ID": external_product_id,
                    "변경 유형": PROMOTION_ACTION_LABELS.get(
                        str(item.get("action", "")),
                        item.get("action", ""),
                    ),
                    "변경 필드": field_name,
                    "변경 전": _display_nullable(safe_change.get("before")),
                    "변경 후": _display_nullable(safe_change.get("after")),
                    "변경 시각": format_etl_datetime(item.get("created_at")),
                }
            )
    return pd.DataFrame(rows, columns=PROMOTION_AUDIT_DISPLAY_COLUMNS)


def reset_etl_load_detail_state(session_state) -> None:
    session_state["etl_load_detail_requested"] = False
    session_state["etl_load_detail_response"] = None
    session_state["etl_load_detail_error"] = None
    session_state["etl_load_product_offset"] = 0
    session_state["etl_reject_offset"] = 0
    session_state["etl_reject_response"] = None
    session_state["etl_reject_error"] = None


def apply_etl_load_search(session_state) -> None:
    session_state["etl_load_applied_filename"] = str(
        session_state.get("etl_load_filename_query", "")
    ).strip()
    session_state["etl_load_applied_profile"] = str(
        session_state.get("etl_load_profile_query", "")
    ).strip()
    session_state["etl_load_offset"] = 0
    session_state["etl_load_list_response"] = None
    session_state["etl_load_list_error"] = None
    session_state["etl_load_initialized"] = False
    session_state["etl_load_selected_run_id"] = None
    reset_etl_load_detail_state(session_state)
    clear_catalog_promotion_preview_state(session_state)


def _on_etl_load_selection_change(session_state) -> None:
    reset_etl_load_detail_state(session_state)
    clear_catalog_promotion_preview_state(session_state)


def _catalog_promotion_error_message(error: Exception) -> str:
    if isinstance(error, CatalogGuardApiConnectionError):
        return "CatalogGuard API 서버에 연결할 수 없습니다."
    if isinstance(error, CatalogGuardApiTimeoutError):
        return "CatalogGuard API 서버의 응답 시간이 초과되었습니다."
    if isinstance(error, ETLLoadNotFoundError):
        return "선택한 ETL 적재 이력을 찾을 수 없습니다."
    if isinstance(error, CatalogGuardApiResponseError):
        return "운영 상품 반영 요청을 처리하지 못했습니다."
    return "운영 상품 반영 요청 중 오류가 발생했습니다."


def _render_catalog_promotion_result() -> None:
    result = st.session_state.get("catalog_promotion_result")
    if not isinstance(result, dict):
        return

    if result.get("status") == "succeeded":
        if result.get("created") is True:
            st.success("운영 상품 반영이 완료되었습니다.")
        else:
            st.info(
                "이미 처리된 ETL 적재 결과입니다. 기존 운영 상품 반영 결과를 표시합니다."
            )
        count_columns = st.columns(3)
        count_columns[0].metric("신규 등록", result.get("inserted_count", 0), border=True)
        count_columns[1].metric("정보 수정", result.get("updated_count", 0), border=True)
        count_columns[2].metric("변경 없음", result.get("unchanged_count", 0), border=True)
        st.caption("새로운 반영이 필요하면 미리보기를 다시 실행하세요.")
        return

    kind = result.get("kind")
    message = str(result.get("message") or "")
    if kind == "preview_stale":
        st.error(
            "미리보기 이후 상품 데이터가 변경되었습니다. "
            "미리보기를 다시 실행하세요."
        )
    elif kind == "promotion_blocked":
        st.error("현재 ETL 적재 결과는 운영 상품에 반영할 수 없습니다.")
        if message:
            st.warning(message)
    elif kind == "promotion_failed":
        st.error("운영 상품 반영 중 오류가 발생했습니다.")
    elif message:
        st.error(message)


def _request_catalog_promotion_preview(api_client) -> None:
    selected_run_id = st.session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return

    clear_catalog_promotion_preview_state(st.session_state)
    st.session_state["catalog_promotion_in_flight"] = True
    try:
        with st.spinner("운영 반영 미리보기를 계산하고 있습니다."):
            response = api_client.get_catalog_promotion_preview(selected_run_id)
        store_catalog_promotion_preview(st.session_state, response)
    except (
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        ETLLoadNotFoundError,
        CatalogGuardApiResponseError,
    ) as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="preview_failed",
            message=build_etl_api_error_display_message(
                _catalog_promotion_error_message(error),
                error,
            ),
        )
    finally:
        st.session_state["catalog_promotion_in_flight"] = False


def _submit_catalog_promotion(api_client) -> None:
    if not can_submit_catalog_promotion(st.session_state):
        return

    selected_run_id = st.session_state["etl_load_selected_run_id"]
    preview_hash = st.session_state["catalog_promotion_preview_hash"]
    st.session_state["catalog_promotion_in_flight"] = True
    try:
        with st.spinner("운영 상품에 반영하고 있습니다."):
            response = api_client.create_catalog_promotion(
                selected_run_id,
                confirmation=True,
                expected_preview_hash=preview_hash,
            )
        store_catalog_promotion_success(st.session_state, response)
    except CatalogPromotionPreviewStaleError as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="preview_stale",
            message=str(error),
        )
    except CatalogPromotionBlockedError as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="promotion_blocked",
            message=str(error),
        )
    except CatalogPromotionFailedError as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="promotion_failed",
            message=str(error),
        )
    except (
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        ETLLoadNotFoundError,
        CatalogGuardApiResponseError,
    ) as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="promotion_failed",
            message=build_etl_api_error_display_message(
                _catalog_promotion_error_message(error),
                error,
            ),
        )
    finally:
        st.session_state["catalog_promotion_in_flight"] = False


def _render_catalog_promotion_preview(api_client) -> None:
    if not isinstance(
        st.session_state.get("catalog_promotion_preview_response"),
        dict,
    ):
        st.session_state["catalog_promotion_confirmation_input"] = False
    st.divider()
    st.subheader("운영 상품 반영")
    st.write(
        "선택한 ETL 적재 결과와 현재 운영 상품을 비교한 뒤, "
        "변경 내용을 확인하고 명시적으로 승인해 반영합니다."
    )
    selected_run_id = st.session_state.get("etl_load_selected_run_id")
    in_flight = st.session_state.get("catalog_promotion_in_flight") is True
    if selected_run_id is None:
        st.info("운영 상품 반영 결과를 확인할 ETL 적재 이력을 선택하세요.")

    if st.button(
        "운영 반영 미리보기",
        key="catalog_promotion_preview",
        disabled=selected_run_id is None or in_flight,
        type="secondary",
    ):
        _request_catalog_promotion_preview(api_client)

    _render_catalog_promotion_result()
    preview = st.session_state.get("catalog_promotion_preview_response")
    if not isinstance(preview, dict):
        return

    eligible = preview.get("promotion_eligible") is True
    if eligible:
        st.success(
            "반영 가능 — ETL 적재 결과를 운영 상품에 반영할 수 있습니다."
        )
    else:
        st.error(
            "반영 불가 — 현재 ETL 적재 결과는 운영 상품에 반영할 수 없습니다."
        )
        for reason in preview.get("blocked_reasons") or []:
            if isinstance(reason, dict) and reason.get("message"):
                st.warning(str(reason["message"]))

    metric_columns = st.columns(4)
    metric_columns[0].metric("신규 등록 예정", preview.get("insert_count", 0), border=True)
    metric_columns[1].metric("수정 예정", preview.get("update_count", 0), border=True)
    metric_columns[2].metric("변경 없음", preview.get("unchanged_count", 0), border=True)
    total_products = (
        int(preview.get("insert_count", 0))
        + int(preview.get("update_count", 0))
        + int(preview.get("unchanged_count", 0))
    )
    metric_columns[3].metric("전체 대상 상품", total_products, border=True)

    items = preview.get("items") or []
    if items:
        st.markdown("#### 상품별 변경 내용")
        display_dataframe = build_catalog_promotion_changes_dataframe(items)
        for value_column in ("변경 전 값", "변경 후 값"):
            display_dataframe[value_column] = display_dataframe[value_column].map(str)
        st.dataframe(
            display_dataframe,
            width="stretch",
            hide_index=True,
        )

    confirmation = st.checkbox(
        "미리보기 내용을 확인했으며 운영 상품 반영에 동의합니다.",
        key="catalog_promotion_confirmation_input",
        disabled=not eligible or not st.session_state.get(
            "catalog_promotion_preview_hash"
        ),
    )
    st.session_state["catalog_promotion_confirmation"] = bool(confirmation)
    if not is_operator():
        st.caption("운영 상품 반영은 운영자 권한이 필요합니다.")
    if st.button(
        "운영 상품에 반영",
        key="catalog_promotion_submit",
        disabled=not can_submit_catalog_promotion(st.session_state) or not is_operator(),
        type="primary",
    ):
        _submit_catalog_promotion(api_client)
        st.rerun()


def build_etl_load_request_params(
    session_state,
    *,
    limit: int = ETL_LOAD_LIMIT,
    offset: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": limit,
        "offset": session_state.get("etl_load_offset", 0)
        if offset is None
        else offset,
    }
    filename = str(session_state.get("etl_load_applied_filename", "")).strip()
    profile_name = str(session_state.get("etl_load_applied_profile", "")).strip()
    if filename:
        params["filename"] = filename
    if profile_name:
        params["profile_name"] = profile_name
    return params


def _fetch_etl_load_list(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("etl_load_initialized"):
        cached_response = session_state.get("etl_load_list_response")
        if isinstance(cached_response, dict):
            return cached_response
        session_state["etl_load_initialized"] = False

    try:
        response = api_client.list_etl_loads(
            **build_etl_load_request_params(session_state)
        )
        session_state["etl_load_list_response"] = response
        session_state["etl_load_list_error"] = None
        session_state["etl_load_initialized"] = True
        return response
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_load_list_error"] = error
        session_state["etl_load_initialized"] = False
        return None


def _fetch_etl_load_detail(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("etl_load_detail_response") is not None:
        return session_state["etl_load_detail_response"]
    if session_state.get("etl_load_detail_error") is not None:
        return None
    selected_run_id = session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return None
    try:
        response = api_client.get_etl_load_detail(
            int(selected_run_id),
            product_limit=ETL_PRODUCT_LIMIT,
            product_offset=session_state["etl_load_product_offset"],
        )
        session_state["etl_load_detail_response"] = response
        session_state["etl_load_detail_error"] = None
        return response
    except (
        ETLLoadNotFoundError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_load_detail_error"] = error
        return None


def _fetch_etl_rejections(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("etl_reject_response") is not None:
        return session_state["etl_reject_response"]
    if session_state.get("etl_reject_error") is not None:
        return None
    selected_run_id = session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return None
    try:
        response = api_client.list_etl_rejections(
            int(selected_run_id),
            limit=ETL_REJECT_LIMIT,
            offset=session_state["etl_reject_offset"],
        )
        session_state["etl_reject_response"] = response
        session_state["etl_reject_error"] = None
        return response
    except (
        ETLLoadNotFoundError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_reject_error"] = error
        return None


def _render_etl_error(error: Exception, *, detail: bool = False) -> None:
    if isinstance(error, CatalogGuardApiConfigurationError):
        message = "ETL 적재 이력 API 주소가 설정되지 않았습니다."
    elif isinstance(error, CatalogGuardApiConnectionError):
        message = "ETL 적재 이력 서버에 연결할 수 없습니다."
    elif isinstance(error, CatalogGuardApiTimeoutError):
        message = "ETL 적재 이력 서버 응답 시간이 초과되었습니다."
    elif isinstance(error, ETLLoadNotFoundError):
        message = "ETL 적재 배치를 찾을 수 없습니다."
    else:
        message = (
            "ETL 적재 상세 정보를 불러오는 중 오류가 발생했습니다."
            if detail
            else "ETL 적재 이력을 불러오는 중 오류가 발생했습니다."
        )
    st.error(build_etl_api_error_display_message(message, error))


def _render_etl_rejections(api_client, detail_response: dict[str, Any]) -> None:
    if not detail_response.get("reject_details_stored", False):
        st.info(
            "이 배치는 reject 상세 저장 기능 도입 전에 생성되어 거부 행 상세가 없습니다."
        )
        return

    response = _fetch_etl_rejections(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("etl_reject_error")
        if error is not None:
            _render_etl_error(error, detail=True)
        return
    if not response.get("available", False):
        st.info("이 배치에는 거부 행 상세가 없습니다.")
        return

    items = response.get("items") or []
    if not items:
        st.info("거부 행이 없습니다.")
        return

    st.subheader("거부 행 상세")
    st.dataframe(
        build_etl_rejection_dataframe(items),
        width="stretch",
        hide_index=True,
    )
    for item in items:
        with st.expander(f"원본 행 {item.get('source_row_number')} - 마스킹 원본"):
            st.json(item.get("masked_source_data") or {})

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ETL_REJECT_LIMIT,
        offset=st.session_state["etl_reject_offset"],
    )
    st.caption(f"거부 행 {current_page} / {total_pages} 페이지 · 전체 {total}개")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "거부 행 이전",
            disabled=not has_previous,
            key="etl_reject_previous",
            type="tertiary",
        ):
            st.session_state["etl_reject_offset"] -= ETL_REJECT_LIMIT
            st.session_state["etl_reject_response"] = None
            st.rerun()
    with next_col:
        if st.button(
            "거부 행 다음",
            disabled=not has_next,
            key="etl_reject_next",
            type="tertiary",
        ):
            st.session_state["etl_reject_offset"] += ETL_REJECT_LIMIT
            st.session_state["etl_reject_response"] = None
            st.rerun()


def _render_etl_search_controls() -> None:
    filename_col, profile_col, search_col = st.columns([3, 3, 1])
    with filename_col:
        st.text_input(
            "원본 파일명",
            key="etl_load_filename_query",
            placeholder="예: vendor_products.csv",
        )
    with profile_col:
        st.text_input(
            "공급사 프로필",
            key="etl_load_profile_query",
            placeholder="예: sample_fashion_vendor_v2",
        )
    with search_col:
        st.button(
            "조회",
            key="etl_load_search",
            on_click=apply_etl_load_search,
            args=(st.session_state,),
        )


def _render_etl_load_pagination(response: dict[str, Any]) -> None:
    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ETL_LOAD_LIMIT,
        offset=st.session_state["etl_load_offset"],
    )
    st.caption(f"{current_page} / {total_pages} 페이지 · 전체 {total}개 배치")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "이전",
            disabled=not has_previous,
            key="etl_load_previous",
            type="tertiary",
        ):
            st.session_state["etl_load_offset"] -= ETL_LOAD_LIMIT
            st.session_state["etl_load_list_response"] = None
            reset_etl_load_detail_state(st.session_state)
            st.rerun()
    with next_col:
        if st.button(
            "다음",
            disabled=not has_next,
            key="etl_load_next",
            type="tertiary",
        ):
            st.session_state["etl_load_offset"] += ETL_LOAD_LIMIT
            st.session_state["etl_load_list_response"] = None
            reset_etl_load_detail_state(st.session_state)
            st.rerun()


def _render_etl_load_detail(api_client) -> None:
    selected_run_id = st.session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return

    st.subheader("적재 배치 상세")
    detail_response = _fetch_etl_load_detail(api_client, st.session_state)
    if detail_response is None:
        error = st.session_state.get("etl_load_detail_error")
        if error is not None:
            _render_etl_error(error, detail=True)
        return

    st.write(f"적재 배치 ID: {detail_response.get('etl_load_run_id', '')}")
    st.write(f"원본 파일명: {detail_response.get('source_filename', '')}")
    st.write(f"공급사 프로필: {detail_response.get('profile_name', '')}")
    st.write(f"프로필 버전: {detail_response.get('profile_version', '')}")
    st.write(f"적재 상품 수: {detail_response.get('loaded_rows', 0)}")
    st.write(f"적재 시간: {format_etl_datetime(detail_response.get('created_at'))}")
    total_rows = detail_response.get("total_rows")
    rejected_rows = detail_response.get("rejected_rows")
    if total_rows is not None and rejected_rows is not None:
        quality_columns = st.columns(4)
        quality_columns[0].metric("전체 입력", f"{total_rows}행", border=True)
        quality_columns[1].metric(
            "정상 적재", f"{detail_response.get('loaded_rows', 0)}행", border=True
        )
        quality_columns[2].metric("변환 거부", f"{rejected_rows}행", border=True)
        quality_columns[3].metric(
            "정상 처리율",
            format_etl_quality_rate(total_rows, detail_response.get("loaded_rows")),
            border=True,
        )
    else:
        st.info(
            "이 배치는 ETL 품질 요약 저장 기능이 추가되기 전에 생성되어 "
            "상세 품질 정보가 없습니다."
        )
    error_counts = detail_response.get("error_counts")
    if isinstance(error_counts, dict):
        if error_counts:
            st.subheader("오류 코드별 발생 건수")
            st.dataframe(
                build_etl_error_counts_dataframe(error_counts),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("변환 과정에서 거부된 행이 없습니다.")
    _render_etl_rejections(api_client, detail_response)

    with st.expander("파일 SHA-256"):
        st.code(f"원본 파일 SHA-256: {detail_response.get('input_file_sha256', '')}")
        st.code(f"적재 파일 SHA-256: {detail_response.get('output_file_sha256', '')}")

    products = detail_response.get("products") or {}
    product_items = products.get("items") or []
    product_dataframe = build_etl_product_dataframe(product_items)
    st.dataframe(product_dataframe, width="stretch", hide_index=True)

    total = max(0, int(products.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ETL_PRODUCT_LIMIT,
        offset=st.session_state["etl_load_product_offset"],
    )
    st.caption(f"상품 {current_page} / {total_pages} 페이지 · 전체 {total}개 상품")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "상품 이전",
            disabled=not has_previous,
            key="etl_product_previous",
            type="tertiary",
        ):
            st.session_state["etl_load_product_offset"] -= ETL_PRODUCT_LIMIT
            st.session_state["etl_load_detail_response"] = None
            st.rerun()
    with next_col:
        if st.button(
            "상품 다음",
            disabled=not has_next,
            key="etl_product_next",
            type="tertiary",
        ):
            st.session_state["etl_load_product_offset"] += ETL_PRODUCT_LIMIT
            st.session_state["etl_load_detail_response"] = None
            st.rerun()


def _clear_catalog_promotion_history_detail(session_state) -> None:
    session_state["catalog_promotion_history_detail_requested"] = False
    session_state["catalog_promotion_history_detail_response"] = None
    session_state["catalog_promotion_history_detail_error"] = None
    session_state["catalog_promotion_audit_offset"] = 0
    session_state["catalog_promotion_audit_response"] = None
    session_state["catalog_promotion_audit_error"] = None
    session_state["catalog_promotion_rollback_result"] = None
    session_state["catalog_promotion_rollback_error"] = None
    session_state["catalog_promotion_rollback_confirmation"] = False


def _on_catalog_promotion_history_filter_change(session_state) -> None:
    session_state["catalog_promotion_history_offset"] = 0
    session_state["catalog_promotion_history_response"] = None
    session_state["catalog_promotion_history_error"] = None
    session_state["catalog_promotion_history_run_id"] = None
    _clear_catalog_promotion_history_detail(session_state)


def _on_catalog_promotion_history_run_change(session_state) -> None:
    _clear_catalog_promotion_history_detail(session_state)


def _fetch_catalog_promotion_history(api_client) -> dict[str, Any] | None:
    cached = st.session_state.get("catalog_promotion_history_response")
    if isinstance(cached, dict):
        return cached
    if st.session_state.get("catalog_promotion_history_error") is not None:
        return None

    params: dict[str, Any] = {
        "limit": PROMOTION_HISTORY_LIMIT,
        "offset": st.session_state["catalog_promotion_history_offset"],
    }
    selected_status = st.session_state.get("catalog_promotion_history_status")
    if selected_status and selected_status != "전체":
        params["status"] = selected_status
    try:
        response = api_client.list_catalog_promotions(**params)
        st.session_state["catalog_promotion_history_response"] = response
        st.session_state["catalog_promotion_history_error"] = None
        return response
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_history_error"] = error
        return None


def _fetch_catalog_promotion_history_detail(api_client) -> dict[str, Any] | None:
    cached = st.session_state.get("catalog_promotion_history_detail_response")
    if isinstance(cached, dict):
        return cached
    if st.session_state.get("catalog_promotion_history_detail_error") is not None:
        return None
    promotion_run_id = st.session_state.get("catalog_promotion_history_run_id")
    if promotion_run_id is None:
        return None
    try:
        response = api_client.get_catalog_promotion_detail(int(promotion_run_id))
        st.session_state["catalog_promotion_history_detail_response"] = response
        st.session_state["catalog_promotion_history_detail_error"] = None
        return response
    except (
        CatalogPromotionNotFoundError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_history_detail_error"] = error
        return None


def _fetch_catalog_promotion_audits(api_client) -> dict[str, Any] | None:
    cached = st.session_state.get("catalog_promotion_audit_response")
    if isinstance(cached, dict):
        return cached
    if st.session_state.get("catalog_promotion_audit_error") is not None:
        return None
    promotion_run_id = st.session_state.get("catalog_promotion_history_run_id")
    if promotion_run_id is None:
        return None
    try:
        response = api_client.list_catalog_promotion_audits(
            int(promotion_run_id),
            limit=PROMOTION_AUDIT_LIMIT,
            offset=st.session_state["catalog_promotion_audit_offset"],
        )
        st.session_state["catalog_promotion_audit_response"] = response
        st.session_state["catalog_promotion_audit_error"] = None
        return response
    except (
        CatalogPromotionNotFoundError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_audit_error"] = error
        return None


def _render_catalog_promotion_history_error(
    message: str,
    error: Exception,
) -> None:
    st.error(build_etl_api_error_display_message(message, error))


def _render_catalog_promotion_audits(api_client) -> None:
    st.markdown("#### 상품 변경 Audit")
    response = _fetch_catalog_promotion_audits(api_client)
    if response is None:
        error = st.session_state.get("catalog_promotion_audit_error")
        if error is not None:
            _render_catalog_promotion_history_error(
                "상품 변경 Audit을 불러오지 못했습니다.",
                error,
            )
        return

    items = response.get("items") or []
    if not items:
        st.info("이 Promotion 실행에는 상품 변경 Audit이 없습니다.")
    else:
        st.dataframe(
            build_catalog_promotion_audit_dataframe(items),
            width="stretch",
            hide_index=True,
        )

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=PROMOTION_AUDIT_LIMIT,
        offset=st.session_state["catalog_promotion_audit_offset"],
    )
    st.caption(f"Audit {current_page} / {total_pages} 페이지 · 전체 {total}건")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "Audit 이전",
            key="catalog_promotion_audit_previous",
            disabled=not has_previous,
        ):
            st.session_state["catalog_promotion_audit_offset"] -= (
                PROMOTION_AUDIT_LIMIT
            )
            st.session_state["catalog_promotion_audit_response"] = None
            st.session_state["catalog_promotion_audit_error"] = None
            st.rerun()
    with next_col:
        if st.button(
            "Audit 다음",
            key="catalog_promotion_audit_next",
            disabled=not has_next,
        ):
            st.session_state["catalog_promotion_audit_offset"] += (
                PROMOTION_AUDIT_LIMIT
            )
            st.session_state["catalog_promotion_audit_response"] = None
            st.session_state["catalog_promotion_audit_error"] = None
            st.rerun()


def _render_catalog_promotion_history_detail(api_client) -> None:
    detail = _fetch_catalog_promotion_history_detail(api_client)
    if detail is None:
        error = st.session_state.get("catalog_promotion_history_detail_error")
        if error is not None:
            _render_catalog_promotion_history_error(
                "Promotion 실행 상세를 불러오지 못했습니다.",
                error,
            )
        return

    st.markdown("#### Promotion 실행 상세")
    st.write(f"실행 ID: {detail.get('promotion_run_id', '')}")
    st.write(f"ETL 배치: {detail.get('etl_load_run_id', '')}")
    st.write(f"원본 파일명: {detail.get('source_filename', '')}")
    st.write(f"상태: {detail.get('status', '')}")
    metric_columns = st.columns(3)
    metric_columns[0].metric("신규 상품", detail.get("inserted_count", 0))
    metric_columns[1].metric("수정 상품", detail.get("updated_count", 0))
    metric_columns[2].metric("변경 없음", detail.get("unchanged_count", 0))
    failure_message = detail.get("safe_failure_message")
    if failure_message:
        st.warning(str(failure_message))
    st.caption(
        "실행 시각: "
        f"{format_etl_datetime(detail.get('started_at') or detail.get('created_at'))}"
    )
    _render_catalog_promotion_rollback(api_client, detail)
    _render_catalog_promotion_audits(api_client)


def _render_catalog_promotion_history(api_client) -> None:
    st.divider()
    st.subheader("Promotion 실행 이력")
    st.write("저장된 Promotion 실행 결과와 상품 변경 Audit을 조회합니다.")
    st.selectbox(
        "상태 필터",
        options=["전체", "applying", "succeeded", "failed", "blocked"],
        key="catalog_promotion_history_status",
        on_change=_on_catalog_promotion_history_filter_change,
        args=(st.session_state,),
    )

    response = _fetch_catalog_promotion_history(api_client)
    if response is None:
        error = st.session_state.get("catalog_promotion_history_error")
        if error is not None:
            _render_catalog_promotion_history_error(
                "Promotion 실행 이력을 불러오지 못했습니다.",
                error,
            )
        return

    items = response.get("items") or []
    if not items:
        st.info("Promotion 실행 이력이 없습니다.")
    else:
        st.dataframe(
            build_catalog_promotion_history_dataframe(items),
            width="stretch",
            hide_index=True,
        )
        run_ids = [item["promotion_run_id"] for item in items]
        labels = {
            item["promotion_run_id"]: (
                f"{item['promotion_run_id']} · {item.get('source_filename', '')} · "
                f"{item.get('status', '')}"
            )
            for item in items
        }
        if st.session_state.get("catalog_promotion_history_run_id") not in run_ids:
            st.session_state["catalog_promotion_history_run_id"] = None
            _clear_catalog_promotion_history_detail(st.session_state)
        st.selectbox(
            "Promotion 실행 선택",
            options=[None, *run_ids],
            format_func=lambda run_id: (
                "조회할 Promotion 실행을 선택하세요."
                if run_id is None
                else labels.get(run_id, str(run_id))
            ),
            key="catalog_promotion_history_run_id",
            on_change=_on_catalog_promotion_history_run_change,
            args=(st.session_state,),
        )
        if st.button(
            "Promotion 상세 조회",
            key="catalog_promotion_history_show_detail",
            disabled=st.session_state.get("catalog_promotion_history_run_id") is None,
        ):
            st.session_state["catalog_promotion_history_detail_requested"] = True
            st.session_state["catalog_promotion_history_detail_response"] = None
            st.session_state["catalog_promotion_history_detail_error"] = None
            st.session_state["catalog_promotion_audit_offset"] = 0
            st.session_state["catalog_promotion_audit_response"] = None
            st.session_state["catalog_promotion_audit_error"] = None
            st.rerun()

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=PROMOTION_HISTORY_LIMIT,
        offset=st.session_state["catalog_promotion_history_offset"],
    )
    st.caption(f"{current_page} / {total_pages} 페이지 · 전체 {total}건")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "이력 이전",
            key="catalog_promotion_history_previous",
            disabled=not has_previous,
        ):
            st.session_state["catalog_promotion_history_offset"] -= (
                PROMOTION_HISTORY_LIMIT
            )
            st.session_state["catalog_promotion_history_response"] = None
            st.session_state["catalog_promotion_history_error"] = None
            st.session_state["catalog_promotion_history_run_id"] = None
            _clear_catalog_promotion_history_detail(st.session_state)
            st.rerun()
    with next_col:
        if st.button(
            "이력 다음",
            key="catalog_promotion_history_next",
            disabled=not has_next,
        ):
            st.session_state["catalog_promotion_history_offset"] += (
                PROMOTION_HISTORY_LIMIT
            )
            st.session_state["catalog_promotion_history_response"] = None
            st.session_state["catalog_promotion_history_error"] = None
            st.session_state["catalog_promotion_history_run_id"] = None
            _clear_catalog_promotion_history_detail(st.session_state)
            st.rerun()

    if st.session_state.get("catalog_promotion_history_detail_requested"):
        _render_catalog_promotion_history_detail(api_client)


def _fetch_etl_profiles(api_client, session_state) -> list[dict[str, Any]] | None:
    cached = session_state.get("etl_web_run_profiles_response")
    if isinstance(cached, dict):
        return cached.get("items") or []
    if session_state.get("etl_web_run_profiles_error") is not None:
        return None

    try:
        response = api_client.list_etl_profiles()
        session_state["etl_web_run_profiles_response"] = response
        session_state["etl_web_run_profiles_error"] = None
        return response.get("items") or []
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
    ) as error:
        session_state["etl_web_run_profiles_error"] = error
        return None


def _on_etl_web_run_profile_change(session_state) -> None:
    session_state["etl_web_run_result"] = None
    session_state["etl_web_run_error"] = None


def _etl_web_run_error_message(error: Exception) -> str:
    if isinstance(error, ETLUnsupportedProfileError):
        return "지원하지 않는 공급사 프로필입니다."
    if isinstance(error, ETLInvalidUploadError):
        return str(error) or "업로드한 CSV를 처리할 수 없습니다."
    if isinstance(error, CatalogGuardApiConfigurationError):
        return "ETL 실행 API 주소가 설정되지 않았습니다."
    if isinstance(error, CatalogGuardApiConnectionError):
        return "ETL 실행 서버에 연결할 수 없습니다."
    if isinstance(error, CatalogGuardApiTimeoutError):
        return "ETL 실행 서버 응답 시간이 초과되었습니다."
    return "ETL 실행 중 오류가 발생했습니다."


def _submit_etl_web_run(api_client, *, profile_id, uploaded_file) -> None:
    st.session_state["etl_web_run_in_flight"] = True
    st.session_state["etl_web_run_error"] = None
    st.session_state["etl_web_run_result"] = None
    try:
        file_bytes = uploaded_file.getvalue()
        with st.spinner("ETL을 실행하고 있습니다."):
            response = api_client.run_etl_load(
                profile_id=profile_id,
                source_filename=uploaded_file.name,
                file_content=file_bytes,
            )
        st.session_state["etl_web_run_result"] = response
        # 새 배치가 즉시 보이도록 ETL History 캐시만 무효화합니다.
        # Promotion 캐시는 이번 ETL 실행과 무관하므로 건드리지 않습니다.
        st.session_state["etl_load_list_response"] = None
        st.session_state["etl_load_initialized"] = False
        st.session_state["etl_load_offset"] = 0
    except (
        ETLUnsupportedProfileError,
        ETLInvalidUploadError,
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["etl_web_run_error"] = error
    finally:
        st.session_state["etl_web_run_in_flight"] = False


def _render_etl_web_run(api_client) -> None:
    st.subheader("ETL 실행")
    st.write("공급사 CSV를 업로드하고 프로필을 선택해 ETL을 실행합니다.")

    profiles = _fetch_etl_profiles(api_client, st.session_state)
    if profiles is None:
        error = st.session_state.get("etl_web_run_profiles_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    "ETL 프로필 목록을 불러오지 못했습니다.", error
                )
            )
        return
    if not profiles:
        st.info("사용할 수 있는 ETL 프로필이 없습니다.")
        return

    profile_ids = [profile["id"] for profile in profiles]
    profile_labels = {profile["id"]: profile["display_name"] for profile in profiles}
    if st.session_state.get("etl_web_run_selected_profile_id") not in profile_ids:
        st.session_state["etl_web_run_selected_profile_id"] = profile_ids[0]
    st.selectbox(
        "ETL 실행 프로필",
        options=profile_ids,
        format_func=lambda profile_id: profile_labels.get(profile_id, profile_id),
        key="etl_web_run_selected_profile_id",
        on_change=_on_etl_web_run_profile_change,
        args=(st.session_state,),
    )
    uploaded_file = st.file_uploader(
        "공급사 CSV 파일",
        type=["csv"],
        key="etl_web_run_upload_file",
    )

    in_flight = st.session_state.get("etl_web_run_in_flight") is True
    selected_profile_id = st.session_state.get("etl_web_run_selected_profile_id")
    can_run_etl = is_operator()
    if not can_run_etl:
        st.caption("ETL 실행은 운영자 권한이 필요합니다.")
    if st.button(
        "ETL 실행",
        key="etl_web_run_submit",
        type="primary",
        disabled=(
            uploaded_file is None
            or selected_profile_id is None
            or in_flight
            or not can_run_etl
        ),
    ):
        _submit_etl_web_run(
            api_client,
            profile_id=selected_profile_id,
            uploaded_file=uploaded_file,
        )
        st.rerun()

    error = st.session_state.get("etl_web_run_error")
    if error is not None:
        st.error(
            build_etl_api_error_display_message(
                _etl_web_run_error_message(error), error
            )
        )

    result = st.session_state.get("etl_web_run_result")
    if isinstance(result, dict):
        if result.get("created") is True:
            st.success(
                f"ETL 실행이 완료되었습니다. 적재 배치 ID: {result.get('etl_load_run_id')}"
            )
        else:
            st.info(
                "동일한 입력으로 이미 처리된 적재 배치입니다. "
                f"적재 배치 ID: {result.get('etl_load_run_id')}"
            )
        metric_columns = st.columns(3)
        metric_columns[0].metric(
            "전체 행", _display_nullable(result.get("total_rows")), border=True
        )
        metric_columns[1].metric("정상 적재", result.get("loaded_rows", 0), border=True)
        metric_columns[2].metric(
            "변환 거부", _display_nullable(result.get("rejected_rows")), border=True
        )
        st.caption(
            "아래 ETL 적재 이력에서 새로 생성된 배치를 선택해 상세 내용과 운영 반영을 진행하세요."
        )


def render_etl_load_history(api_client=None) -> None:
    initialize_etl_load_state()

    if api_client is None:
        try:
            api_client = get_authenticated_api_client()
        except CatalogGuardApiConfigurationError as error:
            _render_etl_error(error)
            return

    _render_etl_web_run(api_client)

    st.subheader("ETL 적재 이력")
    st.write(
        "공급사 CSV를 PostgreSQL staging에 적재한 배치와 staging 상품을 조회합니다."
    )
    _render_etl_search_controls()

    response = _fetch_etl_load_list(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("etl_load_list_error")
        if error is not None:
            _render_etl_error(error)
        return

    items = response.get("items") or []
    if not items:
        st.info("조건에 맞는 ETL 적재 이력이 없습니다.")
        _render_catalog_promotion_history(api_client)
        return

    st.dataframe(
        build_etl_load_dataframe(items),
        width="stretch",
        hide_index=True,
    )
    run_options = [item["etl_load_run_id"] for item in items]
    option_labels = {
        item["etl_load_run_id"]: build_etl_load_option_label(item)
        for item in items
    }
    if st.session_state.get("etl_load_selected_run_id") not in run_options:
        st.session_state["etl_load_selected_run_id"] = None
    synchronize_catalog_promotion_batch(st.session_state)
    st.selectbox(
        "적재 배치 선택",
        options=[None, *run_options],
        format_func=lambda run_id: (
            "ETL 적재 이력을 선택하세요."
            if run_id is None
            else option_labels.get(run_id, str(run_id))
        ),
        key="etl_load_selected_run_id",
        on_change=_on_etl_load_selection_change,
        args=(st.session_state,),
    )
    if st.button("상세 조회", key="etl_load_show_detail"):
        reset_etl_load_detail_state(st.session_state)
        st.session_state["etl_load_detail_requested"] = True
        st.rerun()

    _render_etl_load_pagination(response)
    _render_catalog_promotion_preview(api_client)
    if st.session_state.get("etl_load_detail_requested", False):
        _render_etl_load_detail(api_client)
    _render_catalog_promotion_history(api_client)


def _rollback_ui_error_message(error: Exception) -> str:
    if isinstance(error, CatalogPromotionNotFoundError):
        return "The selected Promotion run no longer exists."
    if isinstance(error, CatalogPromotionPreviewStaleError):
        return "Rollback preview is stale. Create a new preview before executing rollback."
    return "Rollback request could not be completed."


def _render_catalog_promotion_rollback(api_client, detail: dict[str, Any]) -> None:
    if detail.get("status") != "succeeded":
        return
    st.markdown("#### Rollback")
    st.caption("Rollback restores the selected Promotion's recorded before-state. Later changes are detected as conflicts.")
    run_id = detail.get("promotion_run_id")
    if not isinstance(run_id, int):
        return
    preview_key = "catalog_promotion_rollback_preview"
    result_key = "catalog_promotion_rollback_result"
    if st.button("Rollback Preview", key=preview_key):
        try:
            st.session_state[result_key] = api_client.get_catalog_promotion_rollback_preview(run_id)
            st.session_state["catalog_promotion_rollback_error"] = None
        except Exception as error:
            st.session_state[result_key] = None
            st.session_state["catalog_promotion_rollback_error"] = error
    error = st.session_state.get("catalog_promotion_rollback_error")
    if error is not None:
        st.error(_rollback_ui_error_message(error))
        return
    preview = st.session_state.get(result_key)
    if not isinstance(preview, dict):
        return
    if preview.get("rollback_eligible") is True:
        st.success("Rollback is available.")
    else:
        st.error("Rollback is blocked.")
        for reason in preview.get("blocked_reasons") or []:
            if isinstance(reason, dict) and reason.get("message"):
                st.warning(str(reason["message"]))
    cols = st.columns(3)
    cols[0].metric("Restore", preview.get("restore_count", 0))
    cols[1].metric("Delete", preview.get("delete_count", 0))
    cols[2].metric("Conflict", preview.get("conflict_count", 0))
    items = preview.get("items") or []
    if items:
        st.dataframe(pd.DataFrame([{"Product": item.get("external_product_id"), "Action": item.get("rollback_action"), "Conflict": item.get("conflict")} for item in items]), hide_index=True, width="stretch")
    confirmed = st.checkbox("I reviewed the rollback preview and confirm execution.", key="catalog_promotion_rollback_confirmation", disabled=preview.get("rollback_eligible") is not True)
    expected_hash = preview.get("preview_hash")
    if not is_operator():
        st.caption("Rollback execution requires the operator role.")
    if st.button("Execute Rollback", key="catalog_promotion_rollback_execute", type="primary", disabled=not (confirmed and isinstance(expected_hash, str) and is_operator())):
        try:
            response = api_client.create_catalog_promotion_rollback(run_id, confirmation=True, expected_preview_hash=expected_hash)
            st.session_state[result_key] = None
            st.session_state["catalog_promotion_rollback_error"] = None
            st.success(f"Rollback completed. Rollback run ID: {response.get('rollback_run_id')}")
            st.session_state["catalog_promotion_history_response"] = None
        except Exception as error:
            st.error(_rollback_ui_error_message(error))
