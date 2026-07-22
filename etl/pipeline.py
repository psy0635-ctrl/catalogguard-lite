import csv
import hashlib
import io
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from config.settings import CSV_TEMPLATE_COLUMNS, MAX_CSV_ROWS
from core.upload_validator import (
    CsvUploadValidationError,
    decode_csv_bytes,
    find_duplicate_columns,
    validate_csv_file_size,
    validate_csv_filename,
    validate_csv_text_not_empty,
    validate_no_nul_bytes,
)
from etl.profile_loader import ETLProfileValidationError, load_profile
from etl.transformer import transform_rows


class ETLPipelineError(ValueError):
    """Raised for safe, user-facing ETL pipeline failures."""


@dataclass(frozen=True)
class ETLPipelineResult:
    total_rows: int
    loaded_rows: int
    rejected_rows: int
    input_file_sha256: str
    output_file_sha256: str


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_supplier_csv(input_path: Path, required_columns: tuple[str, ...]) -> tuple[list[str], list[dict[str, str]], list[int], bytes]:
    try:
        file_bytes = input_path.read_bytes()
    except FileNotFoundError as error:
        raise ETLPipelineError("Input CSV file was not found") from error
    except OSError as error:
        raise ETLPipelineError("Input CSV file could not be read") from error

    try:
        validate_csv_filename(input_path.name)
        validate_csv_file_size(file_bytes)
        validate_no_nul_bytes(file_bytes)
        csv_text, _ = decode_csv_bytes(file_bytes)
        validate_csv_text_not_empty(csv_text)
        reader = csv.reader(io.StringIO(csv_text), strict=True)
        raw_header = next(reader)
    except StopIteration as error:
        raise ETLPipelineError("Input CSV file is empty") from error
    except (CsvUploadValidationError, csv.Error) as error:
        raise ETLPipelineError("Input CSV file is invalid") from error

    header = [column.strip() for column in raw_header]
    if not header or any(not column for column in header):
        raise ETLPipelineError("Input CSV has a blank header column")
    duplicates = find_duplicate_columns(header)
    if duplicates:
        raise ETLPipelineError("Input CSV has duplicate header columns")
    missing_columns = [column for column in required_columns if column not in header]
    if missing_columns:
        raise ETLPipelineError("Input CSV is missing required source columns")

    rows: list[dict[str, str]] = []
    row_numbers: list[int] = []
    try:
        for source_row_number, values in enumerate(reader, start=2):
            if not values or all(not value.strip() for value in values):
                continue
            if len(values) != len(header):
                raise ETLPipelineError("Input CSV has an invalid row format")
            rows.append(dict(zip(header, values, strict=True)))
            row_numbers.append(source_row_number)
    except csv.Error as error:
        raise ETLPipelineError("Input CSV has an invalid row format") from error

    if not rows:
        raise ETLPipelineError("Input CSV has no product rows")
    if len(rows) > MAX_CSV_ROWS:
        raise ETLPipelineError("Input CSV has too many product rows")
    return header, rows, row_numbers, file_bytes


def _validate_output_paths(
    input_path: Path,
    profile_path: Path,
    output_paths: tuple[Path, Path, Path],
) -> None:
    protected_paths = (input_path, profile_path)
    resolved_paths = [path.resolve() for path in (*protected_paths, *output_paths)]
    if any(path in resolved_paths[2:] for path in resolved_paths[:2]):
        raise ETLPipelineError("Output paths must not overwrite the input CSV or profile")
    if len(set(resolved_paths[2:])) != len(output_paths):
        raise ETLPipelineError("Output paths must be different from each other")
    for output_path in output_paths:
        if output_path.exists() and output_path.is_dir():
            raise ETLPipelineError("Output path must be a file")
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ETLPipelineError("Output directory could not be created") from error


