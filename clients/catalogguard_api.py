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

LIST_RESPONSE_KEYS = ("items", "total", "limit", "offset")
CREATE_RESPONSE_KEYS = ("inspection_run_id", "summary", "results")
DETAIL_RESPONSE_KEYS = (
    "inspection_run_id",
    "source_filename",
    "created_at",
    "summary",
    "results",
)


class CatalogGuardApiError(Exception):
    pass


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
            not_found_error=InspectionNotFoundError(NOT_FOUND_ERROR_MESSAGE),
        )
        self._validate_response_keys(data, DETAIL_RESPONSE_KEYS)
        return data

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, int | str] | None = None,
        not_found_error: InspectionNotFoundError | None = None,
    ) -> dict[str, Any]:
        response = self._get_response(path, params=params, not_found_error=not_found_error)

        try:
            data = response.json()
        except ValueError as error:
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE) from error

        if not isinstance(data, dict):
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
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
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE) from error

        if not isinstance(data, dict):
            raise CatalogGuardApiResponseError(INVALID_RESPONSE_MESSAGE)
        return data

    def _get_response(
        self,
        path: str,
        *,
        params: dict[str, int | str] | None,
        not_found_error: InspectionNotFoundError | None,
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
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code == 404 and not_found_error is not None:
                raise not_found_error from error
            raise CatalogGuardApiResponseError(SERVER_ERROR_MESSAGE) from error
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
            raise CatalogGuardApiResponseError(SERVER_ERROR_MESSAGE) from error
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

    def _normalize_create_response(self, data: dict[str, Any]) -> dict[str, Any]:
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
