import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import BASE_DIR, CSV_TEMPLATE_COLUMNS, REQUIRED_COLUMNS
from db.models import ETLProfileActivation
from etl.models import ETLProfile


class ETLProfileValidationError(ValueError):
    """Raised when a mapping profile cannot safely produce CatalogGuard CSV data."""


class ETLProfileNotFoundError(ValueError):
    """Raised when a requested profile id is not in the server-side allowlist."""


class ETLProfileInactiveError(ValueError):
    """Raised when an allowlisted ETL profile has no active version.

    ETLProfileNotFoundError와 일부러 상속 관계를 두지 않습니다. "없는 프로필"과
    "있지만 비활성인 프로필"은 호출자가 다르게 다뤄야 하는 상태이고, 상속으로 묶으면
    기존 except 절이 비활성 상태까지 조용히 삼켜 두 상태가 섞이기 때문입니다.
    """


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
#
# active_version은 "버전 문자열" 또는 None입니다. None은 비활성(deactivated)이며
# Policy G의 "Delete 대신 Deactivate"를 뜻합니다. 신규 ETL 실행만 막고 versions의
# archive는 그대로 남으므로, 과거 배치가 참조하는 정의는 계속 읽을 수 있습니다.
# ""나 "disabled" 같은 값은 비활성 표시가 아니며, 그런 값은 versions에 없는
# pointer로서 그대로 실패해야 합니다.
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


def get_profile_display_name(profile_id: str) -> str:
    """Return the human-readable name of one allowlisted profile.

    registry dict를 모듈 밖으로 넘기지 않기 위한 접근자입니다. 호출자가 registry
    자체를 들고 가면 어디서든 활성 상태를 직접 읽거나 고칠 수 있게 됩니다.
    """
    return _registry_entry(profile_id)["display_name"]


def registered_profile_versions(profile_id: str) -> list[str]:
    """Return every preserved version of one profile, in registry order.

    activation 쓰기 경로가 "요청한 버전이 실제로 보존된 버전인가"를 물어보는 곳입니다.
    이 목록에 없는 값은 활성화할 수 없습니다. Policy H대로 여기서 "가장 큰 버전"을
    고르지 않고 후보만 돌려줍니다.
    """
    return list(_registry_entry(profile_id)["versions"])


@dataclass(frozen=True)
class ETLProfileActivationState:
    """The resolved activation of one profile: deployment default + runtime override.

    세 값을 따로 들고 다니는 이유는, 이 셋이 서로 다른 질문에 답하기 때문입니다.

    * deployment_active_version — 코드/배포가 정한 기본값
    * runtime_active_version — 운영자가 API로 정한 값 (override가 있을 때만 의미 있음)
    * effective_active_version — 실제로 신규 실행에 쓰이는 값

    화면이나 API가 이 셋을 하나로 뭉개면 "왜 이 프로필이 지금 비활성인가"에 답할 수
    없습니다. 배포가 그렇게 정한 것과 운영자가 내린 것은 다음에 해야 할 일이 다릅니다.
    """

    profile_id: str
    deployment_active_version: str | None
    runtime_override_exists: bool
    runtime_active_version: str | None
    effective_active_version: str | None

    @property
    def is_active(self) -> bool:
        return self.effective_active_version is not None


def _runtime_activation_row(
    session: Session | None,
    profile_id: str,
) -> ETLProfileActivation | None:
    """Read this profile's runtime override row, or None when there is none.

    session이 None이면 조회하지 않고 None을 돌려줍니다. 이는 "override가 없다"가
    아니라 "runtime 상태를 물어볼 수 없는 호출자"라는 뜻이며, 그런 호출자는 배포
    기본값만 보게 됩니다. etl.cli처럼 profile_id가 아니라 파일 경로를 직접 받는
    경로는 애초에 이 resolver를 지나지 않습니다.
    """
    if session is None:
        return None
    return session.scalars(
        select(ETLProfileActivation).where(
            ETLProfileActivation.profile_id == profile_id
        )
    ).one_or_none()


