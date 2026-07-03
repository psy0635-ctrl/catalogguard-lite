import pytest

from config.settings import MAX_CSV_ROWS, MAX_UPLOAD_SIZE_BYTES, REQUIRED_COLUMNS
from core.upload_validator import (
    CsvUploadValidationError,
    decode_csv_bytes,
    validate_and_read_uploaded_csv,
    validate_csv_file_size,
    validate_csv_filename,
)


ROW_VALUES = {
    "product_group_id": "G001",
    "product_id": "P001",
    "product_name": "오버핏 반팔 티셔츠",
    "category": "TOP",
    "color": "BLACK",
    "size": "M",
    "stock": "5",
    "price": "19000",
    "image_path": "a.jpg",
    "description": "안전한 상품 설명",
    "seller": "공식 판매자",
    "external_code": "EXT001",
    "memo": "테스트 메모",
}


def make_csv_text(
    *,
    columns: list[str] | None = None,
    rows: int = 1,
    product_name: str = "오버핏 반팔 티셔츠",
) -> str:
    csv_columns = columns or list(REQUIRED_COLUMNS)
    row_values = {**ROW_VALUES, "product_name": product_name}
    header = ",".join(csv_columns)
    row = ",".join(row_values.get(column.strip(), "") for column in csv_columns)
    return f"{header}\n" + "\n".join(row for _ in range(rows)) + "\n"


def assert_upload_error(file_bytes: bytes, expected_message: str) -> None:
    with pytest.raises(CsvUploadValidationError, match=expected_message):
        validate_and_read_uploaded_csv("products.csv", file_bytes)


def test_validate_and_read_uploaded_csv_accepts_utf8_csv():
    csv_text = make_csv_text()

    dataframe = validate_and_read_uploaded_csv("products.csv", csv_text.encode("utf-8"))

    assert len(dataframe) == 1
    assert list(dataframe.columns) == list(REQUIRED_COLUMNS)
    assert dataframe.loc[0, "product_name"] == "오버핏 반팔 티셔츠"


def test_validate_and_read_uploaded_csv_accepts_utf8_bom_csv():
    csv_bytes = b"\xef\xbb\xbf" + make_csv_text().encode("utf-8")

    dataframe = validate_and_read_uploaded_csv("products.csv", csv_bytes)

    assert len(dataframe) == 1
    assert dataframe.loc[0, "product_id"] == "P001"


def test_validate_and_read_uploaded_csv_accepts_cp949_csv():
    csv_text = make_csv_text(product_name="오버핏 반팔 티셔츠")

    dataframe = validate_and_read_uploaded_csv("products.csv", csv_text.encode("cp949"))

    assert len(dataframe) == 1
    assert dataframe.loc[0, "product_name"] == "오버핏 반팔 티셔츠"


@pytest.mark.parametrize("filename", ["products.csv", "products.CSV", "상품목록.CsV"])
def test_validate_csv_filename_accepts_csv_extension_case_insensitively(filename):
    validate_csv_filename(filename)


@pytest.mark.parametrize(
    "filename",
    ["products.xlsx", "products.txt", "products.exe", "products", None, ""],
)
def test_validate_csv_filename_rejects_non_csv_extension(filename):
    with pytest.raises(CsvUploadValidationError, match="CSV 파일만 업로드"):
        validate_csv_filename(filename)


@pytest.mark.parametrize("file_bytes", [b"", b"   ", b"\n\n", b"\xef\xbb\xbf"])
def test_validate_and_read_uploaded_csv_rejects_empty_files(file_bytes):
    assert_upload_error(file_bytes, "업로드한 파일이 비어 있습니다")


def test_validate_csv_file_size_allows_exact_limit():
    validate_csv_file_size(b"x" * MAX_UPLOAD_SIZE_BYTES)


def test_validate_csv_file_size_rejects_over_limit():
    with pytest.raises(CsvUploadValidationError, match="파일 크기가 너무 큽니다"):
        validate_csv_file_size(b"x" * (MAX_UPLOAD_SIZE_BYTES + 1))


def test_validate_and_read_uploaded_csv_rejects_nul_bytes():
    csv_bytes = b"product_id,product_name\x00,category\nP001,test,TOP\n"

    assert_upload_error(csv_bytes, "일반적인 CSV 텍스트 파일이 아닙니다")


def test_decode_csv_bytes_rejects_unsupported_encoding():
    with pytest.raises(CsvUploadValidationError, match="파일 인코딩을 읽을 수 없습니다"):
        decode_csv_bytes(b"\x80")


def test_validate_and_read_uploaded_csv_rejects_bad_csv_quotes():
    csv_text = (
        ",".join(REQUIRED_COLUMNS)
        + '\nG001,P001,"닫히지 않은 상품명,TOP,BLACK,M,5,19000,a.jpg\n'
    )

    assert_upload_error(csv_text.encode("utf-8"), "CSV 형식이 올바르지 않습니다")


