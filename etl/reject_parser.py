import csv
import io
import json
import re
from dataclasses import dataclass

from core.upload_validator import (
    CsvUploadValidationError,
    decode_csv_bytes,
    find_duplicate_columns,
    validate_csv_file_size,
    validate_csv_filename,
    validate_csv_text_not_empty,
    validate_no_nul_bytes,
)
from config.settings import MAX_CSV_ROWS
from etl.models import ETLRowError
from etl.reject_sanitizer import mask_rejected_source_data


class RejectFileValidationError(ValueError):
    """Raised when a reject CSV cannot be safely stored."""


@dataclass(frozen=True)
class ParsedRejectedRow:
    source_row_number: int
    errors: list[ETLRowError]
    masked_source_data: dict[str, str]


REJECT_REQUIRED_COLUMNS = (
    "source_row_number",
    "error_code",
    "error_field",
    "error_message",
)
ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
MAX_ERROR_CODE_LENGTH = 100
MAX_ERROR_FIELD_LENGTH = 100
MAX_ERROR_MESSAGE_LENGTH = 2_000


def _reject(message: str, error: Exception | None = None) -> RejectFileValidationError:
    return RejectFileValidationError(message) if error is None else RejectFileValidationError(message)


def _parse_json_string_list(
    value: str,
    *,
    field_name: str,
    max_length: int | None = None,
) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise _reject(f"{field_name} must be a JSON array", error) from error
    if not isinstance(parsed, list) or not parsed:
        raise _reject(f"{field_name} must be a non-empty JSON array")
    if any(not isinstance(item, str) or not item.strip() for item in parsed):
        raise _reject(f"{field_name} must contain non-blank strings")
    normalized = [item.strip() for item in parsed]
    if max_length is not None and any(len(item) > max_length for item in normalized):
        raise _reject(f"{field_name} contains an item that is too long")
    return normalized


def _parse_source_row_number(value: str) -> int:
    try:
        row_number = int(value.strip())
    except (TypeError, ValueError) as error:
        raise _reject("source_row_number must be an integer", error) from error
    if row_number < 2:
        raise _reject("source_row_number must be at least 2")
    return row_number


def parse_reject_csv(
    file_bytes: bytes,
    *,
    filename: str,
    expected_row_count: int | None = None,
) -> list[ParsedRejectedRow]:
    """Validate and parse a reject CSV without retaining raw source values."""
    try:
        validate_csv_filename(filename)
        validate_csv_file_size(file_bytes)
        validate_no_nul_bytes(file_bytes)
        csv_text, _ = decode_csv_bytes(file_bytes)
        validate_csv_text_not_empty(csv_text)
        reader = csv.reader(io.StringIO(csv_text), strict=True)
        raw_header = next(reader)
    except StopIteration as error:
        raise _reject("reject CSV must contain a header", error) from error
    except (CsvUploadValidationError, csv.Error) as error:
        raise _reject("reject CSV is invalid", error) from error

    header = [column.strip() for column in raw_header]
    if header[: len(REJECT_REQUIRED_COLUMNS)] != list(REJECT_REQUIRED_COLUMNS):
        raise _reject("reject CSV has an invalid required header")
    if len(header) <= len(REJECT_REQUIRED_COLUMNS):
        raise _reject("reject CSV must contain source columns")
    duplicates = find_duplicate_columns(header)
    if duplicates:
        raise _reject("reject CSV has duplicate columns")

    parsed_rows: list[ParsedRejectedRow] = []
    seen_row_numbers: set[int] = set()
    try:
        for values in reader:
            if not values or all(not value.strip() for value in values):
                continue
            if len(values) != len(header):
                raise _reject("reject CSV has an invalid row format")
            row = dict(zip(header, values, strict=True))
            source_row_number = _parse_source_row_number(row["source_row_number"])
            if source_row_number in seen_row_numbers:
                raise _reject("reject CSV contains duplicate source row numbers")
            seen_row_numbers.add(source_row_number)

            codes = _parse_json_string_list(
                row["error_code"],
                field_name="error_code",
                max_length=MAX_ERROR_CODE_LENGTH,
            )
            fields = _parse_json_string_list(
                row["error_field"],
                field_name="error_field",
                max_length=MAX_ERROR_FIELD_LENGTH,
            )
            messages = _parse_json_string_list(
                row["error_message"],
                field_name="error_message",
                max_length=MAX_ERROR_MESSAGE_LENGTH,
            )
            if len(codes) != len(fields) or len(codes) != len(messages):
                raise _reject("reject error arrays must have the same length")
            for code in codes:
                if ERROR_CODE_PATTERN.fullmatch(code) is None:
                    raise _reject("error_code must use uppercase snake case")

            source_data = {
                column: row[column]
                for column in header
                if column not in REJECT_REQUIRED_COLUMNS
            }
            parsed_rows.append(
                ParsedRejectedRow(
                    source_row_number=source_row_number,
                    errors=[
                        ETLRowError(code=code, field=field, message=message)
                        for code, field, message in zip(
                            codes, fields, messages, strict=True
                        )
                    ],
                    masked_source_data=mask_rejected_source_data(source_data),
                )
            )
            if len(parsed_rows) > MAX_CSV_ROWS:
                raise _reject(f"reject CSV has too many rows (maximum {MAX_CSV_ROWS})")
    except csv.Error as error:
        raise _reject("reject CSV is invalid", error) from error

    if expected_row_count is not None and len(parsed_rows) != expected_row_count:
        raise _reject("reject CSV row count does not match summary")
    return parsed_rows
