from datetime import date, datetime, timezone
import re
from typing import Any
from urllib.parse import quote
from uuid import UUID

import requests

from config.settings import (
    CATALOGGUARD_API_DEFAULT_TIMEOUT_SECONDS,
    get_catalogguard_api_base_url,
    get_catalogguard_api_timeout_seconds,
)


CONFIGURATION_ERROR_MESSAGE = "검수 이력 API 주소가 설정되지 않았습니다."
CONNECTION_ERROR_MESSAGE = "검수 이력 서버에 연결할 수 없습니다."
TIMEOUT_ERROR_MESSAGE = "검수 이력 서버 응답 시간이 초과되었습니다."
NOT_FOUND_ERROR_MESSAGE = "검수 실행 결과를 찾을 수 없습니다."
SERVER_ERROR_MESSAGE = "검수 이력 서버에서 오류가 발생했습니다."
INVALID_RESPONSE_MESSAGE = "검수 이력 서버의 응답 형식이 올바르지 않습니다."
VALID_INSPECTION_STATUS_FILTERS = {"error", "warning", "normal"}
REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

LIST_RESPONSE_KEYS = ("items", "total", "limit", "offset")
CREATE_RESPONSE_KEYS = ("inspection_run_id", "summary", "results")
DETAIL_RESPONSE_KEYS = (
    "inspection_run_id",
    "source_filename",
    "created_at",
    "summary",
    "results",
)
JOB_SUBMISSION_RESPONSE_KEYS = ("job_id", "status", "status_url")
JOB_STATUS_RESPONSE_KEYS = ("job_id", "status")
VALID_JOB_STATUSES = {"queued", "running", "succeeded", "failed"}
ETL_LOAD_LIST_RESPONSE_KEYS = ("items", "total", "limit", "offset")
ETL_LOAD_QUALITY_SUMMARY_RESPONSE_KEYS = (
    "batch_count",
    "quality_available_batch_count",
    "quality_unavailable_batch_count",
    "total_rows",
    "loaded_rows",
    "rejected_rows",
    "rejection_rate",
)
ETL_LOAD_QUALITY_TREND_RESPONSE_KEYS = ("items",)
ETL_LOAD_QUALITY_TREND_ITEM_KEYS = (
    "etl_load_run_id",
    "created_at",
    "total_rows",
    "loaded_rows",
    "rejected_rows",
    "rejection_rate",
)
ETL_QUALITY_OBSERVABILITY_RESPONSE_KEYS = (
    "profile_name",
    "limit",
    "batch_count",
    "latest_batch",
    "previous_batch",
    "rejection_rate_delta",
    "direction",
    "error_codes",
    "recent_batches",
)
ETL_QUALITY_OBSERVABILITY_ERROR_CODE_KEYS = (
    "error_code",
    "total_count",
    "affected_batch_count",
)
ETL_QUALITY_OBSERVABILITY_DIRECTIONS = frozenset(
    {"improved", "unchanged", "worsened", "no_baseline"}
)
ETL_QUALITY_OBSERVABILITY_PROFILE_LIST_KEYS = ("items",)
ETL_QUALITY_OBSERVABILITY_PROFILE_KEYS = ("profile_name",)
ETL_QUALITY_OBSERVABILITY_MIN_LIMIT = 1
ETL_QUALITY_OBSERVABILITY_MAX_LIMIT = 50
ETL_LOAD_ITEM_KEYS = (
    "etl_load_run_id",
    "source_filename",
    "profile_name",
    "profile_version",
    "total_rows",
    "loaded_rows",
    "rejected_rows",
    "created_at",
)
ETL_LOAD_DETAIL_RESPONSE_KEYS = (
    "etl_load_run_id",
    "source_filename",
    "profile_name",
    "profile_version",
    "input_file_sha256",
    "output_file_sha256",
    "total_rows",
    "loaded_rows",
    "rejected_rows",
    "error_counts",
    "created_at",
    "products",
)
ETL_PRODUCT_LIST_KEYS = ("items", "total", "limit", "offset")
ETL_PRODUCT_KEYS = (
    "staging_product_id",
    "product_group_id",
    "product_id",
    "product_name",
    "category",
    "color",
    "size",
    "stock",
    "price",
    "sale_price",
    "image_path",
    "description",
    "seller",
    "created_at",
)
ETL_REJECTION_LIST_KEYS = ("available", "items", "total", "limit", "offset")
ETL_REJECTION_ITEM_KEYS = (
    "rejected_row_id",
    "source_row_number",
    "errors",
    "masked_source_data",
    "created_at",
)
ETL_REJECTION_ERROR_KEYS = ("code", "field", "message")
ETL_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
CATALOG_PROMOTION_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CATALOG_RECONCILIATION_RESPONSE_KEYS = (
    "etl_load_run_id",
    "supplier_key",
    "total_rows",
    "loaded_rows",
    "rejected_rows",
    "new_count",
    "changed_count",
    "unchanged_count",
    "not_observed_in_batch_count",
    "field_change_counts",
    "items",
    "total",
    "limit",
    "offset",
)
CATALOG_RECONCILIATION_ITEM_KEYS = (
    "external_product_id",
    "status",
    "changed_fields",
)
CATALOG_RECONCILIATION_STATUSES = (
    "new",
    "changed",
    "unchanged",
    "not_observed_in_batch",
)
CATALOG_PROMOTION_PREVIEW_RESPONSE_KEYS = (
    "etl_load_run_id",
    "supplier_key",
    "inspection_version",
    "preview_schema_version",
    "preview_hash",
    "promotion_eligible",
    "blocked_reasons",
    "insert_count",
    "update_count",
    "unchanged_count",
    "error_count",
    "warning_count",
    "items",
)
CATALOG_PROMOTION_PREVIEW_ITEM_KEYS = (
    "supplier_key",
    "external_product_id",
    "action",
    "changed_fields",
    "before_data",
    "after_data",
)
CATALOG_PROMOTION_PRODUCT_DATA_KEYS = (
    "external_product_id",
    "product_group_id",
    "product_name",
    "category",
    "color",
    "size",
    "stock",
    "price",
    "sale_price",
    "image_path",
    "description",
    "seller",
)
CATALOG_PROMOTION_RESPONSE_KEYS = (
    "promotion_run_id",
    "etl_load_run_id",
    "status",
    "created",
    "preview_hash",
    "preview_schema_version",
    "inspection_version",
    "inserted_count",
    "updated_count",
    "unchanged_count",
    "blocked_count",
    "error_count",
    "warning_count",
    "started_at",
    "completed_at",
)
CATALOG_PROMOTION_RUN_STATUSES = {"applying", "succeeded", "failed", "blocked"}
CATALOG_PROMOTION_RUN_ITEM_KEYS = (
    "promotion_run_id",
    "etl_load_run_id",
    "source_filename",
    "profile_name",
    "status",
    "inserted_count",
    "updated_count",
    "unchanged_count",
    "blocked_count",
    "error_count",
    "warning_count",
    "failure_code",
    "safe_failure_message",
    "started_at",
    "completed_at",
    "created_at",
)
CATALOG_PROMOTION_RUN_LIST_KEYS = ("items", "total", "limit", "offset")
CATALOG_PROMOTION_RUN_DETAIL_KEYS = (
    *CATALOG_PROMOTION_RUN_ITEM_KEYS,
    "preview_hash",
    "preview_schema_version",
    "inspection_version",
)
CATALOG_PROMOTION_AUDIT_LIST_KEYS = ("items", "total", "limit", "offset")
CATALOG_PROMOTION_AUDIT_ITEM_KEYS = (
    "audit_id",
    "promotion_run_id",
    "catalog_product_id",
    "action",
    "changed_fields",
    "before_data",
    "after_data",
    "created_at",
)
CATALOG_PROMOTION_ROLLBACK_RUN_ITEM_KEYS = (
    "rollback_run_id",
    "target_promotion_run_id",
    "status",
    "restored_count",
    "deleted_count",
    "conflict_count",
    "failure_code",
    "safe_failure_message",
    "started_at",
    "completed_at",
    "created_at",
    "actor_username",
)
CATALOG_PROMOTION_ROLLBACK_RUN_LIST_KEYS = ("items", "total", "limit", "offset")
CATALOG_PROMOTION_ROLLBACK_RUN_DETAIL_KEYS = (
    *CATALOG_PROMOTION_ROLLBACK_RUN_ITEM_KEYS,
    "preview_hash",
    "preview_schema_version",
)
CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_KEYS = (
    "items",
    "total",
    "limit",
    "offset",
)
CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM_KEYS = (
    "rollback_change_id",
    "rollback_run_id",
    "original_audit_id",
    "catalog_product_id",
    "action",
    "changed_fields",
    "before_data",
    "after_data",
    "created_at",
)
ETL_WEB_RUN_RESPONSE_KEYS = (
    "etl_load_run_id",
    "created",
    "profile_name",
    "profile_version",
    "source_filename",
    "total_rows",
    "loaded_rows",
    "rejected_rows",
    "error_counts",
)
ETL_PROFILE_LIST_KEYS = ("items",)
ETL_PROFILE_ITEM_KEYS = ("id", "display_name")
ETL_PROFILE_DETAIL_RESPONSE_KEYS = (
    "id",
    "display_name",
    "profile_name",
    "profile_version",
    "source_columns",
    "required_source_columns",
    "defaults",
)
UNKNOWN_SIZE_TOKEN_REPORT_RESPONSE_KEYS = ("items",)
ETL_UNSUPPORTED_PROFILE_MESSAGE = "지원하지 않는 공급사 프로필입니다."
ETL_INACTIVE_PROFILE_MESSAGE = (
    "선택한 ETL 프로필이 비활성화되었습니다. 사용할 수 있는 프로필을 다시 선택하세요."
)
CATALOG_PROMOTION_NOT_FOUND_MESSAGE = "Promotion run not found."
CATALOG_PROMOTION_ROLLBACK_NOT_FOUND_MESSAGE = (
    "Rollback 실행 이력을 찾을 수 없습니다."
)
CATALOG_PROMOTION_STALE_MESSAGE = (
    "미리보기 이후 상품 데이터가 변경되었습니다. 미리보기를 다시 실행하세요."
)
CATALOG_PROMOTION_BLOCKED_MESSAGE = (
    "현재 ETL 적재 결과는 운영 상품에 반영할 수 없습니다."
)
CATALOG_PROMOTION_FAILED_MESSAGE = "운영 상품 반영 중 오류가 발생했습니다."
LOGIN_RESPONSE_KEYS = ("access_token", "token_type", "expires_in")
CURRENT_USER_RESPONSE_KEYS = ("username", "role")
AUTHENTICATION_REQUIRED_MESSAGE = "로그인이 필요합니다."
INVALID_TOKEN_MESSAGE = "인증 토큰이 유효하지 않습니다. 다시 로그인해 주세요."
INACTIVE_USER_MESSAGE = "비활성화된 계정입니다."
INVALID_CREDENTIALS_MESSAGE = "아이디 또는 비밀번호가 올바르지 않습니다."
INSUFFICIENT_ROLE_MESSAGE = "이 작업을 수행할 권한이 없습니다."


