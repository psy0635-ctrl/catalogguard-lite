from datetime import datetime, timezone
import json

from services.redis_job_store import RedisJobStore


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.deleted: list[str] = []

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.set_calls.append((key, value, ex))

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


def test_redis_job_store_round_trips_state_with_ttl() -> None:
    redis_client = FakeRedis()
    store = RedisJobStore(redis_client, ttl_seconds=900)
    created_at = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)

    state = store.create_queued_job(
        "job-1",
        source_filename="products.csv",
        created_at=created_at,
        actor_user_id=41,
        actor_username="operator01",
    )

    assert state.status == "queued"
    assert redis_client.set_calls[0][0] == "catalogguard:inspection-job:job-1"
    assert redis_client.set_calls[0][2] == 900
    stored_payload = json.loads(redis_client.set_calls[0][1])
    assert stored_payload["job_id"] == "job-1"
    assert stored_payload["status"] == "queued"
    assert stored_payload["actor_user_id"] == 41
    assert stored_payload["actor_username"] == "operator01"
    assert store.get_job("job-1") == state


def test_redis_job_store_deserializes_legacy_payload_without_actor_fields() -> None:
    redis_client = FakeRedis()
    store = RedisJobStore(redis_client, ttl_seconds=900)
    redis_client.values["catalogguard:inspection-job:legacy-job"] = json.dumps(
        {
            "job_id": "legacy-job",
            "status": "queued",
            "created_at": "2026-07-21T16:00:00+00:00",
            "updated_at": "2026-07-21T16:00:00+00:00",
            "source_filename": "legacy.csv",
        }
    )

    state = store.get_job("legacy-job")

    assert state is not None
    assert state.actor_user_id is None
    assert state.actor_username is None


def test_redis_job_store_updates_status_and_result_fields() -> None:
    redis_client = FakeRedis()
    store = RedisJobStore(redis_client, ttl_seconds=900)
    created_at = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 7, 21, 16, 1, tzinfo=timezone.utc)
    store.create_queued_job(
        "job-2",
        source_filename="products.csv",
        created_at=created_at,
    )

    state = store.update_job(
        "job-2",
        status="succeeded",
        updated_at=updated_at,
        created=True,
        inspection_run_id=123,
        summary={
            "total_products": 5,
            "total_issues": 2,
            "error_count": 1,
            "warning_count": 1,
        },
    )

    assert state.status == "succeeded"
    assert state.created is True
    assert state.inspection_run_id == 123
    assert state.summary == {
        "total_products": 5,
        "total_issues": 2,
        "error_count": 1,
        "warning_count": 1,
    }
    assert state.created_at == created_at
    assert state.updated_at == updated_at


def test_redis_job_store_returns_none_for_expired_or_unknown_job() -> None:
    store = RedisJobStore(FakeRedis(), ttl_seconds=900)

    assert store.get_job("missing") is None
