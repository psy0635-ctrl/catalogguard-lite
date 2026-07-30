from datetime import date
import re
from typing import Any
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
CATALOG_PROMOTION_STALE_MESSAGE = (
    "미리보기 이후 상품 데이터가 변경되었습니다. 미리보기를 다시 실행하세요."
)
CATALOG_PROMOTION_BLOCKED_MESSAGE = (
    "현재 ETL 적재 결과는 운영 상품에 반영할 수 없습니다."
)
CATALOG_PROMOTION_FAILED_MESSAGE = "운영 상품 반영 중 오류가 발생했습니다."


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


class CatalogGuardApiClient:
    # Streamlit 화면은 이 클라이언트만 알면 되고, requests 예외나 HTTP 상태 코드는 여기서 숨깁니다.
    # 그래서 app.py는 사용자에게 보여 줄 메시지만 선택하면 됩니다.
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = CATALOGGUARD_API_DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ):
        normalized_base_url = str(base_url).strip().rstrip("/")
        if not normalized_base_url:
            raise CatalogGuardApiConfigurationError(CONFIGURATION_ERROR_MESSAGE)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._base_url = normalized_base_url
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

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

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, int | str] | None = None,
        raise_not_found: bool = False,
        not_found_error: type[CatalogGuardApiError] = InspectionNotFoundError,
        not_found_message: str = NOT_FOUND_ERROR_MESSAGE,
    ) -> dict[str, Any]:
        response = self._get_response(
            path,
            params=params,
            raise_not_found=raise_not_found,
            not_found_error=not_found_error,
            not_found_message=not_found_message,
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
        json_body: dict[str, Any] | None = None,
        raise_not_found: bool = False,
        not_found_error: type[CatalogGuardApiError] = InspectionNotFoundError,
        not_found_message: str = NOT_FOUND_ERROR_MESSAGE,
        map_promotion_errors: bool = False,
    ) -> dict[str, Any]:
        response = self._post_response(
            path,
            files=files,
            json_body=json_body,
            raise_not_found=raise_not_found,
            not_found_error=not_found_error,
            not_found_message=not_found_message,
            map_promotion_errors=map_promotion_errors,
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
        json_body: dict[str, Any] | None = None,
        raise_not_found: bool = False,
        not_found_error: type[CatalogGuardApiError] = InspectionNotFoundError,
        not_found_message: str = NOT_FOUND_ERROR_MESSAGE,
        map_promotion_errors: bool = False,
    ):
        url = f"{self._base_url}{path}"

        try:
            response = self._session.post(
                url,
                files=files,
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
            raise CatalogGuardApiResponseError(
                SERVER_ERROR_MESSAGE,
                request_id=request_id,
            ) from error
        except requests.RequestException as error:
            raise CatalogGuardApiResponseError(SERVER_ERROR_MESSAGE) from error

        return response

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