def _normalize_request_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    if REQUEST_ID_PATTERN.fullmatch(normalized_value) is None:
        return None
    return normalized_value


def _get_response_request_id(response: object | None) -> str | None:
    headers = getattr(response, "headers", None)
    get_header = getattr(headers, "get", None)
    if not callable(get_header):
        return None
    return _normalize_request_id(get_header("X-Request-ID"))


def _error_detail_payload(response: object) -> dict[str, Any] | None:
    """Return the dict body of an error response's "detail" field, or None."""
    try:
        payload = response.json()
    except (AttributeError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("detail"), dict):
        return None
    return payload["detail"]


def _normalize_optional_etl_filter(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def _validate_etl_pagination(limit: int, offset: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be greater than or equal to 0")


def _validate_positive_etl_int(value: object, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _invalid_etl_response() -> "CatalogGuardApiResponseError":
    return CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)


def _validate_etl_list_metadata(
    value: object,
    *,
    allow_limit_zero: bool = False,
) -> bool:
    if type(value) is not int:
        return False
    if value < 0:
        return False
    return allow_limit_zero or value > 0


def _validate_etl_load_item(item: object) -> bool:
    if not isinstance(item, dict) or any(key not in item for key in ETL_LOAD_ITEM_KEYS):
        return False
    if not (
        type(item["etl_load_run_id"]) is int
        and item["etl_load_run_id"] >= 1
        and isinstance(item["source_filename"], str)
        and isinstance(item["profile_name"], str)
        and isinstance(item["profile_version"], str)
        and type(item["loaded_rows"]) is int
        and item["loaded_rows"] >= 0
        and isinstance(item["created_at"], str)
    ):
        return False
    return _validate_etl_quality_counts(
        total_rows=item["total_rows"],
        loaded_rows=item["loaded_rows"],
        rejected_rows=item["rejected_rows"],
        error_counts=None,
    )


def _validate_etl_quality_counts(
    *,
    total_rows: object,
    loaded_rows: object,
    rejected_rows: object,
    error_counts: object,
    require_error_counts: bool = False,
) -> bool:
    if type(loaded_rows) is not int or loaded_rows < 0:
        return False
    quality_values = (total_rows, rejected_rows)
    if all(value is None for value in quality_values):
        return error_counts is None
    if any(value is None for value in quality_values):
        return False
    if any(type(value) is not int or value < 0 for value in quality_values):
        return False
    if total_rows != loaded_rows + rejected_rows:
        return False
    if error_counts is None:
        return not require_error_counts
    if not isinstance(error_counts, dict):
        return False
    for key, value in error_counts.items():
        if not isinstance(key, str) or not key.strip():
            return False
        if type(value) is not int or value < 1:
            return False
    return True


def _validate_etl_load_list_response(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in ETL_LOAD_LIST_RESPONSE_KEYS)
        or not isinstance(data["items"], list)
        or not _validate_etl_list_metadata(data["total"], allow_limit_zero=True)
        or not _validate_etl_list_metadata(data["limit"])
        or not _validate_etl_list_metadata(data["offset"], allow_limit_zero=True)
        or any(not _validate_etl_load_item(item) for item in data["items"])
    ):
        raise _invalid_etl_response()


def _validate_etl_load_quality_summary_response(data: dict[str, Any]) -> None:
    integer_fields = (
        "batch_count",
        "quality_available_batch_count",
        "quality_unavailable_batch_count",
        "total_rows",
        "loaded_rows",
        "rejected_rows",
    )
    rejection_rate = data.get("rejection_rate")
    if (
        any(key not in data for key in ETL_LOAD_QUALITY_SUMMARY_RESPONSE_KEYS)
        or any(
            type(data[field]) is not int or data[field] < 0
            for field in integer_fields
        )
        or type(rejection_rate) not in (int, float)
        or rejection_rate < 0
        or data["quality_available_batch_count"]
        + data["quality_unavailable_batch_count"]
        != data["batch_count"]
    ):
        raise _invalid_etl_response()


def _validate_etl_load_quality_trend_response(data: dict[str, Any]) -> None:
    items = data.get("items")
    if (
        any(key not in data for key in ETL_LOAD_QUALITY_TREND_RESPONSE_KEYS)
        or not isinstance(items, list)
        or any(not _validate_etl_load_quality_trend_item(item) for item in items)
    ):
        raise _invalid_etl_response()


def _validate_etl_load_quality_trend_item(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in ETL_LOAD_QUALITY_TREND_ITEM_KEYS
    ):
        return False
    if not (
        type(item["etl_load_run_id"]) is int
        and item["etl_load_run_id"] >= 1
        and isinstance(item["created_at"], str)
        and type(item["rejection_rate"]) in (int, float)
        and item["rejection_rate"] >= 0
    ):
        return False
    return _validate_etl_quality_counts(
        total_rows=item["total_rows"],
        loaded_rows=item["loaded_rows"],
        rejected_rows=item["rejected_rows"],
        error_counts=None,
    )


def _validate_etl_quality_observability_profile_list_response(
    data: dict[str, Any],
) -> None:
    """Reject a supplier list that is not a deduplicated, ascending set of names.

    이 목록은 그대로 selectbox가 되고, 고른 값이 비교 조회의 정확 일치 입력이 됩니다.
    중복이 있으면 같은 공급사가 두 번 보이고, 정렬이 깨지면 화면마다 순서가 달라지므로
    서버 계약을 여기서 확인합니다.
    """
    items = data.get("items")
    if any(
        key not in data for key in ETL_QUALITY_OBSERVABILITY_PROFILE_LIST_KEYS
    ) or not isinstance(items, list):
        raise _invalid_etl_response()

    profile_names: list[str] = []
    for item in items:
        if not isinstance(item, dict) or any(
            key not in item for key in ETL_QUALITY_OBSERVABILITY_PROFILE_KEYS
        ):
            raise _invalid_etl_response()
        profile_name = item["profile_name"]
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise _invalid_etl_response()
        profile_names.append(profile_name)

    if len(set(profile_names)) != len(profile_names):
        raise _invalid_etl_response()
    if profile_names != sorted(profile_names):
        raise _invalid_etl_response()


def _validate_etl_quality_observability_error_code(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in ETL_QUALITY_OBSERVABILITY_ERROR_CODE_KEYS
    ):
        return False
    return (
        isinstance(item["error_code"], str)
        and bool(item["error_code"].strip())
        and type(item["total_count"]) is int
        and item["total_count"] >= 1
        and type(item["affected_batch_count"]) is int
        and item["affected_batch_count"] >= 1
        # 한 배치에서 같은 코드가 두 번 집계될 수는 없으므로, 배치 수는 합계를 넘지 못합니다.
        and item["affected_batch_count"] <= item["total_count"]
    )


def _parse_etl_created_at(value: object) -> datetime | None:
    """Parse an API created_at string, or return None when it is not usable."""
    if not isinstance(value, str):
        return None
    # API는 UTC를 'Z'로 끝내는데, fromisoformat은 이 표기를 오래된 Python에서 읽지 못합니다.
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    # naive와 aware datetime을 그대로 비교하면 TypeError가 나므로 시간대를 채워 둡니다.
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _is_etl_quality_batches_in_chronological_order(
    recent_batches: list[dict[str, Any]],
) -> bool:
    """Check the server contract that recent_batches runs oldest -> newest.

    서버 service는 created_at ASC, 같은 시각이면 id ASC로 정렬해서 보냅니다. 순서가
    뒤집힌 응답을 그대로 그리면 "직전"과 "최신"이 바뀐 화면이 되므로 여기서 막습니다.
    """
    sort_keys = []
    for item in recent_batches:
        created_at = _parse_etl_created_at(item["created_at"])
        if created_at is None:
            return False
        sort_keys.append((created_at, item["etl_load_run_id"]))
    return all(
        earlier < later for earlier, later in zip(sort_keys, sort_keys[1:])
    )


def _validate_etl_quality_observability_response(data: dict[str, Any]) -> None:
    """Reject observability payloads whose numbers contradict each other.

    서버 응답을 그대로 믿으면 direction과 delta가 서로 반대인 화면을 그리게 됩니다.
    여기서는 필드 타입뿐 아니라 값들 사이의 일관성(비교 대상 유무, 방향과 부호,
    배치 수와 목록 길이, 그리고 latest/previous가 실제로 recent_batches의 마지막 두
    배치인지)까지 확인합니다.
    """
    if any(key not in data for key in ETL_QUALITY_OBSERVABILITY_RESPONSE_KEYS):
        raise _invalid_etl_response()

    profile_name = data["profile_name"]
    limit = data["limit"]
    batch_count = data["batch_count"]
    latest_batch = data["latest_batch"]
    previous_batch = data["previous_batch"]
    delta = data["rejection_rate_delta"]
    direction = data["direction"]
    error_codes = data["error_codes"]
    recent_batches = data["recent_batches"]

    if (
        not isinstance(profile_name, str)
        or not profile_name.strip()
        or type(limit) is not int
        or not ETL_QUALITY_OBSERVABILITY_MIN_LIMIT
        <= limit
        <= ETL_QUALITY_OBSERVABILITY_MAX_LIMIT
        or type(batch_count) is not int
        or batch_count < 0
        or direction not in ETL_QUALITY_OBSERVABILITY_DIRECTIONS
        or not isinstance(error_codes, list)
        or not isinstance(recent_batches, list)
        or any(
            not _validate_etl_quality_observability_error_code(item)
            for item in error_codes
        )
        or any(
            not _validate_etl_load_quality_trend_item(item) for item in recent_batches
        )
        or len(recent_batches) != batch_count
        or batch_count > limit
    ):
        raise _invalid_etl_response()

    for batch in (latest_batch, previous_batch):
        if batch is not None and not _validate_etl_load_quality_trend_item(batch):
            raise _invalid_etl_response()

    # 비교할 배치가 없으면 변화량과 방향도 반드시 "없음"이어야 합니다.
    if (previous_batch is None) != (delta is None):
        raise _invalid_etl_response()
    if (previous_batch is None) != (direction == "no_baseline"):
        raise _invalid_etl_response()
    if latest_batch is None and previous_batch is not None:
        raise _invalid_etl_response()
    if (latest_batch is None) != (batch_count == 0):
        raise _invalid_etl_response()
    if any(item["affected_batch_count"] > batch_count for item in error_codes):
        raise _invalid_etl_response()
    if not _is_etl_quality_batches_in_chronological_order(recent_batches):
        raise _invalid_etl_response()

    # latest/previous는 recent_batches와 다른 출처가 아니라 그 목록의 마지막 두 배치입니다.
    # 값이 어긋나면 요약 지표와 아래 목록이 서로 다른 배치를 가리키게 됩니다.
    if latest_batch != (recent_batches[-1] if batch_count >= 1 else None):
        raise _invalid_etl_response()
    if previous_batch != (recent_batches[-2] if batch_count >= 2 else None):
        raise _invalid_etl_response()

    if previous_batch is None:
        return
    if type(delta) not in (int, float):
        raise _invalid_etl_response()
    expected_delta = round(
        latest_batch["rejection_rate"] - previous_batch["rejection_rate"], 2
    )
    if round(float(delta), 2) != expected_delta:
        raise _invalid_etl_response()
    if (
        (direction == "improved" and delta >= 0)
        or (direction == "worsened" and delta <= 0)
        or (direction == "unchanged" and delta != 0)
    ):
        raise _invalid_etl_response()


def _is_valid_etl_profile_detail_response(data: dict[str, Any]) -> bool:
    text_fields = ("id", "display_name", "profile_name", "profile_version")
    source_columns = data.get("source_columns")
    required_source_columns = data.get("required_source_columns")
    defaults = data.get("defaults")
    return (
        all(isinstance(data.get(field), str) and data[field].strip() for field in text_fields)
        and isinstance(source_columns, dict)
        and bool(source_columns)
        and all(
            isinstance(source, str)
            and source.strip()
            and isinstance(targets, list)
            and bool(targets)
            and all(isinstance(target, str) and target.strip() for target in targets)
            for source, targets in source_columns.items()
        )
        and isinstance(required_source_columns, list)
        and all(
            isinstance(source, str) and source.strip()
            for source in required_source_columns
        )
        and all(source in source_columns for source in required_source_columns)
        and isinstance(defaults, dict)
        and all(
            isinstance(column, str)
            and column.strip()
            and isinstance(value, str)
            for column, value in defaults.items()
        )
    )


def _validate_etl_product_item(item: object) -> bool:
    if not isinstance(item, dict) or any(key not in item for key in ETL_PRODUCT_KEYS):
        return False
    nullable_text_fields = ("description", "seller")
    return (
        type(item["staging_product_id"]) is int
        and item["staging_product_id"] >= 1
        and all(isinstance(item[field], str) for field in (
            "product_group_id",
            "product_id",
            "product_name",
            "category",
            "color",
            "size",
            "image_path",
            "created_at",
        ))
        and type(item["stock"]) is int
        and type(item["price"]) is int
        and (item["sale_price"] is None or type(item["sale_price"]) is int)
        and all(item[field] is None or isinstance(item[field], str) for field in nullable_text_fields)
    )


def _validate_etl_product_list(data: object) -> bool:
    if not isinstance(data, dict) or any(key not in data for key in ETL_PRODUCT_LIST_KEYS):
        return False
    return (
        isinstance(data["items"], list)
        and _validate_etl_list_metadata(data["total"], allow_limit_zero=True)
        and _validate_etl_list_metadata(data["limit"])
        and _validate_etl_list_metadata(data["offset"], allow_limit_zero=True)
        and all(_validate_etl_product_item(item) for item in data["items"])
    )


def _validate_etl_rejection_item(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in ETL_REJECTION_ITEM_KEYS
    ):
        return False
    if (
        type(item["rejected_row_id"]) is not int
        or item["rejected_row_id"] < 1
        or type(item["source_row_number"]) is not int
        or item["source_row_number"] < 2
        or not isinstance(item["errors"], list)
        or not item["errors"]
        or not isinstance(item["masked_source_data"], dict)
        or not isinstance(item["created_at"], str)
    ):
        return False
    if any(
        not isinstance(error, dict)
        or any(key not in error for key in ETL_REJECTION_ERROR_KEYS)
        or any(
            not isinstance(error[key], str) or not error[key].strip()
            for key in ETL_REJECTION_ERROR_KEYS
        )
        for error in item["errors"]
    ):
        return False
    return all(
        isinstance(key, str)
        and key.strip()
        and isinstance(value, str)
        for key, value in item["masked_source_data"].items()
    )


def _validate_etl_rejection_list_response(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in ETL_REJECTION_LIST_KEYS)
        or type(data["available"]) is not bool
        or not isinstance(data["items"], list)
        or not _validate_etl_list_metadata(data["total"], allow_limit_zero=True)
        or not _validate_etl_list_metadata(data["limit"])
        or not _validate_etl_list_metadata(data["offset"], allow_limit_zero=True)
        or any(not _validate_etl_rejection_item(item) for item in data["items"])
    ):
        raise _invalid_etl_response()
    if not data["available"] and (data["items"] or data["total"] != 0):
        raise _invalid_etl_response()