def test_validate_and_read_uploaded_csv_rejects_wrong_column_count():
    csv_text = ",".join(REQUIRED_COLUMNS) + "\nG001,P001,상품명\n"

    assert_upload_error(csv_text.encode("utf-8"), "CSV 형식이 올바르지 않습니다")


@pytest.mark.parametrize(
    "columns",
    [
        [
            "product_group_id",
            "product_id",
            "",
            "product_name",
            "category",
            "color",
            "size",
            "stock",
            "price",
            "image_path",
        ],
        [
            "product_group_id",
            "product_id",
            "   ",
            "product_name",
            "category",
            "color",
            "size",
            "stock",
            "price",
            "image_path",
        ],
    ],
)
def test_validate_and_read_uploaded_csv_rejects_blank_column_names(columns):
    csv_text = make_csv_text(columns=columns)

    assert_upload_error(csv_text.encode("utf-8"), "이름이 비어 있는 컬럼이 있습니다")


@pytest.mark.parametrize(
    "columns",
    [
        [
            "product_group_id",
            "product_id",
            "product_name",
            "product_id",
            "category",
            "color",
            "size",
            "stock",
            "price",
            "image_path",
        ],
        [
            "product_group_id",
            "product_id",
            "product_name",
            " PRODUCT_ID ",
            "category",
            "color",
            "size",
            "stock",
            "price",
            "image_path",
        ],
    ],
)
def test_validate_and_read_uploaded_csv_rejects_duplicate_column_names(columns):
    csv_text = make_csv_text(columns=columns)

    assert_upload_error(csv_text.encode("utf-8"), "중복된 컬럼명이 있습니다: product_id")


def test_validate_and_read_uploaded_csv_rejects_missing_required_columns_in_order():
    columns = [
        "product_group_id",
        "product_id",
        "color",
        "size",
        "stock",
        "price",
        "image_path",
    ]
    csv_text = make_csv_text(columns=columns)

    with pytest.raises(CsvUploadValidationError) as exc_info:
        validate_and_read_uploaded_csv("products.csv", csv_text.encode("utf-8"))

    assert str(exc_info.value) == "필수 컬럼이 없습니다: product_name, category"


def test_validate_and_read_uploaded_csv_allows_missing_optional_columns():
    csv_text = make_csv_text(columns=list(REQUIRED_COLUMNS))

    dataframe = validate_and_read_uploaded_csv("products.csv", csv_text.encode("utf-8"))

    assert "description" not in dataframe.columns
    assert "seller" not in dataframe.columns


def test_validate_and_read_uploaded_csv_allows_extra_columns():
    columns = [*REQUIRED_COLUMNS, "external_code", "memo"]
    csv_text = make_csv_text(columns=columns)

    dataframe = validate_and_read_uploaded_csv("products.csv", csv_text.encode("utf-8"))

    assert list(dataframe.columns) == columns
    assert dataframe.loc[0, "external_code"] == "EXT001"
    assert dataframe.loc[0, "memo"] == "테스트 메모"


def test_validate_and_read_uploaded_csv_rejects_header_only_csv():
    csv_text = ",".join(REQUIRED_COLUMNS) + "\n"

    assert_upload_error(csv_text.encode("utf-8"), "CSV에 상품 데이터가 없습니다")


def test_validate_and_read_uploaded_csv_allows_maximum_row_count():
    csv_text = make_csv_text(rows=MAX_CSV_ROWS)

    dataframe = validate_and_read_uploaded_csv("products.csv", csv_text.encode("utf-8"))

    assert len(dataframe) == MAX_CSV_ROWS


def test_validate_and_read_uploaded_csv_rejects_over_maximum_row_count():
    csv_text = make_csv_text(rows=MAX_CSV_ROWS + 1)

    assert_upload_error(csv_text.encode("utf-8"), "상품 데이터가 너무 많습니다")


def test_validate_and_read_uploaded_csv_does_not_change_original_bytes():
    file_bytes = make_csv_text().encode("utf-8")
    original_bytes = file_bytes[:]

    validate_and_read_uploaded_csv("products.csv", file_bytes)

    assert file_bytes == original_bytes


def test_validate_and_read_uploaded_csv_trims_header_and_keeps_column_order():
    columns = [f" {column} " for column in REQUIRED_COLUMNS]
    csv_text = make_csv_text(columns=columns)

    dataframe = validate_and_read_uploaded_csv("products.csv", csv_text.encode("utf-8"))

    assert list(dataframe.columns) == list(REQUIRED_COLUMNS)


def test_validate_and_read_uploaded_csv_rejects_non_comma_delimited_file():
    csv_text = "product_id;product_name;category\nP001;상품명;TOP\n"

    with pytest.raises(CsvUploadValidationError, match="필수 컬럼이 없습니다"):
        validate_and_read_uploaded_csv("products.csv", csv_text.encode("utf-8"))
