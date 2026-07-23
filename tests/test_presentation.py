# 역할: 내부 검수 문제를 화면용 한글 결과표로 바꾸는 표시 계층을 테스트합니다.
import pandas as pd
import pytest

from core import presentation
from core.group_category_consistency_detector import build_group_category_message
from core.models import ValidationIssue
from core.presentation import (
    FIELD_LABELS,
    PRICE_RECOMMENDATION,
    RESULT_COLUMNS,
    build_result_dataframe,
    build_validation_summary_message,
    calculate_dataframe_height,
    filter_result_dataframe,
    translate_issue_message,
)


def make_issue(**overrides) -> ValidationIssue:
    # 표시 계층 테스트에서 공통으로 쓰는 기본 문제 데이터입니다.
    defaults = dict(
        rule="missing_required_field",
        severity="error",
        product_id="P001",
        product_group_id="G001",
        message="'color' is missing",
    )
    defaults.update(overrides)
    return ValidationIssue(**defaults)


def make_result_dataframe() -> pd.DataFrame:
    # 필터 테스트용으로 여러 상태와 상품 ID가 섞인 결과 표를 만듭니다.
    return pd.DataFrame(
        [
            {
                "검수 상태": "오류",
                "오류 항목": "가격 오류",
                "상품 그룹 ID": "G001",
                "상품 ID": "P001",
                "오류 이유": "가격 -5000원은 음수이므로 사용할 수 없습니다.",
                "수정 권장사항": PRICE_RECOMMENDATION,
            },
            {
                "검수 상태": "오류",
                "오류 항목": "필수 값 누락",
                "상품 그룹 ID": "G002",
                "상품 ID": "P003",
                "오류 이유": "필수 항목 'color' 값이 누락되었습니다.",
                "수정 권장사항": "누락된 필수 값을 입력하세요.",
            },
            {
                "검수 상태": "주의",
                "오류 항목": "품절 상품",
                "상품 그룹 ID": "G003",
                "상품 ID": "P003",
                "오류 이유": "재고가 0개인 품절 상품입니다.",
                "수정 권장사항": "판매 상태와 재입고 여부를 확인하세요.",
            },
            {
                "검수 상태": "오류",
                "오류 항목": "가격 오류",
                "상품 그룹 ID": "G004",
                "상품 ID": "P004",
                "오류 이유": "가격이 누락되었거나 숫자 형식이 아닙니다.",
                "수정 권장사항": PRICE_RECOMMENDATION,
            },
        ],
        columns=RESULT_COLUMNS,
    )


def make_statistics_dataframe(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "검수 상태": "오류",
        "오류 항목": "가격 오류",
        "상품 그룹 ID": "G001",
        "상품 ID": "P001",
        "오류 이유": "테스트 오류 이유",
        "수정 권장사항": "테스트 수정 권장사항",
        "위험 수준": "높음",
    }
    return pd.DataFrame(
        [{**defaults, **row} for row in rows],
        columns=RESULT_COLUMNS,
    )


def test_build_inspection_statistics_counts_all_categories_and_totals():
    results_df = make_statistics_dataframe(
        [
            {"오류 항목": "가격 오류", "위험 수준": "높음", "상품 ID": "P003"},
            {"오류 항목": "가격 오류", "위험 수준": "높음", "상품 ID": "P003"},
            {"오류 항목": "상품 ID 중복", "위험 수준": "높음", "상품 ID": "P001"},
            {"오류 항목": "필수 값 누락", "위험 수준": "중간", "상품 ID": "P001"},
            {"오류 항목": "재고 형식 오류", "위험 수준": "낮음", "상품 ID": "P002"},
        ]
    )

    statistics = presentation.build_inspection_statistics(results_df)

    expected_issue_counts = pd.DataFrame(
        {
            "오류 항목": ["가격 오류", "상품 ID 중복", "재고 형식 오류", "필수 값 누락"],
            "문제 수": [2, 1, 1, 1],
        }
    )
    expected_risk_counts = pd.DataFrame(
        {
            "위험 수준": ["높음", "중간", "낮음"],
            "문제 수": [3, 1, 1],
        }
    )
    expected_product_counts = pd.DataFrame(
        {
            "상품 ID": ["P001", "P003", "P002"],
            "문제 수": [2, 2, 1],
        }
    )

    pd.testing.assert_frame_equal(statistics["issue_counts"], expected_issue_counts)
    pd.testing.assert_frame_equal(statistics["risk_counts"], expected_risk_counts)
    pd.testing.assert_frame_equal(statistics["product_counts"], expected_product_counts)
    assert statistics["total_issues"] == 5
    assert statistics["issue_counts"]["문제 수"].sum() == 5
    assert statistics["risk_counts"]["문제 수"].sum() == 5
    assert statistics["product_counts"]["문제 수"].sum() == 5


