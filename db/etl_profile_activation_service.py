"""Read and write the runtime activation state of one allowlisted ETL profile.

Phase 5B.1 of docs/etl_profile_lifecycle.md. Phase 5A까지 activation은 코드 상수였고,
바꾸려면 코드 수정 → 테스트 → 배포가 필요했습니다. 여기서는 그 상태를 운영자가 API로
바꿀 수 있게 하되, **프로세스 메모리가 아니라 DB에 저장**합니다. 재시작하면 사라지는
상태는 "관리 기능처럼 보이지만 관리되지 않는" 더 나쁜 상태이기 때문입니다.

이 모듈이 하지 않는 일을 분명히 해 둡니다.

* 프로필 정의(source_columns/required_source_columns/defaults)를 바꾸지 않습니다.
  Policy A(Published Version Immutable)는 그대로이고, 여기서 바꾸는 것은 "이미 보존된
  어떤 버전을 신규 실행에 쓸 것인가" 하나뿐입니다.
* 새 프로필을 등록하거나 삭제하지 않습니다. allowlist는 계속 코드 registry입니다.
* 버전을 추론하지 않습니다. Policy H대로 활성 버전은 항상 명시적으로 지정합니다.

effective activation 계산은 여기서 다시 구현하지 않고
etl.profile_loader.resolve_etl_profile_activation() 하나만 씁니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from db.models import ETLProfileActivation
from etl.profile_loader import (
    ETLProfileActivationState,
    get_profile_display_name,
    registered_profile_versions,
    resolve_etl_profile_activation,
)


class ETLProfileVersionNotFoundError(ValueError):
    """Raised when the requested active version is not a preserved version.

    ETLProfileNotFoundError와 상속으로 묶지 않습니다. "없는 프로필"과 "있는 프로필의
    없는 버전"은 운영자가 해야 할 일이 다르고(프로필을 고쳐야 하는가, 버전을 고쳐야
    하는가), 상속으로 묶으면 route의 except 절이 두 상태를 같은 응답으로 뭉갭니다.
    """

    def __init__(self, profile_id: str, profile_version: str):
        self.profile_id = profile_id
        self.profile_version = profile_version
        super().__init__(
            f"Unknown ETL profile version: {profile_id} / {profile_version}"
        )


@dataclass(frozen=True)
class ETLProfileActivationView:
    """One profile's activation as an API caller needs to read it."""

    profile_id: str
    display_name: str
    deployment_active_version: str | None
    runtime_override_exists: bool
    runtime_active_version: str | None
    effective_active_version: str | None
    is_active: bool
    # 활성화할 수 있는 버전 전체입니다. 이 값이 없으면 호출자가 "무엇을 고를 수 있는지"
    # 알 수 없어 존재하지 않는 버전을 추측해 보내게 됩니다.
    available_versions: list[str]
    # actor/updated_at은 runtime override가 있을 때만 채웁니다. override가 없는데 값이
    # 있으면 아무도 바꾼 적 없는 상태를 누군가 바꾼 것처럼 보입니다.
    actor_username: str | None
    updated_at: datetime | None


def _activation_row(
    session: Session,
    profile_id: str,
) -> ETLProfileActivation | None:
    return session.scalars(
        select(ETLProfileActivation).where(
            ETLProfileActivation.profile_id == profile_id
        )
    ).one_or_none()


def _to_view(
    activation: ETLProfileActivationState,
    *,
    row: ETLProfileActivation | None,
) -> ETLProfileActivationView:
    return ETLProfileActivationView(
        profile_id=activation.profile_id,
        display_name=get_profile_display_name(activation.profile_id),
        deployment_active_version=activation.deployment_active_version,
        runtime_override_exists=activation.runtime_override_exists,
        runtime_active_version=activation.runtime_active_version,
        effective_active_version=activation.effective_active_version,
        is_active=activation.is_active,
        available_versions=registered_profile_versions(activation.profile_id),
        actor_username=row.actor_username if row is not None else None,
        updated_at=row.updated_at if row is not None else None,
    )


