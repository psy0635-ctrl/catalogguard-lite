# 역할: 개인정보 탐지와 마스킹 함수가 원본 노출을 막는지 테스트합니다.
from pathlib import Path

import pandas as pd
import pytest

from core.inspection_service import inspect_uploaded_csv
from core.privacy import (
    create_masked_preview,
    mask_email,
    mask_personal_information,
    mask_phone_number,
    mask_resident_registration_number,
)


def test_mask_phone_number_masks_hyphenated_phone_number():
    assert mask_phone_number("010-1234-5678") == "010-****-5678"


def test_mask_phone_number_masks_plain_phone_number():
    assert mask_phone_number("01012345678") == "010****5678"


def test_mask_email_keeps_front_and_masks_remaining_local_part():
    assert mask_email("sample@test.com") == "sa****@test.com"


def test_mask_resident_registration_number_masks_back_digits():
    assert mask_resident_registration_number("000000-1234567") == "000000-*******"


def test_mask_personal_information_masks_values_inside_sentences():
    text = (
        "문의 전화는 010-1234-5678입니다. "
        "이메일은 seller@test.com이고 테스트 값은 000000-1234567입니다."
    )

    masked_text = mask_personal_information(text)

    assert masked_text == (
        "문의 전화는 010-****-5678입니다. "
        "이메일은 se****@test.com이고 테스트 값은 000000-*******입니다."
    )
    assert "010-1234-5678" not in masked_text
    assert "seller@test.com" not in masked_text
    assert "000000-1234567" not in masked_text


def test_mask_personal_information_keeps_general_text_unchanged():
    assert mask_personal_information("오버핏 반팔 티셔츠") == "오버핏 반팔 티셔츠"
    # 공용 마스킹 정책은 확대하지 않고, 계좌 보호는 미리보기 복사본에 적용합니다.
    assert mask_personal_information("계좌 123-456-789012") == "계좌 123-456-789012"


def test_create_masked_preview_keeps_original_dataframe_unchanged():
    original_df = pd.DataFrame(
        {
            "product_id": ["P001"],
            "description": ["문의 전화는 010-1234-5678입니다."],
        }
    )
    before_df = original_df.copy(deep=True)

    masked_df = create_masked_preview(original_df)

    pd.testing.assert_frame_equal(original_df, before_df)
    assert masked_df is not original_df
    assert masked_df.loc[0, "description"] == "문의 전화는 010-****-5678입니다."
    assert original_df.loc[0, "description"] == "문의 전화는 010-1234-5678입니다."


def test_create_masked_preview_does_not_mask_product_id_stock_or_price_columns():
    original_df = pd.DataFrame(
        {
            "product_id": ["01012345678"],
            "stock": [10],
            "price": ["01012345678"],
            "description": ["01012345678"],
        }
    )

    masked_df = create_masked_preview(original_df)

    assert masked_df.loc[0, "product_id"] == "01012345678"
    assert masked_df.loc[0, "stock"] == 10
    assert masked_df.loc[0, "price"] == "01012345678"
    assert masked_df.loc[0, "description"] == "010****5678"


def test_create_masked_preview_does_not_mask_sale_price_column():
    original_df = pd.DataFrame({"sale_price": ["010-1234-5678"]})

    masked_df = create_masked_preview(original_df)

    assert masked_df.loc[0, "sale_price"] == "010-1234-5678"


def test_create_masked_preview_handles_blank_missing_and_non_string_values():
    list_value = ["010-1234-5678"]
    original_df = pd.DataFrame(
        {
            "description": [None, "", pd.NA, list_value],
        }
    )

    masked_df = create_masked_preview(original_df)

    assert masked_df.loc[0, "description"] is None
    assert masked_df.loc[1, "description"] == ""
    assert pd.isna(masked_df.loc[2, "description"])
    assert masked_df.loc[3, "description"] == list_value


