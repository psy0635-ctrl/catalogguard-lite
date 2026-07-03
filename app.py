# 사용자가 보는 웹 화면
import ast

import streamlit as st

from config.settings import OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from core.loader import load_products_from_dataframe
from core.presentation import (
    build_result_dataframe,
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
from core.rules import run_all_rules
from core.upload_validator import (
    CsvUploadValidationError,
    validate_and_read_uploaded_csv,
)


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


st.set_page_config(page_title="CatalogGuard Lite", layout="wide")

st.title("CatalogGuard Lite")
st.write("상품 카탈로그 CSV 파일의 누락 값과 데이터 오류를 검사합니다.")

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

# 파일이 없으면 아래 검사 코드를 실행하지 않고 화면을 멈춥니다.
if uploaded_file is None:
    st.info("검사할 CSV 파일을 업로드해 주세요.")
    st.stop()

file_bytes = uploaded_file.getvalue()

try:
    # 검증된 하나의 DataFrame을 미리보기와 검수에 함께 사용합니다.
    validated_df = validate_and_read_uploaded_csv(uploaded_file.name, file_bytes)
    masked_preview_df = create_masked_preview(validated_df)
    products = load_products_from_dataframe(validated_df)
    issues = run_all_rules(products)
except CsvUploadValidationError as error:
    st.error(str(error))
    st.stop()
except ValueError as error:
    st.error(format_value_error(error))
    st.stop()
except Exception:
    st.error("파일 처리 중 오류가 발생했습니다. CSV 형식과 내용을 확인해 주세요.")
    st.stop()
else:
    # 화면에는 마스킹된 복사본의 상위 100행만 보여주고, 검수에는 원본 Product를 사용합니다.
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

    error_count = sum(issue.severity == "error" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    issue_count = len(issues)
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

    if issue_count > 0:
        # 내부 검수 결과를 화면 표시와 CSV 다운로드에 쓰는 표 형태로 바꿉니다.
        result_df = build_result_dataframe(issues)
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
        else:
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