def _validate_etl_load_detail_response(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in ETL_LOAD_DETAIL_RESPONSE_KEYS)
        or type(data["etl_load_run_id"]) is not int
        or data["etl_load_run_id"] < 1
        or not isinstance(data["source_filename"], str)
        or not isinstance(data["profile_name"], str)
        or not isinstance(data["profile_version"], str)
        or not isinstance(data["input_file_sha256"], str)
        or ETL_SHA256_PATTERN.fullmatch(data["input_file_sha256"]) is None
        or not isinstance(data["output_file_sha256"], str)
        or ETL_SHA256_PATTERN.fullmatch(data["output_file_sha256"]) is None
        or type(data["loaded_rows"]) is not int
        or data["loaded_rows"] < 0
        or not isinstance(data["created_at"], str)
        or not _validate_etl_quality_counts(
            total_rows=data["total_rows"],
            loaded_rows=data["loaded_rows"],
            rejected_rows=data["rejected_rows"],
            error_counts=data["error_counts"],
            require_error_counts=True,
        )
        or not _validate_etl_product_list(data["products"])
    ):
        raise _invalid_etl_response()


def _validate_unknown_size_token_report_response(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in UNKNOWN_SIZE_TOKEN_REPORT_RESPONSE_KEYS)
        or not isinstance(data["items"], list)
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("token"), str)
            or not item["token"].strip()
            or type(item.get("count")) is not int
            or item["count"] < 1
            for item in data["items"]
        )
    ):
        raise _invalid_etl_response()


def _is_catalog_promotion_value(value: object) -> bool:
    return value is None or isinstance(value, str) or type(value) is int


def _validate_catalog_promotion_product_data(data: object) -> bool:
    if not isinstance(data, dict) or any(
        key not in data for key in CATALOG_PROMOTION_PRODUCT_DATA_KEYS
    ):
        return False
    text_fields = (
        "external_product_id",
        "product_group_id",
        "product_name",
        "category",
        "color",
        "size",
        "image_path",
    )
    nullable_text_fields = ("description", "seller")
    return (
        all(isinstance(data[field], str) for field in text_fields)
        and type(data["stock"]) is int
        and type(data["price"]) is int
        and (data["sale_price"] is None or type(data["sale_price"]) is int)
        and all(
            data[field] is None or isinstance(data[field], str)
            for field in nullable_text_fields
        )
    )


def _validate_catalog_promotion_blocked_reason(reason: object) -> bool:
    required_keys = (
        "code",
        "message",
        "supplier_key",
        "external_product_id",
        "staging_product_ids",
    )
    if not isinstance(reason, dict) or any(key not in reason for key in required_keys):
        return False
    return (
        isinstance(reason["code"], str)
        and bool(reason["code"].strip())
        and isinstance(reason["message"], str)
        and bool(reason["message"].strip())
        and (
            reason["supplier_key"] is None
            or isinstance(reason["supplier_key"], str)
        )
        and (
            reason["external_product_id"] is None
            or isinstance(reason["external_product_id"], str)
        )
        and isinstance(reason["staging_product_ids"], list)
        and all(
            type(staging_id) is int and staging_id > 0
            for staging_id in reason["staging_product_ids"]
        )
    )


