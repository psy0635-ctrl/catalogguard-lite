import json
from pathlib import Path

from config.settings import BASE_DIR, CSV_TEMPLATE_COLUMNS, REQUIRED_COLUMNS
from etl.models import ETLProfile


class ETLProfileValidationError(ValueError):
    """Raised when a mapping profile cannot safely produce CatalogGuard CSV data."""


class ETLProfileNotFoundError(ValueError):
    """Raised when a requested profile id is not in the server-side allowlist."""


# 웹 ETL 실행은 이 allowlist에 있는 profile_id만 받습니다.
# 사용자가 보낸 파일 경로를 그대로 신뢰하지 않기 위한 유일한 진입점입니다.
#
# profile_id의 '_v1'은 기존 API 클라이언트 호환을 위해 고정된 식별자이며,
# 실제 검수/적재에 쓰이는 버전이 아닙니다. 실제 버전은 프로필 JSON의 profile_version이고
# ETLLoadRun에도 그 값이 기록되므로, display_name에는 버전을 넣지 않습니다.
#
# versions는 지금까지 공개된 모든 버전의 보존된 정의를 가리키고, 신규 ETL 실행에 쓸
# 버전은 active_version 하나로만 정합니다. "가장 큰 번호"를 active로 추론하지 않는
# 이유는 docs/etl_profile_lifecycle.md Policy H에 있습니다. 버전 문자열은 임의 값을
# 허용하므로 크기 비교가 성립하지 않고, 아직 검증하지 않은 버전이 파일을 추가하는
# 것만으로 운영 실행에 들어가면 안 되기 때문입니다.
ETL_PROFILE_DIR = BASE_DIR / "config" / "etl"
_ETL_PROFILE_REGISTRY: dict[str, dict] = {
    "sample_fashion_vendor_v1": {
        "display_name": "패션 공급사 샘플",
        "profile_name": "sample_fashion_vendor",
        "active_version": "2",
        "versions": {
            "1": "sample_fashion_vendor/v1.json",
            "2": "sample_fashion_vendor/v2.json",
        },
    },
    "sample_marketplace_vendor_v1": {
        "display_name": "마켓플레이스 공급사 샘플",
        "profile_name": "sample_marketplace_vendor",
        "active_version": "2",
        "versions": {
            "1": "sample_marketplace_vendor/v1.json",
            "2": "sample_marketplace_vendor/v2.json",
        },
    },
}


def list_etl_profiles() -> list[dict[str, str]]:
    """Return the allowlisted ETL profiles safe to expose to API/UI callers."""
    return [
        {"id": profile_id, "display_name": info["display_name"]}
        for profile_id, info in _ETL_PROFILE_REGISTRY.items()
    ]


def get_etl_profile_detail(profile_id: str) -> dict[str, object]:
    """Return safe metadata for one allowlisted ETL profile."""
    info = _ETL_PROFILE_REGISTRY.get(profile_id)
    if info is None:
        raise ETLProfileNotFoundError(f"Unknown ETL profile: {profile_id}")

    profile = load_profile(get_profile_path(profile_id))
    return {
        "id": profile_id,
        "display_name": info["display_name"],
        "profile_name": profile.name,
        "profile_version": profile.version,
        "source_columns": dict(profile.source_columns),
        "required_source_columns": profile.required_source_columns,
        "defaults": dict(profile.defaults),
    }


def _registry_entry(profile_id: str) -> dict:
    info = _ETL_PROFILE_REGISTRY.get(profile_id)
    if info is None:
        raise ETLProfileNotFoundError(f"Unknown ETL profile: {profile_id}")
    return info


def _archived_version_path(info: dict, profile_version: str) -> Path:
    """Resolve one registered version to a file inside the profile archive.

    profile_version은 registry versions의 정확한 key여야 하므로, 호출자가 보낸 값이
    경로 조각으로 쓰이지 않습니다. registry 값 자체가 잘못돼 archive 밖을 가리키는
    경우까지 막기 위해, resolve() 뒤에도 ETL_PROFILE_DIR 안에 있는지 확인합니다.
    symlink는 resolve()가 실제 대상으로 바꾼 뒤 검사하므로 밖으로 탈출할 수 없습니다.
    """
    relative_path = info["versions"].get(profile_version)
    if relative_path is None:
        raise ETLProfileNotFoundError(
            f"Unknown ETL profile version: {profile_version}"
        )

    profile_dir = ETL_PROFILE_DIR.resolve()
    candidate_path = (ETL_PROFILE_DIR / relative_path).resolve()
    if not candidate_path.is_relative_to(profile_dir) or not candidate_path.is_file():
        raise ETLProfileNotFoundError(
            f"Unknown ETL profile version: {profile_version}"
        )
    return candidate_path