def _write_csv_temp(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> Path:
    file_descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _write_json_temp(path: Path, data: dict[str, object]) -> Path:
    file_descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as output_file:
            json.dump(data, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _create_backup_path(path: Path) -> Path:
    file_descriptor, backup_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".backup",
    )
    os.close(file_descriptor)
    backup_path = Path(backup_name)
    backup_path.unlink()
    return backup_path


def _replace_temporary_files(temporary_files: list[tuple[Path, Path]]) -> None:
    backups: list[tuple[Path, Path]] = []
    replaced_paths: list[Path] = []
    try:
        for temporary_path, final_path in temporary_files:
            if final_path.exists():
                backup_path = _create_backup_path(final_path)
                os.replace(final_path, backup_path)
                backups.append((final_path, backup_path))
            os.replace(temporary_path, final_path)
            replaced_paths.append(final_path)
    except OSError as error:
        for final_path in reversed(replaced_paths):
            final_path.unlink(missing_ok=True)
        for final_path, backup_path in reversed(backups):
            if backup_path.exists():
                os.replace(backup_path, final_path)
        raise ETLPipelineError("Output files could not be saved") from error
    finally:
        for temporary_path, _ in temporary_files:
            temporary_path.unlink(missing_ok=True)
        for _, backup_path in backups:
            backup_path.unlink(missing_ok=True)


def run_pipeline(
    input_path: Path,
    profile_path: Path,
    output_path: Path,
    rejects_path: Path,
    summary_path: Path,
) -> ETLPipelineResult:
    input_path = Path(input_path)
    profile_path = Path(profile_path)
    output_path = Path(output_path)
    rejects_path = Path(rejects_path)
    summary_path = Path(summary_path)
    _validate_output_paths(
        input_path,
        profile_path,
        (output_path, rejects_path, summary_path),
    )
    started_at = datetime.now(UTC).isoformat()

    try:
        profile = load_profile(profile_path)
    except ETLProfileValidationError as error:
        raise ETLPipelineError(str(error)) from error
    source_columns, source_rows, source_row_numbers, input_bytes = _read_supplier_csv(
        input_path,
        profile.required_source_columns,
    )
    transformed = transform_rows(source_rows, profile, source_row_numbers)
    temporary_paths: list[Path] = []
    try:
        output_temp_path = _write_csv_temp(
            output_path,
            list(CSV_TEMPLATE_COLUMNS),
            transformed.loaded_rows,
        )
        temporary_paths.append(output_temp_path)
        output_bytes = output_temp_path.read_bytes()
        reject_fieldnames = [
            "source_row_number",
            "error_code",
            "error_message",
            *source_columns,
        ]
        rejects_temp_path = _write_csv_temp(
            rejects_path,
            reject_fieldnames,
            transformed.rejected_rows,
        )
        temporary_paths.append(rejects_temp_path)
        error_counts = Counter(
            error_code
            for rejected_row in transformed.rejected_rows
            for error_code in json.loads(rejected_row["error_code"])
        )
        summary_temp_path = _write_json_temp(
            summary_path,
            {
                "profile_name": profile.name,
                "profile_version": profile.version,
                "input_filename": input_path.name,
                "output_filename": output_path.name,
                "input_file_sha256": _sha256_bytes(input_bytes),
                "output_file_sha256": _sha256_bytes(output_bytes),
                "total_rows": len(source_rows),
                "loaded_rows": len(transformed.loaded_rows),
                "rejected_rows": len(transformed.rejected_rows),
                "error_counts": dict(sorted(error_counts.items())),
                "started_at": started_at,
                "completed_at": datetime.now(UTC).isoformat(),
            },
        )
    except OSError as error:
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)
        raise ETLPipelineError("Output files could not be saved") from error
    _replace_temporary_files(
        [
            (output_temp_path, output_path),
            (rejects_temp_path, rejects_path),
            (summary_temp_path, summary_path),
        ]
    )
    return ETLPipelineResult(
        total_rows=len(source_rows),
        loaded_rows=len(transformed.loaded_rows),
        rejected_rows=len(transformed.rejected_rows),
        input_file_sha256=_sha256_bytes(input_bytes),
        output_file_sha256=_sha256_bytes(output_bytes),
    )
