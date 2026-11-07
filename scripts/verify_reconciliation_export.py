"""Verify downloaded CatalogGuard reconciliation CSV and integrity JSON pairs.

This offline tool does not load project configuration or connect to a database.
"""

import argparse
from contextlib import ExitStack, contextmanager
import csv
from datetime import datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys


_MANIFEST_KEYS = {
    "schema_version", "etl_load_run_id", "status_code", "csv_file_name",
    "csv_sha256", "row_count", "columns", "generated_at_utc",
    "consistency_limitation",
}
_EXPECTED_COLUMNS = ["상품 ID", "상태", "변경 필드"]
_ALLOWED_STATUSES = "all|new|changed|unchanged|not_observed_in_batch"
_EXPORT_PREFIX = "catalogguard_reconciliation_"
_MANIFEST_SUFFIX = ".integrity.json"
_CSV_NAME_PATTERN = re.compile(
    rf"{_EXPORT_PREFIX}([1-9][0-9]*)_({_ALLOWED_STATUSES})\.csv\Z"
)
_SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_MAX_MANIFEST_BYTES = 65536

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    import msvcrt

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")

    class _UnicodeString(ctypes.Structure):
        _fields_ = [("length", wintypes.USHORT), ("capacity", wintypes.USHORT), ("buffer", wintypes.LPWSTR)]

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.ULONG), ("root", wintypes.HANDLE),
            ("name", ctypes.POINTER(_UnicodeString)), ("flags", wintypes.ULONG),
            ("security_descriptor", ctypes.c_void_p), ("security_qos", ctypes.c_void_p),
        ]

    class _IoStatusBlock(ctypes.Structure):
        _fields_ = [("status_or_pointer", ctypes.c_void_p), ("information", ctypes.c_size_t)]

    class _BasicInfo(ctypes.Structure):
        _fields_ = [
            ("creation_time", ctypes.c_int64), ("access_time", ctypes.c_int64),
            ("write_time", ctypes.c_int64), ("change_time", ctypes.c_int64),
            ("attributes", wintypes.DWORD),
        ]

    class _StandardInfo(ctypes.Structure):
        _fields_ = [
            ("allocation_size", ctypes.c_int64), ("size", ctypes.c_int64),
            ("link_count", wintypes.DWORD), ("delete_pending", wintypes.BOOLEAN),
            ("directory", wintypes.BOOLEAN),
        ]

    class _FileIdInfo(ctypes.Structure):
        _fields_ = [("volume_serial", ctypes.c_uint64), ("file_id", ctypes.c_ubyte * 16)]

    class _DirectoryEntryHeader(ctypes.Structure):
        # FILE_ID_EXTD_DIR_INFO through FileId. The variable-length UTF-16 name follows.
        _fields_ = [
            ("next_offset", wintypes.ULONG), ("index", wintypes.ULONG),
            ("creation_time", ctypes.c_int64), ("access_time", ctypes.c_int64),
            ("write_time", ctypes.c_int64), ("change_time", ctypes.c_int64),
            ("size", ctypes.c_int64), ("allocation_size", ctypes.c_int64), ("attributes", wintypes.ULONG),
            ("name_length", wintypes.ULONG), ("ea_size", wintypes.ULONG),
            ("tag", wintypes.ULONG), ("file_id", ctypes.c_ubyte * 16),
        ]

    _nt_create_file = _ntdll.NtCreateFile
    _nt_create_file.argtypes = (
        ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock), ctypes.c_void_p, wintypes.ULONG,
        wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
    )
    _nt_create_file.restype = wintypes.LONG
    _nt_error_to_win32 = _ntdll.RtlNtStatusToDosError
    _nt_error_to_win32.argtypes = (wintypes.LONG,)
    _nt_error_to_win32.restype = wintypes.ULONG
    _close_handle = _kernel32.CloseHandle
    _close_handle.argtypes = (wintypes.HANDLE,)
    _close_handle.restype = wintypes.BOOL
    _query_dos_device = _kernel32.QueryDosDeviceW
    _query_dos_device.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    _query_dos_device.restype = wintypes.DWORD
    _volume_information = _kernel32.GetVolumeInformationByHandleW
    _volume_information.argtypes = (
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.LPDWORD,
        wintypes.LPDWORD, wintypes.LPDWORD, wintypes.LPWSTR, wintypes.DWORD,
    )
    _volume_information.restype = wintypes.BOOL
    _file_information = _kernel32.GetFileInformationByHandleEx
    _file_information.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    _file_information.restype = wintypes.BOOL

    _FILE_READ_DATA_OR_LIST_DIRECTORY = 0x0001
    _FILE_READ_ATTRIBUTES = 0x0080
    _SYNCHRONIZE = 0x00100000
    _FILE_SHARE_READ = 0x0001
    _FILE_OPEN = 0x0001
    _FILE_SYNCHRONOUS_IO_NONALERT = 0x0020
    _FILE_OPEN_REPARSE_POINT = 0x00200000
    _OBJ_CASE_INSENSITIVE = 0x0040
    _FILE_BASIC_INFO = 0
    _FILE_STANDARD_INFO = 1
    _FILE_ID_INFO = 18
    _FILE_ID_EXTD_DIRECTORY_INFO = 19
    _ERROR_NO_MORE_FILES = 18


