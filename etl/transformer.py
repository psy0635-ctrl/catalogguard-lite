import json
from dataclasses import dataclass

from config.settings import CSV_TEMPLATE_COLUMNS
from etl.models import ETLProfile


@dataclass(frozen=True)
class TransformRowsResult:
    loaded_rows: list[dict[str, str]]
    rejected_rows: list[dict[str, str]]


ERROR_MESSAGES = {
    "MISSING_SOURCE_VALUE": "필수 공급사 값이 비어 있습니다.",
    "MISSING_PRODUCT_ID": "상품 ID가 비어 있습니다.",
    "INVALID_PRICE": "가격 값을 숫자로 변환할 수 없습니다.",
    "NEGATIVE_PRICE": "가격은 음수일 수 없습니다.",
    "INVALID_STOCK": "재고 값을 정수로 변환할 수 없습니다.",
    "NEGATIVE_STOCK": "재고는 음수일 수 없습니다.",
}


def _clean_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _parse_price(value: str) -> tuple[str | None, str | None]:
    normalized = value.replace("₩", "").replace(",", "").strip()
    if not normalized:
        return None, "INVALID_PRICE"
    try:
        parsed = int(normalized)
    except ValueError:
        return None, "INVALID_PRICE"
    if parsed < 0:
        return None, "NEGATIVE_PRICE"
    return str(parsed), None


def _parse_stock(value: str) -> tuple[str | None, str | None]:
    if not value:
        return None, "INVALID_STOCK"
    try:
        parsed = int(value)
    except ValueError:
        return None, "INVALID_STOCK"
    if parsed < 0:
        return None, "NEGATIVE_STOCK"
    return str(parsed), None


def _build_standard_row(source_row: dict[str, object], profile: ETLProfile) -> dict[str, str]:
    row = {column: _clean_text(profile.defaults.get(column, "")) for column in CSV_TEMPLATE_COLUMNS}
    for source_column, target_columns in profile.source_columns.items():
        value = _clean_text(source_row.get(source_column, ""))
        if isinstance(target_columns, str):
            target_columns = (target_columns,)
        for target_column in target_columns:
            if value or target_column not in profile.defaults:
                row[target_column] = value
    return row


def _build_rejection(
    source_row_number: int,
    source_row: dict[str, object],
    errors: list[tuple[str, str]],
) -> dict[str, str]:
    return {
        "source_row_number": str(source_row_number),
        "error_code": json.dumps([code for code, _ in errors], ensure_ascii=False),
        "error_message": json.dumps([message for _, message in errors], ensure_ascii=False),
        **{column: _clean_text(value) for column, value in source_row.items()},
    }


def transform_rows(
    source_rows: list[dict[str, object]],
    profile: ETLProfile,
    source_row_numbers: list[int] | None = None,
) -> TransformRowsResult:
    loaded_rows: list[dict[str, str]] = []
    rejected_rows: list[dict[str, str]] = []

    row_numbers = source_row_numbers or list(range(2, len(source_rows) + 2))
    for source_row_number, source_row in zip(row_numbers, source_rows, strict=True):
        errors = [
            (
                "MISSING_SOURCE_VALUE",
                f"필수 공급사 값이 비어 있습니다: {column}",
            )
            for column in profile.required_source_columns
            if not _clean_text(source_row.get(column, ""))
        ]
        row = _build_standard_row(source_row, profile)

        if not row["product_id"]:
            errors.append(("MISSING_PRODUCT_ID", ERROR_MESSAGES["MISSING_PRODUCT_ID"]))

        parsed_price, price_error = _parse_price(row["price"])
        if price_error:
            errors.append((price_error, ERROR_MESSAGES[price_error]))
        else:
            row["price"] = parsed_price

        parsed_stock, stock_error = _parse_stock(row["stock"])
        if stock_error:
            errors.append((stock_error, ERROR_MESSAGES[stock_error]))
        else:
            row["stock"] = parsed_stock

        if errors:
            rejected_rows.append(
                _build_rejection(source_row_number, source_row, errors)
            )
        else:
            loaded_rows.append(row)

    return TransformRowsResult(
        loaded_rows=loaded_rows,
        rejected_rows=rejected_rows,
    )