def _validate_catalog_promotion_preview_item(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in CATALOG_PROMOTION_PREVIEW_ITEM_KEYS
    ):
        return False
    changed_fields = item["changed_fields"]
    if not isinstance(changed_fields, dict) or any(
        not isinstance(field_name, str)
        or not field_name
        or not isinstance(change, dict)
        or "before" not in change
        or "after" not in change
        or not _is_catalog_promotion_value(change["before"])
        or not _is_catalog_promotion_value(change["after"])
        for field_name, change in changed_fields.items()
    ):
        return False
    action = item["action"]
    return (
        isinstance(item["supplier_key"], str)
        and isinstance(item["external_product_id"], str)
        and action in {"insert", "update", "unchanged"}
        and (
            item["before_data"] is None
            or _validate_catalog_promotion_product_data(item["before_data"])
        )
        and _validate_catalog_promotion_product_data(item["after_data"])
        and (action != "update" or bool(changed_fields))
        and (action != "unchanged" or not changed_fields)
    )


def _validate_catalog_reconciliation_item(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in CATALOG_RECONCILIATION_ITEM_KEYS
    ):
        return False
    external_product_id = item["external_product_id"]
    status = item["status"]
    changed_fields = item["changed_fields"]
    if (
        not isinstance(external_product_id, str)
        or not external_product_id
        or status not in CATALOG_RECONCILIATION_STATUSES
        or not isinstance(changed_fields, dict)
    ):
        return False
    for change in changed_fields.values():
        if not isinstance(change, dict) or {"before", "after"} - set(change):
            return False
    # changed만 변경 필드를 가집니다. 다른 상태에 변경 필드가 오면 서버 계약이 깨진 것입니다.
    return bool(changed_fields) == (status == "changed")


def _validate_catalog_reconciliation_response(data: dict[str, Any]) -> None:
    if any(key not in data for key in CATALOG_RECONCILIATION_RESPONSE_KEYS):
        raise _invalid_etl_response()
    count_fields = (
        "new_count",
        "changed_count",
        "unchanged_count",
        "not_observed_in_batch_count",
    )
    items = data["items"]
    field_change_counts = data["field_change_counts"]
    # loaded_rows는 서버에서 NOT NULL입니다. total_rows/rejected_rows는 품질 요약
    # 저장 이전 legacy 배치에서 null일 수 있으므로 None을 허용하되, 0으로 바꾸지
    # 않습니다. "거부 행이 없었다"와 "알 수 없다"는 다른 사실입니다.
    nullable_quality_fields = ("total_rows", "rejected_rows")
    if (
        type(data["etl_load_run_id"]) is not int
        or data["etl_load_run_id"] < 1
        or not isinstance(data["supplier_key"], str)
        or not data["supplier_key"]
        or type(data["loaded_rows"]) is not int
        or data["loaded_rows"] < 0
        or any(
            data[field] is not None
            and (type(data[field]) is not int or data[field] < 0)
            for field in nullable_quality_fields
        )
        or any(type(data[field]) is not int or data[field] < 0 for field in count_fields)
        or not isinstance(field_change_counts, dict)
        or any(
            not isinstance(field_name, str)
            or type(count) is not int
            or count < 1
            for field_name, count in field_change_counts.items()
        )
        or not isinstance(items, list)
        or any(not _validate_catalog_reconciliation_item(item) for item in items)
        or not _validate_etl_list_metadata(data["total"], allow_limit_zero=True)
        or not _validate_etl_list_metadata(data["limit"])
        or not _validate_etl_list_metadata(data["offset"], allow_limit_zero=True)
        or len(items) > data["limit"]
        or data["total"]
        != data["new_count"]
        + data["changed_count"]
        + data["unchanged_count"]
        + data["not_observed_in_batch_count"]
    ):
        raise _invalid_etl_response()


def _validate_catalog_promotion_preview_response(data: dict[str, Any]) -> None:
    if any(key not in data for key in CATALOG_PROMOTION_PREVIEW_RESPONSE_KEYS):
        raise _invalid_etl_response()
    count_fields = (
        "insert_count",
        "update_count",
        "unchanged_count",
        "error_count",
        "warning_count",
    )
    preview_hash = data["preview_hash"]
    items = data["items"]
    if (
        type(data["etl_load_run_id"]) is not int
        or data["etl_load_run_id"] < 1
        or not isinstance(data["supplier_key"], str)
        or not isinstance(data["inspection_version"], str)
        or type(data["preview_schema_version"]) is not int
        or data["preview_schema_version"] < 1
        or (
            preview_hash is not None
            and (
                not isinstance(preview_hash, str)
                or CATALOG_PROMOTION_SHA256_PATTERN.fullmatch(preview_hash) is None
            )
        )
        or type(data["promotion_eligible"]) is not bool
        or not isinstance(data["blocked_reasons"], list)
        or any(
            not _validate_catalog_promotion_blocked_reason(reason)
            for reason in data["blocked_reasons"]
        )
        or any(type(data[field]) is not int or data[field] < 0 for field in count_fields)
        or not isinstance(items, list)
        or any(not _validate_catalog_promotion_preview_item(item) for item in items)
        or (
            data["promotion_eligible"]
            and (
                preview_hash is None
                or bool(data["blocked_reasons"])
                or data["insert_count"] + data["update_count"] + data["unchanged_count"]
                != len(items)
            )
        )
    ):
        raise _invalid_etl_response()


def _validate_catalog_promotion_response(data: dict[str, Any]) -> None:
    if any(key not in data for key in CATALOG_PROMOTION_RESPONSE_KEYS):
        raise _invalid_etl_response()
    count_fields = (
        "inserted_count",
        "updated_count",
        "unchanged_count",
        "blocked_count",
        "error_count",
        "warning_count",
    )
    if (
        type(data["promotion_run_id"]) is not int
        or data["promotion_run_id"] < 1
        or type(data["etl_load_run_id"]) is not int
        or data["etl_load_run_id"] < 1
        or data["status"] != "succeeded"
        or type(data["created"]) is not bool
        or not isinstance(data["preview_hash"], str)
        or CATALOG_PROMOTION_SHA256_PATTERN.fullmatch(data["preview_hash"]) is None
        or type(data["preview_schema_version"]) is not int
        or data["preview_schema_version"] < 1
        or not isinstance(data["inspection_version"], str)
        or any(type(data[field]) is not int or data[field] < 0 for field in count_fields)
        or not isinstance(data["started_at"], str)
        or not isinstance(data["completed_at"], str)
    ):
        raise _invalid_etl_response()


def _validate_catalog_promotion_run_item(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in CATALOG_PROMOTION_RUN_ITEM_KEYS
    ):
        return False
    count_fields = (
        "inserted_count",
        "updated_count",
        "unchanged_count",
        "blocked_count",
        "error_count",
        "warning_count",
    )
    optional_text_fields = ("failure_code", "safe_failure_message")
    optional_datetime_fields = ("started_at", "completed_at")
    return (
        type(item["promotion_run_id"]) is int
        and item["promotion_run_id"] > 0
        and type(item["etl_load_run_id"]) is int
        and item["etl_load_run_id"] > 0
        and isinstance(item["source_filename"], str)
        and isinstance(item["profile_name"], str)
        and item["status"] in CATALOG_PROMOTION_RUN_STATUSES
        and all(type(item[field]) is int and item[field] >= 0 for field in count_fields)
        and all(
            item[field] is None or isinstance(item[field], str)
            for field in optional_text_fields
        )
        and all(
            item[field] is None or isinstance(item[field], str)
            for field in optional_datetime_fields
        )
        and isinstance(item["created_at"], str)
    )


def _validate_catalog_promotion_run_list(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in CATALOG_PROMOTION_RUN_LIST_KEYS)
        or not isinstance(data["items"], list)
        or not _validate_etl_list_metadata(data["total"], allow_limit_zero=True)
        or not _validate_etl_list_metadata(data["limit"])
        or not _validate_etl_list_metadata(data["offset"], allow_limit_zero=True)
        or any(
            not _validate_catalog_promotion_run_item(item)
            for item in data["items"]
        )
    ):
        raise _invalid_etl_response()


def _validate_catalog_promotion_run_detail(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in CATALOG_PROMOTION_RUN_DETAIL_KEYS)
        or not _validate_catalog_promotion_run_item(data)
        or (
            data["preview_hash"] is not None
            and (
                not isinstance(data["preview_hash"], str)
                or CATALOG_PROMOTION_SHA256_PATTERN.fullmatch(data["preview_hash"])
                is None
            )
        )
        or (
            data["preview_schema_version"] is not None
            and not isinstance(data["preview_schema_version"], str)
        )
        or (
            data["inspection_version"] is not None
            and not isinstance(data["inspection_version"], str)
        )
    ):
        raise _invalid_etl_response()


def _validate_catalog_promotion_audit_item(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in CATALOG_PROMOTION_AUDIT_ITEM_KEYS
    ):
        return False
    return (
        type(item["audit_id"]) is int
        and item["audit_id"] > 0
        and type(item["promotion_run_id"]) is int
        and item["promotion_run_id"] > 0
        and type(item["catalog_product_id"]) is int
        and item["catalog_product_id"] > 0
        and item["action"] in {"insert", "update"}
        and isinstance(item["changed_fields"], dict)
        and bool(item["changed_fields"])
        and all(
            isinstance(field_name, str)
            and field_name
            and isinstance(change, dict)
            and "before" in change
            and "after" in change
            for field_name, change in item["changed_fields"].items()
        )
        and (item["before_data"] is None or isinstance(item["before_data"], dict))
        and isinstance(item["after_data"], dict)
        and isinstance(item["created_at"], str)
    )


