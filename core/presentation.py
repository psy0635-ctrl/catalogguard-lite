import re

import pandas as pd

from core.models import ValidationIssue


RULE_LABELS = {
    "duplicate_product_id": "상품 ID 중복",
    "missing_required_field": "필수 값 누락",
    "invalid_category": "카테고리 오류",
    "invalid_stock": "재고 형식 오류",
    "out_of_stock": "품절 상품",
    "invalid_price": "가격 오류",
    "zero_price": "가격 0원",
}

RECOMMENDATIONS = {
    "duplicate_product_id": "상품 그룹마다 중복되지 않는 상품 ID를 사용하세요.",
    "missing_required_field": "누락된 필수 값을 입력하세요.",
    "invalid_category": "허용된 카테고리 값으로 수정하세요.",
    "invalid_stock": "재고를 0 이상의 정수로 입력하세요.",
    "out_of_stock": "판매 상태와 재입고 여부를 확인하세요.",
    "invalid_price": "가격을 0 이상의 정수로 입력하세요.",
    "zero_price": "무료 상품이 아니라면 정상 판매 가격을 입력하세요.",
}

SEVERITY_LABELS = {
    "error": "오류",
    "warning": "주의",
}

SEVERITY_ORDER = {
    "error": 0,
    "warning": 1,
}

RESULT_COLUMNS = [
    "검수 상태",
    "오류 항목",
    "상품 그룹 ID",
    "상품 ID",
    "오류 이유",
    "수정 권장사항",
]


def translate_issue_message(issue: ValidationIssue) -> str:
    """검수 결과의 영문 메시지를 사용자용 한글 문장으로 변환합니다."""
    message = issue.message

    if issue.rule == "duplicate_product_id":
        match = re.fullmatch(
            r"product_id '([^']*)' is reused across groups '([^']*)' and '([^']*)'",
            message,
        )
        if match:
            product_id, first_group, second_group = match.groups()
            return (
                f"상품 ID '{product_id}'이 상품 그룹 '{first_group}'와 "
                f"'{second_group}'에서 중복 사용되었습니다."
            )

    if issue.rule == "missing_required_field":
        match = re.fullmatch(r"'([^']*)' is missing", message)
        if match:
            field_name = match.group(1)
            return f"필수 항목 '{field_name}' 값이 누락되었습니다."

    if issue.rule == "invalid_category":
        match = re.fullmatch(r"category '([^']*)' is not one of .+", message)
        if match:
            category = match.group(1)
            return f"카테고리 '{category}'는 허용된 카테고리가 아닙니다."

    if issue.rule == "invalid_stock":
        if message == "stock is missing or not a number":
            return "재고가 누락되었거나 숫자 형식이 아닙니다."

        match = re.fullmatch(r"stock (-?\d+) is negative", message)
        if match:
            stock = match.group(1)
            return f"재고 {stock}개는 음수이므로 사용할 수 없습니다."

    if issue.rule == "out_of_stock" and message == "stock is 0":
        return "재고가 0개인 품절 상품입니다."

    if issue.rule == "invalid_price":
        if message == "price is missing or not a number":
            return "가격이 누락되었거나 숫자 형식이 아닙니다."

        match = re.fullmatch(r"price (-?\d+) is negative", message)
        if match:
            price = match.group(1)
            return f"가격 {price}원은 음수이므로 사용할 수 없습니다."

    if issue.rule == "zero_price" and message == "price is 0":
        return "가격이 0원으로 입력되었습니다."

    return message


def build_result_dataframe(issues: list[ValidationIssue]) -> pd.DataFrame:
    """검수 결과를 Streamlit 표시 및 CSV 다운로드용 표로 변환합니다."""
    sorted_issues = sorted(
        enumerate(issues),
        key=lambda item: (SEVERITY_ORDER.get(item[1].severity, 99), item[0]),
    )

    rows = []
    for _, issue in sorted_issues:
        rows.append(
            {
                "검수 상태": SEVERITY_LABELS.get(issue.severity, issue.severity),
                "오류 항목": RULE_LABELS.get(issue.rule, issue.rule),
                "상품 그룹 ID": issue.product_group_id,
                "상품 ID": issue.product_id,
                "오류 이유": translate_issue_message(issue),
                "수정 권장사항": RECOMMENDATIONS.get(
                    issue.rule, "CSV 내용을 확인하세요."
                ),
            }
        )

    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def filter_result_dataframe(
    result_df: pd.DataFrame,
    status_filter: str = "전체",
    rule_filter: str = "전체",
    product_id_query: str = "",
) -> pd.DataFrame:
    """선택한 조건에 따라 검수 결과 DataFrame을 필터링합니다."""
    filtered_df = result_df.copy()

    if status_filter != "전체":
        filtered_df = filtered_df[filtered_df["검수 상태"] == status_filter]

    if rule_filter != "전체":
        filtered_df = filtered_df[filtered_df["오류 항목"] == rule_filter]

    query = product_id_query.strip()
    if query:
        filtered_df = filtered_df[
            filtered_df["상품 ID"]
            .fillna("")
            .astype(str)
            .str.contains(query, case=False, na=False, regex=False)
        ]

    return filtered_df.reset_index(drop=True)


def calculate_dataframe_height(
    row_count: int,
    *,
    min_height: int = 120,
    max_height: int = 420,
) -> int:
    """행 개수에 맞는 표 높이를 계산합니다."""
    header_height = 38
    row_height = 35
    calculated_height = header_height + row_count * row_height
    return max(min_height, min(calculated_height, max_height))
