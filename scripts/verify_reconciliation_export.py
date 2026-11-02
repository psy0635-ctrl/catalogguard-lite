"""Verify a downloaded CatalogGuard reconciliation CSV and integrity JSON pair.

This offline tool does not load project configuration or connect to a database.
"""

import argparse
import csv
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys


_MANIFEST_KEYS = {
    "schema_version", "etl_load_run_id", "status_code", "csv_file_name",
    "csv_sha256", "row_count", "columns", "generated_at_utc",
    "consistency_limitation",
}
_EXPECTED_COLUMNS = ["상품 ID", "상태", "변경 필드"]
_ALLOWED_STATUSES = "all|new|changed|unchanged|not_observed_in_batch"
_CSV_NAME_PATTERN = re.compile(
    rf"catalogguard_reconciliation_([1-9][0-9]*)_({_ALLOWED_STATUSES})\.csv\Z"
)
_SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_MAX_MANIFEST_BYTES = 65536


class VerificationError(ValueError):
    """The selected files do not satisfy the reconciliation export contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("JSON에 중복된 키가 있습니다.")
        result[key] = value
    return result


def _load_manifest(path: Path) -> dict:
    if path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise VerificationError("JSON 파일이 허용 크기를 초과했습니다.")
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, VerificationError):
            raise
        raise VerificationError("JSON을 UTF-8 형식으로 읽을 수 없습니다.") from None
    if type(data) is not dict or set(data) != _MANIFEST_KEYS:
        raise VerificationError("JSON 필드 구성이 9개 필드 계약과 다릅니다.")
    return data


def _validate_manifest(data: dict, csv_path: Path, manifest_path: Path) -> None:
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise VerificationError("지원하지 않는 JSON 스키마 버전입니다.")
    if type(data["etl_load_run_id"]) is not int or data["etl_load_run_id"] < 1:
        raise VerificationError("배치 ID 형식이 올바르지 않습니다.")
    if type(data["status_code"]) is not str:
        raise VerificationError("상태 코드 형식이 올바르지 않습니다.")
    if type(data["csv_file_name"]) is not str:
        raise VerificationError("CSV 파일명 형식이 올바르지 않습니다.")
    if data["csv_file_name"] != csv_path.name:
        raise VerificationError("JSON에 기록된 CSV 파일명과 실제 파일명이 다릅니다.")
    match = _CSV_NAME_PATTERN.fullmatch(csv_path.name)
    if match is None or int(match.group(1)) != data["etl_load_run_id"] or match.group(2) != data["status_code"]:
        raise VerificationError("CSV 파일명·배치 ID·상태 코드가 서로 일치하지 않습니다.")
    if manifest_path.name != csv_path.name.removesuffix(".csv") + ".integrity.json":
        raise VerificationError("CSV와 JSON 파일명 조합이 올바르지 않습니다.")
    if type(data["csv_sha256"]) is not str or _SHA_PATTERN.fullmatch(data["csv_sha256"]) is None:
        raise VerificationError("SHA-256 값의 형식이 올바르지 않습니다.")
    if type(data["row_count"]) is not int or data["row_count"] < 0:
        raise VerificationError("행 수 형식이 올바르지 않습니다.")
    if data["columns"] != _EXPECTED_COLUMNS or type(data["columns"]) is not list:
        raise VerificationError("CSV 열 계약이 올바르지 않습니다.")
    if type(data["consistency_limitation"]) is not str or not data["consistency_limitation"].strip():
        raise VerificationError("일관성 한계 설명이 없습니다.")
    stamp = data["generated_at_utc"]
    if type(stamp) is not str or not stamp.endswith("Z"):
        raise VerificationError("UTC 생성 시각 형식이 올바르지 않습니다.")
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        raise VerificationError("UTC 생성 시각 형식이 올바르지 않습니다.") from None
    if parsed.utcoffset() != timedelta(0):
        raise VerificationError("UTC 생성 시각 형식이 올바르지 않습니다.")


def verify_reconciliation_export(csv_path: Path, manifest_path: Path) -> None:
    """Raise VerificationError on mismatch; never modify or upload either file."""
    try:
        manifest = _load_manifest(manifest_path)
        _validate_manifest(manifest, csv_path, manifest_path)
        digest = hashlib.sha256()
        with csv_path.open("rb") as stream:
            if stream.read(3) != b"\xef\xbb\xbf":
                raise VerificationError("CSV에 UTF-8 BOM이 없습니다.")
            stream.seek(0)
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != manifest["csv_sha256"]:
            raise VerificationError("CSV 파일의 실제 SHA-256이 JSON과 다릅니다.")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            try:
                columns = next(reader)
            except StopIteration:
                raise VerificationError("CSV 헤더가 없습니다.") from None
            if columns != manifest["columns"]:
                raise VerificationError("CSV 헤더가 JSON과 다릅니다.")
            count = 0
            for row in reader:
                if len(row) != len(_EXPECTED_COLUMNS):
                    raise VerificationError("CSV의 열 개수가 올바르지 않습니다.")
                count += 1
        if count != manifest["row_count"]:
            raise VerificationError("CSV의 실제 행 수가 JSON과 다릅니다.")
    except (OSError, UnicodeError, csv.Error) as exc:
        raise VerificationError("파일을 읽거나 CSV 형식을 해석할 수 없습니다.") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="다운로드한 상품 동기화 CSV와 무결성 JSON이 일치하는지 오프라인 검증합니다."
    )
    parser.add_argument("--csv", type=Path, required=True, help="다운로드한 CSV 파일 경로")
    parser.add_argument("--manifest", type=Path, required=True, help="대응하는 .integrity.json 경로")
    args = parser.parse_args(argv)
    try:
        verify_reconciliation_export(args.csv, args.manifest)
    except VerificationError as exc:
        print(f"검증 실패: {exc}", file=sys.stderr)
        return 1
    print("검증 성공: CSV와 JSON의 SHA-256·행 수·열·파일명이 일치합니다.")
    print("주의: 파일 일치는 상품 데이터의 정확성이나 작성자의 신원을 증명하지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
