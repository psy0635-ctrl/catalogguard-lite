"""Opt-in before baseline for the CSV inspection pipeline; no production timing hooks."""

import csv
import gc
import io
import json
import os
import platform
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable

import pandas as pd
import pytest

from config.settings import (
    CSV_TEMPLATE_COLUMNS,
    INSPECTION_VERSION,
    MAX_CSV_ROWS,
    MAX_UPLOAD_SIZE_BYTES,
)
from core.inspection_service import build_inspection_summary, inspect_dataframe
from core.loader import load_products_from_dataframe
from core.presentation import build_result_dataframe
from core.privacy import create_masked_preview
from core.rules import (
    RULES,
    check_prohibited_and_personal_information,
    run_all_rules,
)
from core.upload_validator import validate_and_read_uploaded_csv


RUN_ENVIRONMENT_VARIABLE = "RUN_INSPECTION_PERFORMANCE"
WARMUP_REPETITIONS = 1
MEASURED_REPETITIONS = 2
PIPELINE_ROWS = (1_000, 5_000, 10_000)
DUPLICATE_ROWS = (250, 500, 1_000)
BENCHMARK_FILENAME = "synthetic_inspection_baseline.csv"


def _require_opt_in() -> None:
    if os.environ.get(RUN_ENVIRONMENT_VARIABLE) != "1":
        pytest.skip(f"set {RUN_ENVIRONMENT_VARIABLE}=1 to run this benchmark")


def _normal_row(index: int) -> dict[str, str]:
    return {
        "product_group_id": f"NORMAL-G{index:05d}",
        "product_id": f"NORMAL-P{index:05d}",
        "product_name": f"Synthetic item {index:05d}",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": "10",
        "price": "10000",
        "sale_price": "",
        "image_path": f"synthetic/images/{index:05d}.jpg",
        "description": "SYNTHETIC CATALOG ITEM",
        "seller": "SYNTHETIC SELLER",
    }


def build_synthetic_rows(dataset: str, row_count: int) -> list[dict[str, str]]:
    if row_count <= 0:
        raise ValueError("row_count must be positive")

    rows = [_normal_row(index) for index in range(row_count)]
    if dataset == "normal_unique":
        return rows
    if dataset == "issue_heavy":
        for row in rows:
            # A stable single error per row; invalid prices are excluded by the outlier rule.
            row["price"] = "0"
        return rows
    if dataset == "duplicate_concentrated":
        for index, row in enumerate(rows):
            # One large same-name/variant bucket deliberately exercises pair comparisons.
            row["product_group_id"] = "DUPLICATE-GROUP"
            row["product_name"] = "Concentrated duplicate product"
            row["price"] = str(10_000 + index)
        return rows
    raise ValueError(f"unknown dataset: {dataset}")