def test_build_inspection_statistics_sorts_tied_issue_counts_by_name():
    results_df = make_statistics_dataframe(
        [
            {"오류 항목": "상품 ID 중복"},
            {"오류 항목": "가격 오류"},
            {"오류 항목": "필수 값 누락"},
            {"오류 항목": "상품 ID 중복"},
            {"오류 항목": "가격 오류"},
        ]
    )

    statistics = presentation.build_inspection_statistics(results_df)

    assert statistics["issue_counts"].to_dict(orient="records") == [
        {"오류 항목": "가격 오류", "문제 수": 2},
        {"오류 항목": "상품 ID 중복", "문제 수": 2},
        {"오류 항목": "필수 값 누락", "문제 수": 1},
    ]


def test_build_inspection_statistics_uses_semantic_risk_order():
    results_df = make_statistics_dataframe(
        [
            {"위험 수준": "낮음"},
            {"위험 수준": "높음"},
            {"위험 수준": "중간"},
            {"위험 수준": "알 수 없음"},
        ]
    )

    statistics = presentation.build_inspection_statistics(results_df)

    assert statistics["risk_counts"].to_dict(orient="records") == [
        {"위험 수준": "높음", "문제 수": 1},
        {"위험 수준": "중간", "문제 수": 1},
        {"위험 수준": "낮음", "문제 수": 1},
        {"위험 수준": "미분류", "문제 수": 1},
    ]


def test_build_inspection_statistics_groups_blank_issue_and_risk_values():
    blank_values = [None, pd.NA, float("nan"), "", "   "]
    results_df = make_statistics_dataframe(
        [
            {"오류 항목": value, "위험 수준": value}
            for value in blank_values
        ]
    )

    statistics = presentation.build_inspection_statistics(results_df)

    assert statistics["issue_counts"].to_dict(orient="records") == [
        {"오류 항목": "분류 없음", "문제 수": 5}
    ]
    assert statistics["risk_counts"].to_dict(orient="records") == [
        {"위험 수준": "미분류", "문제 수": 5}
    ]


def test_build_inspection_statistics_groups_blank_product_ids():
    results_df = make_statistics_dataframe(
        [
            {"상품 ID": value}
            for value in [None, pd.NA, float("nan"), "", "   "]
        ]
    )

    statistics = presentation.build_inspection_statistics(results_df)

    assert statistics["product_counts"].to_dict(orient="records") == [
        {"상품 ID": "상품 ID 없음", "문제 수": 5}
    ]


def test_build_inspection_statistics_distinguishes_missing_product_id_label_input():
    results_df = make_statistics_dataframe(
        [
            {"상품 ID": None},
            {"상품 ID": "상품 ID 없음"},
            {"상품 ID": " 상품 ID 없음 "},
        ]
    )

    statistics = presentation.build_inspection_statistics(results_df)

    assert statistics["product_counts"].to_dict(orient="records") == [
        {"상품 ID": "상품 ID 없음 (입력값)", "문제 수": 2},
        {"상품 ID": "상품 ID 없음", "문제 수": 1},
    ]


def test_build_inspection_statistics_sorts_product_ids_and_missing_id_stably():
    results_df = make_statistics_dataframe(
        [
            {"상품 ID": "P002"},
            {"상품 ID": None},
            {"상품 ID": "P001"},
            {"상품 ID": "P002"},
            {"상품 ID": ""},
            {"상품 ID": "P001"},
        ]
    )

    first_statistics = presentation.build_inspection_statistics(results_df)
    second_statistics = presentation.build_inspection_statistics(results_df)

    expected_product_counts = pd.DataFrame(
        {
            "상품 ID": ["P001", "P002", "상품 ID 없음"],
            "문제 수": [2, 2, 2],
        }
    )
    pd.testing.assert_frame_equal(
        first_statistics["product_counts"],
        expected_product_counts,
    )
    pd.testing.assert_frame_equal(
        second_statistics["product_counts"],
        expected_product_counts,
    )


def test_build_inspection_statistics_returns_all_products_without_top_five_limit():
    results_df = make_statistics_dataframe(
        [{"상품 ID": f"P{index:03d}"} for index in range(1, 7)]
    )

    statistics = presentation.build_inspection_statistics(results_df)

    assert len(statistics["product_counts"]) == 6
    assert statistics["product_counts"]["상품 ID"].tolist() == [
        "P001",
        "P002",
        "P003",
        "P004",
        "P005",
        "P006",
    ]


def test_build_inspection_statistics_handles_empty_dataframe_with_columns():
    results_df = pd.DataFrame(columns=RESULT_COLUMNS)

    statistics = presentation.build_inspection_statistics(results_df)

    assert statistics["total_issues"] == 0
    assert list(statistics["issue_counts"].columns) == ["오류 항목", "문제 수"]
    assert list(statistics["risk_counts"].columns) == ["위험 수준", "문제 수"]
    assert list(statistics["product_counts"].columns) == ["상품 ID", "문제 수"]
    assert statistics["issue_counts"].empty
    assert statistics["risk_counts"].empty
    assert statistics["product_counts"].empty


