# 역할: 이메일, 전화번호, 주민등록번호 형태의 개인정보를 탐지하고 마스킹합니다.
import re
from collections.abc import Callable

import pandas as pd


EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MOBILE_PHONE_PATTERN = re.compile(r"(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
LANDLINE_PHONE_PATTERN = re.compile(r"(?<!\d)0(?:2|[3-6]\d)[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
RESIDENT_REGISTRATION_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")

PREVIEW_MASK_EXCLUDED_COLUMNS = frozenset(
    {
        # ID와 숫자 컬럼은 검수 이해에 필요하고 개인정보 패턴과 겹칠 가능성이 낮아 미리보기 마스킹에서 제외합니다.
        "product_group_id",
        "product_id",
        "stock",
        "price",
        "sale_price",
    }
)


def extract_digits(value: str) -> str:
    # 전화번호와 계좌번호처럼 구분자가 섞인 값에서 숫자만 비교할 때 사용합니다.
    return re.sub(r"\D", "", value)


def find_phone_number_matches(text: str) -> list[re.Match[str]]:
    matches = [
        *MOBILE_PHONE_PATTERN.finditer(text),
        *LANDLINE_PHONE_PATTERN.finditer(text),
    ]
    matches.sort(key=lambda match: (match.start(), match.end()))
    return matches


def find_resident_registration_number_matches(text: str) -> list[re.Match[str]]:
    return list(RESIDENT_REGISTRATION_NUMBER_PATTERN.finditer(text))


def mask_email(value: str) -> str:
    # 이메일 아이디 앞부분만 남기고 나머지 길이만큼 별표로 가립니다.
    local_part, domain = value.split("@", 1)
    visible_count = 1 if len(local_part) <= 2 else 2
    visible_local_part = local_part[:visible_count]
    masked_count = max(1, len(local_part) - visible_count)
    return f"{visible_local_part}{'*' * masked_count}@{domain}"


def mask_phone_number(value: str) -> str:
    digits = extract_digits(value)
    separated_parts = [part for part in re.split(r"[-\s]+", value.strip()) if part]

    if len(separated_parts) >= 3:
        return f"{separated_parts[0]}-****-{separated_parts[-1]}"

    prefix_length = 2 if digits.startswith("02") else 3
    return f"{digits[:prefix_length]}****{digits[-4:]}"


def mask_resident_registration_number(value: str) -> str:
    front, separator, _ = value.partition("-")
    if separator:
        return f"{front}{separator}*******"
    return f"{value[:6]}*******"


def _mask_pattern(
    text: str,
    pattern: re.Pattern[str],
    masker: Callable[[str], str],
) -> str:
    return pattern.sub(lambda match: masker(match.group()), text)


def mask_personal_information(text: str) -> str:
    masked_text = _mask_pattern(text, EMAIL_PATTERN, mask_email)
    masked_text = _mask_pattern(masked_text, MOBILE_PHONE_PATTERN, mask_phone_number)
    masked_text = _mask_pattern(masked_text, LANDLINE_PHONE_PATTERN, mask_phone_number)
    masked_text = _mask_pattern(
        masked_text,
        RESIDENT_REGISTRATION_NUMBER_PATTERN,
        mask_resident_registration_number,
    )
    return masked_text


def _mask_preview_value(value):
    if not isinstance(value, str):
        return value
    if value == "":
        return value
    return mask_personal_information(value)


def create_masked_preview(dataframe: pd.DataFrame) -> pd.DataFrame:
    """원본 DataFrame을 바꾸지 않고 화면 미리보기용 마스킹 복사본을 만듭니다."""
    masked_dataframe = dataframe.copy(deep=True)

    for column in masked_dataframe.columns:
        if str(column) in PREVIEW_MASK_EXCLUDED_COLUMNS:
            continue
        masked_dataframe[column] = masked_dataframe[column].map(_mask_preview_value)

    return masked_dataframe