def resolve_etl_profile_activation(
    profile_id: str,
    *,
    session: Session | None = None,
) -> ETLProfileActivationState:
    """Combine the deployment default with an optional runtime override.

    **effective active version을 계산하는 곳은 여기 한 곳뿐입니다.** Web/S3/HTTP/
    Airflow가 각자 DB를 읽어 각자 판단하면 같은 프로필이 경로마다 다르게 활성으로
    보일 수 있습니다.

    | runtime row | active_version | effective |
    | --- | --- | --- |
    | 없음 | — | 배포 registry의 active_version |
    | 있음 | "2" | "2" |
    | 있음 | NULL | None (비활성) |

    "row 없음"과 "row 있음 + NULL"을 구분합니다. 전자는 아무도 손대지 않아 배포
    기본값을 따르는 상태이고, 후자는 운영자가 명시적으로 내린 상태입니다. 둘을 합치면
    배포 기본값이 바뀔 때 운영자의 결정이 조용히 뒤집힙니다.

    없는 profile_id는 ETLProfileNotFoundError입니다. runtime row만 남아 있고 registry
    에서 사라진 프로필도 마찬가지입니다. registry가 allowlist이고, 그 밖의 값을 DB row
    하나로 되살리면 allowlist가 방어선이 아니게 됩니다.
    """
    info = _registry_entry(profile_id)
    deployment_active_version = info["active_version"]

    row = _runtime_activation_row(session, profile_id)
    if row is None:
        return ETLProfileActivationState(
            profile_id=profile_id,
            deployment_active_version=deployment_active_version,
            runtime_override_exists=False,
            runtime_active_version=None,
            effective_active_version=deployment_active_version,
        )
    return ETLProfileActivationState(
        profile_id=profile_id,
        deployment_active_version=deployment_active_version,
        runtime_override_exists=True,
        runtime_active_version=row.active_version,
        effective_active_version=row.active_version,
    )


def list_etl_profiles(
    *,
    session: Session | None = None,
    include_inactive: bool = False,
) -> list[dict[str, str]]:
    """Return allowlisted ETL profiles, by default only the ones runnable right now.

    기본값(include_inactive=False)은 기존 계약 그대로입니다. 이 목록의 주 호출자는
    Streamlit의 신규 ETL 실행 selector이므로 "관리용 전체 목록"이 아니라 "지금 실행할
    수 있는 프로필 목록"이고, 비활성 프로필은 제외합니다. 서버 차단
    (get_profile_path())이 실제 방어선이고 이 필터는 그 앞단입니다.

    활성 여부는 배포 기본값이 아니라 **effective** 상태로 판단합니다. runtime에서
    내린 프로필이 selector에 계속 보이면 사용자는 고를 수 있는데 실행만 409로 막히는
    화면을 보게 됩니다.

    include_inactive=True는 **운영 관리 화면 전용**입니다. 비활성 프로필을 목록에서
    감추면 한 번 내린 프로필을 다시 고를 수 없어 영영 되살릴 수 없게 됩니다. 관리
    화면은 "무엇을 실행할 수 있는가"가 아니라 "무엇을 관리할 수 있는가"를 묻습니다.

    두 경우 모두 registry allowlist 밖의 항목은 절대 나오지 않고, registry 정의
    순서도 그대로입니다. include_inactive는 필터를 끄는 것이지 후보를 넓히지 않습니다.

    runtime override를 한 번에 읽고 메모리에서 맞춥니다. 프로필마다 따로 질의하면
    프로필 수만큼 왕복이 생깁니다.
    """
    if include_inactive:
        return [
            {"id": profile_id, "display_name": info["display_name"]}
            for profile_id, info in _ETL_PROFILE_REGISTRY.items()
        ]

    overrides: dict[str, str | None] = {}
    if session is not None:
        overrides = {
            row.profile_id: row.active_version
            for row in session.scalars(select(ETLProfileActivation)).all()
        }
    return [
        {"id": profile_id, "display_name": info["display_name"]}
        for profile_id, info in _ETL_PROFILE_REGISTRY.items()
        if (
            overrides[profile_id]
            if profile_id in overrides
            else info["active_version"]
        )
        is not None
    ]


