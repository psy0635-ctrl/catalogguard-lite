# 역할: 사용자가 CSV를 업로드하고 검수 결과를 확인하는 Streamlit 웹 화면입니다.
import hashlib
import re
from datetime import date, datetime
from math import ceil

import pandas as pd
import streamlit as st

from clients.catalogguard_api import (
    CatalogGuardApiConfigurationError,
    CatalogGuardApiConnectionError,
    CatalogGuardApiResponseError,
    CatalogGuardApiTimeoutError,
    InspectionNotFoundError,
    create_catalogguard_api_client,
)
from config.settings import OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from core.presentation import (
    build_inspection_statistics,
    build_validation_summary_message,
    calculate_dataframe_height,
    filter_result_dataframe,
)
from core.privacy import create_masked_preview
from core.product_template import (
    build_product_template_csv,
    get_product_template_filename,
)
from core.result_exporter import build_result_filename, build_validation_result_csv
from core.upload_validator import (
    CsvUploadValidationError,
    validate_and_read_uploaded_csv,
)


HISTORY_LIMIT_DEFAULT = 10
HISTORY_DISPLAY_COLUMNS = [
    "실행 ID",
    "파일명",
    "검수 시간",
    "전체 상품",
    "전체 문제",
    "오류",
    "주의",
]
HISTORY_SUMMARY_DOWNLOAD_COLUMNS = [*HISTORY_DISPLAY_COLUMNS, "검수 상태"]
HISTORY_SUMMARY_DOWNLOAD_LIMIT = 100
HISTORY_SUMMARY_DOWNLOAD_MAX_PAGES = 10000
HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY = "history_summary_download_cache"
HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY = "history_summary_download_error"
HISTORY_SUMMARY_DOWNLOAD_PREPARE_BUTTON_KEY = "history_summary_download_prepare"
HISTORY_DETAIL_DISPLAY_COLUMNS = [
    "검수 상태",
    "오류 항목",
    "상품 그룹 ID",
    "상품 ID",
    "오류 이유",
    "수정 권장사항",
    "위험 수준",
]
WINDOWS_RESERVED_FILENAME_CHARS = re.compile(r'[\\/:\*\?"<>\|]+')
HISTORY_INVALID_DATE_RANGE_MESSAGE = "시작일은 종료일보다 늦을 수 없습니다."
HISTORY_SUMMARY_DOWNLOAD_EMPTY_MESSAGE = "다운로드할 검수 이력이 없습니다."
HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE = (
    "검수 이력 서버의 응답 형식이 올바르지 않습니다."
)
CSV_FORMULA_PREFIX_CHARS = ("=", "+", "-", "@")
HISTORY_STATUS_OPTIONS = ["전체", "오류", "주의", "정상"]
HISTORY_STATUS_LABEL_TO_QUERY = {
    "전체": None,
    "오류": "error",
    "주의": "warning",
    "정상": "normal",
}
HISTORY_STATUS_QUERY_TO_LABEL = {
    query_value: label
    for label, query_value in HISTORY_STATUS_LABEL_TO_QUERY.items()
    if query_value is not None
}
CURRENT_UPLOAD_FILE_HASH_STATE_KEY = "current_upload_file_hash"
CURRENT_INSPECTION_CREATED_STATE_KEY = "current_inspection_created"
CURRENT_INSPECTION_DETAIL_STATE_KEY = "current_inspection_detail_response"


def build_api_error_display_message(
    message: str,
    error: Exception | None = None,
) -> str:
    request_id = getattr(error, "request_id", None)
    if request_id is None:
        return message

    request_id_message = f"요청 ID: {request_id}"
    if request_id_message in message:
        return message
    return f"{message}\n\n{request_id_message}"


def get_overall_status(error_count: int, warning_count: int) -> str:
    # 오류가 하나라도 있으면 전체 상태는 오류, 오류 없이 주의만 있으면 주의입니다.
    if error_count > 0:
        return "오류"
    if warning_count > 0:
        return "주의"
    return "정상"


def build_file_hash(file_bytes: bytes) -> str:
    # Streamlit 세션 안에서 같은 파일을 다시 저장하려는 클릭을 줄이기 위한 해시입니다.
    # 최종 중복 판단은 서버와 DB가 다시 수행하므로, 이 값은 화면 편의용입니다.
    return hashlib.sha256(file_bytes).hexdigest()


def clear_current_inspection_result(session_state) -> None:
    for key in (
        "saved_file_hash",
        "saved_inspection_run_id",
        CURRENT_INSPECTION_CREATED_STATE_KEY,
        CURRENT_INSPECTION_DETAIL_STATE_KEY,
    ):
        session_state.pop(key, None)


def synchronize_current_upload(session_state, file_hash: str) -> None:
    if session_state.get(CURRENT_UPLOAD_FILE_HASH_STATE_KEY) == file_hash:
        return

    clear_current_inspection_result(session_state)
    session_state[CURRENT_UPLOAD_FILE_HASH_STATE_KEY] = file_hash


def get_current_inspection_detail(session_state, file_hash: str) -> dict | None:
    if session_state.get(CURRENT_UPLOAD_FILE_HASH_STATE_KEY) != file_hash:
        return None
    if session_state.get("saved_file_hash") != file_hash:
        return None
    detail_response = session_state.get(CURRENT_INSPECTION_DETAIL_STATE_KEY)
    return detail_response if isinstance(detail_response, dict) else None