def _validate_catalog_promotion_audit_list(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in CATALOG_PROMOTION_AUDIT_LIST_KEYS)
        or not isinstance(data["items"], list)
        or not _validate_etl_list_metadata(data["total"], allow_limit_zero=True)
        or not _validate_etl_list_metadata(data["limit"])
        or not _validate_etl_list_metadata(data["offset"], allow_limit_zero=True)
        or any(
            not _validate_catalog_promotion_audit_item(item)
            for item in data["items"]
        )
    ):
        raise _invalid_etl_response()


def _validate_catalog_promotion_rollback_run_item(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in CATALOG_PROMOTION_ROLLBACK_RUN_ITEM_KEYS
    ):
        return False
    count_fields = ("restored_count", "deleted_count", "conflict_count")
    optional_text_fields = (
        "failure_code",
        "safe_failure_message",
        "started_at",
        "completed_at",
        "actor_username",
    )
    return (
        type(item["rollback_run_id"]) is int
        and item["rollback_run_id"] > 0
        and type(item["target_promotion_run_id"]) is int
        and item["target_promotion_run_id"] > 0
        and item["status"] in CATALOG_PROMOTION_RUN_STATUSES
        and all(type(item[field]) is int and item[field] >= 0 for field in count_fields)
        and all(
            item[field] is None or isinstance(item[field], str)
            for field in optional_text_fields
        )
        and isinstance(item["created_at"], str)
    )


def _validate_catalog_promotion_rollback_run_list(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in CATALOG_PROMOTION_ROLLBACK_RUN_LIST_KEYS)
        or not isinstance(data["items"], list)
        or not _validate_etl_list_metadata(data["total"], allow_limit_zero=True)
        or not _validate_etl_list_metadata(data["limit"])
        or not _validate_etl_list_metadata(data["offset"], allow_limit_zero=True)
        or any(
            not _validate_catalog_promotion_rollback_run_item(item)
            for item in data["items"]
        )
    ):
        raise _invalid_etl_response()


def _validate_catalog_promotion_rollback_run_detail(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in CATALOG_PROMOTION_ROLLBACK_RUN_DETAIL_KEYS)
        or not _validate_catalog_promotion_rollback_run_item(data)
        or (
            data["preview_hash"] is not None
            and (
                not isinstance(data["preview_hash"], str)
                or CATALOG_PROMOTION_SHA256_PATTERN.fullmatch(data["preview_hash"])
                is None
            )
        )
        or (
            data["preview_schema_version"] is not None
            and not isinstance(data["preview_schema_version"], str)
        )
    ):
        raise _invalid_etl_response()


def _validate_catalog_promotion_rollback_change_item(item: object) -> bool:
    if not isinstance(item, dict) or any(
        key not in item for key in CATALOG_PROMOTION_ROLLBACK_CHANGE_ITEM_KEYS
    ):
        return False
    action = item["action"]
    after_data = item["after_data"]
    return (
        type(item["rollback_change_id"]) is int
        and item["rollback_change_id"] > 0
        and type(item["rollback_run_id"]) is int
        and item["rollback_run_id"] > 0
        and type(item["original_audit_id"]) is int
        and item["original_audit_id"] > 0
        and type(item["catalog_product_id"]) is int
        and item["catalog_product_id"] > 0
        and action in {"delete", "restore"}
        and isinstance(item["changed_fields"], dict)
        and bool(item["changed_fields"])
        and isinstance(item["before_data"], dict)
        and (
            (action == "delete" and after_data is None)
            or (action == "restore" and isinstance(after_data, dict))
        )
        and isinstance(item["created_at"], str)
    )


def _validate_catalog_promotion_rollback_change_list(data: dict[str, Any]) -> None:
    if (
        any(key not in data for key in CATALOG_PROMOTION_ROLLBACK_CHANGE_LIST_KEYS)
        or not isinstance(data["items"], list)
        or not _validate_etl_list_metadata(data["total"], allow_limit_zero=True)
        or not _validate_etl_list_metadata(data["limit"])
        or not _validate_etl_list_metadata(data["offset"], allow_limit_zero=True)
        or any(
            not _validate_catalog_promotion_rollback_change_item(item)
            for item in data["items"]
        )
    ):
        raise _invalid_etl_response()


class CatalogGuardApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.request_id = _normalize_request_id(request_id)


class CatalogGuardApiConfigurationError(CatalogGuardApiError):
    pass


class CatalogGuardApiConnectionError(CatalogGuardApiError):
    pass


class CatalogGuardApiTimeoutError(CatalogGuardApiError):
    pass


class InspectionNotFoundError(CatalogGuardApiError):
    pass


class ETLLoadNotFoundError(CatalogGuardApiError):
    pass


class ETLProfileNotFoundError(CatalogGuardApiError):
    pass


class CatalogPromotionNotFoundError(CatalogGuardApiError):
    pass


class CatalogPromotionRollbackNotFoundError(CatalogGuardApiError):
    pass


class CatalogGuardApiResponseError(CatalogGuardApiError):
    pass


