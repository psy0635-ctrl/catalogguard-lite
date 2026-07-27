from core.privacy import (
    MOBILE_PHONE_PATTERN,
    LANDLINE_PHONE_PATTERN,
    RESIDENT_REGISTRATION_NUMBER_PATTERN,
    mask_personal_information,
)
from core.rules import find_suspected_bank_account_matches, mask_account_number


def mask_sensitive_text(value: str) -> str:
    """Mask personal and context-qualified account information in one value."""
    text = str(value)
    occupied_spans = [
        match.span()
        for pattern in (
            MOBILE_PHONE_PATTERN,
            LANDLINE_PHONE_PATTERN,
            RESIDENT_REGISTRATION_NUMBER_PATTERN,
        )
        for match in pattern.finditer(text)
    ]
    account_matches = find_suspected_bank_account_matches(text, occupied_spans)
    for match in reversed(account_matches):
        start, end = match.span()
        text = f"{text[:start]}{mask_account_number(match.group())}{text[end:]}"
    return mask_personal_information(text)


def mask_rejected_source_data(source_data: dict[str, object]) -> dict[str, str]:
    """Return a new string-valued source mapping with sensitive values masked."""
    return {
        str(key): mask_sensitive_text("" if value is None else str(value))
        for key, value in source_data.items()
    }
