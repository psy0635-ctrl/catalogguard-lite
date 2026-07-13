from datetime import date
import re
from typing import Any

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


class CatalogGuardApiResponseError(CatalogGuardApiError):
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

    def get_inspection_detail(self, inspection_run_id: int) -> dict[str, Any]:
        if inspection_run_id <= 0:
            raise ValueError("inspection_run_id must be positive")

        data = self._get_json(
            f"/api/v1/inspections/{inspection_run_id}",
            raise_not_found=True,
        )
        self._validate_response_keys(data, DETAIL_RESPONSE_KEYS)
        return data

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, int | str] | None = None,
        raise_not_found: bool = False,
    ) -> dict[str, Any]:
        response = self._get_response(
            path,
            params=params,
            raise_not_found=raise_not_found,
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
        files: dict[str, tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        response = self._post_response(path, files=files)

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
                raise InspectionNotFoundError(
                    NOT_FOUND_ERROR_MESSAGE,
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
        files: dict[str, tuple[str, bytes, str]],
    ):
        url = f"{self._base_url}{path}"

        try:
            response = self._session.post(
                url,
                files=files,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as error:
            raise CatalogGuardApiTimeoutError(TIMEOUT_ERROR_MESSAGE) from error
        except requests.ConnectionError as error:
            raise CatalogGuardApiConnectionError(CONNECTION_ERROR_MESSAGE) from error
        except requests.HTTPError as error:
            request_id = _get_response_request_id(getattr(error, "response", None))
            raise CatalogGuardApiResponseError(
                SERVER_ERROR_MESSAGE,
                request_id=request_id,
            ) from error
        except requests.RequestException as error:
            raise CatalogGuardApiResponseError(SERVER_ERROR_MESSAGE) from error

        return response

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