@pytest.mark.parametrize("missing_column", ["오류 항목", "위험 수준", "상품 ID"])
def test_build_inspection_statistics_rejects_missing_required_column(missing_column):
    private_test_value = "FAKE_PRIVATE_TEST_VALUE"
    results_df = make_statistics_dataframe(
        [{"오류 이유": private_test_value}]
    ).drop(columns=missing_column)

    with pytest.raises(
        ValueError,
        match="^통계 집계에 필요한 컬럼이 없습니다\\.$",
    ) as error_info:
        presentation.build_inspection_statistics(results_df)

    assert private_test_value not in str(error_info.value)


def test_build_inspection_statistics_does_not_change_original_dataframe():
    results_df = make_statistics_dataframe(
        [
            {"오류 항목": " 가격 오류 ", "위험 수준": " 높음 ", "상품 ID": " P001 "},
            {"오류 항목": None, "위험 수준": pd.NA, "상품 ID": None},
        ]
    )
    results_df.index = [7, 3]
    original_df = results_df.copy(deep=True)

    presentation.build_inspection_statistics(results_df)

    pd.testing.assert_frame_equal(results_df, original_df)


def test_build_inspection_statistics_does_not_return_unused_private_columns():
    private_test_values = [
        "FAKE_EMAIL_TEST_VALUE",
        "FAKE_PHONE_TEST_VALUE",
        "FAKE_ACCOUNT_TEST_VALUE",
    ]
    results_df = make_statistics_dataframe(
        [
            {
                "오류 이유": private_test_values[0],
                "수정 권장사항": private_test_values[1],
                "상품 그룹 ID": private_test_values[2],
            }
        ]
    )

    statistics = presentation.build_inspection_statistics(results_df)

    assert list(statistics["issue_counts"].columns) == ["오류 항목", "문제 수"]
    assert list(statistics["risk_counts"].columns) == ["위험 수준", "문제 수"]
    assert list(statistics["product_counts"].columns) == ["상품 ID", "문제 수"]
    result_text = " ".join(
        statistics[key].to_string(index=False)
        for key in ("issue_counts", "risk_counts", "product_counts")
    )
    for private_test_value in private_test_values:
        assert private_test_value not in result_text


def test_translate_duplicate_product_id_message_to_korean():
    issue = make_issue(
        rule="duplicate_product_id",
        message="product_id 'P003' is reused across groups 'G002' and 'G004'",
    )

    message = translate_issue_message(issue)

    assert message == "상품 ID 'P003'이 상품 그룹 'G002'와 'G004'에서 중복 사용되었습니다."


def test_translate_duplicate_product_id_rows_message_to_korean():
    issue = make_issue(
        rule="duplicate_product_id",
        message="product_id 'P003' is duplicated in rows 2, 4, 7",
    )

    message = translate_issue_message(issue)

    assert message == (
        "동일한 상품 ID 'P003'가 여러 상품에 사용되었습니다. 중복 행: 2, 4, 7."
    )


def test_translate_duplicate_product_name_message_to_korean():
    issue = make_issue(
        rule="duplicate_product_name",
        severity="warning",
        message=(
            "product_name '가짜 테스트 1' normalized to '가짜테스트1' "
            "duplicates rows 2, 3 with product_ids 'P001, P002'"
        ),
    )

    message = translate_issue_message(issue)

    assert message == (
        "상품명 '가짜 테스트 1'이 다른 상품과 동일하거나 정리 후 같은 값으로 "
        "확인되었습니다. 중복 후보 상품 ID: P001, P002. 중복 행: 2, 3."
    )


def test_translate_duplicate_variant_combination_message_to_korean():
    issue = make_issue(
        rule="duplicate_variant_combination",
        message=(
            "product_group_id 'G001' has duplicate variant color 'BLACK' "
            "and size 'M' for product_ids 'P001, P002'"
        ),
    )

    message = translate_issue_message(issue)

    assert message == (
        "상품 그룹 'G001'에서 색상 'BLACK', 사이즈 'M' 조합이 "
        "상품 ID 'P001', 'P002'에 중복되어 있습니다."
    )


def test_translate_missing_required_field_message_to_korean():
    issue = make_issue(rule="missing_required_field", message="'color' is missing")

    message = translate_issue_message(issue)

    assert message == "필수 항목 'color' 값이 누락되었습니다."


def test_translate_duplicate_product_content_message_to_korean():
    issue = make_issue(
        rule="duplicate_product_content",
        message=(
            "product_id 'P002' in group 'G002' duplicates product_id "
            "'P001' in group 'G001' with same product_name, category, color, "
            "size, and price"
        ),
    )

    message = translate_issue_message(issue)

    assert message == (
        "상품 ID 'P002'(그룹 'G002')는 상품 ID 'P001'(그룹 'G001')와 "
        "상품명, 카테고리, 색상, 사이즈, 가격이 모두 같습니다."
    )


