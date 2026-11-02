"""Offline regression tests for the downloaded reconciliation export verifier."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.verify_reconciliation_export import VerificationError, verify_reconciliation_export


def make_pair(tmp_path, *, status="changed", rows=None):
    csv_path = tmp_path / f"catalogguard_reconciliation_42_{status}.csv"
    manifest_path = tmp_path / f"catalogguard_reconciliation_42_{status}.integrity.json"
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(["상품 ID", "상태", "변경 필드"])
    writer.writerows(rows if rows is not None else [["P001", "변경", "상품명,가격\n재고"], ["P002", "변경", "재고"]])
    csv_bytes = content.getvalue().encode("utf-8-sig")
    csv_path.write_bytes(csv_bytes)
    manifest = {
        "schema_version": 1, "etl_load_run_id": 42, "status_code": status,
        "csv_file_name": csv_path.name, "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "row_count": 2 if rows is None else len(rows),
        "columns": ["상품 ID", "상태", "변경 필드"],
        "generated_at_utc": "2026-10-28T06:00:00Z",
        "consistency_limitation": "여러 페이지 단일 시점 Snapshot을 보장하지 않습니다.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return csv_path, manifest_path, manifest


@pytest.mark.parametrize("status", ["all", "new", "changed", "unchanged", "not_observed_in_batch"])
def test_verifies_original_csv_and_manifest(tmp_path, status):
    csv_file, json_file, _ = make_pair(tmp_path, status=status)
    verify_reconciliation_export(csv_file, json_file)


def test_quoted_newline_counts_as_one_csv_row(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    assert b"\n" in csv_file.read_bytes()
    verify_reconciliation_export(csv_file, json_file)


def test_tampered_csv_is_rejected(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    csv_file.write_bytes(csv_file.read_bytes() + b"x")
    with pytest.raises(VerificationError, match="SHA-256"):
        verify_reconciliation_export(csv_file, json_file)


@pytest.mark.parametrize(("field", "bad"), [
    ("schema_version", True), ("etl_load_run_id", 0), ("row_count", True),
    ("csv_sha256", "NOT_A_HASH"), ("status_code", "deleted"),
    ("columns", ["상품 ID", "상태"]), ("generated_at_utc", "2026-10-28T06:00:00+09:00"),
    ("consistency_limitation", ""), ("csv_file_name", "different.csv"),
])
def test_bad_manifest_field_is_rejected(tmp_path, field, bad):
    csv_file, json_file, manifest = make_pair(tmp_path)
    manifest[field] = bad
    json_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerificationError):
        verify_reconciliation_export(csv_file, json_file)


@pytest.mark.parametrize("change", ["missing", "additional"])
def test_exact_nine_keys_required(tmp_path, change):
    csv_file, json_file, manifest = make_pair(tmp_path)
    if change == "missing":
        del manifest["columns"]
    else:
        manifest["secret"] = "should not be here"
    json_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerificationError, match="9개"):
        verify_reconciliation_export(csv_file, json_file)


def test_duplicate_manifest_keys_rejected(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    source = json_file.read_text(encoding="utf-8")
    json_file.write_text(source.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'), encoding="utf-8")
    with pytest.raises(VerificationError, match="중복"):
        verify_reconciliation_export(csv_file, json_file)


def test_manifest_filename_must_match_pair(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    renamed = tmp_path / "another.integrity.json"
    json_file.rename(renamed)
    with pytest.raises(VerificationError, match="파일명"):
        verify_reconciliation_export(csv_file, renamed)


def test_row_count_and_header_mismatch_rejected_even_when_hash_agrees(tmp_path):
    csv_file, json_file, manifest = make_pair(tmp_path)
    manifest["row_count"] = 3
    json_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerificationError, match="행 수"):
        verify_reconciliation_export(csv_file, json_file)

    manifest["row_count"] = 2
    # Hash and header metadata are now self-consistent, but the export's fixed column contract is not.
    modified = csv_file.read_bytes().replace("상품 ID".encode("utf-8"), "비밀정보".encode("utf-8"))
    csv_file.write_bytes(modified)
    manifest["csv_sha256"] = hashlib.sha256(modified).hexdigest()
    manifest["columns"] = ["비밀정보", "상태", "변경 필드"]
    json_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerificationError, match="열 계약"):
        verify_reconciliation_export(csv_file, json_file)


def test_malformed_json_and_csv_rejected(tmp_path):
    csv_file, json_file, manifest = make_pair(tmp_path)
    json_file.write_text("{broken", encoding="utf-8")
    with pytest.raises(VerificationError):
        verify_reconciliation_export(csv_file, json_file)
    csv_file.write_bytes(b'\xef\xbb\xbf"unclosed')
    manifest["csv_sha256"] = hashlib.sha256(csv_file.read_bytes()).hexdigest()
    json_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerificationError):
        verify_reconciliation_export(csv_file, json_file)


def test_missing_files_rejected(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    csv_file.unlink()
    with pytest.raises(VerificationError, match="파일"):
        verify_reconciliation_export(csv_file, json_file)


def test_cli_success_and_failure_exit_codes(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_reconciliation_export.py"
    command = [sys.executable, str(script), "--csv", str(csv_file), "--manifest", str(json_file)]
    options = {"capture_output": True, "text": True, "encoding": "utf-8",
               "env": {**os.environ, "PYTHONIOENCODING": "utf-8"}, "check": False}
    result = subprocess.run(command, **options)
    assert result.returncode == 0
    assert "검증 성공" in result.stdout
    csv_file.write_bytes(csv_file.read_bytes() + b"tampered")
    result = subprocess.run(command, **options)
    assert result.returncode == 1
    assert "검증 실패" in result.stderr


def test_missing_utf8_bom_rejected_even_with_matching_sha(tmp_path):
    csv_file, json_file, manifest = make_pair(tmp_path)
    without_bom = csv_file.read_bytes()[3:]
    csv_file.write_bytes(without_bom)
    manifest["csv_sha256"] = hashlib.sha256(without_bom).hexdigest()
    json_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerificationError, match="BOM"):
        verify_reconciliation_export(csv_file, json_file)


def test_manifest_size_limit_rejected(tmp_path):
    csv_file, json_file, manifest = make_pair(tmp_path)
    manifest["consistency_limitation"] = "x" * 65536
    json_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerificationError, match="크기"):
        verify_reconciliation_export(csv_file, json_file)


def test_wrong_column_count_rejected_even_if_hash_and_row_count_match(tmp_path):
    csv_file, json_file, manifest = make_pair(tmp_path)
    raw_csv = '\ufeff상품 ID,상태,변경 필드\nP001,변경,재고,불필요한 열\n'.encode('utf-8')
    csv_file.write_bytes(raw_csv)
    manifest["csv_sha256"] = hashlib.sha256(raw_csv).hexdigest()
    manifest["row_count"] = 1
    json_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerificationError, match="열 개수"):
        verify_reconciliation_export(csv_file, json_file)


@pytest.mark.parametrize("status", ["all", "new", "changed", "unchanged", "not_observed_in_batch"])
def test_existing_exporters_are_compatible(tmp_path, status):
    from core.result_exporter import build_catalog_reconciliation_integrity_manifest
    from ui.etl_load_history import build_catalog_reconciliation_csv

    csv_file, json_file, _ = make_pair(tmp_path, status=status)
    payload = build_catalog_reconciliation_csv([
        {"external_product_id": 'synthetic,"quoted"\nsecond line',
         "status": "changed" if status == "all" else status,
         "changed_fields": {"price": {"before": "1", "after": "2"}}},
    ])
    csv_file.write_bytes(payload)
    json_file.write_bytes(build_catalog_reconciliation_integrity_manifest(
        payload, etl_load_run_id=42, status_code=status, csv_file_name=csv_file.name,
    ))
    originals = (csv_file.read_bytes(), json_file.read_bytes())
    verify_reconciliation_export(csv_file, json_file)
    assert (csv_file.read_bytes(), json_file.read_bytes()) == originals


def test_deeply_nested_json_rejected_without_traceback(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    json_file.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
    with pytest.raises(VerificationError):
        verify_reconciliation_export(csv_file, json_file)


def test_header_order_rejected_with_matching_hash(tmp_path):
    csv_file, json_file, manifest = make_pair(tmp_path)
    raw = csv_file.read_bytes()
    header, body = raw.split(b"\r\n", 1)
    columns = header[3:].decode("utf-8").split(",")
    raw = (",".join(reversed(columns)) + "\r\n").encode("utf-8-sig") + body
    csv_file.write_bytes(raw)
    manifest["csv_sha256"] = hashlib.sha256(raw).hexdigest()
    json_file.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(VerificationError):
        verify_reconciliation_export(csv_file, json_file)


def test_empty_data_rows_are_counted_correctly(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path, rows=[])
    verify_reconciliation_export(csv_file, json_file)


def test_missing_manifest_rejected(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    json_file.unlink()
    with pytest.raises(VerificationError):
        verify_reconciliation_export(csv_file, json_file)