def is_etl_profile_inactive(
    profile_id: str,
    *,
    session: Session | None = None,
) -> bool:
    """Return True only for an allowlisted profile whose effective version is None.

    S3/HTTP feed는 source adapter가 먼저 실행되는 구조라, 외부를 읽기 전에 비활성
    여부만 값싸게 물어볼 곳이 필요합니다. 이 함수는 registry를 읽기만 하며 경로를
    해석하지도, 예외를 던지지도 않습니다. 실제 실행 차단은 계속 get_profile_path()가
    합니다.

    없는 profile_id는 False입니다. "없음"과 "비활성"은 다른 상태이고, 여기서 unknown을
    함께 처리하면 호출자가 기존 unsupported_profile 계약을 우회하게 되기 때문입니다.
    잘못된 active pointer("999" 등)도 False입니다. 비활성이 아니라 잘못된 설정이므로
    기존대로 get_profile_path()에서 실패해야 합니다.

    판단 기준은 resolve_etl_profile_activation()의 effective 값입니다. 여기서만 배포
    기본값을 보면 runtime에서 내린 프로필의 S3/HTTP 실행이 외부를 먼저 읽고 나서야
    막히게 됩니다.
    """
    if profile_id not in _ETL_PROFILE_REGISTRY:
        return False
    return not resolve_etl_profile_activation(
        profile_id,
        session=session,
    ).is_active


def get_etl_profile_detail(
    profile_id: str,
    *,
    session: Session | None = None,
) -> dict[str, object]:
    """Return safe metadata for the effective active version of one profile.

    runtime override가 있으면 그 버전의 detail을 보여 줍니다. 이 endpoint의 계약은
    "지금 이 프로필로 실행하면 쓰이는 정의"이므로, 배포 기본값을 보여 주면 runtime에서
    버전을 바꾼 뒤 화면과 실제 실행이 어긋납니다.
    """
    info = _ETL_PROFILE_REGISTRY.get(profile_id)
    if info is None:
        raise ETLProfileNotFoundError(f"Unknown ETL profile: {profile_id}")

    profile = load_profile(get_profile_path(profile_id, session=session))
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


def get_profile_path(profile_id: str, *, session: Session | None = None) -> Path:
    """Resolve a profile_id to the config file of its effective active version.

    Never accepts a filesystem path from the caller: profile_id must be an exact
    allowlist key, so arbitrary/relative paths can't reach load_profile().

    effective active version이 None이면 ETLProfileInactiveError를 냅니다. 여기서 다른
    버전으로 대신 실행하지 않습니다. 비활성 프로필은 "무엇을 실행할지 정해지지 않은"
    상태이지 "최신 버전으로 실행해도 되는" 상태가 아니기 때문입니다.

    session을 주면 runtime override까지 반영합니다. 신규 ETL 실행 경로(Web/S3/HTTP/
    Airflow)는 모두 run_web_etl()을 지나며 그 session을 그대로 넘기므로, 네 경로가
    같은 activation을 봅니다.
    """
    activation = resolve_etl_profile_activation(profile_id, session=session)
    if activation.effective_active_version is None:
        raise ETLProfileInactiveError(f"ETL profile is inactive: {profile_id}")
    return _archived_version_path(
        _registry_entry(profile_id),
        activation.effective_active_version,
    )


def get_profile_version_path(profile_id: str, profile_version: str) -> Path:
    """Resolve one archived version of an allowlisted profile.

    과거 정의를 읽기 위한 내부 helper입니다. 신규 ETL 실행은 여전히
    get_profile_path()의 active version만 사용합니다.

    active_version이 None이어도 archive 조회는 계속 됩니다. Deactivate는 Delete가
    아니므로, 과거 배치가 참조하는 정의를 여기서 막으면 안 됩니다.
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