def test_translate_unknown_duplicate_product_content_message_keeps_original_text():
    issue = make_issue(
        rule="duplicate_product_content",
        message="unexpected duplicate product content message",
    )

    message = translate_issue_message(issue)

    assert message == "unexpected duplicate product content message"


def test_translate_invalid_category_message_to_korean():
    issue = make_issue(
        rule="invalid_category",
        message="category 'SHOES' is not one of ['BOTTOM', 'OUTER', 'TOP']",
    )

    message = translate_issue_message(issue)

    assert message == "카테고리 'SHOES'는 허용된 카테고리가 아닙니다."


def test_translate_non_numeric_stock_message_to_korean():
    issue = make_issue(
        rule="invalid_stock",
        message="stock is missing or not a number",
    )

    message = translate_issue_message(issue)

    assert message == "재고가 누락되었거나 숫자 형식이 아닙니다."


def test_translate_negative_stock_message_to_korean():
    issue = make_issue(rule="invalid_stock", message="stock -3 is negative")

    message = translate_issue_message(issue)

    assert message == "재고 -3개는 음수이므로 사용할 수 없습니다."


def test_translate_out_of_stock_message_to_korean():
    issue = make_issue(
        rule="out_of_stock",
        severity="warning",
        message="stock is 0",
    )

    message = translate_issue_message(issue)

    assert message == "재고가 0개인 품절 상품입니다."


def test_translate_non_numeric_price_message_to_korean():
    issue = make_issue(
        rule="invalid_price",
        message="price is missing or not a number",
    )

    message = translate_issue_message(issue)

    assert message == "가격이 누락되었거나 숫자 형식이 아닙니다."


def test_translate_sale_price_greater_than_price_message_to_korean():
    issue = make_issue(
        rule="sale_price_greater_than_price",
        message="sale_price 60000 is greater than price 50000",
    )

    message = translate_issue_message(issue)

    assert message == "할인가 60,000원이 정상가 50,000원보다 큽니다."


def test_translate_non_positive_price_message_to_korean():
    issue = make_issue(
        rule="invalid_non_positive_price",
        message="price -5000 is not positive",
    )

    message = translate_issue_message(issue)

    assert message == "상품 가격이 0 이하입니다. 현재 가격: -5,000원."


def test_translate_zero_price_as_non_positive_message_to_korean():
    issue = make_issue(
        rule="invalid_non_positive_price",
        message="price 0 is not positive",
    )

    message = translate_issue_message(issue)

    assert message == "상품 가격이 0 이하입니다. 현재 가격: 0원."


def test_translate_category_price_anomaly_message_to_korean():
    issue = make_issue(
        rule="category_price_anomaly",
        severity="warning",
        message="price 100000 in category 'TOP' has median 20000 and ratio 5",
    )

    message = translate_issue_message(issue)

    assert message == (
        "같은 카테고리의 일반적인 가격 범위와 큰 차이가 있습니다. "
        "현재 가격 100,000원은 TOP 카테고리 중앙값 20,000원의 5배입니다."
    )


def test_translate_product_category_mismatch_message_to_korean():
    issue = make_issue(
        rule="product_category_mismatch",
        severity="warning",
        message=(
            "product_name keyword '부츠' implies category '신발' "
            "but current category is '상의'"
        ),
    )

    message = translate_issue_message(issue)

    assert message == (
        "상품명에서 '부츠'가 확인되어 신발 상품으로 추정되지만 "
        "현재 카테고리는 '상의'입니다."
    )


def test_translate_unknown_category_price_anomaly_message_keeps_original_text():
    issue = make_issue(
        rule="category_price_anomaly",
        severity="warning",
        message="unexpected category price anomaly message",
    )

    message = translate_issue_message(issue)

    assert message == "unexpected category price anomaly message"


def test_translate_unknown_message_keeps_original_text():
    issue = make_issue(rule="unknown_rule", message="unexpected validation message")

    message = translate_issue_message(issue)

    assert message == "unexpected validation message"


@pytest.mark.parametrize(
    ("rule", "message", "expected"),
    [
        (
            "prohibited_term",
            "field 'product_name' contains prohibited term '카톡'",
            "상품명에 금지어 '카톡'이 포함되어 있습니다.",
        ),
        (
            "email_address",
            "field 'description' contains email address 'te**@example.com'",
            "상품 설명에 이메일 주소 'te**@example.com'이 포함되어 있습니다.",
        ),
        (
            "phone_number",
            "field 'seller' contains phone number '010-****-5678'",
            "판매자 정보에 전화번호 '010-****-5678'이 포함되어 있습니다.",
        ),
        (
            "resident_registration_number",
            (
                "field 'description' contains resident registration number "
                "'000000-*******'"
            ),
            "상품 설명에 주민등록번호 형식 '000000-*******'이 포함되어 있습니다.",
        ),
        (
            "suspected_bank_account",
            "field 'description' contains suspected bank account '123-***-***012'",
            (
                "상품 설명에 계좌번호로 의심되는 값 '123-***-***012'이 "
                "포함되어 있습니다."
            ),
        ),
    ],
)
def test_translate_content_safety_messages_to_korean(rule, message, expected):
    issue = make_issue(rule=rule, message=message)

    translated_message = translate_issue_message(issue)

    assert translated_message == expected


