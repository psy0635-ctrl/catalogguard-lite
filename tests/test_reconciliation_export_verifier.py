"""Offline regression tests for the downloaded reconciliation export verifier."""

from contextlib import contextmanager
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from scripts import verify_reconciliation_export as verifier
from scripts.verify_reconciliation_export import VerificationError, verify_reconciliation_export


def make_pair(tmp_path, *, status="changed", rows=None, batch_id=42):
    csv_path = tmp_path / f"catalogguard_reconciliation_{batch_id}_{status}.csv"
    manifest_path = tmp_path / f"catalogguard_reconciliation_{batch_id}_{status}.integrity.json"
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(["상품 ID", "상태", "변경 필드"])
    writer.writerows(rows if rows is not None else [["P001", "변경", "상품명,가격\n재고"], ["P002", "변경", "재고"]])
    csv_bytes = content.getvalue().encode("utf-8-sig")
    csv_path.write_bytes(csv_bytes)
    manifest = {
        "schema_version": 1, "etl_load_run_id": batch_id, "status_code": status,
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
    assert result.stdout.splitlines() == [
        "검증 성공: CSV와 JSON의 SHA-256·행 수·열·파일명이 일치합니다.",
        "주의: 파일 일치는 상품 데이터의 정확성이나 작성자의 신원을 증명하지 않습니다.",
    ]
    csv_file.write_bytes(csv_file.read_bytes() + b"tampered")
    result = subprocess.run(command, **options)
    assert result.returncode == 1
    assert result.stderr.strip() == "검증 실패: CSV 파일의 실제 SHA-256이 JSON과 다릅니다."
    result = subprocess.run(command[:-2], **options)
    assert result.returncode == 2
    assert "--manifest" in result.stderr


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


def run_directory_cli(directory, *extra_args):
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_reconciliation_export.py"
    return subprocess.run(
        [sys.executable, "-I", "-S", "-X", "utf8", str(script), "--directory", str(directory), *extra_args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


@pytest.mark.parametrize("tampered", [False, True])
def test_directory_checks_all_pairs_in_order_and_preserves_inputs(tmp_path, tampered):
    later_csv, later_json, _ = make_pair(tmp_path, batch_id=43)
    first_csv, first_json, _ = make_pair(tmp_path, rows=[["synthetic-private-row", "변경", "재고"]])
    if tampered:
        first_csv.write_bytes(first_csv.read_bytes() + b"tampered")
    files = (first_csv, first_json, later_csv, later_json)
    before = [hashlib.sha256(path.read_bytes()).digest() for path in files]

    result = run_directory_cli(tmp_path)

    assert result.returncode == (1 if tampered else 0)
    first, second, summary = result.stdout.splitlines()
    if tampered:
        assert first.startswith(f"FAIL {first_csv.name}:")
        assert "SHA-256" in first
        assert summary == "검사 대상 2건 | 성공 1건 | 실패 1건"
    else:
        assert first == f"PASS {first_csv.name}"
        assert summary == "검사 대상 2건 | 성공 2건 | 실패 0건"
    assert second == f"PASS {later_csv.name}"
    assert "synthetic-private-row" not in result.stdout + result.stderr
    assert [hashlib.sha256(path.read_bytes()).digest() for path in files] == before


@pytest.mark.parametrize("missing", ["CSV", ".integrity.json"])
def test_directory_rejects_missing_counterpart(tmp_path, missing):
    csv_file, json_file, _ = make_pair(tmp_path)
    (csv_file if missing == "CSV" else json_file).unlink()

    result = run_directory_cli(tmp_path)

    assert result.returncode == 1
    assert f"대응하는 {missing} 파일이 없습니다." in result.stdout
    assert "검사 대상 1건 | 성공 0건 | 실패 1건" in result.stdout


@pytest.mark.parametrize("name", [
    "catalogguard_reconciliation_042_changed.csv",
    "catalogguard_reconciliation_42_changed.JSON",
    "CatalogGuard_reconciliation_42_changed.integrity.json",
    "catalogguard_reconciliation_synthetic-private-name.csv",
])
def test_directory_rejects_malformed_catalogguard_names(tmp_path, name):
    (tmp_path / name).write_text("unused", encoding="utf-8")

    result = run_directory_cli(tmp_path)

    assert result.returncode == 1
    assert "FAIL [항목 1]: CatalogGuard 파일명 규칙" in result.stdout
    assert name not in result.stdout + result.stderr
    assert "검사 대상 1건 | 성공 0건 | 실패 1건" in result.stdout


def test_directory_does_not_pair_different_batch_filenames(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    renamed_json = json_file.rename(tmp_path / json_file.name.replace("_42_", "_43_"))

    result = run_directory_cli(tmp_path)

    assert result.returncode == 1
    assert f"FAIL {csv_file.name}: 대응하는 .integrity.json 파일이 없습니다." in result.stdout
    assert f"FAIL {renamed_json.name}: 대응하는 CSV 파일이 없습니다." in result.stdout
    assert "검사 대상 2건 | 성공 0건 | 실패 2건" in result.stdout


@pytest.mark.parametrize(("field", "value"), [("etl_load_run_id", 43), ("status_code", "new")])
def test_directory_reuses_manifest_filename_metadata_validation(tmp_path, field, value):
    _, json_file, manifest = make_pair(tmp_path)
    manifest[field] = value
    json_file.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_directory_cli(tmp_path)

    assert result.returncode == 1
    assert "CSV 파일명·배치 ID·상태 코드가 서로 일치하지 않습니다." in result.stdout


def test_directory_rejects_case_mismatched_counterpart(tmp_path):
    csv_file, json_file, _ = make_pair(tmp_path)
    payload = csv_file.read_bytes()
    csv_file.unlink()
    (tmp_path / csv_file.name.upper()).write_bytes(payload)

    result = run_directory_cli(tmp_path)

    assert result.returncode == 1
    assert "FAIL [항목 1]: CatalogGuard 파일명 규칙과 일치하지 않습니다." in result.stdout
    assert f"FAIL {json_file.name}: 대응하는 CSV 파일이 없습니다." in result.stdout
    assert "검사 대상 2건 | 성공 0건 | 실패 2건" in result.stdout


def test_directory_ignores_unrelated_files_and_nested_pairs(tmp_path):
    (tmp_path / "ordinary.csv").write_text("unused", encoding="utf-8")
    (tmp_path / "ordinary.integrity.json").write_text("unused", encoding="utf-8")
    nested = tmp_path / "catalogguard_reconciliation_43_changed.csv"
    nested.mkdir()
    make_pair(nested, batch_id=43)
    csv_file, _, _ = make_pair(tmp_path)

    result = run_directory_cli(tmp_path)

    assert result.returncode == 0
    assert result.stdout.splitlines() == [f"PASS {csv_file.name}", "검사 대상 1건 | 성공 1건 | 실패 0건"]


@pytest.mark.parametrize("unrelated_file", [False, True])
def test_directory_without_candidates_fails(tmp_path, unrelated_file):
    if unrelated_file:
        (tmp_path / "notes.txt").touch()

    result = run_directory_cli(tmp_path)

    assert result.returncode == 1
    assert "검증 대상 파일이 없습니다." in result.stdout
    assert "검사 대상 0건 | 성공 0건 | 실패 0건" in result.stdout


@pytest.mark.parametrize("link_index", [0, 1], ids=["csv", "manifest"])
def test_directory_rejects_hardlink_shared_with_outside(tmp_path, link_index):
    exports = tmp_path / "exports"
    exports.mkdir()
    files = make_pair(exports)[:2]
    link = files[link_index]
    outside = link.rename(tmp_path / link.name)
    link.hardlink_to(outside)
    assert link.stat().st_nlink == 2

    result = run_directory_cli(exports)

    assert result.returncode == 1
    assert "하드 링크로 공유된 파일은 허용되지 않습니다." in result.stdout
    assert "검사 대상 1건 | 성공 0건 | 실패 1건" in result.stdout


@pytest.mark.parametrize("link_index", [0, 1], ids=["csv", "manifest"])
def test_directory_rejects_file_symlink_to_outside(tmp_path, link_index):
    exports = tmp_path / "exports"
    outside = tmp_path / "outside"
    exports.mkdir()
    outside.mkdir()
    files = make_pair(exports)[:2]
    link = files[link_index]
    target = link.rename(outside / link.name)
    try:
        link.symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows requires symbolic link creation privileges")
        raise

    result = run_directory_cli(exports)

    assert result.returncode == 1
    assert "심볼릭 링크 또는 재분석 지점은 허용되지 않습니다." in result.stdout
    assert "검사 대상 1건 | 성공 0건 | 실패 1건" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 file attributes")
@pytest.mark.parametrize("link_index", [0, 1], ids=["csv", "manifest"])
def test_directory_rejects_mocked_windows_file_reparse_attribute(tmp_path, monkeypatch, capsys, link_index):
    files = make_pair(tmp_path)[:2]
    flagged_file = files[link_index]
    open_handle = verifier._win_open
    get_info = verifier._win_info
    flagged_handle = None

    def track_file_handle(name, parent=None, *, directory=False):
        nonlocal flagged_handle
        handle = open_handle(name, parent, directory=directory)
        if not directory and name == flagged_file.name:
            flagged_handle = handle
        return handle

    def info_with_reparse_point(handle, info_class, info):
        result = get_info(handle, info_class, info)
        if handle == flagged_handle and info_class == verifier._FILE_BASIC_INFO:
            result.attributes |= stat.FILE_ATTRIBUTE_REPARSE_POINT
        return result

    open_osfhandle = verifier.msvcrt.open_osfhandle

    def guarded_open_osfhandle(handle, flags):
        assert handle != flagged_handle, "a reparse point was handed to the content reader"
        return open_osfhandle(handle, flags)

    monkeypatch.setattr(verifier, "_win_open", track_file_handle)
    monkeypatch.setattr(verifier, "_win_info", info_with_reparse_point)
    monkeypatch.setattr(verifier.msvcrt, "open_osfhandle", guarded_open_osfhandle)

    assert verifier.main(["--directory", str(tmp_path)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        f"FAIL {files[0].name}: 심볼릭 링크 또는 재분석 지점은 허용되지 않습니다.",
        "검사 대상 1건 | 성공 0건 | 실패 1건",
    ]


@pytest.mark.parametrize("denied_index", [0, 1], ids=["csv", "manifest"])
def test_directory_handles_file_read_permission_error(tmp_path, monkeypatch, capsys, denied_index):
    files = make_pair(tmp_path)[:2]
    next_csv, _, _ = make_pair(tmp_path, batch_id=43)
    if sys.platform == "win32":
        open_file = verifier._win_open_binary

        def deny_one_handle(handle, name, identity):
            if name == files[denied_index].name:
                raise PermissionError("synthetic-private-path")
            return open_file(handle, name, identity)

        monkeypatch.setattr(verifier, "_win_open_binary", deny_one_handle)
    else:
        open_path = Path.open

        def deny_one_file(path, *args, **kwargs):
            if path == files[denied_index]:
                raise PermissionError("synthetic-private-path")
            return open_path(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", deny_one_file)

    assert verifier.main(["--directory", str(tmp_path)]) == 1
    output = capsys.readouterr()
    assert output.out.splitlines() == [
        f"FAIL {files[0].name}: 파일을 읽거나 CSV 형식을 해석할 수 없습니다.",
        f"PASS {next_csv.name}",
        "검사 대상 2건 | 성공 1건 | 실패 1건",
    ]
    assert not output.err


def test_directory_handles_listing_permission_error(tmp_path, monkeypatch, capsys):
    def deny_listing(path):
        raise PermissionError("synthetic-private-directory")

    if sys.platform == "win32":
        monkeypatch.setattr(verifier, "_win_list", deny_listing)
    else:
        monkeypatch.setattr(Path, "iterdir", deny_listing)

    assert verifier.main(["--directory", str(tmp_path)]) == 2
    output = capsys.readouterr()
    assert output.err.strip() == "폴더 경로 오류: 입력 폴더를 읽거나 안전성을 확인할 수 없습니다."
    assert not output.out


@pytest.mark.skipif(sys.platform != "win32", reason="Windows directory junction")
def test_directory_rejects_windows_junctions(tmp_path):
    exports = tmp_path / "exports"
    exports.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    nested = outside / "nested"
    nested.mkdir()
    make_pair(nested)
    link = exports / "catalogguard_reconciliation_42_changed.csv"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, check=True)

    result = run_directory_cli(exports)
    assert result.returncode == 1
    assert "심볼릭 링크 또는 재분석 지점은 허용되지 않습니다." in result.stdout

    for directory in (link, link / nested.name):
        result = run_directory_cli(directory)
        assert result.returncode == 2
        assert "심볼릭 링크 또는 재분석 지점은 허용되지 않습니다." in result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NTFS sharing and junctions")
@pytest.mark.parametrize("replace_parent", [False, True], ids=["directory", "parent"])
def test_windows_blocks_directory_replacement_after_listing(tmp_path, monkeypatch, capsys, replace_parent):
    parent = tmp_path / "parent"
    exports = parent / "exports"
    outside = tmp_path / "outside"
    outside_exports = outside / "exports"
    exports.mkdir(parents=True)
    outside_exports.mkdir(parents=True)
    csv_file, json_file, _ = make_pair(exports)
    make_pair(outside_exports, rows=[["outside-synthetic", "changed", "stock"]])
    csv_file.write_bytes(csv_file.read_bytes() + b"tampered")
    expected = {path.name: path.stat() for path in (csv_file, json_file)}
    opened = []
    target = parent if replace_parent else exports
    redirect_to = outside if replace_parent else outside_exports
    moved = target.with_name(target.name + "-moved")
    verify_entries = verifier._verify_entries
    open_binary = verifier._win_open_binary

    def attempt_replacement(directory, entries, verify_pair):
        try:
            target.rename(moved)
        except OSError as exc:
            assert exc.winerror in (5, 32)
        else:
            subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(target), str(redirect_to)],
                capture_output=True, check=True,
            )
            pytest.fail("정션 교체에 필요한 이름 변경이 허용됐습니다.")
        return verify_entries(directory, entries, verify_pair)

    @contextmanager
    def track_open(handle, name, identity):
        with open_binary(handle, name, identity) as stream:
            assert os.path.samestat(os.fstat(stream.fileno()), expected[name])
            opened.append(name)
            yield stream

    monkeypatch.setattr(verifier, "_verify_entries", attempt_replacement)
    monkeypatch.setattr(verifier, "_win_open_binary", track_open)

    assert verifier.main(["--directory", str(exports)]) == 1
    assert opened == [json_file.name, csv_file.name]
    output = capsys.readouterr()
    assert output.out.splitlines() == [
        f"FAIL {csv_file.name}: CSV 파일의 실제 SHA-256이 JSON과 다릅니다.",
        "검사 대상 1건 | 성공 0건 | 실패 1건",
    ]
    assert not output.err
    target.rename(moved)  # Locks are released on verification failure.
    moved.rename(target)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NTFS identity and reparse points")
@pytest.mark.parametrize("replace_manifest", [False, True], ids=["csv", "manifest"])
@pytest.mark.parametrize("change", ["replacement", "junction", "edit"])
def test_windows_rejects_file_replacement_after_listing(tmp_path, monkeypatch, capsys, replace_manifest, change):
    exports = tmp_path / "exports"
    outside = tmp_path / "outside"
    exports.mkdir()
    outside.mkdir()
    csv_file, json_file, _ = make_pair(exports)
    target = json_file if replace_manifest else csv_file
    make_pair(outside)
    payload = target.read_bytes()
    verify_entries = verifier._verify_entries
    open_binary = verifier._win_open_binary
    opened = []

    def replace_file(directory, entries, verify_pair):
        if change == "edit":
            target.write_bytes(payload)
            times = target.stat()
            # Ensure a different last-write time even on coarse timestamp clocks.
            os.utime(target, ns=(times.st_atime_ns, times.st_mtime_ns + 2_000_000_000))
        elif change == "junction":
            target.unlink()
            subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(target), str(outside)],
                capture_output=True, check=True,
            )
        else:
            target.unlink()
            target.write_bytes(payload)
        return verify_entries(directory, entries, verify_pair)

    @contextmanager
    def track_open(handle, name, identity):
        with open_binary(handle, name, identity) as stream:
            opened.append(name)
            yield stream

    monkeypatch.setattr(verifier, "_verify_entries", replace_file)
    monkeypatch.setattr(verifier, "_win_open_binary", track_open)

    assert verifier.main(["--directory", str(exports)]) == 1
    assert opened == ([] if replace_manifest else [json_file.name])
    reason = {
        "replacement": "파일 식별자가 일치하지 않습니다",
        "junction": "재분석 지점은 허용되지 않습니다",
        "edit": "쓰기 시각이 일치하지 않습니다",
    }[change]
    assert reason in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NTFS sharing")
def test_windows_blocks_pair_writes_and_replacement_while_reading(tmp_path, monkeypatch, capsys):
    csv_file, json_file, _ = make_pair(tmp_path)
    before = [hashlib.sha256(path.read_bytes()).digest() for path in (csv_file, json_file)]
    verify_csv = verifier._verify_csv

    def attempt_changes(stream, manifest):
        for path in (csv_file, json_file):
            with pytest.raises(PermissionError):
                path.write_bytes(b"changed")
            with pytest.raises(OSError) as rename_error:
                path.rename(path.with_suffix(".moved"))
            assert rename_error.value.winerror in (5, 32)
        return verify_csv(stream, manifest)

    monkeypatch.setattr(verifier, "_verify_csv", attempt_changes)

    assert verifier.main(["--directory", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == f"PASS {csv_file.name}"
    assert [hashlib.sha256(path.read_bytes()).digest() for path in (csv_file, json_file)] == before


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NTFS sharing")
@pytest.mark.parametrize("writer_index", [0, 1], ids=["csv", "manifest"])
def test_windows_fails_closed_for_preexisting_writer(tmp_path, capsys, writer_index):
    files = make_pair(tmp_path)[:2]
    with files[writer_index].open("r+b"):
        assert verifier.main(["--directory", str(tmp_path)]) == 1
    assert "파일을 읽거나 CSV 형식을 해석할 수 없습니다." in capsys.readouterr().out
    assert verifier.main(["--directory", str(tmp_path)]) == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive mappings")
@pytest.mark.parametrize("target", [r"\??\C:\folder", r"\Device\LanmanRedirector\server\share"])
def test_windows_rejects_mocked_aliased_drive_before_opening(tmp_path, monkeypatch, capsys, target):
    def query_dos_device(drive, buffer, length):
        buffer.value = target
        return len(target) + 1

    def unexpected_open(*args, **kwargs):
        pytest.fail("드라이브 별칭으로 파일이나 폴더를 열었습니다.")

    monkeypatch.setattr(verifier, "_query_dos_device", query_dos_device)
    monkeypatch.setattr(verifier, "_win_open", unexpected_open)

    assert verifier.main(["--directory", str(tmp_path)]) == 2
    assert "로컬 NTFS 드라이브" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform != "win32", reason="Windows handle-based directory enumeration")
def test_windows_enumerates_past_first_directory_buffer(tmp_path):
    for index in range(420):
        (tmp_path / f"b{index:04d}_{'x' * 80}.txt").touch()
    csv_file, _, _ = make_pair(tmp_path)
    (tmp_path / ("z" * 80)).touch()

    result = run_directory_cli(tmp_path)

    assert result.returncode == 0
    assert result.stdout.splitlines() == [f"PASS {csv_file.name}", "검사 대상 1건 | 성공 1건 | 실패 0건"]


@pytest.mark.parametrize("options", [
    ("--csv", "a.csv"), ("--manifest", "a.integrity.json"),
    ("--csv", "a.csv", "--manifest", "a.integrity.json"),
])
def test_directory_rejects_single_file_options(tmp_path, options):
    result = run_directory_cli(tmp_path, *options)

    assert result.returncode == 2
    assert "함께 사용할 수 없습니다." in result.stderr


def test_directory_rejects_invalid_input_paths(tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.touch()
    for path in (file_path, tmp_path / "missing"):
        result = run_directory_cli(path)
        assert result.returncode == 2
        assert "폴더 경로 오류" in result.stderr

    result = run_directory_cli("")
    assert result.returncode == 2
    assert "폴더 경로를 지정해야 합니다." in result.stderr