class CatalogPromotionApiError(CatalogGuardApiResponseError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        promotion_run_id: int | None = None,
        blocked_reasons: list[dict[str, Any]] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.code = code
        self.promotion_run_id = promotion_run_id
        self.blocked_reasons = list(blocked_reasons or [])


class CatalogPromotionPreviewStaleError(CatalogPromotionApiError):
    pass


class CatalogPromotionBlockedError(CatalogPromotionApiError):
    pass


class CatalogPromotionFailedError(CatalogPromotionApiError):
    pass


class ETLWebRunApiError(CatalogGuardApiResponseError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.code = code


class ETLUnsupportedProfileError(ETLWebRunApiError):
    pass


class ETLProfileInactiveError(ETLWebRunApiError):
    """서버가 409 inactive_profile을 보냈을 때 쓰는 전용 오류입니다.

    ETLUnsupportedProfileError와 형제 관계로 둡니다. "없는 프로필"과 "있지만 비활성인
    프로필"은 사용자가 해야 할 일이 다르므로(오타 수정 vs 다른 프로필 선택) 한쪽이
    다른 쪽을 상속하면 안 됩니다. 서버 etl.profile_loader의 같은 이름 예외와는 다른
    module이고, 이쪽은 HTTP 응답을 표현합니다.
    """


class ETLInvalidUploadError(ETLWebRunApiError):
    pass


class CatalogGuardApiAuthenticationError(CatalogGuardApiResponseError):
    """HTTP 401: 로그인되지 않았거나 access token이 유효하지 않습니다."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.code = code


class InvalidCredentialsError(CatalogGuardApiAuthenticationError):
    """로그인 시 아이디/비밀번호가 올바르지 않거나 계정이 비활성 상태입니다."""


class CatalogGuardApiAuthorizationError(CatalogGuardApiResponseError):
    """HTTP 403: 로그인은 됐지만 현재 역할로는 허용되지 않는 작업입니다."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.code = code


class CatalogGuardApiClient:
    # Streamlit 화면은 이 클라이언트만 알면 되고, requests 예외나 HTTP 상태 코드는 여기서 숨깁니다.
    # 그래서 app.py는 사용자에게 보여 줄 메시지만 선택하면 됩니다.
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = CATALOGGUARD_API_DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
        access_token: str | None = None,
    ):
        normalized_base_url = str(base_url).strip().rstrip("/")
        if not normalized_base_url:
            raise CatalogGuardApiConfigurationError(CONFIGURATION_ERROR_MESSAGE)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._base_url = normalized_base_url
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        if access_token:
            self.set_access_token(access_token)

    def set_access_token(self, access_token: str | None) -> None:
        # 매 호출마다 인자로 넘기지 않고, 세션 헤더에 한 번 설정해 이후 모든 요청에 자동으로 붙습니다.
        if access_token:
            self._session.headers["Authorization"] = f"Bearer {access_token}"
        else:
            self._session.headers.pop("Authorization", None)

    def login(self, *, username: str, password: str) -> dict[str, Any]:
        data = self._post_json(
            "/api/v1/auth/login",
            json_body={"username": username, "password": password},
        )
        self._validate_response_keys(data, LOGIN_RESPONSE_KEYS)
        return data

    def get_current_user(self) -> dict[str, Any]:
        data = self._get_json("/api/v1/auth/me")
        self._validate_response_keys(data, CURRENT_USER_RESPONSE_KEYS)
        return data

    def list_inspections(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        filename: str | None = None,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        # filename은 비어 있으면 보내지 않아 기존 전체 목록 API와 똑같이 동작합니다.
        params: dict[str, int | str] = {"limit": limit, "offset": offset}
        normalized_filename = "" if filename is None else str(filename).strip()
        if len(normalized_filename) > 100:
            raise ValueError("filename must be 100 characters or fewer")
        if normalized_filename:
            params["filename"] = normalized_filename

        normalized_start_date = self._normalize_date_param(start_date)
        normalized_end_date = self._normalize_date_param(end_date)
        if normalized_start_date:
            params["start_date"] = normalized_start_date
        if normalized_end_date:
            params["end_date"] = normalized_end_date

        normalized_status = self._normalize_status_param(status)
        if normalized_status:
            params["status"] = normalized_status

        data = self._get_json(
            "/api/v1/inspections",
            params=params,
        )
        self._validate_response_keys(data, LIST_RESPONSE_KEYS)
        return data

    def create_inspection(
        self,
        *,
        source_filename: str,
        file_content: bytes,
        content_type: str = "text/csv",
    ) -> dict[str, Any]:
        # 파일 검수 저장 API는 multipart/form-data를 사용합니다.
        # 서버가 직접 SHA-256을 계산해야 하므로 클라이언트는 해시를 보내지 않습니다.
        normalized_filename = str(source_filename).strip()
        if not normalized_filename:
            raise ValueError("source_filename must not be empty")
        if not file_content:
            raise ValueError("file_content must not be empty")

        data = self._post_json(
            "/api/v1/inspections",
            files={
                "file": (
                    normalized_filename,
                    file_content,
                    content_type or "text/csv",
                )
            },
        )
        self._validate_response_keys(data, CREATE_RESPONSE_KEYS)
        return self._normalize_create_response(data)

    def run_etl_load(
        self,
        *,
        profile_id: str,
        source_filename: str,
        file_content: bytes,
        content_type: str = "text/csv",
    ) -> dict[str, Any]:
        # 공급사 CSV와 profile_id를 함께 업로드해 기존 ETL Pipeline/staging 적재를
        # 실행합니다. profile_id는 서버 allowlist의 키일 뿐, 파일 경로가 아닙니다.
        normalized_profile_id = str(profile_id).strip()
        if not normalized_profile_id:
            raise ValueError("profile_id must not be empty")
        normalized_filename = str(source_filename).strip()
        if not normalized_filename:
            raise ValueError("source_filename must not be empty")
        if not file_content:
            raise ValueError("file_content must not be empty")

        data = self._post_json(
            "/api/v1/etl-loads",
            files={
                "file": (
                    normalized_filename,
                    file_content,
                    content_type or "text/csv",
                )
            },
            data={"profile_id": normalized_profile_id},
            map_etl_run_errors=True,
        )
        self._validate_response_keys(data, ETL_WEB_RUN_RESPONSE_KEYS)
        return data

    def list_etl_profiles(self) -> dict[str, Any]:
        data = self._get_json("/api/v1/etl-profiles")
        self._validate_response_keys(data, ETL_PROFILE_LIST_KEYS)
        items = data.get("items")
        if not isinstance(items, list) or any(
            not isinstance(item, dict)
            or any(key not in item for key in ETL_PROFILE_ITEM_KEYS)
            for item in items
        ):
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        return data

    def get_etl_profile_detail(self, profile_id: str) -> dict[str, Any]:
        normalized_profile_id = str(profile_id).strip()
        if not normalized_profile_id:
            raise ValueError("profile_id must not be empty")

        data = self._get_json(
            f"/api/v1/etl-profiles/{quote(normalized_profile_id, safe='')}",
            raise_not_found=True,
            not_found_error=ETLProfileNotFoundError,
            not_found_message="ETL 프로필을 찾을 수 없습니다.",
            # 이 endpoint만 409 inactive_profile을 전용 오류로 구분합니다.
            map_inactive_profile=True,
        )
        self._validate_response_keys(data, ETL_PROFILE_DETAIL_RESPONSE_KEYS)
        if not _is_valid_etl_profile_detail_response(data):
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        return data

    def submit_inspection_job(
        self,
        *,
        source_filename: str,
        file_content: bytes,
        content_type: str = "text/csv",
    ) -> dict[str, Any]:
        normalized_filename = str(source_filename).strip()
        if not normalized_filename:
            raise ValueError("source_filename must not be empty")
        if not file_content:
            raise ValueError("file_content must not be empty")

        data = self._post_json(
            "/api/v1/inspection-jobs",
            files={
                "file": (
                    normalized_filename,
                    file_content,
                    content_type or "text/csv",
                )
            },
        )
        self._validate_response_keys(data, JOB_SUBMISSION_RESPONSE_KEYS)
        normalized_job_id = self._normalize_job_id(data["job_id"])
        if (
            normalized_job_id is None
            or data["status"] != "queued"
            or data["status_url"]
            != f"/api/v1/inspection-jobs/{normalized_job_id}"
        ):
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        return data

    def get_inspection_job(self, job_id: str) -> dict[str, Any]:
        normalized_job_id = self._normalize_job_id(job_id)
        if normalized_job_id is None:
            raise ValueError("job_id must be a valid UUID")

        data = self._get_json(
            f"/api/v1/inspection-jobs/{normalized_job_id}",
            raise_not_found=True,
        )
        self._validate_response_keys(data, JOB_STATUS_RESPONSE_KEYS)
        if (
            self._normalize_job_id(data["job_id"]) != normalized_job_id
            or data["status"] not in VALID_JOB_STATUSES
        ):
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        if data["status"] == "succeeded":
            inspection_run_id = data.get("inspection_run_id")
            created = data.get("created")
            if (
                type(inspection_run_id) is not int
                or inspection_run_id <= 0
                or type(created) is not bool
            ):
                raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        return data

    def get_inspection_detail(self, inspection_run_id: int) -> dict[str, Any]:
        if inspection_run_id <= 0:
            raise ValueError("inspection_run_id must be positive")

        data = self._get_json(
            f"/api/v1/inspections/{inspection_run_id}",
            raise_not_found=True,
        )
        self._validate_response_keys(data, DETAIL_RESPONSE_KEYS)
        return data

    def list_etl_loads(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
        filename: str | None = None,
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        _validate_etl_pagination(limit, offset)
        params: dict[str, int | str] = {"limit": limit, "offset": offset}
        normalized_filename = _normalize_optional_etl_filter(filename)
        normalized_profile_name = _normalize_optional_etl_filter(profile_name)
        if normalized_filename:
            params["filename"] = normalized_filename
        if normalized_profile_name:
            params["profile_name"] = normalized_profile_name

        data = self._get_json("/api/v1/etl-loads", params=params)
        _validate_etl_load_list_response(data)
        return data

    def get_etl_load_quality_summary(
        self,
        *,
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        normalized_profile_name = _normalize_optional_etl_filter(profile_name)
        if normalized_profile_name:
            params["profile_name"] = normalized_profile_name

        data = self._get_json(
            "/api/v1/etl-loads/quality-summary",
            params=params,
        )
        _validate_etl_load_quality_summary_response(data)
        return data

    def get_etl_load_quality_trend(
        self,
        *,
        profile_name: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        params: dict[str, int | str] = {"limit": limit}
        normalized_profile_name = _normalize_optional_etl_filter(profile_name)
        if normalized_profile_name:
            params["profile_name"] = normalized_profile_name

        data = self._get_json(
            "/api/v1/etl-loads/quality-trend",
            params=params,
        )
        _validate_etl_load_quality_trend_response(data)
        return data

    def get_etl_quality_observability_profiles(self) -> dict[str, Any]:
        """List suppliers that have quality data to compare.

        후보는 ETL Profile Registry가 아니라 실제 적재 이력에서 옵니다. registry에서
        내려간 과거 공급사라도 품질 정보가 있는 배치가 남아 있으면 비교할 수 있습니다.
        """
        data = self._get_json("/api/v1/etl-loads/quality-observability/profiles")
        _validate_etl_quality_observability_profile_list_response(data)
        return data

    def get_etl_quality_observability(
        self,
        *,
        profile_name: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Fetch one supplier's latest-vs-previous ETL quality comparison.

        profile_name은 선택 필터가 아닙니다. 값을 비우면 서로 다른 공급사의 배치를
        비교하게 되므로, 요청을 보내기 전에 여기서 막습니다.
        """
        normalized_profile_name = _normalize_optional_etl_filter(profile_name)
        if not normalized_profile_name:
            raise ValueError("profile_name must not be empty")
        if (
            type(limit) is not int
            or not ETL_QUALITY_OBSERVABILITY_MIN_LIMIT
            <= limit
            <= ETL_QUALITY_OBSERVABILITY_MAX_LIMIT
        ):
            raise ValueError(
                "limit must be between "
                f"{ETL_QUALITY_OBSERVABILITY_MIN_LIMIT} and "
                f"{ETL_QUALITY_OBSERVABILITY_MAX_LIMIT}"
            )

        data = self._get_json(
            "/api/v1/etl-loads/quality-observability",
            params={"profile_name": normalized_profile_name, "limit": limit},
        )
        _validate_etl_quality_observability_response(data)
        return data

    def list_unknown_size_tokens(self, *, limit: int = 20) -> dict[str, Any]:
        _validate_etl_pagination(limit, 0)
        data = self._get_json(
            "/api/v1/catalog/unknown-size-tokens",
            params={"limit": limit},
        )
        _validate_unknown_size_token_report_response(data)
        return data

    def get_etl_load_detail(
        self,
        etl_load_run_id: int,
        *,
        product_limit: int = 20,
        product_offset: int = 0,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(etl_load_run_id, "etl_load_run_id")
        _validate_etl_pagination(product_limit, product_offset)

        data = self._get_json(
            f"/api/v1/etl-loads/{etl_load_run_id}",
            params={
                "product_limit": product_limit,
                "product_offset": product_offset,
            },
            raise_not_found=True,
            not_found_error=ETLLoadNotFoundError,
            not_found_message="ETL 적재 배치를 찾을 수 없습니다.",
        )
        _validate_etl_load_detail_response(data)
        return data

    def list_etl_rejections(
        self,
        etl_load_run_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(etl_load_run_id, "etl_load_run_id")
        _validate_etl_pagination(limit, offset)

        data = self._get_json(
            f"/api/v1/etl-loads/{etl_load_run_id}/rejections",
            params={"limit": limit, "offset": offset},
            raise_not_found=True,
            not_found_error=ETLLoadNotFoundError,
            not_found_message="ETL ?곸옱 諛곗튂瑜?李얠쓣 ???놁뒿?덈떎.",
        )
        _validate_etl_rejection_list_response(data)
        return data

    def list_catalog_promotions(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        etl_load_run_id: int | None = None,
        filename: str | None = None,
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        _validate_etl_pagination(limit, offset)
        params: dict[str, int | str] = {"limit": limit, "offset": offset}

        normalized_status = "" if status is None else str(status).strip()
        if normalized_status:
            if normalized_status not in CATALOG_PROMOTION_RUN_STATUSES:
                raise ValueError(
                    "status must be one of: applying, succeeded, failed, blocked"
                )
            params["status"] = normalized_status

        if etl_load_run_id is not None:
            _validate_positive_etl_int(etl_load_run_id, "etl_load_run_id")
            params["etl_load_run_id"] = etl_load_run_id

        for key, value in (
            ("filename", filename),
            ("profile_name", profile_name),
        ):
            normalized = _normalize_optional_etl_filter(value)
            if normalized:
                params[key] = normalized

        data = self._get_json("/api/v1/catalog-promotions", params=params)
        _validate_catalog_promotion_run_list(data)
        return data

    def get_catalog_promotion_detail(
        self,
        promotion_run_id: int,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(promotion_run_id, "promotion_run_id")
        data = self._get_json(
            f"/api/v1/catalog-promotions/{promotion_run_id}",
            raise_not_found=True,
            not_found_error=CatalogPromotionNotFoundError,
            not_found_message=CATALOG_PROMOTION_NOT_FOUND_MESSAGE,
        )
        _validate_catalog_promotion_run_detail(data)
        return data

    def list_catalog_promotion_audits(
        self,
        promotion_run_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(promotion_run_id, "promotion_run_id")
        _validate_etl_pagination(limit, offset)
        data = self._get_json(
            f"/api/v1/catalog-promotions/{promotion_run_id}/audits",
            params={"limit": limit, "offset": offset},
            raise_not_found=True,
            not_found_error=CatalogPromotionNotFoundError,
            not_found_message=CATALOG_PROMOTION_NOT_FOUND_MESSAGE,
        )
        _validate_catalog_promotion_audit_list(data)
        return data

    def list_catalog_promotion_rollbacks(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
        status: str | None = None,
        target_promotion_run_id: int | None = None,
    ) -> dict[str, Any]:
        _validate_etl_pagination(limit, offset)
        params: dict[str, int | str] = {"limit": limit, "offset": offset}

        normalized_status = "" if status is None else str(status).strip()
        if normalized_status:
            if normalized_status not in CATALOG_PROMOTION_RUN_STATUSES:
                raise ValueError(
                    "status must be one of: applying, succeeded, failed, blocked"
                )
            params["status"] = normalized_status

        if target_promotion_run_id is not None:
            _validate_positive_etl_int(
                target_promotion_run_id,
                "target_promotion_run_id",
            )
            params["target_promotion_run_id"] = target_promotion_run_id

        data = self._get_json(
            "/api/v1/catalog-promotion-rollbacks",
            params=params,
        )
        _validate_catalog_promotion_rollback_run_list(data)
        return data

    def get_catalog_promotion_rollback_detail(
        self,
        rollback_run_id: int,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(rollback_run_id, "rollback_run_id")
        data = self._get_json(
            f"/api/v1/catalog-promotion-rollbacks/{rollback_run_id}",
            raise_not_found=True,
            not_found_error=CatalogPromotionRollbackNotFoundError,
            not_found_message=CATALOG_PROMOTION_ROLLBACK_NOT_FOUND_MESSAGE,
        )
        _validate_catalog_promotion_rollback_run_detail(data)
        return data

    def list_catalog_promotion_rollback_changes(
        self,
        rollback_run_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(rollback_run_id, "rollback_run_id")
        _validate_etl_pagination(limit, offset)
        data = self._get_json(
            f"/api/v1/catalog-promotion-rollbacks/{rollback_run_id}/changes",
            params={"limit": limit, "offset": offset},
            raise_not_found=True,
            not_found_error=CatalogPromotionRollbackNotFoundError,
            not_found_message=CATALOG_PROMOTION_ROLLBACK_NOT_FOUND_MESSAGE,
        )
        _validate_catalog_promotion_rollback_change_list(data)
        return data

    def get_catalog_reconciliation(
        self,
        etl_load_run_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        # 읽기 전용 보고서입니다. 운영 카탈로그를 바꾸지 않습니다.
        _validate_positive_etl_int(etl_load_run_id, "etl_load_run_id")
        _validate_etl_pagination(limit, offset)

        data = self._get_json(
            f"/api/v1/etl-loads/{etl_load_run_id}/catalog-reconciliation",
            params={"limit": limit, "offset": offset},
            raise_not_found=True,
            not_found_error=ETLLoadNotFoundError,
            not_found_message="ETL 적재 배치를 찾을 수 없습니다.",
        )
        _validate_catalog_reconciliation_response(data)
        return data

    def get_catalog_promotion_preview(
        self,
        etl_load_run_id: int,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(etl_load_run_id, "etl_load_run_id")
        data = self._post_json(
            f"/api/v1/etl-loads/{etl_load_run_id}/promotion-preview",
            raise_not_found=True,
            not_found_error=ETLLoadNotFoundError,
            not_found_message="ETL 적재 배치를 찾을 수 없습니다.",
        )
        _validate_catalog_promotion_preview_response(data)
        return data

    def create_catalog_promotion(
        self,
        etl_load_run_id: int,
        *,
        confirmation: bool,
        expected_preview_hash: str,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(etl_load_run_id, "etl_load_run_id")
        if confirmation is not True:
            raise ValueError("confirmation must be true")
        if (
            not isinstance(expected_preview_hash, str)
            or CATALOG_PROMOTION_SHA256_PATTERN.fullmatch(expected_preview_hash)
            is None
        ):
            raise ValueError(
                "expected_preview_hash must be a lowercase SHA-256 hex string"
            )

        data = self._post_json(
            f"/api/v1/etl-loads/{etl_load_run_id}/promotions",
            json_body={
                "confirmation": True,
                "expected_preview_hash": expected_preview_hash,
            },
            raise_not_found=True,
            not_found_error=ETLLoadNotFoundError,
            not_found_message="ETL 적재 배치를 찾을 수 없습니다.",
            map_promotion_errors=True,
        )
        _validate_catalog_promotion_response(data)
        return data

    def get_catalog_promotion_rollback_preview(self, promotion_run_id: int) -> dict[str, Any]:
        _validate_positive_etl_int(promotion_run_id, "promotion_run_id")
        data = self._post_json(
            f"/api/v1/catalog-promotions/{promotion_run_id}/rollback-preview",
            raise_not_found=True,
            not_found_error=CatalogPromotionNotFoundError,
            not_found_message=CATALOG_PROMOTION_NOT_FOUND_MESSAGE,
        )
        required = {"target_promotion_run_id", "preview_schema_version", "preview_hash", "rollback_eligible", "blocked_reasons", "restore_count", "delete_count", "conflict_count", "items"}
        if not isinstance(data, dict) or not required.issubset(data) or data["target_promotion_run_id"] != promotion_run_id:
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        return data

    def create_catalog_promotion_rollback(
        self,
        promotion_run_id: int,
        *,
        confirmation: bool,
        expected_preview_hash: str,
    ) -> dict[str, Any]:
        _validate_positive_etl_int(promotion_run_id, "promotion_run_id")
        if confirmation is not True:
            raise ValueError("confirmation must be true")
        if not isinstance(expected_preview_hash, str) or CATALOG_PROMOTION_SHA256_PATTERN.fullmatch(expected_preview_hash) is None:
            raise ValueError("expected_preview_hash must be a lowercase SHA-256 hex string")
        data = self._post_json(
            f"/api/v1/catalog-promotions/{promotion_run_id}/rollback",
            json_body={"confirmation": True, "expected_preview_hash": expected_preview_hash},
            raise_not_found=True,
            not_found_error=CatalogPromotionNotFoundError,
            not_found_message=CATALOG_PROMOTION_NOT_FOUND_MESSAGE,
            map_promotion_errors=True,
        )
        required = {"rollback_run_id", "target_promotion_run_id", "status", "created", "preview_hash", "preview_schema_version", "restored_count", "deleted_count", "conflict_count", "started_at", "completed_at"}
        if not isinstance(data, dict) or not required.issubset(data) or data["target_promotion_run_id"] != promotion_run_id:
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        return data

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, int | str] | None = None,
        raise_not_found: bool = False,
        not_found_error: type[CatalogGuardApiError] = InspectionNotFoundError,
        not_found_message: str = NOT_FOUND_ERROR_MESSAGE,
        map_inactive_profile: bool = False,
    ) -> dict[str, Any]:
        response = self._get_response(
            path,
            params=params,
            raise_not_found=raise_not_found,
            not_found_error=not_found_error,
            not_found_message=not_found_message,
            map_inactive_profile=map_inactive_profile,
        )

        try:
            data = response.json()
        except ValueError as error:
            raise CatalogGuardApiResponseError(
                INVALID_RESPONSE_MESSAGE,
                request_id=_get_response_request_id(response),
            ) from error

        if not isinstance(data, dict):
            raise CatalogGuardApiResponseError(
                INVALID_RESPONSE_MESSAGE,
                request_id=_get_response_request_id(response),
            )
        return data

    def _post_json(
        self,
        path: str,
        *,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        raise_not_found: bool = False,
        not_found_error: type[CatalogGuardApiError] = InspectionNotFoundError,
        not_found_message: str = NOT_FOUND_ERROR_MESSAGE,
        map_promotion_errors: bool = False,
        map_etl_run_errors: bool = False,
    ) -> dict[str, Any]:
        response = self._post_response(
            path,
            files=files,
            data=data,
            json_body=json_body,
            raise_not_found=raise_not_found,
            not_found_error=not_found_error,
            not_found_message=not_found_message,
            map_promotion_errors=map_promotion_errors,
            map_etl_run_errors=map_etl_run_errors,
        )

        try:
            data = response.json()
        except ValueError as error:
            raise CatalogGuardApiResponseError(
                INVALID_RESPONSE_MESSAGE,
                request_id=_get_response_request_id(response),
            ) from error

        if not isinstance(data, dict):
            raise CatalogGuardApiResponseError(
                INVALID_RESPONSE_MESSAGE,
                request_id=_get_response_request_id(response),
            )
        return data

    def _get_response(
        self,
        path: str,
        *,
        params: dict[str, int | str] | None,
        raise_not_found: bool,
        not_found_error: type[CatalogGuardApiError] = InspectionNotFoundError,
        not_found_message: str = NOT_FOUND_ERROR_MESSAGE,
        map_inactive_profile: bool = False,
    ):
        url = f"{self._base_url}{path}"

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as error:
            raise CatalogGuardApiTimeoutError(TIMEOUT_ERROR_MESSAGE) from error
        except requests.ConnectionError as error:
            raise CatalogGuardApiConnectionError(CONNECTION_ERROR_MESSAGE) from error
        except requests.HTTPError as error:
            error_response = getattr(error, "response", None)
            request_id = _get_response_request_id(error_response)
            status_code = getattr(error_response, "status_code", None)
            if status_code == 404 and raise_not_found:
                raise not_found_error(
                    not_found_message,
                    request_id=request_id,
                ) from error
            # opt-in입니다. 모든 GET의 409를 profile 오류로 바꾸면 관계없는 endpoint의
            # 상태 충돌까지 잘못 분류됩니다. 켠 곳에서도 payload의 code가 실제로
            # inactive_profile일 때만 전용 오류가 됩니다.
            if map_inactive_profile and status_code == 409:
                inactive_error = self._build_inactive_profile_error(
                    error_response,
                    request_id=request_id,
                )
                if inactive_error is not None:
                    raise inactive_error from error
            auth_error = self._build_auth_error(
                status_code,
                error_response,
                request_id=request_id,
            )
            if auth_error is not None:
                raise auth_error from error
            raise CatalogGuardApiResponseError(
                SERVER_ERROR_MESSAGE,
                request_id=request_id,
            ) from error
        except requests.RequestException as error:
            raise CatalogGuardApiResponseError(SERVER_ERROR_MESSAGE) from error

        return response

    def _post_response(
        self,
        path: str,
        *,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        raise_not_found: bool = False,
        not_found_error: type[CatalogGuardApiError] = InspectionNotFoundError,
        not_found_message: str = NOT_FOUND_ERROR_MESSAGE,
        map_promotion_errors: bool = False,
        map_etl_run_errors: bool = False,
    ):
        url = f"{self._base_url}{path}"

        try:
            response = self._session.post(
                url,
                files=files,
                data=data,
                json=json_body,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as error:
            raise CatalogGuardApiTimeoutError(TIMEOUT_ERROR_MESSAGE) from error
        except requests.ConnectionError as error:
            raise CatalogGuardApiConnectionError(CONNECTION_ERROR_MESSAGE) from error
        except requests.HTTPError as error:
            error_response = getattr(error, "response", None)
            request_id = _get_response_request_id(error_response)
            status_code = getattr(error_response, "status_code", None)
            if status_code == 404 and raise_not_found:
                raise not_found_error(
                    not_found_message,
                    request_id=request_id,
                ) from error
            if map_promotion_errors:
                promotion_error = self._build_catalog_promotion_error(
                    error_response,
                    request_id=request_id,
                )
                if promotion_error is not None:
                    raise promotion_error from error
            if map_etl_run_errors:
                etl_run_error = self._build_etl_run_error(
                    error_response,
                    request_id=request_id,
                )
                if etl_run_error is not None:
                    raise etl_run_error from error
            auth_error = self._build_auth_error(
                status_code,
                error_response,
                request_id=request_id,
            )
            if auth_error is not None:
                raise auth_error from error
            raise CatalogGuardApiResponseError(
                SERVER_ERROR_MESSAGE,
                request_id=request_id,
            ) from error
        except requests.RequestException as error:
            raise CatalogGuardApiResponseError(SERVER_ERROR_MESSAGE) from error

        return response

    def _build_auth_error(
        self,
        status_code: int | None,
        response: object,
        *,
        request_id: str | None,
    ) -> CatalogGuardApiResponseError | None:
        if status_code not in (401, 403):
            return None

        code = None
        try:
            payload = response.json()
        except (AttributeError, ValueError):
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("detail"), dict):
            code = payload["detail"].get("code")

        if status_code == 403:
            return CatalogGuardApiAuthorizationError(
                INSUFFICIENT_ROLE_MESSAGE,
                code=code or "insufficient_role",
                request_id=request_id,
            )

        if code == "invalid_credentials":
            return InvalidCredentialsError(
                INVALID_CREDENTIALS_MESSAGE,
                code=code,
                request_id=request_id,
            )
        if code == "inactive_user":
            return CatalogGuardApiAuthenticationError(
                INACTIVE_USER_MESSAGE,
                code=code,
                request_id=request_id,
            )
        if code == "authentication_required":
            return CatalogGuardApiAuthenticationError(
                AUTHENTICATION_REQUIRED_MESSAGE,
                code=code,
                request_id=request_id,
            )
        return CatalogGuardApiAuthenticationError(
            INVALID_TOKEN_MESSAGE,
            code=code or "invalid_token",
            request_id=request_id,
        )

    def _build_catalog_promotion_error(
        self,
        response: object,
        *,
        request_id: str | None,
    ) -> CatalogPromotionApiError | None:
        try:
            payload = response.json()
        except (AttributeError, ValueError):
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("detail"), dict):
            return None

        detail = payload["detail"]
        code = detail.get("code")
        promotion_run_id = detail.get("promotion_run_id")
        if type(promotion_run_id) is not int or promotion_run_id < 1:
            promotion_run_id = None

        if code == "preview_stale":
            return CatalogPromotionPreviewStaleError(
                CATALOG_PROMOTION_STALE_MESSAGE,
                code=code,
                promotion_run_id=promotion_run_id,
                request_id=request_id,
            )
        if code == "promotion_blocked":
            blocked_reasons = detail.get("blocked_reasons")
            safe_blocked_reasons = (
                blocked_reasons
                if isinstance(blocked_reasons, list)
                and all(
                    _validate_catalog_promotion_blocked_reason(reason)
                    for reason in blocked_reasons
                )
                else []
            )
            return CatalogPromotionBlockedError(
                CATALOG_PROMOTION_BLOCKED_MESSAGE,
                code=code,
                promotion_run_id=promotion_run_id,
                blocked_reasons=safe_blocked_reasons,
                request_id=request_id,
            )
        if code == "promotion_failed":
            return CatalogPromotionFailedError(
                CATALOG_PROMOTION_FAILED_MESSAGE,
                code=code,
                promotion_run_id=promotion_run_id,
                request_id=request_id,
            )
        return None

    def _build_inactive_profile_error(
        self,
        response: object,
        *,
        request_id: str | None,
    ) -> "ETLProfileInactiveError | None":
        """Return the inactive-profile error only when the payload actually says so.

        code가 다른 값이거나 JSON/detail이 없으면 None을 돌려주어, 호출자가 기존
        일반 오류 처리를 그대로 쓰게 합니다. 409를 무조건 비활성으로 해석하지
        않습니다.

        사용자에게 보여 줄 문구는 서버 message 원문이 아니라 클라이언트가 관리하는
        고정 문구를 씁니다. 서버 문구가 그대로 화면에 새면 내부 표현이 노출될 수
        있고, 문구가 바뀌면 UI가 조용히 따라 바뀌기 때문입니다.
        """
        detail = _error_detail_payload(response)
        if detail is None or detail.get("code") != "inactive_profile":
            return None
        return ETLProfileInactiveError(
            ETL_INACTIVE_PROFILE_MESSAGE,
            code="inactive_profile",
            request_id=request_id,
        )

    def _build_etl_run_error(
        self,
        response: object,
        *,
        request_id: str | None,
    ) -> ETLWebRunApiError | None:
        inactive_error = self._build_inactive_profile_error(
            response,
            request_id=request_id,
        )
        if inactive_error is not None:
            return inactive_error

        detail = _error_detail_payload(response)
        if detail is None:
            return None

        code = detail.get("code")
        message = detail.get("message")
        safe_message = message if isinstance(message, str) and message else None

        if code == "unsupported_profile":
            return ETLUnsupportedProfileError(
                ETL_UNSUPPORTED_PROFILE_MESSAGE,
                code=code,
                request_id=request_id,
            )
        if code == "invalid_upload":
            return ETLInvalidUploadError(
                safe_message or "업로드한 CSV를 처리할 수 없습니다.",
                code=code,
                request_id=request_id,
            )
        return None

    def _validate_response_keys(
        self,
        data: dict[str, Any],
        required_keys: tuple[str, ...],
    ) -> None:
        if any(key not in data for key in required_keys):
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)

    def _normalize_date_param(self, value: date | str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()

        normalized_value = str(value).strip()
        return normalized_value or None

    def _normalize_status_param(self, value: str | None) -> str | None:
        normalized_value = "" if value is None else str(value).strip()
        if not normalized_value:
            return None
        if normalized_value not in VALID_INSPECTION_STATUS_FILTERS:
            raise ValueError("status must be one of: error, warning, normal")
        return normalized_value

    def _normalize_job_id(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        try:
            return str(UUID(value.strip()))
        except (ValueError, AttributeError):
            return None

    def _normalize_create_response(self, data: dict[str, Any]) -> dict[str, Any]:
        # created는 새 서버가 추가한 필드입니다.
        # 구버전 서버 응답에는 없을 수 있으므로 True로 보정하되, 있으면 반드시 bool이어야 합니다.
        normalized_data = dict(data)
        if "created" not in normalized_data:
            normalized_data["created"] = True
            return normalized_data

        if type(normalized_data["created"]) is not bool:
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        return normalized_data


def create_catalogguard_api_client() -> CatalogGuardApiClient:
    base_url = get_catalogguard_api_base_url()
    if base_url is None:
        raise CatalogGuardApiConfigurationError(CONFIGURATION_ERROR_MESSAGE)

    return CatalogGuardApiClient(
        base_url,
        timeout_seconds=get_catalogguard_api_timeout_seconds(),
    )