@pytest.mark.parametrize(
    "rule",
    [
        "prohibited_term",
        "email_address",
        "phone_number",
        "resident_registration_number",
        "suspected_bank_account",
    ],
)
def test_translate_unknown_content_safety_message_keeps_original_text(rule):
    issue = make_issue(rule=rule, message="unexpected content safety message")

    message = translate_issue_message(issue)

    assert message == "unexpected content safety message"


def test_field_labels_include_content_scan_fields():
    assert FIELD_LABELS == {
        "product_name": "상품명",
        "description": "상품 설명",
        "seller": "판매자 정보",
    }


@pytest.mark.parametrize(
    ("rule", "message", "expected_label", "recommendation_fragment"),
    [
        (
            "prohibited_term",
            "field 'product_name' contains prohibited term '카톡'",
            "금지어 포함",
            "금지어를 제거",
        ),
        (
            "email_address",
            "field 'description' contains email address 'te**@example.com'",
            "이메일 주소 포함",
            "이메일 주소를 제거",
        ),
        (
            "phone_number",
            "field 'seller' contains phone number '010-****-5678'",
            "전화번호 포함",
            "전화번호를 제거",
        ),
        (
            "resident_registration_number",
            (
                "field 'description' contains resident registration number "
                "'000000-*******'"
            ),
            "주민등록번호 형식 포함",
            "즉시 제거",
        ),
        (
            "suspected_bank_account",
            "field 'description' contains suspected bank account '123-***-***012'",
            "계좌번호 의심",
            "개인 금융정보",
        ),
    ],
)
def test_build_result_dataframe_displays_content_safety_labels_and_recommendations(
    rule,
    message,
    expected_label,
    recommendation_fragment,
):
    issue = make_issue(
        rule=rule,
        severity="warning" if rule == "suspected_bank_account" else "error",
        message=message,
    )

    df = build_result_dataframe([issue])

    assert df.iloc[0]["오류 항목"] == expected_label
    assert recommendation_fragment in df.iloc[0]["수정 권장사항"]


def test_build_result_dataframe_does_not_show_raw_personal_information():
    issues = [
        make_issue(
            rule="email_address",
            message="field 'description' contains email address 'te**@example.com'",
        ),
        make_issue(
            rule="phone_number",
            message="field 'seller' contains phone number '010-****-5678'",
        ),
        make_issue(
            rule="resident_registration_number",
            message=(
                "field 'description' contains resident registration number "
                "'000000-*******'"
            ),
        ),
        make_issue(
            rule="suspected_bank_account",
            severity="warning",
            message="field 'description' contains suspected bank account '123-***-***012'",
        ),
    ]

    df = build_result_dataframe(issues)
    reason_text = " ".join(df["오류 이유"].tolist())

    assert "test@example.com" not in reason_text
    assert "010-1234-5678" not in reason_text
    assert "000000-1234567" not in reason_text
    assert "123-456-789012" not in reason_text
    assert "te**@example.com" in reason_text
    assert "010-****-5678" in reason_text
    assert "000000-*******" in reason_text
    assert "123-***-***012" in reason_text


def test_build_result_dataframe_uses_expected_columns_and_display_values():
    issues = [
        make_issue(
            rule="category_price_anomaly",
            severity="warning",
            product_id="P010",
            product_group_id="G010",
            message="price 100000 in category 'TOP' has median 20000 and ratio 5",
        ),
        make_issue(
            rule="invalid_non_positive_price",
            severity="error",
            product_id="P020",
            product_group_id="G020",
            message="price -5000 is not positive",
        ),
    ]

    df = build_result_dataframe(issues)

    assert list(df.columns) == RESULT_COLUMNS
    assert df.iloc[0]["검수 상태"] == "오류"
    assert df.iloc[0]["오류 항목"] == "가격 오류"
    assert df.iloc[0]["상품 그룹 ID"] == "G020"
    assert df.iloc[0]["상품 ID"] == "P020"
    assert df.iloc[0]["오류 이유"] == "상품 가격이 0 이하입니다. 현재 가격: -5,000원."
    assert df.iloc[0]["수정 권장사항"] == PRICE_RECOMMENDATION
    assert df.iloc[0]["위험 수준"] == "높음"
    assert df.iloc[1]["검수 상태"] == "주의"
    assert df.iloc[1]["위험 수준"] == "중간"


def test_build_result_dataframe_uses_positive_price_recommendation_for_invalid_price():
    issue = make_issue(
        rule="invalid_price",
        message="price is missing or not a number",
    )

    df = build_result_dataframe([issue])

    assert df.iloc[0]["수정 권장사항"] == PRICE_RECOMMENDATION
    assert "가격을 0 이상의 정수로 입력하세요." not in df.iloc[0]["수정 권장사항"]


