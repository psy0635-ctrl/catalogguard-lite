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

Phase 5B.4에서 여기에 append-only history가 더해졌습니다. current-state 표
(etl_profile_activations)는 그대로 두고, **성공한 operator 명령**을 별도 표
(etl_profile_activation_events)에 하나씩 남깁니다. 두 쓰기는 반드시 같은 트랜잭션
안에서 일어납니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from db.models import ETLProfileActivation, ETLProfileActivationEvent
from etl.profile_loader import (
    ETLProfileActivationState,
    get_profile_display_name,
    registered_profile_versions,
    resolve_etl_profile_activation,
)


class PendingWriteBeforeActivationReadError(RuntimeError):
    """Raised when a caller hands over a session that already holds pending writes.

    아래 end_activation_read_transaction()이 왜 필요한지와 함께 읽어야 합니다.
    """


def end_activation_read_transaction(session: Session) -> None:
    """End the read-only transaction that an activation lookup autobegan.

    신규 ETL 실행 경로는 activation을 확인한 뒤 곧바로 쓰기 트랜잭션을 엽니다
    (load_standard_csv()의 `with session.begin()`). 확인 SELECT가 session을 autobegin
    시킨 채로 두면 그 begin()이 "A transaction is already begun"으로 실패합니다.
    조회는 읽기 전용이므로 여기서 끝내도 잃을 것이 없고, 그 사이에 끼는 run_pipeline()은
    파일 I/O라 idle 트랜잭션을 붙들고 있을 이유도 없습니다.

    그냥 rollback()만 하면 위험이 하나 생깁니다. 나중에 누군가 이 앞에 쓰기를 추가하면
    그 쓰기가 **조용히** 사라집니다. 지금까지 같은 상황은 load_standard_csv()의 begin()이
    InvalidRequestError로 시끄럽게 실패시켜 줬는데, rollback이 그 신호를 지웁니다.
    그래서 rollback 전에 보류 중인 ORM 쓰기가 있으면 먼저 소리를 냅니다.

    한계를 정확히 적어 둡니다. 이 검사는 ORM 단위 작업(new/dirty/deleted)만 봅니다.
    session.execute(insert(...)) 같은 Core 쓰기는 여기서 감지되지 않고 함께 rollback
    됩니다. 다만 그런 호출자는 원래도 허용되지 않았습니다 — load_standard_csv()가 자기
    트랜잭션을 여는 구조라, run_web_etl()에 넘기는 session은 트랜잭션이 열려 있지 않아야
    한다는 것이 이 함수 이전부터의 계약입니다.
    """
    if session.new or session.dirty or session.deleted:
        raise PendingWriteBeforeActivationReadError(
            "run_web_etl() requires a session without pending writes."
        )
    session.rollback()


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


