import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePath

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.settings import REQUIRED_FIELDS
from core.upload_validator import CsvUploadValidationError, validate_and_read_uploaded_csv
from db.models import CatalogProductStaging, ETLLoadRun


class ETLLoadError(ValueError):
    """Raised for safe, user-facing ETL staging load failures."""


@dataclass(frozen=True)
class ETLLoadOutcome:
    etl_load_run_id: int
    created: bool
    loaded_rows: int


ETLLoadResult = ETLLoadOutcome
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SUMMARY_FIELDS = (
    "profile_name",
    "profile_version",
    "input_filename",
    "input_file_sha256",
    "output_file_sha256",
    "loaded_rows",
)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _required_text(summary: dict[str, object], field_name: str) -> str:
    value = summary.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ETLLoadError(f"요약 JSON의 {field_name} 값이 올바르지 않습니다")
    return value.strip()


def _normalize_hash(value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ETLLoadError(f"요약 JSON의 {field_name} 값이 올바르지 않습니다")
    return normalized


def _normalize_source_filename(value: str) -> str:
    filename = PurePath(value.replace("\\", "/")).name.strip()
    if not filename or filename in {".", ".."}:
        raise ETLLoadError("요약 JSON의 input_filename 값이 올바르지 않습니다")
    if len(filename) > 255:
        suffix = PurePath(filename).suffix
        if suffix and len(suffix) < 255:
            filename = f"{filename[:255 - len(suffix)]}{suffix}"
        else:
            filename = filename[:255]
    return filename


def _read_summary(summary_json_bytes: bytes) -> dict[str, object]:
    try:
        summary = json.loads(summary_json_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ETLLoadError("요약 JSON을 읽을 수 없습니다") from error
    if not isinstance(summary, dict):
        raise ETLLoadError("요약 JSON 형식이 올바르지 않습니다")
    missing_fields = [field for field in _SUMMARY_FIELDS if field not in summary]
    if missing_fields:
        raise ETLLoadError("요약 JSON 필수 필드가 없습니다")
    return summary


def _normalize_summary(summary: dict[str, object]) -> dict[str, object]:
    loaded_rows = summary["loaded_rows"]
    if not isinstance(loaded_rows, int) or isinstance(loaded_rows, bool) or loaded_rows < 0:
        raise ETLLoadError("요약 JSON의 loaded_rows 값이 올바르지 않습니다")

    profile_name = _required_text(summary, "profile_name")
    profile_version = _required_text(summary, "profile_version")
    if len(profile_name) > 100:
        raise ETLLoadError("profile_name이 너무 깁니다")
    if len(profile_version) > 20:
        raise ETLLoadError("profile_version이 너무 깁니다")

    return {
        "profile_name": profile_name,
        "profile_version": profile_version,
        "input_filename": _normalize_source_filename(
            _required_text(summary, "input_filename")
        ),
        "input_file_sha256": _normalize_hash(
            _required_text(summary, "input_file_sha256"),
            "input_file_sha256",
        ),
        "output_file_sha256": _normalize_hash(
            _required_text(summary, "output_file_sha256"),
            "output_file_sha256",
        ),
        "loaded_rows": loaded_rows,
    }


def _clean_cell(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _parse_non_negative_integer(value: object, field_name: str) -> int:
    normalized = _clean_cell(value).replace(",", "")
    try:
        parsed = int(normalized)
    except (TypeError, ValueError) as error:
        raise ETLLoadError(f"표준 CSV의 {field_name} 값이 올바르지 않습니다") from error
    if parsed < 0:
        raise ETLLoadError(f"표준 CSV의 {field_name} 값이 음수입니다")
    return parsed


def _build_staging_rows(dataframe: pd.DataFrame) -> list[dict[str, object]]:
    staging_rows: list[dict[str, object]] = []
    for row in dataframe.to_dict(orient="records"):
        cleaned = {field: _clean_cell(row.get(field)) for field in dataframe.columns}
        missing_fields = [field for field in REQUIRED_FIELDS if not cleaned.get(field)]
        if missing_fields:
            raise ETLLoadError("표준 CSV의 필수 상품 값이 비어 있습니다")
        sale_price_text = cleaned.get("sale_price", "")
        staging_rows.append(
            {
                "product_group_id": cleaned["product_group_id"],
                "product_id": cleaned["product_id"],
                "product_name": cleaned["product_name"],
                "category": cleaned["category"],
                "color": cleaned["color"],
                "size": cleaned["size"],
                "stock": _parse_non_negative_integer(cleaned["stock"], "stock"),
                "price": _parse_non_negative_integer(cleaned["price"], "price"),
                "sale_price": (
                    None
                    if not sale_price_text
                    else _parse_non_negative_integer(sale_price_text, "sale_price")
                ),
                "image_path": cleaned["image_path"],
                "description": cleaned.get("description") or None,
                "seller": cleaned.get("seller") or None,
            }
        )
    return staging_rows


def _add_staging_products(
    session: Session,
    *,
    etl_load_run_id: int,
    rows: list[dict[str, object]],
) -> None:
    session.add_all(
        [
            CatalogProductStaging(etl_load_run_id=etl_load_run_id, **row)
            for row in rows
        ]
    )
    session.flush()


def load_standard_csv(
    session: Session,
    standard_csv_bytes: bytes,
    summary_json_bytes: bytes,
    standard_csv_filename: str = "catalogguard_ready.csv",
) -> ETLLoadOutcome:
    """Validate ETL output and atomically add one idempotent staging batch."""
    summary = _normalize_summary(_read_summary(summary_json_bytes))
    actual_output_hash = _sha256_bytes(standard_csv_bytes)
    if actual_output_hash != summary["output_file_sha256"]:
        raise ETLLoadError("표준 CSV와 요약 JSON의 output_file_sha256가 일치하지 않습니다")

    try:
        dataframe = validate_and_read_uploaded_csv(standard_csv_filename, standard_csv_bytes)
    except (CsvUploadValidationError, UnicodeError, ValueError) as error:
        raise ETLLoadError("표준 CSV가 올바르지 않습니다") from error
    staging_rows = _build_staging_rows(dataframe)
    if len(staging_rows) != summary["loaded_rows"]:
        raise ETLLoadError("표준 CSV 행 수와 요약 JSON의 loaded_rows가 일치하지 않습니다")

    identity = {
        "input_file_sha256": summary["input_file_sha256"],
        "profile_name": summary["profile_name"],
        "profile_version": summary["profile_version"],
    }
    try:
        with session.begin():
            existing = session.scalar(
                select(ETLLoadRun).where(
                    ETLLoadRun.input_file_sha256 == identity["input_file_sha256"],
                    ETLLoadRun.profile_name == identity["profile_name"],
                    ETLLoadRun.profile_version == identity["profile_version"],
                )
            )
            if existing is not None:
                return ETLLoadOutcome(existing.id, False, existing.loaded_rows)

            load_run = ETLLoadRun(
                source_filename=summary["input_filename"],
                profile_name=summary["profile_name"],
                profile_version=summary["profile_version"],
                input_file_sha256=summary["input_file_sha256"],
                output_file_sha256=summary["output_file_sha256"],
                loaded_rows=summary["loaded_rows"],
            )
            session.add(load_run)
            session.flush()
            _add_staging_products(
                session,
                etl_load_run_id=load_run.id,
                rows=staging_rows,
            )
            return ETLLoadOutcome(load_run.id, True, load_run.loaded_rows)
    except IntegrityError:
        # A concurrent caller may have won the unique identity race.
        session.rollback()
        existing = session.scalar(
            select(ETLLoadRun).where(
                ETLLoadRun.input_file_sha256 == identity["input_file_sha256"],
                ETLLoadRun.profile_name == identity["profile_name"],
                ETLLoadRun.profile_version == identity["profile_version"],
            )
        )
        if existing is not None:
            return ETLLoadOutcome(existing.id, False, existing.loaded_rows)
        raise


load_etl_output = load_standard_csv
