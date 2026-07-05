# 역할: 검수 결과 DataFrame을 엑셀에서 안전하게 열 수 있는 다운로드 CSV로 변환합니다.
import re

import pandas as pd


DEFAULT_RESULT_FILENAME = "catalogguard_validation_results.csv"
MAX_FILENAME_STEM_LENGTH = 120
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")
FORBIDDEN_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_csv_cell(value: object) -> object:
    """CSV 수식 삽입 공격을 막기 위해 문자열 값을 안전하게 처리합니다."""
    if not isinstance(value, str):
        return value
    if not value:
        return value
    # 이미 작은따옴표로 보호된 값은 다시 붙이지 않아 다운로드 결과가 지저분해지지 않게 합니다.
    if value.startswith("'") and len(value) > 1 and value[1] in CSV_FORMULA_PREFIXES:
        return value
    if value[0] in CSV_FORMULA_PREFIXES:
        return f"'{value}"
    return value


def prepare_export_dataframe(result_df: pd.DataFrame) -> pd.DataFrame:
    """원본 결과 DataFrame을 수정하지 않고 다운로드용 복사본을 만듭니다."""
    export_df = result_df.copy(deep=True)

    for column in export_df.columns:
        values = export_df[column].tolist()
        if not any(isinstance(value, str) for value in values):
            continue

        export_df[column] = pd.Series(
            [sanitize_csv_cell(value) for value in values],
            index=export_df.index,
            dtype=object,
        )

    return export_df


def build_validation_result_csv(result_df: pd.DataFrame) -> bytes:
    """검수 결과를 UTF-8 BOM CSV 바이트로 변환합니다."""
    export_df = prepare_export_dataframe(result_df)
    csv_text = export_df.to_csv(index=False)
    return csv_text.encode("utf-8-sig")


def build_result_filename(uploaded_filename: str | None) -> str:
    """업로드한 파일명을 바탕으로 안전한 결과 파일명을 만듭니다."""
    if not uploaded_filename:
        return DEFAULT_RESULT_FILENAME

    basename = str(uploaded_filename).replace("\\", "/").split("/")[-1].strip()
    if basename.lower().endswith(".csv"):
        basename = basename[:-4]

    safe_stem = FORBIDDEN_FILENAME_CHARS.sub("_", basename).strip(" .")
    if not safe_stem:
        return DEFAULT_RESULT_FILENAME

    safe_stem = safe_stem[:MAX_FILENAME_STEM_LENGTH]
    return f"{safe_stem}_validation_results.csv"
