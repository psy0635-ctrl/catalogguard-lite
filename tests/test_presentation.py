import pandas as pd

from core.models import ValidationIssue
from core.presentation import (
    RESULT_COLUMNS,
    build_result_dataframe,
    calculate_dataframe_height,
    filter_result_dataframe,
    translate_issue_message,
)


def make_issue(**overrides) -> ValidationIssue:
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
    return pd.DataFrame(
        [
            {
                "검수 상태": "오류",
                "오류 항목": "가격 오류",
                "상품 그룹 ID": "G001",
                "상품 ID": "P001",
                "오류 이유": "가격 -5000원은 음수이므로 사용할 수 없습니다.",
                "수정 권장사항": "가격을 0 이상의 정수로 입력하세요.",
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
                "수정 권장사항": "가격을 0 이상의 정수로 입력하세요.",
            },
        ],
        columns=RESULT_COLUMNS,
    )


def test_translate_duplicate_product_id_message_to_korean():
    issue = make_issue(
        rule="duplicate_product_id",
        message="product_id 'P003' is reused across groups 'G002' and 'G004'",
    )

    message = translate_issue_message(issue)

    assert message == "상품 ID 'P003'이 상품 그룹 'G002'와 'G004'에서 중복 사용되었습니다."


def test_translate_missing_required_field_message_to_korean():
    issue = make_issue(rule="missing_required_field", message="'color' is missing")

    message = translate_issue_message(issue)

    assert message == "필수 항목 'color' 값이 누락되었습니다."


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


def test_translate_negative_price_message_to_korean():
    issue = make_issue(rule="invalid_price", message="price -5000 is negative")

    message = translate_issue_message(issue)

    assert message == "가격 -5000원은 음수이므로 사용할 수 없습니다."


def test_translate_zero_price_message_to_korean():
    issue = make_issue(
        rule="zero_price",
        severity="warning",
        message="price is 0",
    )

    message = translate_issue_message(issue)

    assert message == "가격이 0원으로 입력되었습니다."


def test_translate_unknown_message_keeps_original_text():
    issue = make_issue(rule="unknown_rule", message="unexpected validation message")

    message = translate_issue_message(issue)

    assert message == "unexpected validation message"


def test_build_result_dataframe_uses_expected_columns_and_display_values():
    issues = [
        make_issue(
            rule="zero_price",
            severity="warning",
            product_id="P010",
            product_group_id="G010",
            message="price is 0",
        ),
        make_issue(
            rule="invalid_price",
            severity="error",
            product_id="P020",
            product_group_id="G020",
            message="price -5000 is negative",
        ),
    ]

    df = build_result_dataframe(issues)

    assert list(df.columns) == RESULT_COLUMNS
    assert df.iloc[0]["검수 상태"] == "오류"
    assert df.iloc[0]["오류 항목"] == "가격 오류"
    assert df.iloc[0]["상품 그룹 ID"] == "G020"
    assert df.iloc[0]["상품 ID"] == "P020"
    assert df.iloc[0]["오류 이유"] == "가격 -5000원은 음수이므로 사용할 수 없습니다."
    assert df.iloc[0]["수정 권장사항"] == "가격을 0 이상의 정수로 입력하세요."
    assert df.iloc[1]["검수 상태"] == "주의"


def test_build_result_dataframe_handles_empty_issue_list():
    df = build_result_dataframe([])

    assert list(df.columns) == RESULT_COLUMNS
    assert df.empty


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
