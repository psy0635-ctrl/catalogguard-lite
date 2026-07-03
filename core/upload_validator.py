# 업로드된 CSV 파일이 검수 가능한 형태인지 먼저 확인하는 공통 유틸입니다.
import csv
import io
from collections.abc import Iterable

import pandas as pd

from config.settings import (
    MAX_CSV_ROWS,
    MAX_UPLOAD_SIZE_BYTES,
    REQUIRED_COLUMNS,
    SUPPORTED_CSV_ENCODINGS,
)


class CsvUploadValidationError(ValueError):
    """사용자에게 보여줄 수 있는 CSV 업로드 검증 오류입니다."""


def format_size_limit(size_bytes: int) -> str:
    size_mb = size_bytes // (1024 * 1024)
    if size_mb * 1024 * 1024 == size_bytes:
        return f"{size_mb}MB"
    return f"{size_bytes:,}바이트"


def validate_csv_filename(filename: str | None) -> None:
    """CSV 확장자와 파일명을 검사합니다."""
    if not filename:
        raise CsvUploadValidationError("CSV 파일만 업로드할 수 있습니다.")

    basename = str(filename).replace("\\", "/").split("/")[-1].strip()
    if not basename.casefold().endswith(".csv"):
        raise CsvUploadValidationError("CSV 파일만 업로드할 수 있습니다.")


def validate_csv_file_size(file_bytes: bytes) -> None:
    """빈 파일과 최대 파일 크기를 검사합니다."""
    if len(file_bytes) == 0:
        raise CsvUploadValidationError("업로드한 파일이 비어 있습니다.")

    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        size_limit = format_size_limit(MAX_UPLOAD_SIZE_BYTES)
        raise CsvUploadValidationError(
            f"파일 크기가 너무 큽니다. 최대 {size_limit}까지 업로드할 수 있습니다."
        )


def validate_no_nul_bytes(file_bytes: bytes) -> None:
    if b"\x00" in file_bytes:
        raise CsvUploadValidationError("일반적인 CSV 텍스트 파일이 아닙니다.")


def decode_csv_bytes(file_bytes: bytes) -> tuple[str, str]:
    """CSV 바이트를 지원 인코딩으로 디코딩합니다."""
    for encoding in SUPPORTED_CSV_ENCODINGS:
        try:
            return file_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise CsvUploadValidationError(
        "파일 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949 CSV를 사용해 주세요."
    )


def validate_csv_text_not_empty(csv_text: str) -> None:
    if not csv_text.lstrip("\ufeff").strip():
        raise CsvUploadValidationError("업로드한 파일이 비어 있습니다.")


def _get_csv_reader(csv_text: str) -> csv.reader:
    return csv.reader(io.StringIO(csv_text), strict=True)


def _is_blank_csv_row(row: list[str]) -> bool:
    return not row or all(value.strip() == "" for value in row)


def find_duplicate_columns(columns: Iterable[str]) -> list[str]:
    seen_columns: dict[str, str] = {}
    duplicates = []

    for column in columns:
        key = column.casefold()
        if key in seen_columns:
            duplicate = seen_columns[key]
            if duplicate not in duplicates:
                duplicates.append(duplicate)
            continue

        seen_columns[key] = column

    return duplicates


def validate_csv_header(csv_text: str) -> list[str]:
    """빈 컬럼명, 중복 컬럼명, 필수 컬럼 누락을 확인합니다."""
    reader = _get_csv_reader(csv_text)

    try:
        raw_header = next(reader)
    except StopIteration as error:
        raise CsvUploadValidationError("업로드한 파일이 비어 있습니다.") from error
    except csv.Error as error:
        raise CsvUploadValidationError(
            "CSV 형식이 올바르지 않습니다. 따옴표와 열 개수를 확인해 주세요."
        ) from error

    cleaned_header = [column.strip() for column in raw_header]
    if not cleaned_header or any(column == "" for column in cleaned_header):
        raise CsvUploadValidationError("이름이 비어 있는 컬럼이 있습니다.")

    duplicate_columns = find_duplicate_columns(cleaned_header)
    if duplicate_columns:
        duplicate_text = ", ".join(duplicate_columns)
        raise CsvUploadValidationError(f"중복된 컬럼명이 있습니다: {duplicate_text}")

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in cleaned_header
    ]
    if missing_columns:
        missing_text = ", ".join(missing_columns)
        raise CsvUploadValidationError(f"필수 컬럼이 없습니다: {missing_text}")

    return cleaned_header


def validate_csv_row_lengths(csv_text: str, expected_column_count: int) -> None:
    reader = _get_csv_reader(csv_text)

    try:
        next(reader)
        for row in reader:
            if _is_blank_csv_row(row):
                continue
            if len(row) != expected_column_count:
                raise CsvUploadValidationError(
                    "CSV 형식이 올바르지 않습니다. 따옴표와 열 개수를 확인해 주세요."
                )
    except csv.Error as error:
        raise CsvUploadValidationError(
            "CSV 형식이 올바르지 않습니다. 따옴표와 열 개수를 확인해 주세요."
        ) from error


def read_csv_dataframe(csv_text: str, cleaned_header: list[str]) -> pd.DataFrame:
    try:
        dataframe = pd.read_csv(
            io.StringIO(csv_text),
            dtype=str,
            keep_default_na=False,
            on_bad_lines="error",
        )
    except pd.errors.EmptyDataError as error:
        raise CsvUploadValidationError("업로드한 파일이 비어 있습니다.") from error
    except pd.errors.ParserError as error:
        raise CsvUploadValidationError(
            "CSV 형식이 올바르지 않습니다. 따옴표와 열 개수를 확인해 주세요."
        ) from error

    dataframe = dataframe.copy(deep=True)
    dataframe.columns = cleaned_header
    return dataframe


def validate_csv_row_count(dataframe: pd.DataFrame) -> None:
    if dataframe.empty:
        raise CsvUploadValidationError("CSV에 상품 데이터가 없습니다.")

    if len(dataframe) > MAX_CSV_ROWS:
        raise CsvUploadValidationError(
            f"상품 데이터가 너무 많습니다. 최대 {MAX_CSV_ROWS:,}행까지 지원합니다."
        )


def validate_and_read_uploaded_csv(
    filename: str | None,
    file_bytes: bytes,
) -> pd.DataFrame:
    """업로드 CSV를 검증하고 정상 DataFrame을 반환합니다."""
    validate_csv_filename(filename)
    validate_csv_file_size(file_bytes)
    validate_no_nul_bytes(file_bytes)
    csv_text, _ = decode_csv_bytes(file_bytes)
    validate_csv_text_not_empty(csv_text)
    cleaned_header = validate_csv_header(csv_text)
    validate_csv_row_lengths(csv_text, len(cleaned_header))
    dataframe = read_csv_dataframe(csv_text, cleaned_header)
    validate_csv_row_count(dataframe)
    return dataframe