def test_build_result_dataframe_uses_positive_price_recommendation_for_zero_price():
    issue = make_issue(rule="zero_price", message="price is 0")

    df = build_result_dataframe([issue])

    assert df.iloc[0]["수정 권장사항"] == PRICE_RECOMMENDATION
    assert "가격을 0 이상의 정수로 입력하세요." not in df.iloc[0]["수정 권장사항"]


def test_build_result_dataframe_displays_non_standard_color_warning_in_korean():
    issue = make_issue(
        rule="non_standard_color",
        severity="warning",
        message="color '블랙' should be standardized to 'BLACK'",
    )

    df = build_result_dataframe([issue])
    row = df.iloc[0]

    assert row["검수 상태"] == "주의"
    assert row["오류 항목"] == "색상 표기 비표준"
    assert row["오류 이유"] == "색상 '블랙'은 표준값 'BLACK'으로 통일하는 것이 좋습니다."
    assert row["수정 권장사항"] == "오류 이유에 표시된 표준 색상값으로 수정하세요."
    assert row["위험 수준"] == "낮음"
    assert issue.message not in row["오류 이유"]


def test_build_result_dataframe_displays_non_standard_size_warning_in_korean():
    issue = make_issue(
        rule="non_standard_size",
        severity="warning",
        message="size 'medium' should be standardized to 'M'",
    )

    df = build_result_dataframe([issue])
    row = df.iloc[0]

    assert row["검수 상태"] == "주의"
    assert row["오류 항목"] == "사이즈 표기 비표준"
    assert row["오류 이유"] == "사이즈 'medium'은 표준값 'M'으로 통일하는 것이 좋습니다."
    assert row["수정 권장사항"] == "오류 이유에 표시된 표준 사이즈값으로 수정하세요."
    assert row["위험 수준"] == "낮음"
    assert issue.message not in row["오류 이유"]


@pytest.mark.parametrize(
    ("total_issue_count", "error_count", "warning_count", "expected"),
    [
        (
            8,
            6,
            2,
            "총 8건의 문제가 발견되었습니다. 오류 6건, 주의 2건입니다.",
        ),
        (
            6,
            6,
            0,
            "총 6건의 문제가 발견되었습니다. 오류 6건, 주의 0건입니다.",
        ),
        (
            2,
            0,
            2,
            "총 2건의 문제가 발견되었습니다. 오류 0건, 주의 2건입니다.",
        ),
    ],
)
def test_build_validation_summary_message_counts_errors_and_warnings(
    total_issue_count,
    error_count,
    warning_count,
    expected,
):
    assert (
        build_validation_summary_message(
            total_issue_count,
            error_count,
            warning_count,
        )
        == expected
    )


def test_build_result_dataframe_handles_empty_issue_list():
    df = build_result_dataframe([])

    assert list(df.columns) == RESULT_COLUMNS
    assert df.empty


def test_build_result_dataframe_displays_duplicate_product_content_label_and_recommendation():
    issue = make_issue(
        rule="duplicate_product_content",
        severity="error",
        product_id="P002",
        product_group_id="G002",
        message=(
            "product_id 'P002' in group 'G002' duplicates product_id "
            "'P001' in group 'G001' with same product_name, category, color, "
            "size, and price"
        ),
    )

    df = build_result_dataframe([issue])

    assert df.iloc[0]["검수 상태"] == "오류"
    assert df.iloc[0]["오류 항목"] == "완전 중복 상품"
    assert df.iloc[0]["오류 이유"] == (
        "상품 ID 'P002'(그룹 'G002')는 상품 ID 'P001'(그룹 'G001')와 "
        "상품명, 카테고리, 색상, 사이즈, 가격이 모두 같습니다."
    )
    assert "중복 등록된 상품을 삭제하거나 하나로 통합" in df.iloc[0]["수정 권장사항"]
    assert df.iloc[0]["위험 수준"] == "높음"


def test_build_result_dataframe_displays_duplicate_variant_combination_in_korean():
    issue = make_issue(
        rule="duplicate_variant_combination",
        severity="error",
        product_id="P002",
        product_group_id="G001",
        message=(
            "product_group_id 'G001' has duplicate variant color 'BLACK' "
            "and size 'M' for product_ids 'P001, P002'"
        ),
    )

    df = build_result_dataframe([issue])

    assert df.iloc[0]["검수 상태"] == "오류"
    assert df.iloc[0]["오류 항목"] == "상품 옵션 조합 중복"
    assert df.iloc[0]["오류 이유"] == (
        "상품 그룹 'G001'에서 색상 'BLACK', 사이즈 'M' 조합이 "
        "상품 ID 'P001', 'P002'에 중복되어 있습니다."
    )
    assert df.iloc[0]["수정 권장사항"] == (
        "같은 상품 그룹 안에서 색상과 사이즈 조합이 한 번만 사용되도록 "
        "중복 상품을 통합하거나 옵션 값을 수정하세요."
    )
    assert df.iloc[0]["위험 수준"] == "중간"