class VerificationError(ValueError):
    """The selected files do not satisfy the reconciliation export contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("JSON에 중복된 키가 있습니다.")
        result[key] = value
    return result


def _load_manifest(stream) -> dict:
    payload = stream.read(_MAX_MANIFEST_BYTES + 1)
    if len(payload) > _MAX_MANIFEST_BYTES:
        raise VerificationError("JSON 파일이 허용 크기를 초과했습니다.")
    try:
        data = json.loads(
            payload.decode("utf-8"),
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
    if manifest_path.name != csv_path.name.removesuffix(".csv") + _MANIFEST_SUFFIX:
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


def _verify_csv(stream, manifest: dict) -> None:
    if stream.read(3) != b"\xef\xbb\xbf":
        raise VerificationError("CSV에 UTF-8 BOM이 없습니다.")
    stream.seek(0)
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    if digest.hexdigest() != manifest["csv_sha256"]:
        raise VerificationError("CSV 파일의 실제 SHA-256이 JSON과 다릅니다.")

    stream.seek(0)
    with io.TextIOWrapper(stream, encoding="utf-8-sig", newline="") as text_stream:
        reader = csv.reader(text_stream, strict=True)
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


def _verify_opened_pair(csv_path: Path, manifest_path: Path, open_binary) -> None:
    try:
        with open_binary(manifest_path) as manifest_stream:
            manifest = _load_manifest(manifest_stream)
            _validate_manifest(manifest, csv_path, manifest_path)
            with open_binary(csv_path) as csv_stream:
                _verify_csv(csv_stream, manifest)
    except (OSError, UnicodeError, csv.Error):
        raise VerificationError("파일을 읽거나 CSV 형식을 해석할 수 없습니다.") from None


def verify_reconciliation_export(csv_path: Path, manifest_path: Path) -> None:
    """Raise VerificationError on mismatch; never modify or upload either file."""
    _verify_opened_pair(csv_path, manifest_path, lambda path: path.open("rb"))


_REPARSE_ERROR = "심볼릭 링크 또는 재분석 지점은 허용되지 않습니다."


def _win_open(name: str, parent=None, *, directory=False):
    # A relative open has exactly one component. Never let it supply a new root,
    # traverse to another directory, or name an NTFS alternate data stream.
    if parent is not None and (not name or name in (".", "..") or any(c in name for c in "\\/:\0")):
        raise VerificationError("허용되지 않는 경로 구성 요소입니다.")
    encoded_size = len(name.encode("utf-16-le", errors="surrogatepass"))
    if encoded_size > 65532:
        raise VerificationError("경로 구성 요소가 너무 깁니다.")
    buffer = ctypes.create_unicode_buffer(name, encoded_size // 2 + 1)
    object_name = _UnicodeString(encoded_size, encoded_size + 2, ctypes.cast(buffer, wintypes.LPWSTR))
    attributes = _ObjectAttributes(
        ctypes.sizeof(_ObjectAttributes), parent, ctypes.pointer(object_name),
        _OBJ_CASE_INSENSITIVE if directory else 0, None, None,
    )
    handle = wintypes.HANDLE()
    status = _nt_create_file(
        ctypes.byref(handle), _FILE_READ_DATA_OR_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE,
        ctypes.byref(attributes), ctypes.byref(_IoStatusBlock()), None, 0,
        _FILE_SHARE_READ, _FILE_OPEN, _FILE_OPEN_REPARSE_POINT | _FILE_SYNCHRONOUS_IO_NONALERT, None, 0,
    )
    if status != 0:
        raise ctypes.WinError(_nt_error_to_win32(status))
    return handle.value


def _win_info(handle, info_class: int, info):
    if not _file_information(handle, info_class, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return info


def _win_check_object(handle, *, directory: bool) -> int:
    basic = _win_info(handle, _FILE_BASIC_INFO, _BasicInfo())
    if basic.attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise VerificationError(_REPARSE_ERROR)
    if basic.attributes & (stat.FILE_ATTRIBUTE_DEVICE | stat.FILE_ATTRIBUTE_OFFLINE):
        raise VerificationError("열린 항목의 종류 또는 안전성을 확인할 수 없습니다.")
    standard = _win_info(handle, _FILE_STANDARD_INFO, _StandardInfo())
    if standard.delete_pending or bool(standard.directory) != directory:
        raise VerificationError("열린 항목의 종류 또는 안전성을 확인할 수 없습니다.")
    if not directory and standard.link_count != 1:
        raise VerificationError("하드 링크로 공유된 파일은 허용되지 않습니다.")
    return basic.write_time


def _win_directory(directory: Path, guards: ExitStack):
    if not re.fullmatch(r"[A-Za-z]:\\", directory.anchor):
        raise VerificationError("로컬 NTFS 드라이브의 폴더 경로를 지정해야 합니다.")
    if any(":" in part or part.endswith((".", " ")) for part in directory.parts[1:]):
        raise VerificationError("폴더 경로에 허용되지 않는 이름이 있습니다.")

    # Resolve the DOS drive once to a local volume device. SUBST, UNC and mapped
    # network drives have different targets. Child opens never use the drive letter.
    target = ctypes.create_unicode_buffer(32768)
    if not _query_dos_device(directory.drive, target, len(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not re.fullmatch(r"\\Device\\HarddiskVolume[0-9]+", target.value):
        raise VerificationError("로컬 NTFS 드라이브의 폴더 경로를 지정해야 합니다.")
    handle = _win_open(target.value + "\\", directory=True)
    guards.callback(_close_handle, handle)
    _win_check_object(handle, directory=True)
    filesystem = ctypes.create_unicode_buffer(32)
    if not _volume_information(handle, None, 0, None, None, None, filesystem, len(filesystem)):
        raise ctypes.WinError(ctypes.get_last_error())
    if filesystem.value != "NTFS":
        raise VerificationError("Windows 폴더 검증은 로컬 NTFS에서만 지원합니다.")

    for name in directory.parts[1:]:
        handle = _win_open(name, handle, directory=True)
        guards.callback(_close_handle, handle)
        _win_check_object(handle, directory=True)
    return handle


def _win_list(handle):
    """Yield names and identity from the already-open directory."""
    buffer = ctypes.create_string_buffer(65536)
    header_size = ctypes.sizeof(_DirectoryEntryHeader)
    while _file_information(handle, _FILE_ID_EXTD_DIRECTORY_INFO, buffer, len(buffer)):
        offset = 0
        while True:
            if offset + header_size > len(buffer):
                raise VerificationError("폴더 항목 정보를 확인할 수 없습니다.")
            item = _DirectoryEntryHeader.from_buffer(buffer, offset)
            start = offset + header_size
            end = start + item.name_length
            if not item.name_length or item.name_length % 2 or end > len(buffer):
                raise VerificationError("폴더 항목 정보를 확인할 수 없습니다.")
            name = buffer[start:end].decode("utf-16-le", errors="surrogatepass")
            yield name, item.attributes, (bytes(item.file_id), item.write_time)
            if not item.next_offset:
                break
            if offset + item.next_offset < end:
                raise VerificationError("폴더 항목 정보를 확인할 수 없습니다.")
            offset += item.next_offset
    if ctypes.get_last_error() != _ERROR_NO_MORE_FILES:
        raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def _win_open_binary(directory_handle, name: str, expected: tuple[bytes, int]):
    handle = _win_open(name, directory_handle)
    try:
        write_time = _win_check_object(handle, directory=False)
        identity = _win_info(handle, _FILE_ID_INFO, _FileIdInfo())
        expected_id, expected_write_time = expected
        if not any(expected_id) or bytes(identity.file_id) != expected_id:
            raise VerificationError("검색 후 파일이 교체되었거나 파일 식별자가 일치하지 않습니다.")
        if write_time != expected_write_time:
            raise VerificationError("검색 후 파일이 수정되었거나 쓰기 시각이 일치하지 않습니다.")
        # The descriptor owns the Windows handle after a successful transfer.
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        _close_handle(handle)
        raise
    try:
        with os.fdopen(fd, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)


def _entry_type(path: Path) -> int:
    """Classify an entry without following links in its final component."""
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise VerificationError(_REPARSE_ERROR)
    return stat.S_IFMT(mode)


def _path_entries(directory: Path) -> dict[str, str | None]:
    for component in (*reversed(directory.parents), directory):
        if _entry_type(component) != stat.S_IFDIR:
            raise VerificationError("입력 경로가 폴더가 아닙니다.")
    entries: dict[str, str | None] = {}
    for path in directory.iterdir():
        if not path.name.lower().startswith(_EXPORT_PREFIX):
            continue
        try:
            entry_type = _entry_type(path)
            if entry_type == stat.S_IFDIR:
                continue
            if entry_type != stat.S_IFREG:
                raise VerificationError("일반 파일만 검증할 수 있습니다.")
            if path.lstat().st_nlink != 1:
                raise VerificationError("하드 링크로 공유된 파일은 허용되지 않습니다.")
            entries[path.name] = None
        except OSError:
            entries[path.name] = "파일의 안전성을 확인할 수 없습니다."
        except VerificationError as exc:
            entries[path.name] = str(exc)
    return entries


def _verify_directory(directory: Path) -> int:
    with ExitStack() as guards:
        try:
            directory = directory.absolute()
            if sys.platform == "win32":
                handle = _win_directory(directory, guards)
                entries = {}
                identities = {}
                for name, attributes, identity in _win_list(handle):
                    if not name.lower().startswith(_EXPORT_PREFIX):
                        continue
                    if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        entries[name] = _REPARSE_ERROR
                    elif not attributes & stat.FILE_ATTRIBUTE_DIRECTORY:
                        entries[name] = None
                        identities[name] = identity

                def verify_pair(csv_path, manifest_path):
                    def open_binary(path):
                        return _win_open_binary(handle, path.name, identities[path.name])

                    _verify_opened_pair(csv_path, manifest_path, open_binary)
            else:
                entries = _path_entries(directory)
                verify_pair = verify_reconciliation_export
        except OSError:
            print("폴더 경로 오류: 입력 폴더를 읽거나 안전성을 확인할 수 없습니다.", file=sys.stderr)
            return 2
        except VerificationError as exc:
            print(f"폴더 경로 오류: {exc}", file=sys.stderr)
            return 2
        return _verify_entries(directory, entries, verify_pair)


def _verify_entries(directory: Path, entries: dict[str, str | None], verify_pair) -> int:
    passed = failed = 0
    for name in sorted(entries):
        csv_name = name.removesuffix(_MANIFEST_SUFFIX) + ".csv" if name.endswith(_MANIFEST_SUFFIX) else name
        if not _CSV_NAME_PATTERN.fullmatch(csv_name):
            failed += 1
            reason = entries[name] or "CatalogGuard 파일명 규칙과 일치하지 않습니다."
            print(f"FAIL [항목 {passed + failed}]: {reason}")
            continue
        if name != csv_name and csv_name in entries:
            continue  # The CSV entry reports this pair once.

        manifest_name = csv_name.removesuffix(".csv") + _MANIFEST_SUFFIX
        try:
            for member in (csv_name, manifest_name):
                if reason := entries.get(member):
                    raise VerificationError(reason)
            if csv_name not in entries:
                raise VerificationError("대응하는 CSV 파일이 없습니다.")
            if manifest_name not in entries:
                raise VerificationError("대응하는 .integrity.json 파일이 없습니다.")
            verify_pair(directory / csv_name, directory / manifest_name)
        except VerificationError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
        else:
            passed += 1
            print(f"PASS {name}")

    if not entries:
        print("검증 대상 파일이 없습니다.")
    print(f"검사 대상 {passed + failed}건 | 성공 {passed}건 | 실패 {failed}건")
    return 0 if passed and not failed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="다운로드한 상품 동기화 CSV와 무결성 JSON이 일치하는지 오프라인 검증합니다."
    )
    parser.add_argument("--csv", type=Path, help="다운로드한 CSV 파일 경로")
    parser.add_argument("--manifest", type=Path, help="대응하는 .integrity.json 경로")
    parser.add_argument("--directory", help="CSV와 JSON 파일 쌍이 있는 폴더 경로")
    args = parser.parse_args(argv)
    if args.directory is not None:
        if args.csv is not None or args.manifest is not None:
            parser.error("--directory는 --csv 또는 --manifest와 함께 사용할 수 없습니다.")
        if not args.directory:
            parser.error("--directory에 폴더 경로를 지정해야 합니다.")
        return _verify_directory(Path(args.directory))
    missing = [option for option in ("csv", "manifest") if getattr(args, option) is None]
    if missing:
        parser.error("the following arguments are required: " + ", ".join(f"--{option}" for option in missing))
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
