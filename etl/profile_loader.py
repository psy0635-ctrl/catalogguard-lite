import json
from pathlib import Path

from config.settings import CSV_TEMPLATE_COLUMNS, REQUIRED_COLUMNS
from etl.models import ETLProfile


class ETLProfileValidationError(ValueError):
    """Raised when a mapping profile cannot safely produce CatalogGuard CSV data."""


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
