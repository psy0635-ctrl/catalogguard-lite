# 역할: 동기식 CSV 검수 벤치마크의 가상 데이터, 입력 검증, 결과 구조를 테스트합니다.
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from config.settings import CSV_TEMPLATE_COLUMNS, MAX_CSV_ROWS
from core.inspection_service import InspectionReport
from core.privacy import (
    find_phone_number_matches,
    find_resident_registration_number_matches,
)
from scripts.benchmark_inspection import (
    BENCHMARK_RESULT_FIELDS,
    build_benchmark_report,
    generate_csv_bytes,
    generate_product_rows,
    inspect_csv_bytes,
    measure_inspection,
    save_benchmark_report,
    validate_benchmark_inputs,
)


def test_generate_product_rows_returns_requested_synthetic_rows():
    rows = generate_product_rows(12, seed=20260720)

    assert len(rows) == 12
    assert all(list(row) == CSV_TEMPLATE_COLUMNS for row in rows)
    assert all(row["product_id"].startswith("BENCH-P") for row in rows)
    assert all(row["product_group_id"].startswith("BENCH-G") for row in rows)
    assert all(row["image_path"].startswith("benchmark/images/") for row in rows)
    assert all(row["seller"].startswith("BENCHMARK_SELLER") for row in rows)


@pytest.mark.parametrize("row_count", [0, -1])
def test_generate_product_rows_rejects_non_positive_row_count(row_count):
    with pytest.raises(ValueError, match="rows"):
        generate_product_rows(row_count)


def test_generate_product_rows_is_reproducible_for_fixed_seed():
    assert generate_product_rows(100, seed=7) == generate_product_rows(100, seed=7)


def test_generate_product_rows_contains_benchmark_scenarios_without_real_pii():
    rows = generate_product_rows(100, seed=20260720)
    product_id_counts = Counter(row["product_id"] for row in rows)
    groups = defaultdict(list)
    for row in rows:
        groups[row["product_group_id"]].append(row)

    duplicate_content_fields = ("product_name", "category", "color", "size", "price")
    duplicate_content_counts = Counter(
        tuple(row[field] for field in duplicate_content_fields) for row in rows
    )
    text = "\n".join(
        str(value)
        for row in rows
        for value in row.values()
    )

    assert any(count > 1 for count in product_id_counts.values())
    assert any(count > 1 for count in duplicate_content_counts.values())
    assert any(row["color"] == "블랙" for row in rows)
    assert any(row["size"] == "medium" for row in rows)
    assert any(
        len({(row["color"], row["size"]) for row in group_rows})
        < len(group_rows)
        for group_rows in groups.values()
        if len(group_rows) > 1
    )
    assert any(
        len({row["category"] for row in group_rows}) > 1
        for group_rows in groups.values()
    )
    assert any(int(row["price"]) >= 1_000_000 for row in rows)
    assert "외부결제" in text
    assert "benchmark-user@example.invalid" in text
    assert find_phone_number_matches(text) == []
    assert find_resident_registration_number_matches(text) == []


def test_generate_csv_bytes_uses_supported_columns_and_requested_row_count():
    csv_bytes = generate_csv_bytes(25, seed=3)
    report = inspect_csv_bytes(csv_bytes)

    assert isinstance(csv_bytes, bytes)
    assert csv_bytes
    assert list(report.source_dataframe.columns) == CSV_TEMPLATE_COLUMNS
    assert report.summary.total_products == 25


@pytest.mark.parametrize(
    ("rows", "repeat"),
    [([], 1), ([0], 1), ([-1], 1), ([1], 0), ([1], -1)],
)
def test_validate_benchmark_inputs_rejects_invalid_values(rows, repeat):
    with pytest.raises(ValueError):
        validate_benchmark_inputs(rows, repeat)


def test_validate_benchmark_inputs_rejects_rows_over_project_limit():
    with pytest.raises(ValueError, match=f"{MAX_CSV_ROWS:,}"):
        validate_benchmark_inputs([MAX_CSV_ROWS + 1], 1)


def test_measure_inspection_returns_required_result_structure():
    result = measure_inspection(10, repeat=1, seed=11)

    assert set(result) == set(BENCHMARK_RESULT_FIELDS)
    assert result["rows"] == 10
    assert isinstance(result["csv_size_bytes"], int)
    assert isinstance(result["issue_count"], int)


def test_inspect_csv_bytes_uses_common_inspection_report_contract():
    report = inspect_csv_bytes(generate_csv_bytes(100, seed=20260720))

    assert isinstance(report, InspectionReport)
    assert report.summary.total_products == 100
    assert report.summary.total_issues == len(report.issues)
    assert len(report.result_dataframe) == len(report.issues)
    assert {
        "duplicate_product_id",
        "inconsistent_group_category",
        "duplicate_variant_combination",
        "duplicate_product_content",
        "non_standard_color",
        "non_standard_size",
        "category_price_anomaly",
        "prohibited_term",
        "email_address",
    }.issubset({issue.rule for issue in report.issues})


def test_save_benchmark_report_creates_parent_directory_and_safe_json():
    result = {field: 0 for field in BENCHMARK_RESULT_FIELDS}
    result["rows"] = 1
    report = build_benchmark_report([result], repeat=1, warmup=1)
    with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
        output_path = (
            Path(temporary_directory) / "nested" / "inspection-benchmark.json"
        )

        save_benchmark_report(output_path, report)

        saved_report = json.loads(output_path.read_text(encoding="utf-8"))
        assert output_path.is_file()
        assert set(saved_report) == {
            "generated_at",
            "python_version",
            "platform",
            "git_sha",
            "repeat",
            "warmup",
            "results",
        }
        assert saved_report["results"] == [result]
        serialized_report = output_path.read_text(encoding="utf-8")
        assert "DATABASE_URL" not in serialized_report
        assert "benchmark-user@example.invalid" not in serialized_report
