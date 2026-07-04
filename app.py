# 역할: 사용자가 CSV를 업로드하고 검수 결과를 확인하는 Streamlit 웹 화면입니다.
import ast
import hashlib
import re
from datetime import datetime
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
from core.inspection_service import inspect_dataframe
from core.presentation import (
    build_validation_summary_message,
    calculate_dataframe_height,
    filter_result_dataframe,
)
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


def format_value_error(error: ValueError) -> str:
    # 로더에서 올라온 내부 오류를 화면에 보여 줄 한국어 안내문으로 바꿉니다.
    message = str(error)
    if "CSV 파일에 상품 데이터가 없습니다" in message:
        return message

    prefix = "Missing required columns:"
    if prefix not in message:
        return "필수 컬럼이 없거나 CSV 내용이 올바르지 않습니다."

    missing_text = message.split(prefix, 1)[1].strip()
    try:
        missing_columns = ast.literal_eval(missing_text)
    except (SyntaxError, ValueError):
        missing_columns = missing_text

    if isinstance(missing_columns, list):
        missing_text = ", ".join(str(column) for column in missing_columns)

    return f"필수 컬럼이 없습니다: {missing_text}"


def get_overall_status(error_count: int, warning_count: int) -> str:
    # 오류가 하나라도 있으면 전체 상태는 오류, 오류 없이 주의만 있으면 주의입니다.
    if error_count > 0:
        return "오류"
    if warning_count > 0:
        return "주의"
    return "정상"


def build_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def get_saved_inspection_run_id(session_state, file_hash: str) -> int | None:
    if session_state.get("saved_file_hash") != file_hash:
        return None
    return session_state.get("saved_inspection_run_id")


def mark_inspection_saved(
    session_state,
    *,
    file_hash: str,
    inspection_run_id: int,
) -> None:
    session_state["saved_file_hash"] = file_hash
    session_state["saved_inspection_run_id"] = inspection_run_id


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


def initialize_history_state() -> None:
    if "history_limit" not in st.session_state:
        st.session_state.history_limit = HISTORY_LIMIT_DEFAULT
    if "history_offset" not in st.session_state:
        st.session_state.history_offset = 0
    if "history_view_mode" not in st.session_state:
        st.session_state.history_view_mode = "list"
    if "selected_inspection_run_id" not in st.session_state:
        st.session_state.selected_inspection_run_id = None


def render_inspection_save_failure(detail_message: str) -> None:
    st.error("검수 결과는 확인할 수 있지만 이력 저장에 실패했습니다.")
    st.caption(detail_message)


