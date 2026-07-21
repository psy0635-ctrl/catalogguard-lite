from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any, Literal

from config.settings import get_inspection_job_ttl_seconds, get_redis_job_url


InspectionJobStatus = Literal["queued", "running", "succeeded", "failed"]
JOB_KEY_PREFIX = "catalogguard:inspection-job:"


@dataclass(frozen=True)
class InspectionJobState:
    job_id: str
    status: InspectionJobStatus
    created_at: datetime
    updated_at: datetime
    source_filename: str | None = None
    created: bool | None = None
    inspection_run_id: int | None = None
    summary: dict[str, int] | None = None
    error_code: str | None = None
    safe_error_message: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _deserialize_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class RedisJobStore:
    def __init__(
        self,
        redis_client: Any,
        *,
        ttl_seconds: int,
        key_prefix: str = JOB_KEY_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix

    def _key(self, job_id: str) -> str:
        return f"{self._key_prefix}{job_id}"

    def _save(self, state: InspectionJobState) -> None:
        payload = asdict(state)
        payload["created_at"] = _serialize_datetime(state.created_at)
        payload["updated_at"] = _serialize_datetime(state.updated_at)
        self._redis.set(
            self._key(state.job_id),
            json.dumps(payload, ensure_ascii=False),
            ex=self._ttl_seconds,
        )

    def create_queued_job(
        self,
        job_id: str,
        *,
        source_filename: str,
        created_at: datetime | None = None,
    ) -> InspectionJobState:
        timestamp = created_at or _utc_now()
        state = InspectionJobState(
            job_id=job_id,
            status="queued",
            created_at=timestamp,
            updated_at=timestamp,
            source_filename=source_filename,
        )
        self._save(state)
        return state

    def get_job(self, job_id: str) -> InspectionJobState | None:
        raw_value = self._redis.get(self._key(job_id))
        if raw_value is None:
            return None
        payload = json.loads(raw_value)
        return InspectionJobState(
            job_id=str(payload["job_id"]),
            status=payload["status"],
            created_at=_deserialize_datetime(payload["created_at"]),
            updated_at=_deserialize_datetime(payload["updated_at"]),
            source_filename=payload.get("source_filename"),
            created=payload.get("created"),
            inspection_run_id=payload.get("inspection_run_id"),
            summary=payload.get("summary"),
            error_code=payload.get("error_code"),
            safe_error_message=payload.get("safe_error_message"),
        )

    def update_job(
        self,
        job_id: str,
        *,
        status: InspectionJobStatus,
        updated_at: datetime | None = None,
        **fields: Any,
    ) -> InspectionJobState:
        existing_state = self.get_job(job_id)
        if existing_state is None:
            raise KeyError(f"inspection job not found: {job_id}")
        state_data = asdict(existing_state)
        state_data.update(fields)
        state_data["status"] = status
        state_data["updated_at"] = updated_at or _utc_now()
        state = InspectionJobState(**state_data)
        self._save(state)
        return state

    def delete_job(self, job_id: str) -> None:
        self._redis.delete(self._key(job_id))


_default_store: RedisJobStore | None = None


def get_redis_job_store() -> RedisJobStore:
    global _default_store
    if _default_store is None:
        import redis

        _default_store = RedisJobStore(
            redis.Redis.from_url(get_redis_job_url(), decode_responses=True),
            ttl_seconds=get_inspection_job_ttl_seconds(),
        )
    return _default_store
