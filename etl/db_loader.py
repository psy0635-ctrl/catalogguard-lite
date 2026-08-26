import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePath

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.settings import (
    ETL_INITIAL_SOURCE_REF_MAX_LENGTH,
    ETL_INITIAL_SOURCE_TYPE_UNKNOWN,
    ETL_INITIAL_SOURCE_TYPES,
    REQUIRED_FIELDS,
)
from etl.profile_fingerprint import compute_profile_definition_sha256_from_payload
from etl.profile_loader import ETLProfileValidationError, normalize_profile_semantic_payload
from core.fashion_attribute_validator import is_field_required_for_category
from core.upload_validator import CsvUploadValidationError, validate_and_read_uploaded_csv
from db.models import CatalogProductStaging, ETLLoadRun, ETLRejectedRow
from etl.reject_parser import ParsedRejectedRow, parse_reject_csv


class ETLLoadError(ValueError):
    """Raised for safe, user-facing ETL staging load failures."""


@dataclass(frozen=True)
class ETLLoadOutcome:
    etl_load_run_id: int
    created: bool
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    error_counts: dict[str, int] | None
    reject_details_stored: bool
    rejects_file_sha256: str | None
    # 이 배치를 최초로 만든 입력 경로입니다. duplicate일 때는 이번 요청의 source가 아니라
    # 이미 저장돼 있는 최초 source를 그대로 돌려줍니다.
    initial_source_type: str = ETL_INITIAL_SOURCE_TYPE_UNKNOWN
    initial_source_ref: str | None = None
    profile_definition_sha256: str | None = None
    profile_definition_snapshot: dict[str, object] | None = None
    application_commit_sha: str | None = None


