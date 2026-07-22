import csv
import json
import subprocess
import sys


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
        "image_link": "image_path",
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
    "defaults": {"product_group_id": "sample_fashion_vendor"},
}


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "etl.cli", *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def write_cli_inputs(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(PROFILE), encoding="utf-8")
    input_path = tmp_path / "supplier.csv"
    with input_path.open("w", encoding="utf-8", newline="") as source_file:
        writer = csv.writer(source_file)
        writer.writerow(PROFILE["source_columns"].keys())
        writer.writerow(
            ["0001", "테스트 상품", "TOP", "BLACK", "M", "1", "12000", "image.jpg"]
        )
        writer.writerow(
            ["", "오류 상품", "TOP", "BLACK", "M", "1", "무료", "image.jpg"]
        )
    return input_path, profile_path


def test_cli_help_describes_all_required_file_options():
    result = run_cli("--help")

    assert result.returncode == 0
    for option in ("--input", "--profile", "--output", "--rejects", "--summary"):
        assert option in result.stdout


def test_cli_completes_with_rejected_rows_and_returns_zero(tmp_path):
    input_path, profile_path = write_cli_inputs(tmp_path)
    output_path = tmp_path / "out" / "ready.csv"
    rejects_path = tmp_path / "out" / "rejects.csv"
    summary_path = tmp_path / "out" / "summary.json"

    result = run_cli(
        "--input", str(input_path),
        "--profile", str(profile_path),
        "--output", str(output_path),
        "--rejects", str(rejects_path),
        "--summary", str(summary_path),
    )

    assert result.returncode == 0
    assert "정상 변환: 1" in result.stdout
    assert "오류 행: 1" in result.stdout
    assert output_path.exists() and rejects_path.exists() and summary_path.exists()


def test_cli_returns_one_for_a_pipeline_error_without_traceback(tmp_path):
    input_path, profile_path = write_cli_inputs(tmp_path)
    profile_path.write_text("{", encoding="utf-8")

    result = run_cli(
        "--input", str(input_path),
        "--profile", str(profile_path),
        "--output", str(tmp_path / "ready.csv"),
        "--rejects", str(tmp_path / "rejects.csv"),
        "--summary", str(tmp_path / "summary.json"),
    )

    assert result.returncode == 1
    assert "ETL 실패" in result.stderr
    assert "Traceback" not in result.stderr