def test_create_masked_preview_removes_raw_personal_information_from_preview_rows():
    original_df = pd.DataFrame(
        {
            "product_name": ["테스트 상품"],
            "description": ["문의 010-1234-5678 seller@test.com 000000-1234567"],
            "seller": ["공식 판매자"],
        }
    )

    preview_rows = create_masked_preview(original_df).head(100)
    preview_text = preview_rows.to_csv(index=False)

    assert "010-1234-5678" not in preview_text
    assert "seller@test.com" not in preview_text
    assert "000000-1234567" not in preview_text
    assert "010-****-5678" in preview_text
    assert "se****@test.com" in preview_text
    assert "000000-*******" in preview_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("테스트 계좌 123-456-789012", "테스트 계좌 123-***-***012"),
        ("입금 123-456-789012", "입금 123-***-***012"),
        ("송금 123-456-789012", "송금 123-***-***012"),
        ("은행 123-456-789012", "은행 123-***-***012"),
        ("예금주 123-456-789012", "예금주 123-***-***012"),
        ("상품 코드 123-456-789012", "상품 코드 123-456-789012"),
        ("계좌 123-456-789012 2026", "계좌 123-***-***012 2026"),
        ("계좌 123-456-789012 999999999", "계좌 123-***-***012 999999999"),
        (
            "계좌 123-456-789012 999999999999999",
            "계좌 123-***-***012 999999999999999",
        ),
        ("계좌 123 456 789012 2026", "계좌 123-***-***012 2026"),
        (
            "계좌 123 456 789012 999999999999999",
            "계좌 123-***-***012 999999999999999",
        ),
        (
            "계좌 123-456-789012 123-456-789012",
            "계좌 123-***-***012 123-***-***012",
        ),
        (
            "계좌 123-456-789012 010-000-0000",
            "계좌 123-***-***012 010-****-0000",
        ),
        ("계좌 123 456 789012", "계좌 123-***-***012"),
        (
            "계좌 123 456 789012 123 456 789012",
            "계좌 123-***-***012 123-***-***012",
        ),
        ("계좌 12345 67890 1234", "계좌 123-***-***234"),
        ("계좌 1234567890 1234", "계좌 123-***-***234"),
        (
            "계좌 1234 5678901234 1234 5678901234",
            "계좌 123-***-***234 123-***-***234",
        ),
        (
            "상품 코드 123-456-789012 123-456-789012",
            "상품 코드 123-456-789012 123-456-789012",
        ),
        (
            "계좌 123-456-789012/123-456-789012",
            "계좌 123-***-***012/123-***-***012",
        ),
        (
            "계좌 123456789012 123 456 789012 123-456-789012",
            "계좌 123-***-***012 123-***-***012 123-***-***012",
        ),
        (
            "계좌 123-456-789012 000000-3000000",
            "계좌 123-***-***012 000000-*******",
        ),
        ("계좌 999999999 999999999999999", "계좌 999999999 999999999999999"),
        (
            "계좌 123456789012 / 123-456-789012 / 123456789012",
            "계좌 123-***-***012 / 123-***-***012 / 123-***-***012",
        ),
        (
            "문의 qa-user@example.com 계좌 010-000-0000 01000000000 "
            "000000-3000000 000000-3000000 123-456-789012",
            "문의 qa*****@example.com 계좌 010-****-0000 010****0000 "
            "000000-******* 000000-******* 123-***-***012",
        ),
    ],
)
def test_create_masked_preview_masks_all_account_occurrences_with_context(text, expected):
    source = pd.DataFrame({"description": [text]})
    before = source.copy(deep=True)

    preview = create_masked_preview(source)

    assert preview.loc[0, "description"] == expected
    pd.testing.assert_frame_equal(source, before)


@pytest.mark.parametrize(
    "column", ["product_group_id", "product_id", "stock", "price", "sale_price"]
)
def test_create_masked_preview_keeps_account_text_in_excluded_columns(column):
    source = pd.DataFrame({column: ["계좌 123-456-789012"]})

    pd.testing.assert_frame_equal(create_masked_preview(source), source)


def test_golden_account_preview_masks_number_without_changing_source():
    path = Path(__file__).parent / "quality" / "golden_catalog.csv"
    report = inspect_uploaded_csv(path.name, path.read_bytes())
    account_rows = report.source_dataframe[
        report.source_dataframe["product_id"] == "P-ACCOUNT"
    ]
    assert len(account_rows) == 1
    index = account_rows.index[0]

    assert report.source_dataframe.loc[index, "description"] == "테스트 계좌 123-456-789012"
    assert report.masked_preview_dataframe.loc[index, "description"] == (
        "테스트 계좌 123-***-***012"
    )