def get_etl_profile_activation(
    session: Session,
    *,
    profile_id: str,
) -> ETLProfileActivationView:
    """Return the deployment default, the runtime override, and what actually applies.

    읽기 전용입니다. 없는 profile_id는 ETLProfileNotFoundError입니다.
    """
    activation = resolve_etl_profile_activation(profile_id, session=session)
    row = _activation_row(session, profile_id) if activation.runtime_override_exists else None
    return _to_view(activation, row=row)


def _normalized_version(profile_id: str, active_version: str | None) -> str | None:
    """Validate the requested version against the preserved archive, or None.

    공백만 있는 값은 비활성으로 해석하지 않습니다. Phase 5A가 registry에서 고정한
    "placeholder 문자열은 비활성 표시가 아니다" 규칙과 같습니다. 비활성을 뜻하는 값은
    JSON null 하나뿐이라, 상태가 모호해질 여지를 두지 않습니다.
    """
    if active_version is None:
        return None
    if not isinstance(active_version, str) or not active_version.strip():
        raise ETLProfileVersionNotFoundError(profile_id, str(active_version))

    stripped = active_version.strip()
    if stripped not in registered_profile_versions(profile_id):
        raise ETLProfileVersionNotFoundError(profile_id, stripped)
    return stripped


def set_etl_profile_activation(
    session: Session,
    *,
    profile_id: str,
    active_version: str | None,
    actor_user_id: int | None,
    actor_username: str | None,
) -> ETLProfileActivationView:
    """Set (or clear) the runtime active version for one allowlisted profile.

    active_version이 None이면 비활성(Policy G의 Deactivate)입니다. archive와 registry
    항목, 과거 etl_load_runs는 그대로 남고 신규 실행만 막힙니다.

    값이 있으면 **registry versions의 정확한 key**여야 합니다. 임의 문자열("999")을
    허용하면 존재하지 않는 버전이 활성으로 저장되고, 그 프로필의 다음 실행이 실행
    시점에 가서야 실패합니다. 그 실패는 운영자가 방금 한 행동과 멀리 떨어져 있어
    원인을 찾기 어렵습니다.

    비활성으로 만들 때는 versions를 검증하지 않습니다. 검증할 버전 자체가 없기 때문이며,
    이는 "잘못된 pointer"가 아니라 "pointer 없음"이라는 별개의 상태입니다.

    actor는 인증된 호출자에서만 받습니다. 요청 body의 사용자 이름을 그대로 저장하면
    누구든 다른 사람 이름으로 기록을 남길 수 있습니다.

    동시에 두 operator가 같은 프로필을 바꾸면 INSERT가 unique index에서 충돌합니다.
    ON CONFLICT DO UPDATE로 한 문장에서 처리해 IntegrityError를 사용자에게 노출하지
    않으며, 결과는 last-write-wins입니다. 이 MVP에서는 그것으로 충분합니다. 진 쪽의
    결정이 흔적 없이 사라지지 않도록 actor_username과 updated_at을 함께 남기므로,
    조회하면 마지막으로 누가 언제 바꿨는지 볼 수 있습니다.
    """
    # 검증을 트랜잭션 밖에서 먼저 합니다. 잘못된 입력이 쓰기 트랜잭션을 열지 않게 하고,
    # 없는 profile_id는 여기서 ETLProfileNotFoundError로 끝납니다.
    get_profile_display_name(profile_id)
    normalized_version = _normalized_version(profile_id, active_version)

    with session.begin():
        session.execute(
            postgresql_insert(ETLProfileActivation)
            .values(
                profile_id=profile_id,
                active_version=normalized_version,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
            )
            .on_conflict_do_update(
                index_elements=[ETLProfileActivation.profile_id],
                set_={
                    "active_version": normalized_version,
                    "actor_user_id": actor_user_id,
                    "actor_username": actor_username,
                    # 같은 값으로 다시 저장했더라도 "언제 확인했는가"는 갱신합니다.
                    # 그 시각 자체가 운영 기록의 일부입니다.
                    "updated_at": func.now(),
                },
            )
        )

    activation = resolve_etl_profile_activation(profile_id, session=session)
    return _to_view(activation, row=_activation_row(session, profile_id))