def test_build_result_dataframe_displays_duplicate_product_name_warning():
    issue = make_issue(
        rule="duplicate_product_name",
        severity="warning",
        product_id="P002",
        product_group_id="G002",
        message=(
            "product_name '가짜 테스트 1' normalized to '가짜테스트1' "
            "duplicates rows 2, 3 with product_ids 'P001, P002'"
        ),
    )

    df = build_result_dataframe([issue])

    assert df.iloc[0]["검수 상태"] == "주의"
    assert df.iloc[0]["오류 항목"] == "상품명 중복"
    assert "정리 후 같은 값" in df.iloc[0]["오류 이유"]
    assert df.iloc[0]["수정 권장사항"] == (
        "모델명, 색상, 옵션, 용량 또는 상품 ID를 확인하십시오."
    )
    assert df.iloc[0]["위험 수준"] == "중간"


def test_build_result_dataframe_displays_price_outlier_label_and_recommendation():
    issue = make_issue(
        rule="category_price_anomaly",
        severity="warning",
        product_id="P005",
        product_group_id="G005",
        message="price 100000 in category 'TOP' has median 20000 and ratio 5",
    )

    df = build_result_dataframe([issue])

    assert df.iloc[0]["검수 상태"] == "주의"
    assert df.iloc[0]["오류 항목"] == "가격 이상치"
    assert df.iloc[0]["오류 이유"] == (
        "같은 카테고리의 일반적인 가격 범위와 큰 차이가 있습니다. "
        "현재 가격 100,000원은 TOP 카테고리 중앙값 20,000원의 5배입니다."
    )
    assert df.iloc[0]["수정 권장사항"] == (
        "가격 단위, 숫자 입력 오류, 할인 가격 입력 여부를 확인하십시오."
    )
    assert df.iloc[0]["위험 수준"] == "중간"


def test_build_result_dataframe_displays_product_category_mismatch_warning():
    issue = make_issue(
        rule="product_category_mismatch",
        severity="warning",
        product_id="P002",
        product_group_id="G001",
        message=(
            "product_name keyword '부츠' implies category '신발' "
            "but current category is '상의'"
        ),
    )

    df = build_result_dataframe([issue])

    assert df.iloc[0]["검수 상태"] == "주의"
    assert df.iloc[0]["오류 항목"] == "상품명·카테고리 불일치"
    assert df.iloc[0]["오류 이유"] == (
        "상품명에서 '부츠'가 확인되어 신발 상품으로 추정되지만 "
        "현재 카테고리는 '상의'입니다."
    )
    assert df.iloc[0]["수정 권장사항"] == (
        "상품명과 카테고리를 확인하고 올바른 카테고리로 수정하십시오."
    )
    assert df.iloc[0]["위험 수준"] == "중간"


def test_calculate_dataframe_height_uses_min_height_for_empty_rows():
    assert calculate_dataframe_height(0, min_height=120, max_height=420) == 120


def test_calculate_dataframe_height_increases_for_small_row_counts():
    one_row_height = calculate_dataframe_height(1)
    three_row_height = calculate_dataframe_height(3)

    assert three_row_height > one_row_height


def test_calculate_dataframe_height_does_not_exceed_max_height():
    assert calculate_dataframe_height(100, min_height=120, max_height=420) == 420


def test_filter_result_dataframe_returns_all_rows_with_default_filters():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df)

    assert len(filtered_df) == len(df)
    assert list(filtered_df.columns) == RESULT_COLUMNS


def test_filter_result_dataframe_filters_error_status():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df, status_filter="오류")

    assert len(filtered_df) == 3
    assert set(filtered_df["검수 상태"]) == {"오류"}


def test_filter_result_dataframe_filters_warning_status():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df, status_filter="주의")

    assert len(filtered_df) == 1
    assert filtered_df.iloc[0]["검수 상태"] == "주의"


def test_filter_result_dataframe_filters_rule_label():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df, rule_filter="가격 오류")

    assert len(filtered_df) == 2
    assert set(filtered_df["오류 항목"]) == {"가격 오류"}


def test_filter_result_dataframe_searches_exact_product_id_text():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df, product_id_query="P003")

    assert len(filtered_df) == 2
    assert set(filtered_df["상품 ID"]) == {"P003"}


def test_filter_result_dataframe_searches_partial_product_id_text():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df, product_id_query="P00")

    assert len(filtered_df) == 4


def test_filter_result_dataframe_searches_product_id_case_insensitively():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df, product_id_query="p003")

    assert len(filtered_df) == 2
    assert set(filtered_df["상품 ID"]) == {"P003"}


