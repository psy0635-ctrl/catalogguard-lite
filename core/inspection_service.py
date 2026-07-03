# 역할: Streamlit과 FastAPI가 함께 쓰는 CSV 검수 전체 흐름을 제공합니다.
from dataclasses import dataclass

import pandas as pd

from core.loader import load_products_from_dataframe
from core.models import Product, ValidationIssue
from core.presentation import build_result_dataframe
from core.privacy import create_masked_preview
from core.rules import run_all_rules
from core.upload_validator import validate_and_read_uploaded_csv


@dataclass
class InspectionSummary:
    total_products: int
    total_issues: int
    error_count: int
    warning_count: int


@dataclass
class InspectionReport:
    source_dataframe: pd.DataFrame
    masked_preview_dataframe: pd.DataFrame
    products: list[Product]
    issues: list[ValidationIssue]
    result_dataframe: pd.DataFrame
    summary: InspectionSummary


def build_inspection_summary(
    products: list[Product],
    issues: list[ValidationIssue],
) -> InspectionSummary:
    error_count = sum(issue.severity == "error" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)

    return InspectionSummary(
        total_products=len(products),
        total_issues=len(issues),
        error_count=error_count,
        warning_count=warning_count,
    )


def inspect_dataframe(dataframe: pd.DataFrame) -> InspectionReport:
    """검증된 DataFrame을 검수하고 화면/API에서 쓸 결과를 반환합니다."""
    masked_preview_dataframe = create_masked_preview(dataframe)
    products = load_products_from_dataframe(dataframe)
    issues = run_all_rules(products)
    result_dataframe = build_result_dataframe(issues)

    return InspectionReport(
        source_dataframe=dataframe,
        masked_preview_dataframe=masked_preview_dataframe,
        products=products,
        issues=issues,
        result_dataframe=result_dataframe,
        summary=build_inspection_summary(products, issues),
    )


def inspect_uploaded_csv(filename: str | None, file_bytes: bytes) -> InspectionReport:
    """업로드 CSV 바이트를 검증한 뒤 기존 검수 흐름을 실행합니다."""
    dataframe = validate_and_read_uploaded_csv(filename, file_bytes)
    return inspect_dataframe(dataframe)