def get_profile_path(profile_id: str) -> Path:
    """Resolve a profile_id to the config file of its active version.

    Never accepts a filesystem path from the caller: profile_id must be an exact
    allowlist key, so arbitrary/relative paths can't reach load_profile().
    """
    info = _registry_entry(profile_id)
    return _archived_version_path(info, info["active_version"])


def get_profile_version_path(profile_id: str, profile_version: str) -> Path:
    """Resolve one archived version of an allowlisted profile.

    과거 정의를 읽기 위한 내부 helper입니다. 신규 ETL 실행은 여전히
    get_profile_path()의 active version만 사용합니다.
    """
    return _archived_version_path(_registry_entry(profile_id), profile_version)


def _require_non_empty_text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ETLProfileValidationError(f"{key} is required")
    return value.strip()


def _normalize_targets(target: object) -> tuple[str, ...]:
    raw_targets = [target] if isinstance(target, str) else target
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ETLProfileValidationError("source_columns contains an invalid target column")
    if not all(isinstance(value, str) and value.strip() for value in raw_targets):
        raise ETLProfileValidationError("source_columns contains an invalid target column")
    return tuple(value.strip() for value in raw_targets)


def _validate_mapping(data: dict) -> dict[str, tuple[str, ...]]:
    mapping = data.get("source_columns")
    if not isinstance(mapping, dict) or not mapping:
        raise ETLProfileValidationError("source_columns must be a non-empty object")

    normalized_mapping: dict[str, tuple[str, ...]] = {}
    targets: set[str] = set()
    allowed_columns = set(CSV_TEMPLATE_COLUMNS)
    for source, raw_target in mapping.items():
        if not isinstance(source, str) or not source.strip():
            raise ETLProfileValidationError("source_columns contains an invalid source column")
        source = source.strip()
        target_columns = _normalize_targets(raw_target)
        for target in target_columns:
            if target not in allowed_columns:
                raise ETLProfileValidationError(f"Unsupported target column: {target}")
            if target in targets:
                raise ETLProfileValidationError(f"Duplicate target column: {target}")
            targets.add(target)
        normalized_mapping[source] = target_columns
    return normalized_mapping


def _validate_required_sources(
    data: dict,
    mapping: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    required_sources = data.get("required_source_columns")
    if not isinstance(required_sources, list) or not all(
        isinstance(column, str) and column.strip() for column in required_sources
    ):
        raise ETLProfileValidationError("required_source_columns must be a list of column names")

    normalized_sources = tuple(column.strip() for column in required_sources)
    missing_mappings = [column for column in normalized_sources if column not in mapping]
    if missing_mappings:
        raise ETLProfileValidationError(
            "required_source_columns must be mapped: " + ", ".join(missing_mappings)
        )
    return normalized_sources


def _validate_defaults(data: dict) -> dict[str, str]:
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ETLProfileValidationError("defaults must be an object")

    allowed_columns = set(CSV_TEMPLATE_COLUMNS)
    normalized_defaults: dict[str, str] = {}
    for column, value in defaults.items():
        if not isinstance(column, str) or column not in allowed_columns:
            raise ETLProfileValidationError(f"Unsupported default column: {column}")
        if value is None:
            raise ETLProfileValidationError(f"Default value cannot be null: {column}")
        normalized_defaults[column] = str(value).strip()
    return normalized_defaults


def load_profile(profile_path: Path) -> ETLProfile:
    try:
        with profile_path.open(encoding="utf-8") as profile_file:
            data = json.load(profile_file)
    except FileNotFoundError as error:
        raise ETLProfileValidationError("Mapping profile file was not found") from error
    except json.JSONDecodeError as error:
        raise ETLProfileValidationError("Mapping profile is not valid JSON") from error

    if not isinstance(data, dict):
        raise ETLProfileValidationError("Mapping profile must be a JSON object")

    mapping = _validate_mapping(data)
    defaults = _validate_defaults(data)
    _validate_required_sources(data, mapping)
    produced_columns = {
        target
        for targets in mapping.values()
        for target in targets
    } | set(defaults)
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in produced_columns]
    if missing_columns:
        raise ETLProfileValidationError(
            "Required CatalogGuard columns are not produced: " + ", ".join(missing_columns)
        )

    return ETLProfile(
        name=_require_non_empty_text(data, "profile_name"),
        version=_require_non_empty_text(data, "profile_version"),
        source_columns=mapping,
        required_source_columns=_validate_required_sources(data, mapping),
        defaults=defaults,
    )
