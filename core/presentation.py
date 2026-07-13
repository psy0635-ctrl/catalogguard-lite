# 역할: 내부 검수 문제를 화면과 CSV에 표시할 한글 결과표로 변환합니다.
import re

import pandas as pd

from core.models import ValidationIssue


# 내부 규칙 이름을 사용자가 볼 한국어 이름으로 바꾸는 표입니다.
RULE_LABELS = {
    "duplicate_product_id": "상품 ID 중복",
    "duplicate_product_name": "상품명 중복",
    "missing_required_field": "필수 값 누락",
    "invalid_category": "카테고리 오류",
    "invalid_stock": "재고 형식 오류",
    "out_of_stock": "품절 상품",
    "invalid_price": "가격 오류",
    "invalid_non_positive_price": "가격 오류",
    "zero_price": "가격 0원",
    "price_outlier": "가격 이상치",
    "category_price_anomaly": "가격 이상치",
    "product_category_mismatch": "상품명·카테고리 불일치",
    "duplicate_product_content": "완전 중복 상품",
    "prohibited_term": "금지어 포함",
    "email_address": "이메일 주소 포함",
    "phone_number": "전화번호 포함",
    "resident_registration_number": "주민등록번호 형식 포함",
    "suspected_bank_account": "계좌번호 의심",
}

# 각 규칙별로 화면에 보여 줄 수정 가이드입니다.
PRICE_RECOMMENDATION = "0보다 큰 정상 판매 가격을 입력하십시오."

RECOMMENDATIONS = {
    "duplicate_product_id": "각 상품에 고유한 상품 ID를 입력하십시오.",
    "duplicate_product_name": "모델명, 색상, 옵션, 용량 또는 상품 ID를 확인하십시오.",
    "missing_required_field": "누락된 필수 값을 입력하세요.",
    "invalid_category": "허용된 카테고리 값으로 수정하세요.",
    "invalid_stock": "재고를 0 이상의 정수로 입력하세요.",
    "out_of_stock": "판매 상태와 재입고 여부를 확인하세요.",
    "invalid_price": PRICE_RECOMMENDATION,
    "invalid_non_positive_price": PRICE_RECOMMENDATION,
    "zero_price": PRICE_RECOMMENDATION,
    "price_outlier": (
        "같은 카테고리 상품의 일반적인 가격 범위와 비교하여 "
        "입력 가격이 맞는지 확인하세요."
    ),
    "category_price_anomaly": (
        "가격 단위, 숫자 입력 오류, 할인 가격 입력 여부를 확인하십시오."
    ),
    "product_category_mismatch": (
        "상품명과 카테고리를 확인하고 올바른 카테고리로 수정하십시오."
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

RISK_LEVELS = {
    "duplicate_product_id": "높음",
    "duplicate_product_name": "중간",
    "duplicate_product_content": "높음",
    "missing_required_field": "높음",
    "invalid_category": "중간",
    "invalid_stock": "중간",
    "out_of_stock": "낮음",
    "invalid_price": "높음",
    "invalid_non_positive_price": "높음",
    "zero_price": "중간",
    "price_outlier": "중간",
    "category_price_anomaly": "중간",
    "product_category_mismatch": "중간",
    "prohibited_term": "높음",
    "email_address": "높음",
    "phone_number": "높음",
    "resident_registration_number": "높음",
    "suspected_bank_account": "중간",
}

# 내부 필드명을 화면용 한국어 필드명으로 바꿉니다.
FIELD_LABELS = {
    "product_name": "상품명",
    "description": "상품 설명",
    "seller": "판매자 정보",
}

# severity는 내부 값이고, 화면에는 한국어 상태로 보여줍니다.
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
    "위험 수준",
]


def translate_issue_message(issue: ValidationIssue) -> str:
    """검수 결과의 영문 메시지를 사용자용 한글 문장으로 변환합니다."""
    message = issue.message

    # 개인정보 관련 메시지는 이미 마스킹된 값만 들어오므로 그대로 화면 문장에 사용합니다.
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
            # 예: product_name -> 상품명
            field_name, value = match.groups()
            field_label = FIELD_LABELS.get(field_name, field_name)
            return formatter(field_label, value)

    if issue.rule == "duplicate_product_id":
        match = re.fullmatch(
            r"product_id '([^']*)' is duplicated in rows ([0-9, ]+)",
            message,
        )
        if match:
            product_id, rows = match.groups()
            return (
                f"동일한 상품 ID '{product_id}'가 여러 상품에 사용되었습니다. "
                f"중복 행: {rows}."
            )

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

    if issue.rule == "duplicate_product_name":
        match = re.fullmatch(
            r"product_name '([^']*)' normalized to '([^']*)' duplicates rows "
            r"([0-9, ]+) with product_ids '([^']*)'",
            message,
        )
        if match:
            product_name, _, rows, product_ids = match.groups()
            return (
                f"상품명 '{product_name}'이 다른 상품과 동일하거나 정리 후 "
                f"같은 값으로 확인되었습니다. 중복 후보 상품 ID: {product_ids}. "
                f"중복 행: {rows}."
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

    if issue.rule == "invalid_non_positive_price":
        match = re.fullmatch(r"price (-?\d+) is not positive", message)
        if match:
            price = int(match.group(1))
            return f"상품 가격이 0 이하입니다. 현재 가격: {price:,}원."

    if issue.rule == "zero_price" and message == "price is 0":
        return "가격이 0원으로 입력되었습니다."

    if issue.rule == "category_price_anomaly":
        match = re.fullmatch(
            r"price ([0-9]+) in category '([^']*)' has median ([0-9.]+) "
            r"and ratio ([0-9.]+)",
            message,
        )
        if match:
            price, category, median_price, ratio = match.groups()
            return (
                "같은 카테고리의 일반적인 가격 범위와 큰 차이가 있습니다. "
                f"현재 가격 {int(price):,}원은 {category} 카테고리 중앙값 "
                f"{float(median_price):,.0f}원의 {float(ratio):g}배입니다."
            )

    if issue.rule == "product_category_mismatch":
        match = re.fullmatch(
            r"product_name keyword '([^']*)' implies category '([^']*)' "
            r"but current category is '([^']*)'",
            message,
        )
        if match:
            keyword, inferred_category, current_category = match.groups()
            return (
                f"상품명에서 '{keyword}'가 확인되어 {inferred_category} 상품으로 "
                f"추정되지만 현재 카테고리는 '{current_category}'입니다."
            )

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
    # 오류를 주의보다 먼저 보여주고, 같은 심각도 안에서는 원래 발견 순서를 유지합니다.
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
                "위험 수준": RISK_LEVELS.get(issue.rule, ""),
            }
        )

    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def _normalize_statistics_text(value: object, empty_value: str) -> str:
    """통계 집계용 단일 값을 문자열로 정규화합니다."""
    if value is None or pd.isna(value):
        return empty_value

    normalized = str(value).strip()
    return normalized or empty_value