def test_filter_result_dataframe_strips_product_id_query_spaces():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df, product_id_query="  P003  ")

    assert len(filtered_df) == 2
    assert set(filtered_df["상품 ID"]) == {"P003"}


def test_filter_result_dataframe_applies_combined_filters():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(
        df,
        status_filter="오류",
        rule_filter="가격 오류",
        product_id_query="P004",
    )

    assert len(filtered_df) == 1
    assert filtered_df.iloc[0]["상품 ID"] == "P004"


def test_filter_result_dataframe_keeps_columns_when_no_rows_match():
    df = make_result_dataframe()

    filtered_df = filter_result_dataframe(df, product_id_query="NOT_FOUND")

    assert filtered_df.empty
    assert list(filtered_df.columns) == RESULT_COLUMNS


def test_filter_result_dataframe_handles_empty_dataframe():
    df = pd.DataFrame(columns=RESULT_COLUMNS)

    filtered_df = filter_result_dataframe(
        df,
        status_filter="오류",
        rule_filter="가격 오류",
        product_id_query="P001",
    )

    assert filtered_df.empty
    assert list(filtered_df.columns) == RESULT_COLUMNS


def test_filter_result_dataframe_handles_missing_product_ids():
    df = make_result_dataframe()
    df.loc[0, "상품 ID"] = None
    df.loc[1, "상품 ID"] = ""
    df.loc[2, "상품 ID"] = pd.NA

    filtered_df = filter_result_dataframe(df, product_id_query="P004")

    assert len(filtered_df) == 1
    assert filtered_df.iloc[0]["상품 ID"] == "P004"


def test_filter_result_dataframe_does_not_change_original_dataframe():
    df = make_result_dataframe()
    original_df = df.copy(deep=True)

    filter_result_dataframe(df, status_filter="오류", product_id_query="P004")

    pd.testing.assert_frame_equal(df, original_df)


def test_build_result_dataframe_presents_group_category_issue_in_korean():
    message = build_group_category_message(
        'G"한글, 001',
        [
            {
                "display_value": "TOP, PREMIUM",
                "product_ids": ["P'001", 'P"002'],
            },
            {
                "display_value": '가방 "한정판"',
                "product_ids": ["상품 003"],
            },
        ],
    )
    issue = make_issue(
        rule="inconsistent_group_category",
        severity="error",
        product_group_id='G"한글, 001',
        product_id="P'001",
        message=message,
    )

    result = build_result_dataframe([issue])

    assert result.iloc[0].to_dict() == {
        "검수 상태": "오류",
        "오류 항목": "상품 그룹 카테고리 불일치",
        "상품 그룹 ID": 'G"한글, 001',
        "상품 ID": "P'001",
        "오류 이유": (
            "상품 그룹 'G\"한글, 001'에 서로 다른 카테고리 "
            "'TOP, PREMIUM', '가방 \"한정판\"'가 함께 등록되어 있습니다."
        ),
        "수정 권장사항": (
            "같은 상품 그룹의 상품이 동일한 카테고리를 사용하도록 "
            "product_group_id 또는 category 값을 확인하세요."
        ),
        "위험 수준": "중간",
    }
    assert "inconsistent_group_category" not in result.iloc[0]["오류 이유"]
    assert "product_ids" not in result.iloc[0]["오류 이유"]


def test_translate_group_category_message_uses_safe_korean_fallback_for_bad_json():
    internal_message = "inconsistent_group_category:{broken-json"
    issue = make_issue(
        rule="inconsistent_group_category",
        message=internal_message,
    )

    reason = translate_issue_message(issue)
    result = build_result_dataframe([issue])

    assert reason == "상품 그룹의 카테고리 값이 서로 다릅니다."
    assert result.iloc[0]["오류 이유"] == reason
    assert internal_message not in reason
    assert result.iloc[0]["수정 권장사항"]


def test_translate_group_category_message_uses_safe_fallback_for_deep_json():
    deeply_nested_categories = "[" * 1500 + "0" + "]" * 1500
    internal_message = (
        'inconsistent_group_category:{"product_group_id":"G001","categories":'
        f"{deeply_nested_categories}}}"
    )
    issue = make_issue(
        rule="inconsistent_group_category",
        message=internal_message,
    )

    assert translate_issue_message(issue) == "상품 그룹의 카테고리 값이 서로 다릅니다."


def test_filter_result_dataframe_filters_group_category_rule_label():
    issue = make_issue(
        rule="inconsistent_group_category",
        message=build_group_category_message(
            "G001",
            [
                {"display_value": "TOP", "product_ids": ["P001"]},
                {"display_value": "BOTTOM", "product_ids": ["P002"]},
            ],
        ),
    )
    result = build_result_dataframe([issue])

    filtered = filter_result_dataframe(
        result,
        status_filter="오류",
        rule_filter="상품 그룹 카테고리 불일치",
        product_id_query="p001",
    )

    assert len(filtered) == 1
    assert filtered.iloc[0]["상품 ID"] == "P001"