def build_csv_bytes(dataset: str, row_count: int) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_TEMPLATE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(build_synthetic_rows(dataset, row_count))
    return output.getvalue().encode("utf-8")


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "min_ms": round(min(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "max_ms": round(max(values), 3),
    }


def measure(callable_: Callable[[], object]) -> tuple[dict[str, float], object]:
    for _ in range(WARMUP_REPETITIONS):
        callable_()
    durations = []
    result: object = None
    for _ in range(MEASURED_REPETITIONS):
        started_at = time.perf_counter_ns()
        result = callable_()
        durations.append((time.perf_counter_ns() - started_at) / 1_000_000)
    return _summary(durations), result


def _stage_report(dataframe: pd.DataFrame) -> dict[str, object]:
    masked_preview_timing, _ = measure(lambda: create_masked_preview(dataframe))
    product_loading_timing, products = measure(
        lambda: load_products_from_dataframe(dataframe)
    )
    assert isinstance(products, list)
    rules_timing, issues = measure(lambda: run_all_rules(products))
    assert isinstance(issues, list)
    presentation_timing, result_dataframe = measure(
        lambda: build_result_dataframe(issues)
    )
    assert isinstance(result_dataframe, pd.DataFrame)
    summary_timing, summary = measure(lambda: build_inspection_summary(products, issues))

    return {
        "masked_preview_ms": masked_preview_timing,
        "product_loading_ms": product_loading_timing,
        "rules_total_ms": rules_timing,
        "presentation_ms": presentation_timing,
        "summary_ms": summary_timing,
        "products": len(products),
        "issues": len(issues),
        "error_count": summary.error_count,
        "warning_count": summary.warning_count,
    }


def _rule_profile(products: list[object]) -> list[dict[str, object]]:
    profile = []
    for rule in RULES:
        timing, issues = measure(lambda rule=rule: rule(products))
        assert isinstance(issues, list)
        profile.append(
            {
                "rule": rule.__name__,
                "issue_count": len(issues),
                **timing,
            }
        )
    return sorted(profile, key=lambda item: float(item["median_ms"]), reverse=True)


def _memory_peak_mb(csv_bytes: bytes) -> float:
    gc.collect()
    tracemalloc.start()
    try:
        dataframe = validate_and_read_uploaded_csv(BENCHMARK_FILENAME, csv_bytes)
        inspect_dataframe(dataframe)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return round(peak_bytes / (1024 * 1024), 3)


def _pipeline_dataset_report(dataset: str, row_count: int) -> dict[str, object]:
    csv_bytes = build_csv_bytes(dataset, row_count)
    assert len(csv_bytes) <= MAX_UPLOAD_SIZE_BYTES

    validation_timing, dataframe = measure(
        lambda: validate_and_read_uploaded_csv(BENCHMARK_FILENAME, csv_bytes)
    )
    assert isinstance(dataframe, pd.DataFrame)
    inspection_timing, report = measure(lambda: inspect_dataframe(dataframe))
    end_to_end_timing, end_to_end_report = measure(
        lambda: inspect_dataframe(
            validate_and_read_uploaded_csv(BENCHMARK_FILENAME, csv_bytes)
        )
    )

    assert report.summary.total_products == row_count
    assert end_to_end_report.summary.total_products == row_count
    stage = _stage_report(dataframe)
    return {
        "csv_bytes": len(csv_bytes),
        "products": report.summary.total_products,
        "issues": report.summary.total_issues,
        "error_count": report.summary.error_count,
        "warning_count": report.summary.warning_count,
        "validation_ms": validation_timing,
        "inspection_ms": inspection_timing,
        "end_to_end_no_db_ms": end_to_end_timing,
        "stages": stage,
        "peak_tracemalloc_mb": _memory_peak_mb(csv_bytes),
    }


def _duplicate_dataset_report(row_count: int) -> dict[str, object]:
    csv_bytes = build_csv_bytes("duplicate_concentrated", row_count)
    dataframe = validate_and_read_uploaded_csv(BENCHMARK_FILENAME, csv_bytes)
    products = load_products_from_dataframe(dataframe)
    rules_timing, issues = measure(lambda: run_all_rules(products))
    profile = _rule_profile(products)
    duplicate_product_name = next(
        item
        for item in profile
        if item["rule"] == "check_duplicate_product_name"
    )
    return {
        "csv_bytes": len(csv_bytes),
        "products": len(products),
        "issues": len(issues),
        "rules_total_ms": rules_timing,
        "duplicate_product_name": duplicate_product_name,
        "top_rules": profile[:3],
    }


def _content_safety_products(row_count: int) -> list[object]:
    """Create no-issue products outside the focused rule timing window."""
    dataframe = pd.DataFrame(build_synthetic_rows("normal_unique", row_count))
    products = load_products_from_dataframe(dataframe)
    assert len(products) == row_count
    assert all(product.product_name and product.description and product.seller for product in products)
    return products


@pytest.mark.performance
def test_content_safety_scan_before_after_benchmark() -> None:
    """Focused opt-in benchmark for content-safety normalization work only."""
    _require_opt_in()

    report = {}
    for row_count in PIPELINE_ROWS:
        products = _content_safety_products(row_count)
        timing, issues = measure(
            lambda products=products: check_prohibited_and_personal_information(products)
        )
        assert issues == []
        report[str(row_count)] = {
            "products": len(products),
            "issues": len(issues),
            **timing,
        }

    print(
        json.dumps(
            {
                "benchmark": "focused_content_safety_scan",
                "environment": {
                    "python": sys.version,
                    "pandas": pd.__version__,
                    "inspection_version": INSPECTION_VERSION,
                },
                "repetitions": {
                    "warmup": WARMUP_REPETITIONS,
                    "measured": MEASURED_REPETITIONS,
                },
                "results": report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@pytest.mark.performance
def test_inspection_pipeline_before_baseline() -> None:
    _require_opt_in()

    normal = {
        f"normal_unique_{row_count}": _pipeline_dataset_report(
            "normal_unique", row_count
        )
        for row_count in PIPELINE_ROWS
    }
    issue_heavy = {
        f"issue_heavy_{row_count}": _pipeline_dataset_report("issue_heavy", row_count)
        for row_count in PIPELINE_ROWS
    }
    ten_thousand_dataframe = validate_and_read_uploaded_csv(
        BENCHMARK_FILENAME, build_csv_bytes("normal_unique", 10_000)
    )
    rule_profile = _rule_profile(load_products_from_dataframe(ten_thousand_dataframe))
    duplicate = {
        f"duplicate_concentrated_{row_count}": _duplicate_dataset_report(row_count)
        for row_count in DUPLICATE_ROWS
    }
    report = {
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor() or "unavailable",
            "pandas": pd.__version__,
            "inspection_version": INSPECTION_VERSION,
            "max_csv_rows": MAX_CSV_ROWS,
            "max_upload_size_bytes": MAX_UPLOAD_SIZE_BYTES,
        },
        "repetitions": {"warmup": WARMUP_REPETITIONS, "measured": MEASURED_REPETITIONS},
        "rule_count": len(RULES),
        "datasets": {"normal_unique": normal, "issue_heavy": issue_heavy},
        "normal_unique_10000_rule_profile": rule_profile,
        "duplicate_concentrated": duplicate,
        "persistence": {"executed": False, "reason": "no TEST_DATABASE_URL benchmark was added"},
    }

    assert len(RULES) == 16
    assert normal["normal_unique_10000"]["products"] == MAX_CSV_ROWS
    assert issue_heavy["issue_heavy_10000"]["issues"] == MAX_CSV_ROWS
    assert all(item["products"] == rows for item, rows in zip(duplicate.values(), DUPLICATE_ROWS))
    print(json.dumps(report, ensure_ascii=False, indent=2))