# 세 명령이 남기는 event의 모양을 한 곳에서 정합니다. 각 함수가 따로 만들면 한쪽만
# 필드가 빠지거나 다른 값을 넣는 차이가 조용히 생깁니다. 허용되는 action 값
# (activate/deactivate/reset)은 DB CHECK 제약이 최종적으로 강제합니다.
def _record_activation_event(
    session: Session,
    *,
    action: str,
    activation: ETLProfileActivationState,
    actor_user_id: int | None,
    actor_username: str | None,
) -> None:
    """Append one event for a command the server just accepted.

    **커밋하지 않습니다.** 트랜잭션 경계는 호출자(set_/reset_)가 가집니다. 여기서
    commit하면 상태 변경과 기록이 서로 다른 트랜잭션으로 갈라져, 뒤이어 실패했을 때
    기록만 남거나 상태만 바뀝니다.

    activation은 **명령 직후의 상태**여야 합니다. 호출자가 같은 트랜잭션 안에서
    resolve한 값을 넘기므로, 여기서 registry를 다시 읽지 않습니다.
    """
    session.add(
        ETLProfileActivationEvent(
            profile_id=activation.profile_id,
            action=action,
            deployment_active_version=activation.deployment_active_version,
            runtime_override_exists=activation.runtime_override_exists,
            runtime_active_version=activation.runtime_active_version,
            effective_active_version=activation.effective_active_version,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
        )
    )


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
    않으며, 결과는 last-write-wins입니다.

    **이 표는 append-only history가 아니라 프로필당 current-state row 하나입니다.**
    A가 deactivate하고 B가 v2를 activate하면 최종 row에는 B의 active_version과
    actor_username, updated_at만 남습니다. A의 이전 결정은 보존되지 않습니다.
    actor_username과 updated_at은 "현재 상태를 마지막으로 만든 것이 누구/언제인가"일
    뿐이고, 그것으로 activation 변경 이력을 되짚을 수는 없습니다.

    이 표 자체는 여전히 이력이 아닙니다. 성공한 명령의 append-only 기록은 Phase 5B.4가
    추가한 **별도 표**(etl_profile_activation_events)에 남고, 아래에서 이 upsert와
    **같은 트랜잭션 안에서** 함께 기록합니다. 두 쓰기를 다른 트랜잭션으로 나누면 상태만
    바뀌고 기록이 없거나, 기록만 있고 상태가 안 바뀐 순간이 생깁니다.
    """
    # 검증을 트랜잭션 밖에서 먼저 합니다. 잘못된 입력이 쓰기 트랜잭션을 열지 않게 하고,
    # 없는 profile_id는 여기서 ETLProfileNotFoundError로 끝납니다. 실패한 요청은 상태도
    # history event도 만들지 않아야 하므로, 이 순서가 audit 정확성의 일부입니다.
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
        # event가 담는 것은 "이 명령이 성공한 직후의 상태"입니다. 그래서 같은 트랜잭션
        # 안에서 resolve합니다. 여기서 effective를 다시 계산하지 않는 이유는 계속
        # 같습니다 — 계산하는 곳은 resolve_etl_profile_activation() 한 곳뿐입니다.
        _record_activation_event(
            session,
            action="activate" if normalized_version is not None else "deactivate",
            activation=resolve_etl_profile_activation(profile_id, session=session),
            actor_user_id=actor_user_id,
            actor_username=actor_username,
        )

    # 응답은 지금까지와 같이 커밋 뒤에 다시 읽습니다. row의 updated_at처럼 DB가 채우는
    # 값을 그대로 보여 주기 위해서이고, 이 endpoint의 기존 응답 계약을 바꾸지 않습니다.
    activation = resolve_etl_profile_activation(profile_id, session=session)
    return _to_view(activation, row=_activation_row(session, profile_id))


def reset_etl_profile_activation(
    session: Session,
    *,
    profile_id: str,
    actor_user_id: int | None,
    actor_username: str | None,
) -> ETLProfileActivationView:
    """Remove the runtime override so the deployment default applies again.

    Phase 5B.3. set_etl_profile_activation(active_version=None)과 **다른 동작**입니다.
    그쪽은 "운영자가 명시적으로 내렸다"는 상태를 만들고, 이쪽은 그 상태 자체를 지웁니다.

    | 동작 | row | effective |
    | --- | --- | --- |
    | PUT active_version="2" | 있음 (active_version='2') | "2" |
    | PUT active_version=null | 있음 (active_version=NULL) | None (명시적 비활성) |
    | DELETE (여기) | 없음 | 배포 registry의 active_version |

    **되살아날 수 있습니다.** 명시적 비활성 override를 지우면 배포 기본값이 다시
    적용되므로, 배포 기본값이 활성이면 그 프로필은 reset과 동시에 활성이 됩니다.
    호출자(API/UI)는 이것을 단순한 정리 동작으로 보여 주면 안 됩니다.

    idempotent합니다. override가 이미 없어도 오류를 내지 않고 배포 기본값 상태를
    그대로 돌려줍니다. DELETE를 두 번 보내는 것은 재시도이지 오류가 아니기 때문입니다.
    다만 없는 profile_id는 계속 ETLProfileNotFoundError입니다 — "지울 것이 없다"와
    "그런 프로필이 없다"는 운영자가 해야 할 일이 다릅니다.

    이 표는 current-state row 하나뿐이라, 지우면 그 row의 actor_username/updated_at/
    active_version도 함께 사라집니다. **그래서 이 명령을 누가 언제 내렸는지가 남는 곳은
    Phase 5B.4의 history 표뿐입니다.** 이 함수가 actor를 받는 이유가 그것입니다 — 저장할
    current-state row는 없어지지만, 명령 자체는 기록되어야 합니다.

    그 결과 reset 직후에는 current-state 응답의 actor_username/updated_at이 None이고
    history에는 actor가 남습니다. 모순이 아니라 서로 다른 질문에 대한 답입니다. 전자는
    "지금 이 override를 만든 사람"이고(override 자체가 없으므로 없음), 후자는 "그 override를
    지운 명령을 내린 사람"입니다.

    override가 원래 없어 지운 row가 0건이어도 event는 남깁니다. API는 idempotent 200이지만
    이것은 **성공한 운영 명령**이고, 이 표가 기록하는 단위가 상태 변화가 아니라 명령이기
    때문입니다.
    """
    # 검증을 트랜잭션 밖에서 먼저 합니다. set_etl_profile_activation()과 같은 순서로,
    # 없는 profile_id는 쓰기 트랜잭션을 열기 전에 여기서 끝납니다. 실패한 요청은 history
    # event도 남기지 않습니다.
    get_profile_display_name(profile_id)

    with session.begin():
        session.execute(
            delete(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == profile_id
            )
        )
        # DELETE와 event INSERT가 같은 트랜잭션입니다. event 기록이 실패하면 override
        # 삭제도 함께 rollback되어, "지워졌는데 기록이 없는" 상태가 생기지 않습니다.
        _record_activation_event(
            session,
            action="reset",
            activation=resolve_etl_profile_activation(profile_id, session=session),
            actor_user_id=actor_user_id,
            actor_username=actor_username,
        )

    activation = resolve_etl_profile_activation(profile_id, session=session)
    # row를 지웠으므로 actor/updated_at은 항상 None입니다. _to_view()가 row=None에서
    # 그렇게 채우므로 여기서 따로 계산하지 않습니다.
    return _to_view(activation, row=None)


@dataclass(frozen=True)
class ETLProfileActivationEventView:
    """One recorded activation command as an API caller needs to read it.

    actor_user_id는 일부러 없습니다. DB 관계용 ID이고, 화면이 필요로 하는 것은 삭제된
    사용자에게도 남는 actor_username snapshot입니다. view에 두지 않으면 응답에 실수로
    새어 나갈 자리 자체가 없습니다.
    """

    event_id: int
    profile_id: str
    action: str
    deployment_active_version: str | None
    runtime_override_exists: bool
    runtime_active_version: str | None
    effective_active_version: str | None
    actor_username: str | None
    created_at: datetime


@dataclass(frozen=True)
class ETLProfileActivationHistory:
    items: list[ETLProfileActivationEventView]
    total: int
    limit: int
    offset: int


def _to_event_view(
    event: ETLProfileActivationEvent,
) -> ETLProfileActivationEventView:
    return ETLProfileActivationEventView(
        event_id=event.id,
        profile_id=event.profile_id,
        action=event.action,
        deployment_active_version=event.deployment_active_version,
        runtime_override_exists=event.runtime_override_exists,
        runtime_active_version=event.runtime_active_version,
        effective_active_version=event.effective_active_version,
        actor_username=event.actor_username,
        created_at=event.created_at,
    )


def list_etl_profile_activation_history(
    session: Session,
    *,
    profile_id: str,
    limit: int,
    offset: int,
) -> ETLProfileActivationHistory:
    """List one profile's recorded activation commands, newest first.

    읽기 전용입니다. 이 표에 대한 UPDATE/DELETE/purge 경로는 만들지 않습니다 —
    append-only는 애플리케이션 계약이고, 그 계약은 "쓰기 함수가 INSERT 하나뿐"이라는
    사실로 지켜집니다.

    한 번에 한 프로필만 조회합니다. 전체 프로필을 섞어 보여 주는 화면이 아직 없고,
    profile_id index가 그대로 쓰이는 질의 형태이기도 합니다.

    정렬은 created_at DESC, id DESC입니다. created_at은 트랜잭션 시각이라 같은 값이
    나올 수 있어 id로 tie를 끊습니다. 다만 이 순서를 분산 환경의 절대적 인과 순서로
    읽으면 안 됩니다 — 동시에 성공한 두 명령의 상대 순서는 이 표가 답할 수 있는 질문이
    아닙니다(activation의 동시성 정책은 지금도 last-write-wins입니다).

    없는 profile_id는 ETLProfileNotFoundError입니다. registry가 allowlist이므로,
    registry에서 사라진 과거 프로필의 event는 이 API로 조회할 수 없습니다. 그 상황이
    실제로 생기면 별도 조회 경로를 설계해야 합니다.
    """
    get_profile_display_name(profile_id)

    events = list(
        session.scalars(
            select(ETLProfileActivationEvent)
            .where(ETLProfileActivationEvent.profile_id == profile_id)
            .order_by(
                ETLProfileActivationEvent.created_at.desc(),
                ETLProfileActivationEvent.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = int(
        session.scalar(
            select(func.count())
            .select_from(ETLProfileActivationEvent)
            .where(ETLProfileActivationEvent.profile_id == profile_id)
        )
        or 0
    )
    return ETLProfileActivationHistory(
        items=[_to_event_view(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )
