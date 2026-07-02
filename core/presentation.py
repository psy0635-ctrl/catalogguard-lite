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
    "price_outlier": "가격 이상치",
    "duplicate_product_content": "완전 중복 상품",
    "prohibited_term": "금지어 포함",
    "email_address": "이메일 주소 포함",
    "phone_number": "전화번호 포함",
    "resident_registration_number": "주민등록번호 형식 포함",
    "suspected_bank_account": "계좌번호 의심",
}

RECOMMENDATIONS = {
    "duplicate_product_id": "상품 그룹마다 중복되지 않는 상품 ID를 사용하세요.",
    "missing_required_field": "누락된 필수 값을 입력하세요.",
    "invalid_category": "허용된 카테고리 값으로 수정하세요.",
    "invalid_stock": "재고를 0 이상의 정수로 입력하세요.",
    "out_of_stock": "판매 상태와 재입고 여부를 확인하세요.",
    "invalid_price": "가격을 0 이상의 정수로 입력하세요.",
    "zero_price": "무료 상품이 아니라면 정상 판매 가격을 입력하세요.",
    "price_outlier": (
        "같은 카테고리 상품의 일반적인 가격 범위와 비교하여 "
        "입력 가격이 맞는지 확인하세요."
    ),
    "duplicate_product_content": (
        "상품 ID와 상품 그룹을 확인하고 중복 등록된 상품을 삭제하거나 하나로 통합하세요."
    ),
    "prohibited_term": (
        "운영 정책상 허용되는 표현으로 수정하고 금지어를 제거하세요."
    ),
    "email_address": "상품 정보에서 이메일 주소를 제거하세요.",
    "phone_number": "상품 정보에서 전화번호를 제거하세요.",
    "resident_registration_number": (
        "상품 정보에서 주민등록번호 형태의 개인정보를 즉시 제거하세요."
    ),
    "suspected_bank_account": (
        "계좌번호가 맞는지 확인하고 개인 금융정보라면 제거하세요."
    ),
}

FIELD_LABELS = {
    "product_name": "상품명",
    "description": "상품 설명",
    "seller": "판매자 정보",
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

    content_message_patterns = {
        "prohibited_term": (
            r"field '([^']*)' contains prohibited term '([^']*)'",
            lambda field, value: f"{field}에 금지어 '{value}'이 포함되어 있습니다.",
        ),
        "email_address": (
            r"field '([^']*)' contains email address '([^']*)'",
            lambda field, value: f"{field}에 이메일 주소 '{value}'이 포함되어 있습니다.",
        ),
        "phone_number": (
            r"field '([^']*)' contains phone number '([^']*)'",
            lambda field, value: f"{field}에 전화번호 '{value}'이 포함되어 있습니다.",
        ),
        "resident_registration_number": (
            r"field '([^']*)' contains resident registration number '([^']*)'",
            lambda field, value: f"{field}에 주민등록번호 형식 '{value}'이 포함되어 있습니다.",
        ),
        "suspected_bank_account": (
            r"field '([^']*)' contains suspected bank account '([^']*)'",
            lambda field, value: (
                f"{field}에 계좌번호로 의심되는 값 '{value}'이 포함되어 있습니다."
            ),
        ),
    }
    content_pattern = content_message_patterns.get(issue.rule)
    if content_pattern:
        pattern, formatter = content_pattern
        match = re.fullmatch(pattern, message)
        if match:
            field_name, value = match.groups()
            field_label = FIELD_LABELS.get(field_name, field_name)
            return formatter(field_label, value)

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

    if issue.rule == "duplicate_product_content":
        match = re.fullmatch(
            r"product_id '([^']*)' in group '([^']*)' duplicates product_id "
            r"'([^']*)' in group '([^']*)' with same product_name, category, "
            r"color, size, and price",
            message,
        )
        if match:
            product_id, product_group_id, base_product_id, base_group_id = match.groups()
            return (
                f"상품 ID '{product_id}'(그룹 '{product_group_id}')는 상품 ID "
                f"'{base_product_id}'(그룹 '{base_group_id}')와 상품명, "
                "카테고리, 색상, 사이즈, 가격이 모두 같습니다."
            )

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

    if issue.rule == "price_outlier":
        match = re.fullmatch(
            r"price (-?\d+) is outside category '([^']*)' expected range "
            r"(-?\d+) to (-?\d+)",
            message,
        )
        if match:
            price, category, lower_bound, upper_bound = match.groups()
            return (
                f"가격 {int(price):,}원은 {category} 카테고리의 일반적인 "
                f"가격 범위인 {int(lower_bound):,}원~{int(upper_bound):,}원을 "
                "벗어났습니다."
            )

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
