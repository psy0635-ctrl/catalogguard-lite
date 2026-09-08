# 역할: 검수 결과 DataFrame을 엑셀에서 안전하게 열 수 있는 다운로드 CSV로 변환합니다.
import re
from collections.abc import Mapping, Sequence

import pandas as pd

from core.presentation import SEVERITY_LABELS, SEVERITY_ORDER


DEFAULT_RESULT_FILENAME = "catalogguard_validation_results.csv"
MAX_FILENAME_STEM_LENGTH = 120
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")
FORBIDDEN_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')
CORRECTION_WORKSHEET_COLUMNS = [
    "원본 행",
    "상품 그룹 ID",
    "상품 ID",
    "문제 수",
    "대표 검수 상태",
    "오류 항목",
    "오류 이유",
    "수정 권장사항",
]
CORRECTION_WORKSHEET_UNAVAILABLE_MESSAGE = (
    "이전 검수 이력은 원본 행 식별 정보가 없어 수정 작업표를 제공할 수 없습니다."
)
DISPLAY_SEVERITY_ORDER = {
    SEVERITY_LABELS[severity]: order for severity, order in SEVERITY_ORDER.items()
}


class CorrectionWorksheetUnavailableError(ValueError):
    """모든 issue에 source row identity가 없을 때 작업표 생성을 막습니다."""


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


def build_correction_worksheet_dataframe(
    results: Sequence[Mapping[str, object]],
) -> pd.DataFrame:
    """검수 issue를 원본 논리 행별 수정 작업표로 묶습니다."""
    if any(
        not _has_source_row_identity(result.get("source_row_number"))
        for result in results
    ):
        raise CorrectionWorksheetUnavailableError(CORRECTION_WORKSHEET_UNAVAILABLE_MESSAGE)

    grouped_results: dict[int, list[Mapping[str, object]]] = {}
    for result in results:
        source_row_number = result["source_row_number"]
        # 위 완전성 검증 뒤에는 int임이 보장됩니다.
        grouped_results.setdefault(source_row_number, []).append(result)

    rows = []
    for source_row_number in sorted(grouped_results):
        issues = grouped_results[source_row_number]
        rows.append(
            {
                "원본 행": source_row_number,
                "상품 그룹 ID": _join_distinct_values(issues, "product_group_id"),
                "상품 ID": _join_distinct_values(issues, "product_id"),
                "문제 수": len(issues),
                "대표 검수 상태": _representative_status(issues),
                "오류 항목": _join_distinct_values(issues, "error_field"),
                "오류 이유": _join_all_values(issues, "reason"),
                "수정 권장사항": _join_distinct_values(issues, "recommendation"),
            }
        )

    return pd.DataFrame(rows, columns=CORRECTION_WORKSHEET_COLUMNS)


def build_correction_worksheet_csv(results: Sequence[Mapping[str, object]]) -> bytes:
    """수정 작업표를 기존 CSV 보안·UTF-8 BOM 정책으로 내보냅니다."""
    worksheet = build_correction_worksheet_dataframe(results)
    return prepare_export_dataframe(worksheet).to_csv(index=False).encode(
        "utf-8-sig"
    )


def _has_source_row_identity(value: object) -> bool:
    return type(value) is int and value >= 2


def _join_distinct_values(
    issues: Sequence[Mapping[str, object]],
    field: str,
) -> str:
    values = _values_in_input_order(issues, field, distinct=True)
    return "\n".join(values)


def _join_all_values(
    issues: Sequence[Mapping[str, object]],
    field: str,
) -> str:
    values = _values_in_input_order(issues, field, distinct=False)
    return "\n".join(values)


def _values_in_input_order(
    issues: Sequence[Mapping[str, object]],
    field: str,
    *,
    distinct: bool,
) -> list[str]:
    values: list[str] = []
    for issue in issues:
        value = "" if issue.get(field) is None else str(issue.get(field))
        if distinct and value in values:
            continue
        values.append(value)
    return values


def _representative_status(issues: Sequence[Mapping[str, object]]) -> str:
    statuses = _values_in_input_order(issues, "status", distinct=False)
    return min(
        enumerate(statuses),
        key=lambda item: (DISPLAY_SEVERITY_ORDER.get(item[1], 99), item[0]),
    )[1]


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
