import csv
import hashlib
import json
from pathlib import Path

import pytest

from config.settings import BASE_DIR
from core.inspection_service import inspect_dataframe
from core.upload_validator import validate_and_read_uploaded_csv
from etl import pipeline as pipeline_module
from etl.pipeline import ETLPipelineError, run_pipeline


PROFILE = {
    "profile_name": "sample_fashion_vendor",
    "profile_version": "1",
    "source_columns": {
        "vendor_sku": "product_id",
        "item_name": "product_name",
        "main_category": "category",
        "colour": "color",
        "size_name": "size",
        "quantity": "stock",
        "list_price": "price",
        "discount_price": "sale_price",
        "image_link": "image_path",
        "description_text": "description",
        "brand_name": "seller",
    },
    "required_source_columns": [
        "vendor_sku",
        "item_name",
        "main_category",
        "list_price",
        "colour",
        "size_name",
        "image_link",
    ],
    "defaults": {"product_group_id": "sample_fashion_vendor", "stock": 0},
}


SOURCE_COLUMNS = [
    "vendor_sku",
    "item_name",
    "main_category",
    "brand_name",
    "list_price",
    "discount_price",
    "colour",
    "size_name",
    "quantity",
    "description_text",
    "image_link",
]


SOURCE_ROWS = [
    [
        "000123",
        "기본 티셔츠",
        "TOP",
        "Sample Brand",
        "12,000",
        "10000",
        "BLACK",
        "M",
        "10",
        "기본 설명",
        "https://example.test/one.jpg",
    ],
    [
        "",
        "오류 상품",
        "TOP",
        "Sample Brand",
        "무료",
        "0",
        "BLACK",
        "M",
        "1.5",
        "",
        "https://example.test/two.jpg",
    ],
    [
        "000125",
        "할인 품질 확인 상품",
        "TOP",
        "Sample Brand",
        "12000",
        "15000",
        "black",
        "medium",
        "",
        "",
        "https://example.test/three.jpg",
    ],
]


def write_profile_and_source(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(PROFILE), encoding="utf-8")
    input_path = tmp_path / "supplier.csv"
    with input_path.open("w", encoding="utf-8", newline="") as source_file:
        writer = csv.writer(source_file)
        writer.writerow(SOURCE_COLUMNS)
        writer.writerows(SOURCE_ROWS)
    return input_path, profile_path


def output_paths(tmp_path):
    return (
        tmp_path / "out" / "catalogguard_ready.csv",
        tmp_path / "out" / "rejected_rows.csv",
        tmp_path / "out" / "etl_summary.json",
    )


def test_run_pipeline_writes_standard_reject_and_summary_files(tmp_path):
    input_path, profile_path = write_profile_and_source(tmp_path)
    output_path, rejects_path, summary_path = output_paths(tmp_path)

    result = run_pipeline(input_path, profile_path, output_path, rejects_path, summary_path)

    assert (result.total_rows, result.loaded_rows, result.rejected_rows) == (3, 2, 1)
    standard_bytes = output_path.read_bytes()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["input_file_sha256"] == hashlib.sha256(input_path.read_bytes()).hexdigest()
    assert summary["output_file_sha256"] == hashlib.sha256(standard_bytes).hexdigest()
    assert summary["loaded_rows"] + summary["rejected_rows"] == summary["total_rows"]
    assert "C:\\" not in summary_path.read_text(encoding="utf-8")

    with output_path.open(encoding="utf-8", newline="") as output_file:
        output_rows = list(csv.DictReader(output_file))
    with rejects_path.open(encoding="utf-8", newline="") as rejects_file:
        rejected_rows = list(csv.DictReader(rejects_file))
    assert [row["product_id"] for row in output_rows] == ["000123", "000125"]
    assert output_rows[1]["stock"] == "0"
    assert output_rows[0]["sale_price"] == "10000"
    assert output_rows[1]["sale_price"] == "15000"
    assert rejected_rows[0]["source_row_number"] == "3"
    assert "INVALID_PRICE" in rejected_rows[0]["error_code"]


def test_pipeline_output_is_accepted_by_real_catalogguard_validator_and_inspector(tmp_path):
    input_path, profile_path = write_profile_and_source(tmp_path)
    output_path, rejects_path, summary_path = output_paths(tmp_path)

    run_pipeline(input_path, profile_path, output_path, rejects_path, summary_path)

    dataframe = validate_and_read_uploaded_csv(output_path.name, output_path.read_bytes())
    report = inspect_dataframe(dataframe)
    assert len(dataframe) == 2
    assert report.summary.total_products == 2
    sale_price_issues = [
        issue for issue in report.issues if issue.rule == "sale_price_greater_than_price"
    ]
    assert [issue.product_id for issue in sale_price_issues] == ["000125"]