ETLLoadResult = ETLLoadOutcome
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_APPLICATION_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SUMMARY_FIELDS = (
    "profile_name",
    "profile_version",
    "input_filename",
    "input_file_sha256",
    "output_file_sha256",
    "total_rows",
    "loaded_rows",
    "rejected_rows",
    "error_counts",
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


def _validate_profile_definition_sha256(value: object) -> str | None:
    """Validate the profile definition hash without normalizing its spelling.

    This is lineage metadata rather than an input/output file hash.  Accepting
    whitespace or upper-case variants would make an invalid producer summary
    look canonical, so the on-the-wire value must already be lower-case hex.
    """
    if value is None:
        return None
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ETLLoadError("요약 JSON의 profile_definition_sha256 값이 올바르지 않습니다")
    return value


def _normalize_profile_definition_snapshot(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    try:
        return normalize_profile_semantic_payload(value)
    except ETLProfileValidationError as error:
        raise ETLLoadError("요약 JSON의 profile_definition_snapshot 값이 올바르지 않습니다") from error


def _validate_application_commit_sha(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _APPLICATION_COMMIT_SHA_PATTERN.fullmatch(value) is None:
        raise ETLLoadError("요약 JSON의 application_commit_sha 값이 올바르지 않습니다")
    return value


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
    row_counts: dict[str, int] = {}
    for field_name in ("total_rows", "loaded_rows", "rejected_rows"):
        value = summary[field_name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ETLLoadError(f"요약 JSON의 {field_name} 값이 올바르지 않습니다")
        row_counts[field_name] = value
    if row_counts["total_rows"] != row_counts["loaded_rows"] + row_counts["rejected_rows"]:
        raise ETLLoadError("요약 JSON의 행 수 합계가 올바르지 않습니다")

    raw_error_counts = summary["error_counts"]
    if not isinstance(raw_error_counts, dict):
        raise ETLLoadError("요약 JSON의 error_counts 값이 올바르지 않습니다")
    error_counts: dict[str, int] = {}
    for raw_key, value in raw_error_counts.items():
        if not isinstance(raw_key, str):
            raise ETLLoadError("요약 JSON의 error_counts 값이 올바르지 않습니다")
        key = raw_key.strip()
        if not key or key in error_counts:
            raise ETLLoadError("요약 JSON의 error_counts 값이 올바르지 않습니다")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ETLLoadError("요약 JSON의 error_counts 값이 올바르지 않습니다")
        error_counts[key] = value
    if row_counts["rejected_rows"] == 0 and error_counts:
        raise ETLLoadError("요약 JSON의 error_counts 값이 올바르지 않습니다")
    if row_counts["rejected_rows"] > 0 and (
        not error_counts or sum(error_counts.values()) < row_counts["rejected_rows"]
    ):
        raise ETLLoadError("요약 JSON의 error_counts 값이 올바르지 않습니다")

    profile_name = _required_text(summary, "profile_name")
    profile_version = _required_text(summary, "profile_version")
    if len(profile_name) > 100:
        raise ETLLoadError("profile_name이 너무 깁니다")
    if len(profile_version) > 20:
        raise ETLLoadError("profile_version이 너무 깁니다")

    normalized_summary: dict[str, object] = {
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
        **row_counts,
        "error_counts": error_counts,
    }
    if "rejects_file_sha256" in summary:
        normalized_summary["rejects_file_sha256"] = _normalize_hash(
            _required_text(summary, "rejects_file_sha256"),
            "rejects_file_sha256",
        )
    if "profile_definition_sha256" in summary:
        normalized_summary["profile_definition_sha256"] = _validate_profile_definition_sha256(
            summary["profile_definition_sha256"],
        )
    if "profile_definition_snapshot" in summary:
        normalized_summary["profile_definition_snapshot"] = _normalize_profile_definition_snapshot(
            summary["profile_definition_snapshot"]
        )
    snapshot = normalized_summary.get("profile_definition_snapshot")
    fingerprint = normalized_summary.get("profile_definition_sha256")
    if snapshot is not None:
        if fingerprint is None:
            raise ETLLoadError(
                "요약 JSON의 profile_definition_snapshot에는 profile_definition_sha256가 필요합니다"
            )
        if compute_profile_definition_sha256_from_payload(snapshot) != fingerprint:
            raise ETLLoadError(
                "요약 JSON의 profile_definition_snapshot과 profile_definition_sha256가 일치하지 않습니다"
            )
    if "application_commit_sha" in summary:
        normalized_summary["application_commit_sha"] = _validate_application_commit_sha(
            summary["application_commit_sha"],
        )
    return normalized_summary


def _validate_existing_profile_definition(existing: ETLLoadRun, incoming: str | None) -> None:
    """Reject only the provable known-known semantic definition mismatch."""
    if (
        existing.profile_definition_sha256 is not None
        and incoming is not None
        and existing.profile_definition_sha256 != incoming
    ):
        raise ETLLoadError(
            "동일한 profile_name/profile_version의 프로필 정의가 기존 ETL 배치와 일치하지 않습니다"
        )


def _validated_source_type(value: str) -> str:
    # DB CheckConstraint가 마지막 방어선이지만, 여기서 먼저 막아야 안전한 ETLLoadError로 실패합니다.
    if value not in ETL_INITIAL_SOURCE_TYPES:
        raise ETLLoadError("허용하지 않는 ETL source type입니다")
    return value


def _normalized_source_ref(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    # source_filename과 같은 방식으로, 너무 긴 값은 driver 오류 대신 잘라서 저장합니다.
    return normalized[:ETL_INITIAL_SOURCE_REF_MAX_LENGTH]


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
        # REQUIRED_FIELDS는 그대로 두고, 검수와 같은 카테고리별 정책으로 예외만 판단합니다.
        # 정책에 없는 카테고리(빈 값, 허용 목록에 없는 값)는 기존처럼 모두 필수입니다.
        missing_fields = [
            field
            for field in REQUIRED_FIELDS
            if not cleaned.get(field)
            and is_field_required_for_category(cleaned.get("category", ""), field)
        ]
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


def _add_rejected_rows(
    session: Session,
    *,
    etl_load_run_id: int,
    rows: list[ParsedRejectedRow],
) -> None:
    session.add_all(
        [
            ETLRejectedRow(
                etl_load_run_id=etl_load_run_id,
                source_row_number=row.source_row_number,
                errors=[
                    {
                        "code": error.code,
                        "field": error.field,
                        "message": error.message,
                    }
                    for error in row.errors
                ],
                masked_source_data=row.masked_source_data,
            )
            for row in rows
        ]
    )
    session.flush()


def load_standard_csv(
    session: Session,
    standard_csv_bytes: bytes,
    summary_json_bytes: bytes,
    standard_csv_filename: str = "catalogguard_ready.csv",
    rejects_csv_bytes: bytes | None = None,
    rejects_csv_filename: str = "rejected_rows.csv",
    actor_user_id: int | None = None,
    actor_username: str | None = None,
    initial_source_type: str = ETL_INITIAL_SOURCE_TYPE_UNKNOWN,
    initial_source_ref: str | None = None,
) -> ETLLoadOutcome:
    """Validate ETL output and atomically add one idempotent staging batch."""
    source_type = _validated_source_type(initial_source_type)
    source_ref = _normalized_source_ref(initial_source_ref)
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

    rejects_file_sha256 = summary.get("rejects_file_sha256")
    parsed_rejects: list[ParsedRejectedRow] = []
    if rejects_file_sha256 is None:
        if rejects_csv_bytes is not None:
            raise ETLLoadError(
                "rejects_file_sha256가 없으면 reject CSV를 받을 수 없습니다"
            )
    else:
        if rejects_csv_bytes is None:
            raise ETLLoadError(
                "rejects_file_sha256가 있으면 reject CSV가 필요합니다"
            )
        if _sha256_bytes(rejects_csv_bytes) != rejects_file_sha256:
            raise ETLLoadError(
                "reject CSV와 summary의 rejects_file_sha256가 일치하지 않습니다"
            )
        try:
            parsed_rejects = parse_reject_csv(
                rejects_csv_bytes,
                filename=rejects_csv_filename,
                expected_row_count=summary["rejected_rows"],
            )
        except (ValueError, TypeError) as error:
            raise ETLLoadError("reject CSV가 올바르지 않습니다") from error

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
                _validate_existing_profile_definition(
                    existing, summary.get("profile_definition_sha256")
                )
                # duplicate입니다. 이번 요청의 source로 기존 배치를 덮어쓰지 않고,
                # 저장돼 있는 최초 source를 그대로 돌려줍니다.
                return ETLLoadOutcome(
                    existing.id,
                    False,
                    existing.total_rows,
                    existing.loaded_rows,
                    existing.rejected_rows,
                    existing.error_counts,
                    existing.reject_details_stored,
                    existing.rejects_file_sha256,
                    initial_source_type=existing.initial_source_type,
                    initial_source_ref=existing.initial_source_ref,
                    profile_definition_sha256=existing.profile_definition_sha256,
                    profile_definition_snapshot=existing.profile_definition_snapshot,
                    application_commit_sha=existing.application_commit_sha,
                )

            load_run = ETLLoadRun(
                source_filename=summary["input_filename"],
                profile_name=summary["profile_name"],
                profile_version=summary["profile_version"],
                input_file_sha256=summary["input_file_sha256"],
                output_file_sha256=summary["output_file_sha256"],
                profile_definition_sha256=summary.get("profile_definition_sha256"),
                profile_definition_snapshot=summary.get("profile_definition_snapshot"),
                application_commit_sha=summary.get("application_commit_sha"),
                loaded_rows=summary["loaded_rows"],
                total_rows=summary["total_rows"],
                rejected_rows=summary["rejected_rows"],
                error_counts=summary["error_counts"],
                reject_details_stored=rejects_file_sha256 is not None,
                rejects_file_sha256=rejects_file_sha256,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
                initial_source_type=source_type,
                initial_source_ref=source_ref,
            )
            session.add(load_run)
            session.flush()
            _add_staging_products(
                session,
                etl_load_run_id=load_run.id,
                rows=staging_rows,
            )
            _add_rejected_rows(
                session,
                etl_load_run_id=load_run.id,
                rows=parsed_rejects,
            )
            return ETLLoadOutcome(
                load_run.id,
                True,
                load_run.total_rows,
                load_run.loaded_rows,
                load_run.rejected_rows,
                load_run.error_counts,
                load_run.reject_details_stored,
                load_run.rejects_file_sha256,
                initial_source_type=load_run.initial_source_type,
                initial_source_ref=load_run.initial_source_ref,
                profile_definition_sha256=load_run.profile_definition_sha256,
                profile_definition_snapshot=load_run.profile_definition_snapshot,
                application_commit_sha=load_run.application_commit_sha,
            )
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
            _validate_existing_profile_definition(
                existing, summary.get("profile_definition_sha256")
            )
            # unique identity 경쟁에서 진 요청입니다. 여기서도 기존 row를 update하지 않습니다.
            return ETLLoadOutcome(
                existing.id,
                False,
                existing.total_rows,
                existing.loaded_rows,
                existing.rejected_rows,
                existing.error_counts,
                existing.reject_details_stored,
                existing.rejects_file_sha256,
                initial_source_type=existing.initial_source_type,
                initial_source_ref=existing.initial_source_ref,
                profile_definition_sha256=existing.profile_definition_sha256,
                profile_definition_snapshot=existing.profile_definition_snapshot,
                application_commit_sha=existing.application_commit_sha,
            )
        raise


load_etl_output = load_standard_csv