def build_inspection_save_message(
    *,
    inspection_run_id: int,
    created: bool,
) -> str:
    if created:
        return f"검수 결과를 새 이력으로 저장했습니다. 실행 ID: {inspection_run_id}"
    return (
        "이미 검수한 동일 파일이므로 기존 검수 결과를 불러왔습니다. "
        f"실행 ID: {inspection_run_id}"
    )


def apply_inspection_save_response(
    session_state,
    *,
    file_hash: str,
    response: dict,
    detail_response: dict,
) -> tuple[int, bool, str]:
    inspection_run_id = response["inspection_run_id"]
    detail_run_id = detail_response["inspection_run_id"]
    if type(inspection_run_id) is not int or inspection_run_id <= 0:
        raise ValueError("invalid create inspection_run_id")
    if type(detail_run_id) is not int or detail_run_id <= 0:
        raise ValueError("invalid detail inspection_run_id")
    if detail_run_id != inspection_run_id:
        raise ValueError("create and detail inspection_run_id do not match")

    created = response.get("created", True)
    if type(created) is not bool:
        raise ValueError("invalid created value")

    summary = detail_response["summary"]
    results = detail_response["results"]
    required_summary_fields = (
        "total_products",
        "total_issues",
        "error_count",
        "warning_count",
    )
    if not isinstance(summary, dict) or any(
        field not in summary
        or type(summary[field]) is not int
        or summary[field] < 0
        for field in required_summary_fields
    ):
        raise ValueError("invalid inspection summary")

    required_result_fields = (
        "status",
        "product_group_id",
        "product_id",
        "error_field",
        "reason",
        "recommendation",
        "risk_level",
    )
    if not isinstance(results, list) or any(
        not isinstance(result, dict)
        or any(
            field not in result or not isinstance(result[field], str)
            for field in required_result_fields
        )
        for result in results
    ):
        raise ValueError("invalid inspection results")

    session_state["saved_file_hash"] = file_hash
    session_state["saved_inspection_run_id"] = inspection_run_id
    session_state[CURRENT_INSPECTION_CREATED_STATE_KEY] = created
    session_state[CURRENT_INSPECTION_DETAIL_STATE_KEY] = dict(detail_response)
    return (
        inspection_run_id,
        created,
        build_inspection_save_message(
            inspection_run_id=inspection_run_id,
            created=created,
        ),
    )


def calculate_history_pagination(
    *,
    total: int,
    limit: int,
    offset: int,
) -> tuple[int, int, bool, bool]:
    safe_total = max(0, total)
    safe_limit = max(1, limit)
    safe_offset = max(0, offset)

    current_page = safe_offset // safe_limit + 1
    total_pages = max(1, ceil(safe_total / safe_limit))
    has_previous = safe_offset > 0
    has_next = safe_offset + safe_limit < safe_total
    return current_page, total_pages, has_previous, has_next


def format_history_datetime(value: object) -> str:
    if value is None:
        return ""

    text_value = str(value)
    normalized_value = (
        f"{text_value[:-1]}+00:00" if text_value.endswith("Z") else text_value
    )
    try:
        parsed_datetime = datetime.fromisoformat(normalized_value)
    except ValueError:
        return text_value

    return parsed_datetime.strftime("%Y-%m-%d %H:%M:%S")


