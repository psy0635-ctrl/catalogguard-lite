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
    ETLLoadNotFoundError,
    create_catalogguard_api_client,
)


ETL_LOAD_LIMIT = 10
ETL_PRODUCT_LIMIT = 20
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


def reset_etl_load_detail_state(session_state) -> None:
    session_state["etl_load_detail_requested"] = False
    session_state["etl_load_detail_response"] = None
    session_state["etl_load_detail_error"] = None
    session_state["etl_load_product_offset"] = 0


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


def _on_etl_load_selection_change(session_state) -> None:
    reset_etl_load_detail_state(session_state)


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
        quality_columns[0].metric("전체 입력", f"{total_rows}행")
        quality_columns[1].metric("정상 적재", f"{detail_response.get('loaded_rows', 0)}행")
        quality_columns[2].metric("변환 거부", f"{rejected_rows}행")
        quality_columns[3].metric(
            "정상 처리율",
            format_etl_quality_rate(total_rows, detail_response.get("loaded_rows")),
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
        ):
            st.session_state["etl_load_product_offset"] -= ETL_PRODUCT_LIMIT
            st.session_state["etl_load_detail_response"] = None
            st.rerun()
    with next_col:
        if st.button(
            "상품 다음",
            disabled=not has_next,
            key="etl_product_next",
        ):
            st.session_state["etl_load_product_offset"] += ETL_PRODUCT_LIMIT
            st.session_state["etl_load_detail_response"] = None
            st.rerun()


def render_etl_load_history(api_client=None) -> None:
    initialize_etl_load_state()
    st.subheader("ETL 적재 이력")
    st.write(
        "공급사 CSV를 PostgreSQL staging에 적재한 배치와 staging 상품을 조회합니다."
    )
    _render_etl_search_controls()

    if api_client is None:
        try:
            api_client = create_catalogguard_api_client()
        except CatalogGuardApiConfigurationError as error:
            _render_etl_error(error)
            return

    response = _fetch_etl_load_list(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("etl_load_list_error")
        if error is not None:
            _render_etl_error(error)
        return

    items = response.get("items") or []
    if not items:
        st.info("조건에 맞는 ETL 적재 이력이 없습니다.")
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
        st.session_state["etl_load_selected_run_id"] = run_options[0]
    st.selectbox(
        "적재 배치 선택",
        options=run_options,
        format_func=lambda run_id: option_labels.get(run_id, str(run_id)),
        key="etl_load_selected_run_id",
        on_change=_on_etl_load_selection_change,
        args=(st.session_state,),
    )
    if st.button("상세 조회", key="etl_load_show_detail"):
        reset_etl_load_detail_state(st.session_state)
        st.session_state["etl_load_detail_requested"] = True
        st.rerun()

    _render_etl_load_pagination(response)
    if st.session_state.get("etl_load_detail_requested", False):
        _render_etl_load_detail(api_client)