def test_pipeline_is_deterministic_for_output_and_reject_files(tmp_path):
    input_path, profile_path = write_profile_and_source(tmp_path)
    first_output, first_rejects, first_summary = output_paths(tmp_path / "first")
    second_output, second_rejects, second_summary = output_paths(tmp_path / "second")

    first = run_pipeline(input_path, profile_path, first_output, first_rejects, first_summary)
    second = run_pipeline(input_path, profile_path, second_output, second_rejects, second_summary)

    assert first_output.read_bytes() == second_output.read_bytes()
    assert first_rejects.read_bytes() == second_rejects.read_bytes()
    assert first.output_file_sha256 == second.output_file_sha256
    assert (first.loaded_rows, first.rejected_rows) == (second.loaded_rows, second.rejected_rows)


def test_pipeline_rejects_an_output_path_that_would_overwrite_input(tmp_path):
    input_path, profile_path = write_profile_and_source(tmp_path)
    _, rejects_path, summary_path = output_paths(tmp_path)

    with pytest.raises(ETLPipelineError, match="must not overwrite"):
        run_pipeline(input_path, profile_path, input_path, rejects_path, summary_path)


def test_pipeline_rejects_an_output_path_that_would_overwrite_profile(tmp_path):
    input_path, profile_path = write_profile_and_source(tmp_path)
    output_path, rejects_path, summary_path = output_paths(tmp_path)
    original_profile = profile_path.read_bytes()

    with pytest.raises(ETLPipelineError, match="must not overwrite"):
        run_pipeline(input_path, profile_path, profile_path, rejects_path, summary_path)

    assert profile_path.read_bytes() == original_profile


def test_pipeline_rejects_supplier_csv_missing_required_source_column(tmp_path):
    input_path, profile_path = write_profile_and_source(tmp_path)
    input_path.write_text("vendor_sku,item_name\n001,상품\n", encoding="utf-8")
    output_path, rejects_path, summary_path = output_paths(tmp_path)

    with pytest.raises(ETLPipelineError, match="required source columns"):
        run_pipeline(input_path, profile_path, output_path, rejects_path, summary_path)


def test_pipeline_restores_existing_outputs_when_a_later_replace_fails(tmp_path, monkeypatch):
    input_path, profile_path = write_profile_and_source(tmp_path)
    output_path, rejects_path, summary_path = output_paths(tmp_path)
    output_path.parent.mkdir()
    output_path.write_text("previous output", encoding="utf-8")
    rejects_path.write_text("previous rejects", encoding="utf-8")
    summary_path.write_text("previous summary", encoding="utf-8")
    original_replace = pipeline_module.os.replace
    replace_failed = False

    def fail_reject_replace(source, destination):
        nonlocal replace_failed
        if Path(destination) == rejects_path and not replace_failed:
            replace_failed = True
            raise OSError("simulated replace failure")
        return original_replace(source, destination)

    monkeypatch.setattr(pipeline_module.os, "replace", fail_reject_replace)

    with pytest.raises(ETLPipelineError, match="could not be saved"):
        run_pipeline(input_path, profile_path, output_path, rejects_path, summary_path)

    assert output_path.read_text(encoding="utf-8") == "previous output"
    assert rejects_path.read_text(encoding="utf-8") == "previous rejects"
    assert summary_path.read_text(encoding="utf-8") == "previous summary"
    assert not list(output_path.parent.glob("*.tmp"))


def test_pipeline_cleans_temporary_outputs_when_summary_write_fails(tmp_path, monkeypatch):
    input_path, profile_path = write_profile_and_source(tmp_path)
    output_path, rejects_path, summary_path = output_paths(tmp_path)

    def fail_summary_write(*args, **kwargs):
        raise OSError("simulated summary write failure")

    monkeypatch.setattr(pipeline_module, "_write_json_temp", fail_summary_write)

    with pytest.raises(ETLPipelineError, match="could not be saved"):
        run_pipeline(input_path, profile_path, output_path, rejects_path, summary_path)

    assert not output_path.exists()
    assert not rejects_path.exists()
    assert not summary_path.exists()
    assert not list(output_path.parent.glob("*.tmp"))


def test_repository_sample_profile_converts_mixed_supplier_fixture(tmp_path):
    output_path, rejects_path, summary_path = output_paths(tmp_path)

    result = run_pipeline(
        BASE_DIR / "tests" / "fixtures" / "etl" / "sample_vendor_mixed.csv",
        BASE_DIR / "config" / "etl" / "sample_fashion_vendor_v1.json",
        output_path,
        rejects_path,
        summary_path,
    )

    assert (result.total_rows, result.loaded_rows, result.rejected_rows) == (3, 2, 1)
    with output_path.open(encoding="utf-8", newline="") as output_file:
        output_rows = list(csv.DictReader(output_file))
    assert [row["product_group_id"] for row in output_rows] == ["000123", "000125"]