def render_inspection_save_button(
    *,
    source_filename: str,
    file_bytes: bytes,
    content_type: str,
) -> None:
    file_hash = build_file_hash(file_bytes)
    saved_inspection_run_id = get_saved_inspection_run_id(
        st.session_state,
        file_hash,
    )

    if st.button("검수 이력에 저장", key="save_inspection_history"):
        if saved_inspection_run_id is not None:
            st.info(
                "이미 검수 이력에 저장된 파일입니다. "
                f"실행 ID: {saved_inspection_run_id}"
            )
            return

        try:
            api_client = create_catalogguard_api_client()
            response = api_client.create_inspection(
                source_filename=source_filename,
                file_content=file_bytes,
                content_type=content_type,
            )
            inspection_run_id = int(response["inspection_run_id"])
        except CatalogGuardApiConfigurationError:
            render_inspection_save_failure(
                "검수 이력 API 주소가 설정되지 않았습니다."
            )
            return
        except CatalogGuardApiConnectionError:
            render_inspection_save_failure("검수 이력 서버에 연결할 수 없습니다.")
            return
        except CatalogGuardApiTimeoutError:
            render_inspection_save_failure(
                "검수 이력 서버 응답 시간이 초과되었습니다."
            )
            return
        except (CatalogGuardApiResponseError, KeyError, TypeError, ValueError):
            render_inspection_save_failure(
                "검수 이력 서버에서 오류가 발생했습니다."
            )
            return

        mark_inspection_saved(
            st.session_state,
            file_hash=file_hash,
            inspection_run_id=inspection_run_id,
        )
        st.success(f"검수 이력에 저장되었습니다. 실행 ID: {inspection_run_id}")
        return

    if saved_inspection_run_id is not None:
        st.info(
            "이미 검수 이력에 저장된 파일입니다. "
            f"실행 ID: {saved_inspection_run_id}"
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

    try:
        # 검증된 하나의 DataFrame을 미리보기와 검수에 함께 사용합니다.
        validated_df = validate_and_read_uploaded_csv(uploaded_file.name, file_bytes)
        inspection_report = inspect_dataframe(validated_df)
    except CsvUploadValidationError as error:
        st.error(str(error))
        return
    except ValueError as error:
        st.error(format_value_error(error))
        return
    except Exception:
        st.error("파일 처리 중 오류가 발생했습니다. CSV 형식과 내용을 확인해 주세요.")
        return

    # 화면에는 마스킹된 복사본의 상위 100행만 보여주고, 검수에는 원본 Product를 사용합니다.
    masked_preview_df = inspection_report.masked_preview_dataframe
    products = inspection_report.products
    issues = inspection_report.issues
    summary = inspection_report.summary

    st.subheader("상품 데이터 미리보기")
    preview_rows = masked_preview_df.head(100)
    st.dataframe(
        preview_rows,
        height=calculate_dataframe_height(len(preview_rows)),
        use_container_width=True,
        hide_index=True,
    )
    if len(masked_preview_df) > len(preview_rows):
        st.caption(f"전체 {len(masked_preview_df)}행 중 앞 100행만 표시합니다.")

    error_count = summary.error_count
    warning_count = summary.warning_count
    issue_count = summary.total_issues
    overall_status = get_overall_status(error_count, warning_count)

    # 사용자가 현재 CSV 상태를 빠르게 판단할 수 있는 요약 숫자입니다.
    st.subheader("검수 요약")
    status_col, product_col, issue_col, error_col, warning_col = st.columns(5)
    status_col.metric("전체 상태", overall_status)
    product_col.metric("전체 상품 수", len(products))
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

    render_inspection_save_button(
        source_filename=uploaded_file.name,
        file_bytes=file_bytes,
        content_type=getattr(uploaded_file, "type", None) or "text/csv",
    )

    if issue_count <= 0:
        return

    # 내부 검수 결과를 화면 표시와 CSV 다운로드에 쓰는 표 형태로 바꿉니다.
    result_df = inspection_report.result_dataframe
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

    # 필터는 화면 표와 다운로드 CSV에 동일하게 적용됩니다.
    st.caption(f"현재 조건에 맞는 검수 결과: {len(filtered_result_df)}건")

    if filtered_result_df.empty:
        st.info("선택한 조건에 맞는 검수 결과가 없습니다.")
        return

    st.dataframe(
        filtered_result_df,
        height=calculate_dataframe_height(len(filtered_result_df)),
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = build_validation_result_csv(filtered_result_df)
    st.download_button(
        "현재 필터 결과 CSV 다운로드",
        data=csv_bytes,
        file_name=build_result_filename(uploaded_file.name),
        mime="text/csv",
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


def render_inspection_history_list(api_client) -> None:
    limit = st.session_state.history_limit
    offset = st.session_state.history_offset

    try:
        history_response = api_client.list_inspections(limit=limit, offset=offset)
    except CatalogGuardApiConnectionError:
        st.error("검수 이력 서버에 연결할 수 없습니다.")
        return
    except CatalogGuardApiTimeoutError:
        st.error("검수 이력 서버 응답 시간이 초과되었습니다.")
        return
    except InspectionNotFoundError:
        st.error("검수 실행 결과를 찾을 수 없습니다.")
        return
    except CatalogGuardApiResponseError:
        st.error("검수 이력을 불러오는 중 오류가 발생했습니다.")
        return

    total = max(0, int(history_response["total"]))
    if total > 0 and offset >= total:
        st.session_state.history_offset = ((total - 1) // limit) * limit
        st.rerun()

    history_dataframe = build_history_dataframe(history_response["items"])
    if history_dataframe.empty:
        st.info("저장된 검수 이력이 없습니다.")
    else:
        st.dataframe(
            history_dataframe,
            use_container_width=True,
            hide_index=True,
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
    st.session_state.history_view_mode = "list"
    st.session_state.selected_inspection_run_id = None
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
    except InspectionNotFoundError:
        st.error("선택한 검수 실행 결과를 찾을 수 없습니다.")
        return
    except CatalogGuardApiConnectionError:
        st.error("검수 이력 서버에 연결할 수 없습니다.")
        return
    except CatalogGuardApiTimeoutError:
        st.error("검수 이력 서버 응답 시간이 초과되었습니다.")
        return
    except CatalogGuardApiResponseError:
        st.error("검수 상세 결과를 불러오는 중 오류가 발생했습니다.")
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
    if not should_show_history_detail_download(detail_dataframe):
        st.info("이 검수 실행에서 발견된 문제가 없습니다.")
        return

    st.dataframe(
        detail_dataframe,
        height=calculate_dataframe_height(len(detail_dataframe)),
        use_container_width=True,
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
