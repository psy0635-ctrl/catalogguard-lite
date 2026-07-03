import pandas as pd

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
