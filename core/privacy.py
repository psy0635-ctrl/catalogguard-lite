# 역할: 개인정보와 계좌번호 의심 값을 탐지하고 미리보기 복사본을 마스킹합니다.
import re
from collections.abc import Callable

import pandas as pd

from config.settings import BANK_ACCOUNT_CONTEXT_TERMS


EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MOBILE_PHONE_PATTERN = re.compile(r"(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
LANDLINE_PHONE_PATTERN = re.compile(r"(?<!\d)0(?:2|[3-6]\d)[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
RESIDENT_REGISTRATION_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")

BANK_ACCOUNT_PATTERN = re.compile(r"(?<![\d-])(?:\d[-\s]?){9,13}\d(?![-\s]?\d)")
BANK_ACCOUNT_MAX_DIGITS = 14


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


def normalize_content_text(value: str) -> str:
    """내용 검색을 위해 공백과 영문 대소문자를 정리합니다."""
    return " ".join(value.split()).casefold()


def spans_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    # 두 정규식 결과가 같은 글자 구간을 가리키는지 확인합니다.
    return first[0] < second[1] and second[0] < first[1]


def _has_bank_account_context_from_normalized_text(
    normalized_text: str,
    normalized_context_terms: list[tuple[str, str]],
) -> bool:
    return any(
        normalized_term in normalized_text
        for _, normalized_term in normalized_context_terms
    )


def has_bank_account_context(text: str) -> bool:
    # 긴 숫자만으로 계좌라고 판단하지 않도록, 주변 문맥어가 있는지 먼저 봅니다.
    normalized_text = normalize_content_text(text)
    normalized_context_terms = [
        (term, normalize_content_text(term)) for term in BANK_ACCOUNT_CONTEXT_TERMS
    ]
    return _has_bank_account_context_from_normalized_text(
        normalized_text,
        normalized_context_terms,
    )


def _find_suspected_bank_account_matches_with_context(
    text: str,
    occupied_spans: list[tuple[int, int]],
    has_context: bool,
    *,
    deduplicate: bool = True,
) -> list[re.Match[str]]:
    """검수는 번호별 한 건, 미리보기는 모든 출현 위치가 필요합니다."""
    if not has_context:
        return []

    matches = []
    seen_numbers = set()
    for match in BANK_ACCOUNT_PATTERN.finditer(text):
        # 이미 전화번호나 주민등록번호로 잡힌 숫자는 계좌번호로 중복 표시하지 않습니다.
        if any(spans_overlap(match.span(), occupied_span) for occupied_span in occupied_spans):
            continue

        digits = extract_digits(match.group())
        if not 10 <= len(digits) <= BANK_ACCOUNT_MAX_DIGITS:
            continue
        if deduplicate and digits in seen_numbers:
            continue

        seen_numbers.add(digits)
        matches.append(match)

    return matches


def find_suspected_bank_account_matches(
    text: str,
    occupied_spans: list[tuple[int, int]],
) -> list[re.Match[str]]:
    return _find_suspected_bank_account_matches_with_context(
        text,
        occupied_spans,
        has_bank_account_context(text),
    )


def mask_account_number(value: str) -> str:
    digits = extract_digits(value)
    return f"{digits[:3]}-***-***{digits[-3:]}"


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


def _mask_overlapping_emails(text: str) -> str:
    """원본에서 겹치는 이메일을 찾고 서로 겹치지 않는 아이디 부분만 치환합니다."""
    parts = []
    cursor = search_start = 0
    # 매번 @ 다음에서 탐색하므로 후보 수는 원문의 @ 개수를 넘지 않습니다.
    for _ in range(text.count("@")):
        match = EMAIL_PATTERN.search(text, search_start)
        if match is None:
            break
        at_index = text.index("@", match.start(), match.end())
        parts.append(text[cursor:match.start()])
        parts.append(mask_email(match.group()).split("@", 1)[0])
        cursor = at_index
        # match.end()로 건너뛰면 도메인과 겹치는 다음 이메일을 놓칩니다.
        search_start = at_index + 1
    parts.append(text[cursor:])
    return "".join(parts)


def mask_personal_information(text: str) -> str:
    masked_text = _mask_overlapping_emails(text)
    masked_text = _mask_pattern(masked_text, MOBILE_PHONE_PATTERN, mask_phone_number)
    masked_text = _mask_pattern(masked_text, LANDLINE_PHONE_PATTERN, mask_phone_number)
    masked_text = _mask_pattern(
        masked_text,
        RESIDENT_REGISTRATION_NUMBER_PATTERN,
        mask_resident_registration_number,
    )
    return masked_text


def _find_preview_account_matches(
    text: str, occupied_spans: list[tuple[int, int]]
) -> list[re.Match[str]]:
    if not has_bank_account_context(text):
        return []

    matches = []
    next_start = 0
    for start, character in enumerate(text):
        if start < next_start or not character.isdecimal():
            continue
        if start > 0 and (text[start - 1].isdecimal() or text[start - 1] == "-"):
            continue

        best = BANK_ACCOUNT_PATTERN.match(text, start)
        if best and any(spans_overlap(best.span(), span) for span in occupied_spans):
            best = None
        # 숫자마다 구분자 하나를 허용하므로 최대 탐색 폭은 2 * 자릿수 - 1입니다.
        max_end = min(len(text), start + 2 * BANK_ACCOUNT_MAX_DIGITS - 1)
        for end in range(start + 1, max_end + 1):
            if end == len(text) or not text[end].isspace():
                continue
            if best is not None and end <= best.end():
                continue
            # 표시용 문자열에서 공백을 끝 경계로 시험하며, 내부 공백은 가장 긴 후보에 남깁니다.
            candidate = BANK_ACCOUNT_PATTERN.fullmatch(text, start, end)
            if candidate and not any(
                spans_overlap(candidate.span(), span) for span in occupied_spans
            ):
                best = candidate
        if best is not None:
            matches.append(best)
            next_start = best.end()
    return matches


def mask_inspection_reason(text: str | None) -> str | None:
    """표시용 설명의 개인정보와 계좌 의심 값을 기존 문맥 기준으로 보호합니다."""
    if text is None:
        return None
    # v17의 파싱 실패 원문에는 정규화로 패턴이 사라진 개인정보도 들어 있습니다.
    if (
        re.search(r"(?:^|\n)(?:'?[=+\-@])?product_name '", text)
        and "' normalized to '" in text
        and " duplicates rows " in text
        and " with product_ids '" in text
    ):
        return "검수 상세 설명을 안전하게 표시할 수 없습니다. 오류 항목과 원본 행을 확인하세요."
    return _mask_private_text(text)


def mask_result_reason_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """식별자와 숫자 열을 보존하고 이유 열만 보호한 출력 복사본을 만듭니다."""
    protected = dataframe.copy(deep=True)
    for column in ("오류 이유", "reason"):
        if column in protected.columns:
            protected[column] = pd.Series(
                [mask_inspection_reason(value) if isinstance(value, str) else value
                 for value in protected[column]],
                index=protected.index, dtype=object,
            )
    return protected


def _mask_private_text(text: str) -> str:
    # 원본 위치에서 겹침을 판단하고 뒤에서부터 치환해 앞쪽 위치가 밀리지 않게 합니다.
    occupied_spans = [
        match.span()
        for match in [
            *find_phone_number_matches(text),
            *find_resident_registration_number_matches(text),
        ]
    ]
    account_matches = _find_preview_account_matches(text, occupied_spans)
    for match in reversed(account_matches):
        start, end = match.span()
        text = f"{text[:start]}{mask_account_number(match.group())}{text[end:]}"
    return mask_personal_information(text)


def _mask_preview_value(value):
    if not isinstance(value, str) or value == "":
        return value
    return _mask_private_text(value)


def create_masked_preview(dataframe: pd.DataFrame) -> pd.DataFrame:
    """원본 DataFrame을 바꾸지 않고 화면 미리보기용 마스킹 복사본을 만듭니다."""
    masked_dataframe = dataframe.copy(deep=True)

    for column in masked_dataframe.columns:
        if str(column) in PREVIEW_MASK_EXCLUDED_COLUMNS:
            continue
        masked_dataframe[column] = masked_dataframe[column].map(_mask_preview_value)

    return masked_dataframe