def build_history_dataframe(items: list[dict]) -> pd.DataFrame:
    rows = [
        {
            "실행 ID": item.get("inspection_run_id"),
            "파일명": item.get("source_filename"),
            "검수 시간": format_history_datetime(item.get("created_at")),
            "전체 상품": item.get("total_products"),
            "전체 문제": item.get("total_issues"),
            "오류": item.get("error_count"),
            "주의": item.get("warning_count"),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=HISTORY_DISPLAY_COLUMNS)


def build_history_summary_dataframe(items: list[dict]) -> pd.DataFrame:
    rows = []
    for item in items:
        error_count = int(item.get("error_count") or 0)
        warning_count = int(item.get("warning_count") or 0)
        rows.append(
            {
                "실행 ID": item.get("inspection_run_id"),
                "파일명": escape_csv_formula_value(item.get("source_filename")),
                "검수 시간": format_history_datetime(item.get("created_at")),
                "전체 상품": item.get("total_products"),
                "전체 문제": item.get("total_issues"),
                "오류": error_count,
                "주의": warning_count,
                "검수 상태": get_overall_status(error_count, warning_count),
            }
        )
    return pd.DataFrame(rows, columns=HISTORY_SUMMARY_DOWNLOAD_COLUMNS)


def escape_csv_formula_value(value: object) -> object:
    if value is None:
        return None

    text_value = str(value)
    if text_value.startswith(CSV_FORMULA_PREFIX_CHARS):
        return f"'{text_value}"
    return value


def build_history_summary_csv(items: list[dict]) -> bytes:
    dataframe = build_history_summary_dataframe(items)
    return dataframe.to_csv(index=False).encode("utf-8-sig")


def build_history_summary_download_filename(now: datetime | None = None) -> str:
    timestamp_source = now or datetime.now()
    return f"inspection_history_{timestamp_source:%Y%m%d_%H%M%S}.csv"


def build_history_summary_download_cache_key(
    session_state,
    *,
    total: int,
) -> tuple[tuple[str, str], ...]:
    request_params = build_history_list_request_params(
        session_state,
        limit=HISTORY_SUMMARY_DOWNLOAD_LIMIT,
        offset=0,
    )
    return (
        ("total", str(max(0, int(total)))),
        ("filename", str(request_params.get("filename", ""))),
        ("start_date", str(request_params.get("start_date", ""))),
        ("end_date", str(request_params.get("end_date", ""))),
        ("status", str(request_params.get("status", ""))),
    )


def clear_history_summary_download_cache(session_state) -> None:
    session_state.pop(HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY, None)
    session_state.pop(HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY, None)


def show_history_summary_download_error(
    session_state,
    message: str,
    error: Exception | None = None,
) -> None:
    display_message = build_api_error_display_message(message, error)
    session_state[HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY] = display_message
    st.error(display_message)


def validate_history_summary_page_response(response: dict) -> tuple[list[dict], int]:
    if not isinstance(response, dict):
        raise CatalogGuardApiResponseError(
            HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE
        )

    page_items = response.get("items")
    total = response.get("total")
    if (
        not isinstance(page_items, list)
        or type(total) is not int
        or total < 0
        or len(page_items) > HISTORY_SUMMARY_DOWNLOAD_LIMIT
        or any(not isinstance(item, dict) for item in page_items)
    ):
        raise CatalogGuardApiResponseError(
            HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE
        )
    if total == 0 and page_items:
        raise CatalogGuardApiResponseError(
            HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE
        )
    if total > 0 and not page_items:
        raise CatalogGuardApiResponseError(
            HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE
        )
    return page_items, total


def fetch_all_history_summary_items(api_client, session_state) -> tuple[list[dict], int]:
    all_items: list[dict] = []
    seen_inspection_run_ids: set[object] = set()
    offset = 0

    for _ in range(HISTORY_SUMMARY_DOWNLOAD_MAX_PAGES):
        request_params = build_history_list_request_params(
            session_state,
            limit=HISTORY_SUMMARY_DOWNLOAD_LIMIT,
            offset=offset,
        )
        page_response = api_client.list_inspections(**request_params)
        page_items, total = validate_history_summary_page_response(page_response)
        if total == 0:
            return [], 0

        for page_item in page_items:
            inspection_run_id = page_item.get("inspection_run_id")
            if inspection_run_id is None:
                continue
            if inspection_run_id in seen_inspection_run_ids:
                raise CatalogGuardApiResponseError(
                    HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE
                )
            seen_inspection_run_ids.add(inspection_run_id)

        all_items.extend(page_items)
        if len(all_items) > total:
            raise CatalogGuardApiResponseError(
                HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE
            )
        if len(all_items) >= total:
            return all_items, total
        if len(page_items) < HISTORY_SUMMARY_DOWNLOAD_LIMIT:
            raise CatalogGuardApiResponseError(
                HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE
            )

        offset += HISTORY_SUMMARY_DOWNLOAD_LIMIT

    raise CatalogGuardApiResponseError(HISTORY_SUMMARY_DOWNLOAD_INVALID_RESPONSE_MESSAGE)


def format_history_option_label(item: dict) -> str:
    return (
        f"{item.get('inspection_run_id')} · "
        f"{item.get('source_filename')} · "
        f"{format_history_datetime(item.get('created_at'))}"
    )


def build_history_detail_dataframe(results: list[dict]) -> pd.DataFrame:
    rows = [
        {
            "검수 상태": result.get("status"),
            "오류 항목": result.get("error_field"),
            "상품 그룹 ID": result.get("product_group_id"),
            "상품 ID": result.get("product_id"),
            "오류 이유": result.get("reason"),
            "수정 권장사항": result.get("recommendation"),
            "위험 수준": result.get("risk_level"),
        }
        for result in results
    ]
    return pd.DataFrame(rows, columns=HISTORY_DETAIL_DISPLAY_COLUMNS)


def build_history_detail_csv(dataframe: pd.DataFrame) -> bytes:
    ordered_dataframe = dataframe.reindex(columns=HISTORY_DETAIL_DISPLAY_COLUMNS)
    return ordered_dataframe.to_csv(index=False).encode("utf-8-sig")


def build_history_download_filename(
    inspection_run_id: int,
    source_filename: str | None,
) -> str:
    run_id_text = WINDOWS_RESERVED_FILENAME_CHARS.sub(
        "_",
        str(inspection_run_id).strip() or "unknown",
    ).strip(" ._")
    raw_source_name = str(source_filename or "").strip()
    if raw_source_name.lower().endswith(".csv"):
        raw_source_name = raw_source_name[:-4]
    safe_source_name = WINDOWS_RESERVED_FILENAME_CHARS.sub(
        "_",
        raw_source_name,
    ).strip(" ._")
    if not safe_source_name:
        safe_source_name = "inspection"

    return f"inspection_{run_id_text}_{safe_source_name}_results.csv"


def should_show_history_detail_download(dataframe: pd.DataFrame) -> bool:
    return not dataframe.empty


def normalize_history_filename_query(value: object) -> str:
    # 검색어 앞뒤 공백을 없애서 " products "와 "products"를 같은 검색어로 봅니다.
    return str(value or "").strip()


def normalize_history_date_query(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return date.fromisoformat(text_value)
    except ValueError:
        return None


def normalize_history_status_input(value: object) -> str:
    status_label = str(value or "").strip()
    if status_label in HISTORY_STATUS_LABEL_TO_QUERY:
        return status_label
    return "전체"


def normalize_history_status_query(value: object) -> str | None:
    status_query = "" if value is None else str(value).strip()
    if status_query in HISTORY_STATUS_QUERY_TO_LABEL:
        return status_query
    return None


def get_history_filename_query(session_state) -> str:
    return normalize_history_filename_query(
        session_state.get("history_filename_query", "")
    )


def get_history_start_date_query(session_state) -> date | None:
    return normalize_history_date_query(session_state.get("history_start_date_query"))


def get_history_end_date_query(session_state) -> date | None:
    return normalize_history_date_query(session_state.get("history_end_date_query"))


def get_history_status_query(session_state) -> str | None:
    return normalize_history_status_query(session_state.get("history_status_query"))


def apply_history_search(session_state) -> None:
    # 검색 버튼을 누른 순간의 입력값만 실제 검색 조건으로 확정합니다.
    filename_query = normalize_history_filename_query(
        session_state.get("history_filename_input", "")
    )
    start_date_query = normalize_history_date_query(
        session_state.get("history_start_date_input")
    )
    end_date_query = normalize_history_date_query(
        session_state.get("history_end_date_input")
    )
    status_input = normalize_history_status_input(
        session_state.get("history_status_input", "전체")
    )
    status_query = HISTORY_STATUS_LABEL_TO_QUERY[status_input]
    if (
        start_date_query is not None
        and end_date_query is not None
        and start_date_query > end_date_query
    ):
        session_state["history_filter_error"] = HISTORY_INVALID_DATE_RANGE_MESSAGE
        return

    session_state["history_filename_input"] = filename_query
    session_state["history_filename_query"] = filename_query
    session_state["history_start_date_query"] = start_date_query
    session_state["history_end_date_query"] = end_date_query
    session_state["history_status_input"] = status_input
    session_state["history_status_query"] = status_query
    session_state["history_filter_error"] = None
    # 새 검색은 항상 첫 페이지부터 보여줘야 하므로 offset을 0으로 돌립니다.
    session_state["history_offset"] = 0
    clear_history_summary_download_cache(session_state)


def apply_history_filename_search(session_state) -> None:
    apply_history_search(session_state)


def reset_history_search(session_state) -> None:
    # 초기화는 입력창과 실제 검색 조건을 모두 비워 전체 목록을 다시 보게 합니다.
    session_state["history_filename_input"] = ""
    session_state["history_filename_query"] = ""
    session_state["history_start_date_input"] = None
    session_state["history_end_date_input"] = None
    session_state["history_start_date_query"] = None
    session_state["history_end_date_query"] = None
    session_state["history_status_input"] = "전체"
    session_state["history_status_query"] = None
    session_state["history_filter_error"] = None
    session_state["history_offset"] = 0
    clear_history_summary_download_cache(session_state)


def reset_history_filename_search(session_state) -> None:
    reset_history_search(session_state)


def build_history_list_request_params(
    session_state,
    *,
    limit: int,
    offset: int,
) -> dict[str, int | str]:
    # API에는 기본 페이지 정보(limit/offset)를 항상 보내고, 검색어는 있을 때만 보냅니다.
    params: dict[str, int | str] = {"limit": limit, "offset": offset}
    filename_query = get_history_filename_query(session_state)
    if filename_query:
        params["filename"] = filename_query
    start_date_query = get_history_start_date_query(session_state)
    if start_date_query is not None:
        params["start_date"] = start_date_query.isoformat()
    end_date_query = get_history_end_date_query(session_state)
    if end_date_query is not None:
        params["end_date"] = end_date_query.isoformat()
    status_query = get_history_status_query(session_state)
    if status_query is not None:
        params["status"] = status_query
    return params


def get_empty_history_message(
    filename_query: str,
    start_date_query: date | None = None,
    end_date_query: date | None = None,
    status_query: str | None = None,
) -> str:
    if normalize_history_filename_query(filename_query):
        return "입력한 파일명과 일치하는 검수 이력이 없습니다."
    if start_date_query is not None or end_date_query is not None:
        return "선택한 날짜 조건과 일치하는 검수 이력이 없습니다."
    if normalize_history_status_query(status_query) is not None:
        return "선택한 검수 상태와 일치하는 검수 이력이 없습니다."
    return "저장된 검수 이력이 없습니다."


def build_history_filter_caption(session_state) -> str:
    parts = []
    filename_query = get_history_filename_query(session_state)
    if filename_query:
        parts.append(f"파일명: {filename_query}")

    start_date_query = get_history_start_date_query(session_state)
    end_date_query = get_history_end_date_query(session_state)
    if start_date_query is not None:
        parts.append(f"시작일: {start_date_query.isoformat()}")
    if end_date_query is not None:
        parts.append(f"종료일: {end_date_query.isoformat()}")
    status_query = get_history_status_query(session_state)
    if status_query is not None:
        parts.append(f"검수 상태: {HISTORY_STATUS_QUERY_TO_LABEL[status_query]}")

    if not parts:
        return ""
    return "적용 중인 검색 조건 · " + " · ".join(parts)


def return_history_list_state(session_state) -> None:
    # 상세 화면에서 목록으로 돌아와도 검색어와 현재 페이지는 유지합니다.
    session_state["history_view_mode"] = "list"
    session_state["selected_inspection_run_id"] = None


def initialize_history_state() -> None:
    if "history_limit" not in st.session_state:
        st.session_state.history_limit = HISTORY_LIMIT_DEFAULT
    if "history_offset" not in st.session_state:
        st.session_state.history_offset = 0
    if "history_view_mode" not in st.session_state:
        st.session_state.history_view_mode = "list"
    if "selected_inspection_run_id" not in st.session_state:
        st.session_state.selected_inspection_run_id = None
    if "history_filename_input" not in st.session_state:
        st.session_state.history_filename_input = ""
    if "history_filename_query" not in st.session_state:
        st.session_state.history_filename_query = ""
    if "history_start_date_input" not in st.session_state:
        st.session_state.history_start_date_input = None
    if "history_end_date_input" not in st.session_state:
        st.session_state.history_end_date_input = None
    if "history_start_date_query" not in st.session_state:
        st.session_state.history_start_date_query = None
    if "history_end_date_query" not in st.session_state:
        st.session_state.history_end_date_query = None
    if "history_status_input" not in st.session_state:
        st.session_state.history_status_input = "전체"
    if "history_status_query" not in st.session_state:
        st.session_state.history_status_query = None
    if "history_filter_error" not in st.session_state:
        st.session_state.history_filter_error = None


def render_inspection_statistics(
    results_df: pd.DataFrame,
    expected_total_issues: int | None = None,
) -> None:
    st.subheader("검수 결과 통계")
    st.caption("아래 통계는 필터 적용 전 전체 검수 결과를 기준으로 합니다.")

    try:
        statistics = build_inspection_statistics(results_df)
    except ValueError:
        st.error("검수 결과 통계를 표시할 수 없습니다.")
        return

    issue_counts = statistics["issue_counts"]
    risk_counts = statistics["risk_counts"]
    product_counts = statistics["product_counts"]
    total_issues = statistics["total_issues"]

    if expected_total_issues is not None and expected_total_issues != total_issues:
        st.error(
            "검수 요약과 상세 결과 수가 일치하지 않아 통계를 표시할 수 없습니다."
        )
        return

    if total_issues == 0:
        st.info("발견된 문제가 없어 통계로 표시할 항목이 없습니다.")
        return

    top_products = product_counts.head(5)
    table_height = calculate_dataframe_height(
        max(len(issue_counts), len(risk_counts), len(top_products))
    )
    issue_column, risk_column, product_column = st.columns(3)

    for column, title, dataframe in (
        (issue_column, "오류 항목별 발생 건수", issue_counts),
        (risk_column, "위험 수준별 발생 건수", risk_counts),
        (product_column, "문제가 많은 상품 TOP 5", top_products),
    ):
        with column:
            st.markdown(f"**{title}**")
            st.dataframe(
                dataframe,
                hide_index=True,
                width="stretch",
                height=table_height,
            )


def render_inspection_save_failure(
    detail_message: str,
    error: Exception | None = None,
) -> None:
    st.error("검수를 완료하지 못했습니다.")
    st.caption(build_api_error_display_message(detail_message, error))


def render_inspection_save_button(
    *,
    source_filename: str,
    file_bytes: bytes,
    content_type: str,
) -> dict | None:
    file_hash = build_file_hash(file_bytes)
    synchronize_current_upload(st.session_state, file_hash)
    detail_response = get_current_inspection_detail(
        st.session_state,
        file_hash,
    )

    st.caption("검수를 실행하면 결과가 검수 이력에 저장됩니다.")
    st.caption("동일한 파일과 검수 버전은 중복 저장되지 않습니다.")
    if st.button("검수 실행 및 이력 저장", key="save_inspection_history"):
        if detail_response is None:
            clear_current_inspection_result(st.session_state)
        else:
            inspection_run_id = int(detail_response["inspection_run_id"])
            created = bool(
                st.session_state.get(CURRENT_INSPECTION_CREATED_STATE_KEY, True)
            )
            message = build_inspection_save_message(
                inspection_run_id=inspection_run_id,
                created=created,
            )

        if detail_response is not None:
            if created:
                st.success(message)
            else:
                st.info(message)
            return detail_response

        try:
            api_client = create_catalogguard_api_client()
            response = api_client.create_inspection(
                source_filename=source_filename,
                file_content=file_bytes,
                content_type=content_type,
            )
            inspection_run_id = int(response["inspection_run_id"])
            detail_response = api_client.get_inspection_detail(inspection_run_id)
            _, created, message = apply_inspection_save_response(
                st.session_state,
                file_hash=file_hash,
                response=response,
                detail_response=detail_response,
            )
        except CatalogGuardApiConfigurationError as error:
            clear_current_inspection_result(st.session_state)
            render_inspection_save_failure(
                "검수 API 주소가 설정되지 않았습니다.", error
            )
            return None
        except CatalogGuardApiConnectionError as error:
            clear_current_inspection_result(st.session_state)
            render_inspection_save_failure(
                "검수 서버에 연결할 수 없습니다.", error
            )
            return None
        except CatalogGuardApiTimeoutError as error:
            clear_current_inspection_result(st.session_state)
            render_inspection_save_failure(
                "검수 서버 응답 시간이 초과되었습니다.", error
            )
            return None
        except InspectionNotFoundError as error:
            clear_current_inspection_result(st.session_state)
            render_inspection_save_failure(
                "저장된 검수 상세 결과를 찾을 수 없습니다.", error
            )
            return None
        except (CatalogGuardApiResponseError, KeyError, TypeError, ValueError) as error:
            clear_current_inspection_result(st.session_state)
            render_inspection_save_failure(
                "검수 서버에서 오류가 발생했습니다.", error
            )
            return None

        if created:
            st.success(message)
        else:
            st.info(message)
        return detail_response

    if detail_response is None:
        return None

    inspection_run_id = int(detail_response["inspection_run_id"])
    created = bool(st.session_state.get(CURRENT_INSPECTION_CREATED_STATE_KEY, True))
    message = build_inspection_save_message(
        inspection_run_id=inspection_run_id,
        created=created,
    )
    if created:
        st.success(message)
    else:
        st.info(message)
    return detail_response


def render_uploaded_inspection_result(
    detail_response: dict,
    *,
    fallback_source_filename: str,
) -> None:
    summary = detail_response.get("summary") or {}
    total_products = summary.get("total_products", 0)
    issue_count = summary.get("total_issues", 0)
    error_count = summary.get("error_count", 0)
    warning_count = summary.get("warning_count", 0)
    overall_status = get_overall_status(error_count, warning_count)

    st.subheader("검수 요약")
    status_col, product_col, issue_col, error_col, warning_col = st.columns(5)
    status_col.metric("전체 상태", overall_status)
    product_col.metric("전체 상품 수", total_products)
    issue_col.metric("전체 문제 수", issue_count)
    error_col.metric("오류 수", error_count)
    warning_col.metric("주의 수", warning_count)

    summary_message = build_validation_summary_message(
        issue_count,
        error_count,
        warning_count,
    )
    if error_count > 0:
        st.error(summary_message)
    elif warning_count > 0:
        st.warning(summary_message)
    else:
        st.success("검사가 완료되었습니다. 발견된 문제가 없습니다.")

    result_df = build_history_detail_dataframe(detail_response.get("results", []))
    render_inspection_statistics(
        result_df,
        expected_total_issues=issue_count,
    )
    if issue_count <= 0:
        return

    rule_options = [
        "전체",
        *sorted(
            rule
            for rule in result_df["오류 항목"].dropna().unique().tolist()
            if rule
        ),
    ]

    st.subheader("검수 결과")
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        status_filter = st.selectbox("검수 상태", ["전체", "오류", "주의"])
    with filter_col2:
        rule_filter = st.selectbox("오류 항목", rule_options)
    with filter_col3:
        product_id_query = st.text_input("상품 ID 검색", placeholder="예: P003")

    filtered_result_df = filter_result_dataframe(
        result_df,
        status_filter=status_filter,
        rule_filter=rule_filter,
        product_id_query=product_id_query,
    )

    st.caption(f"현재 조건에 맞는 검수 결과: {len(filtered_result_df)}건")
    if filtered_result_df.empty:
        st.info("선택한 조건에 맞는 검수 결과가 없습니다.")
        return

    st.dataframe(
        filtered_result_df,
        height=calculate_dataframe_height(len(filtered_result_df)),
        width="stretch",
        hide_index=True,
    )
    source_filename = (
        detail_response.get("source_filename") or fallback_source_filename
    )
    st.download_button(
        "현재 필터 결과 CSV 다운로드",
        data=build_validation_result_csv(filtered_result_df),
        file_name=build_result_filename(source_filename),
        mime="text/csv",
    )


def render_csv_inspection_tab() -> None:
    st.subheader("CSV 입력 템플릿")
    st.write("올바른 컬럼 구조가 필요한 경우 아래 템플릿을 내려받아 작성하세요.")
    st.caption(
        "템플릿에는 가짜 예시 상품 1개가 포함되어 있습니다. "
        "실제 사용 전 예시 행을 삭제하거나 상품 정보로 교체해 주세요."
    )
    st.caption(f"필수 컬럼: {', '.join(REQUIRED_COLUMNS)}")
    st.caption(f"선택 컬럼: {', '.join(OPTIONAL_COLUMNS)}")
    st.download_button(
        "CSV 입력 템플릿 다운로드",
        data=build_product_template_csv(),
        file_name=get_product_template_filename(),
        mime="text/csv",
    )

    uploaded_file = st.file_uploader("CSV 파일 업로드", type=["csv"])

    # 파일이 없으면 아래 검사 코드를 실행하지 않고 CSV 탭 렌더링만 마칩니다.
    if uploaded_file is None:
        st.info("검사할 CSV 파일을 업로드해 주세요.")
        return

    file_bytes = uploaded_file.getvalue()
    file_hash = build_file_hash(file_bytes)
    synchronize_current_upload(st.session_state, file_hash)

    try:
        validated_df = validate_and_read_uploaded_csv(uploaded_file.name, file_bytes)
        masked_preview_df = create_masked_preview(validated_df)
    except CsvUploadValidationError as error:
        st.error(str(error))
        return
    except Exception:
        st.error("파일 처리 중 오류가 발생했습니다. CSV 형식과 내용을 확인해 주세요.")
        return

    st.subheader("상품 데이터 미리보기")
    preview_rows = masked_preview_df.head(100)
    st.dataframe(
        preview_rows,
        height=calculate_dataframe_height(len(preview_rows)),
        width="stretch",
        hide_index=True,
    )
    if len(masked_preview_df) > len(preview_rows):
        st.caption(f"전체 {len(masked_preview_df)}행 중 앞 100행만 표시합니다.")

    detail_response = render_inspection_save_button(
        source_filename=uploaded_file.name,
        file_bytes=file_bytes,
        content_type=getattr(uploaded_file, "type", None) or "text/csv",
    )
    if detail_response is None:
        return
    render_uploaded_inspection_result(
        detail_response,
        fallback_source_filename=uploaded_file.name,
    )


def render_inspection_history_tab() -> None:
    st.subheader("검수 이력")
    st.write("저장된 검수 실행 기록을 최근 순서대로 확인합니다.")

    initialize_history_state()

    try:
        api_client = create_catalogguard_api_client()
    except CatalogGuardApiConfigurationError:
        st.warning("검수 이력 API 주소가 설정되지 않았습니다.")
        st.caption("로컬 실행 시 CATALOGGUARD_API_BASE_URL 환경변수를 설정해 주세요.")
        return

    if st.session_state.history_view_mode == "detail":
        render_inspection_history_detail(api_client)
        return

    render_inspection_history_list(api_client)


def render_history_filename_search_controls() -> None:
    # 입력만으로는 검색하지 않고, 사용자가 검색 버튼을 누를 때만 목록을 다시 조회합니다.
    input_col, start_col, end_col, status_col, search_col, reset_col = st.columns(
        [3, 1.4, 1.4, 1.2, 1, 1]
    )
    with input_col:
        st.text_input(
            "파일명 검색",
            placeholder="예: products_dev.csv",
            key="history_filename_input",
            max_chars=100,
        )
    with start_col:
        st.date_input(
            "시작일",
            value=st.session_state.get("history_start_date_input"),
            key="history_start_date_input",
        )
    with end_col:
        st.date_input(
            "종료일",
            value=st.session_state.get("history_end_date_input"),
            key="history_end_date_input",
        )
    with status_col:
        st.selectbox(
            "검수 상태",
            options=HISTORY_STATUS_OPTIONS,
            key="history_status_input",
        )
    with search_col:
        st.button(
            "검색",
            key="history_filename_search",
            on_click=apply_history_search,
            args=(st.session_state,),
        )
    with reset_col:
        st.button(
            "초기화",
            key="history_filename_reset",
            on_click=reset_history_search,
            args=(st.session_state,),
        )


def render_history_summary_download(api_client, session_state, *, total: int) -> None:
    if total <= 0:
        clear_history_summary_download_cache(session_state)
        st.info(HISTORY_SUMMARY_DOWNLOAD_EMPTY_MESSAGE)
        return

    cache_key = build_history_summary_download_cache_key(
        session_state,
        total=total,
    )
    prepared_download = session_state.get(HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY)
    if not (
        isinstance(prepared_download, dict)
        and prepared_download.get("cache_key") == cache_key
    ):
        st.caption(f"현재 검색 조건에 맞는 전체 {total}건을 다운로드할 수 있습니다.")

    if st.button(
        "CSV 다운로드 준비",
        key=HISTORY_SUMMARY_DOWNLOAD_PREPARE_BUTTON_KEY,
    ):
        try:
            history_items, download_total = fetch_all_history_summary_items(
                api_client,
                session_state,
            )
            if not history_items:
                clear_history_summary_download_cache(session_state)
                st.info(HISTORY_SUMMARY_DOWNLOAD_EMPTY_MESSAGE)
                return
            csv_bytes = build_history_summary_csv(history_items)
        except CatalogGuardApiConnectionError as error:
            clear_history_summary_download_cache(session_state)
            show_history_summary_download_error(
                session_state,
                "전체 검수 이력 CSV를 준비하는 중 서버에 연결할 수 없습니다.",
                error,
            )
            return
        except CatalogGuardApiTimeoutError as error:
            clear_history_summary_download_cache(session_state)
            show_history_summary_download_error(
                session_state,
                "전체 검수 이력 CSV를 준비하는 중 서버 응답 시간이 초과되었습니다.",
                error,
            )
            return
        except CatalogGuardApiResponseError as error:
            clear_history_summary_download_cache(session_state)
            show_history_summary_download_error(
                session_state,
                "전체 검수 이력 CSV를 준비하는 중 오류가 발생했습니다.",
                error,
            )
            return
        except ValueError as error:
            clear_history_summary_download_cache(session_state)
            show_history_summary_download_error(
                session_state,
                "현재 검색 조건으로 전체 검수 이력 CSV를 준비할 수 없습니다.",
                error,
            )
            return

        session_state.pop(HISTORY_SUMMARY_DOWNLOAD_ERROR_STATE_KEY, None)
        cache_key = build_history_summary_download_cache_key(
            session_state,
            total=download_total,
        )
        session_state[HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY] = {
            "cache_key": cache_key,
            "csv_bytes": csv_bytes,
            "file_name": build_history_summary_download_filename(),
            "total": download_total,
        }

    prepared_download = session_state.get(HISTORY_SUMMARY_DOWNLOAD_CACHE_STATE_KEY)
    if not (
        isinstance(prepared_download, dict)
        and prepared_download.get("cache_key") == cache_key
    ):
        return

    st.caption(f"준비된 전체 {prepared_download['total']}건을 다운로드합니다.")
    st.download_button(
        "전체 검수 이력 요약 CSV 다운로드",
        data=prepared_download["csv_bytes"],
        file_name=prepared_download["file_name"],
        mime="text/csv",
        key="history_summary_download",
    )


def render_inspection_history_list(api_client) -> None:
    render_history_filename_search_controls()
    if st.session_state.get("history_filter_error"):
        st.error(st.session_state.history_filter_error)
        return

    limit = st.session_state.history_limit
    offset = st.session_state.history_offset
    # 현재 페이지와 실제 적용 중인 파일명 검색어를 API Client에 넘길 형태로 만듭니다.
    request_params = build_history_list_request_params(
        st.session_state,
        limit=limit,
        offset=offset,
    )

    try:
        history_response = api_client.list_inspections(**request_params)
    except CatalogGuardApiConnectionError as error:
        st.error(build_api_error_display_message("검수 이력 서버에 연결할 수 없습니다.", error))
        return
    except CatalogGuardApiTimeoutError as error:
        st.error(
            build_api_error_display_message("검수 이력 서버 응답 시간이 초과되었습니다.", error)
        )
        return
    except InspectionNotFoundError as error:
        st.error(build_api_error_display_message("검수 실행 결과를 찾을 수 없습니다.", error))
        return
    except CatalogGuardApiResponseError as error:
        st.error(
            build_api_error_display_message("검수 이력을 불러오는 중 오류가 발생했습니다.", error)
        )
        return
    except ValueError:
        st.error("파일명 검색어는 최대 100자까지 입력할 수 있습니다.")
        return

    total = max(0, int(history_response["total"]))
    if total > 0 and offset >= total:
        st.session_state.history_offset = ((total - 1) // limit) * limit
        st.rerun()

    filter_caption = build_history_filter_caption(st.session_state)
    if filter_caption:
        st.caption(filter_caption)

    history_dataframe = build_history_dataframe(history_response["items"])
    filename_query = get_history_filename_query(st.session_state)
    start_date_query = get_history_start_date_query(st.session_state)
    end_date_query = get_history_end_date_query(st.session_state)
    status_query = get_history_status_query(st.session_state)
    if history_dataframe.empty:
        st.info(
            get_empty_history_message(
                filename_query,
                start_date_query,
                end_date_query,
                status_query,
            )
        )
        st.caption(HISTORY_SUMMARY_DOWNLOAD_EMPTY_MESSAGE)
    else:
        st.dataframe(
            history_dataframe,
            width="stretch",
            hide_index=True,
        )
        render_history_summary_download(
            api_client,
            st.session_state,
            total=total,
        )
        run_options = [
            item["inspection_run_id"]
            for item in history_response["items"]
            if item.get("inspection_run_id") is not None
        ]
        option_labels = {
            item["inspection_run_id"]: format_history_option_label(item)
            for item in history_response["items"]
            if item.get("inspection_run_id") is not None
        }
        if run_options:
            selected_run_id = st.selectbox(
                "검수 실행 선택",
                options=run_options,
                format_func=lambda run_id: option_labels.get(run_id, str(run_id)),
                key="history_run_selector",
            )
            if st.button("상세 보기", key="history_show_detail"):
                st.session_state.selected_inspection_run_id = int(selected_run_id)
                st.session_state.history_view_mode = "detail"
                st.rerun()

    current_page, total_pages, has_previous, has_next = calculate_history_pagination(
        total=total,
        limit=limit,
        offset=offset,
    )
    st.caption(f"{current_page} / {total_pages} 페이지 · 전체 {total}건")

    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button("이전", disabled=not has_previous, key="history_previous"):
            st.session_state.history_offset = max(0, offset - limit)
            st.rerun()
    with next_col:
        if st.button("다음", disabled=not has_next, key="history_next"):
            st.session_state.history_offset = offset + limit
            st.rerun()


def return_to_history_list() -> None:
    return_history_list_state(st.session_state)
    st.rerun()


def render_inspection_history_detail(api_client) -> None:
    st.subheader("검수 상세 결과")
    if st.button("목록으로 돌아가기", key="history_back_to_list"):
        return_to_history_list()

    inspection_run_id = st.session_state.selected_inspection_run_id
    if inspection_run_id is None:
        st.warning("선택한 검수 실행이 없습니다.")
        return

    try:
        detail_response = api_client.get_inspection_detail(inspection_run_id)
    except InspectionNotFoundError as error:
        st.error(
            build_api_error_display_message("선택한 검수 실행 결과를 찾을 수 없습니다.", error)
        )
        return
    except CatalogGuardApiConnectionError as error:
        st.error(build_api_error_display_message("검수 이력 서버에 연결할 수 없습니다.", error))
        return
    except CatalogGuardApiTimeoutError as error:
        st.error(
            build_api_error_display_message("검수 이력 서버 응답 시간이 초과되었습니다.", error)
        )
        return
    except CatalogGuardApiResponseError as error:
        st.error(
            build_api_error_display_message("검수 상세 결과를 불러오는 중 오류가 발생했습니다.", error)
        )
        return

    st.write(f"파일명: {detail_response.get('source_filename', '')}")
    st.write(f"검수 시간: {format_history_datetime(detail_response.get('created_at'))}")
    st.write(f"실행 ID: {detail_response.get('inspection_run_id', '')}")

    summary = detail_response.get("summary") or {}
    product_col, issue_col, error_col, warning_col = st.columns(4)
    product_col.metric("전체 상품", summary.get("total_products", 0))
    issue_col.metric("전체 문제", summary.get("total_issues", 0))
    error_col.metric("오류", summary.get("error_count", 0))
    warning_col.metric("주의", summary.get("warning_count", 0))

    detail_dataframe = build_history_detail_dataframe(detail_response.get("results", []))
    render_inspection_statistics(
        detail_dataframe,
        expected_total_issues=summary.get("total_issues", 0),
    )
    if not should_show_history_detail_download(detail_dataframe):
        st.info("이 검수 실행에서 발견된 문제가 없습니다.")
        return

    st.dataframe(
        detail_dataframe,
        height=calculate_dataframe_height(len(detail_dataframe)),
        width="stretch",
        hide_index=True,
    )
    st.download_button(
        "상세 결과 CSV 다운로드",
        data=build_history_detail_csv(detail_dataframe),
        file_name=build_history_download_filename(
            inspection_run_id,
            detail_response.get("source_filename", ""),
        ),
        mime="text/csv",
    )


def main() -> None:
    st.set_page_config(page_title="CatalogGuard Lite", layout="wide")

    st.title("CatalogGuard Lite")
    st.write("상품 카탈로그 CSV 파일의 누락 값과 데이터 오류를 검사합니다.")

    inspection_tab, history_tab = st.tabs(["CSV 검수", "검수 이력"])
    with inspection_tab:
        render_csv_inspection_tab()
    with history_tab:
        render_inspection_history_tab()


if __name__ == "__main__":
    main()