def build_inspection_statistics(
    results_df: pd.DataFrame,
) -> dict[str, pd.DataFrame | int]:
    """전체 검수 결과를 오류 항목, 위험 수준, 상품 ID별로 집계합니다."""
    required_columns = ("오류 항목", "위험 수준", "상품 ID")
    if any(column not in results_df.columns for column in required_columns):
        raise ValueError("통계 집계에 필요한 컬럼이 없습니다.")

    issue_values = results_df["오류 항목"].map(
        lambda value: _normalize_statistics_text(value, "분류 없음")
    )
    issue_counts = (
        issue_values.value_counts(sort=False)
        .rename_axis("오류 항목")
        .reset_index(name="문제 수")
        .sort_values(
            ["문제 수", "오류 항목"],
            ascending=[False, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    supported_risk_levels = {"높음", "중간", "낮음"}
    risk_values = results_df["위험 수준"].map(
        lambda value: _normalize_statistics_text(value, "미분류")
    )
    risk_values = risk_values.where(
        risk_values.isin(supported_risk_levels), "미분류"
    )
    risk_counts = (
        risk_values.value_counts(sort=False)
        .rename_axis("위험 수준")
        .reset_index(name="문제 수")
    )
    risk_order = {"높음": 0, "중간": 1, "낮음": 2, "미분류": 3}
    risk_counts["_정렬 순서"] = risk_counts["위험 수준"].map(risk_order)
    risk_counts = (
        risk_counts.sort_values("_정렬 순서", kind="stable")
        .drop(columns="_정렬 순서")
        .reset_index(drop=True)
    )

    product_values = results_df["상품 ID"].map(
        lambda value: _normalize_statistics_text(value, "")
    )
    product_rows = pd.DataFrame(
        {
            "_상품 ID": product_values,
            "_상품 ID 없음": product_values.eq(""),
        }
    )
    product_counts = (
        product_rows.groupby(
            ["_상품 ID", "_상품 ID 없음"], sort=False, dropna=False
        )
        .size()
        .reset_index(name="문제 수")
        .sort_values(
            ["문제 수", "_상품 ID 없음", "_상품 ID"],
            ascending=[False, True, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    product_counts["상품 ID"] = product_counts.apply(
        lambda row: (
            "상품 ID 없음"
            if row["_상품 ID 없음"]
            else (
                "상품 ID 없음 (입력값)"
                if row["_상품 ID"] == "상품 ID 없음"
                else row["_상품 ID"]
            )
        ),
        axis=1,
    )
    product_counts = product_counts[["상품 ID", "문제 수"]]

    return {
        "issue_counts": issue_counts,
        "risk_counts": risk_counts,
        "product_counts": product_counts,
        "total_issues": len(results_df),
    }


def build_validation_summary_message(
    total_issue_count: int,
    error_count: int,
    warning_count: int,
) -> str:
    """검수 요약 알림에 표시할 문제 개수 문장을 만듭니다."""
    return (
        f"총 {total_issue_count}건의 문제가 발견되었습니다. "
        f"오류 {error_count}건, 주의 {warning_count}건입니다."
    )


def filter_result_dataframe(
    result_df: pd.DataFrame,
    status_filter: str = "전체",
    rule_filter: str = "전체",
    product_id_query: str = "",
) -> pd.DataFrame:
    """선택한 조건에 따라 검수 결과 DataFrame을 필터링합니다."""
    # 원본 DataFrame을 직접 바꾸지 않기 위해 복사본에서 필터링합니다.
    filtered_df = result_df.copy()

    if status_filter != "전체":
        filtered_df = filtered_df[filtered_df["검수 상태"] == status_filter]

    if rule_filter != "전체":
        filtered_df = filtered_df[filtered_df["오류 항목"] == rule_filter]

    query = product_id_query.strip()
    if query:
        # 상품 ID 검색은 일부 글자만 입력해도 찾을 수 있게 contains로 처리합니다.
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
    # 표가 너무 작거나 너무 커지지 않도록 최소/최대 높이를 함께 적용합니다.
    header_height = 38
    row_height = 35
    calculated_height = header_height + row_count * row_height
    return max(min_height, min(calculated_height, max_height))
