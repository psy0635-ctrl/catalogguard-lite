from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from config.database import get_optional_database_url
from db.models import (
    CatalogProductChange,
    CatalogPromotionRollback,
    CatalogPromotionRollbackChange,
    CatalogPromotionRun,
    ETLLoadRun,
)
from db.session import create_database_engine, create_session_factory


class _Rows:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _ReadOnlySession:
    def __init__(self, rows, *, parent_exists=True):
        self.rows = rows
        self.parent_exists = parent_exists
        self.scalar_calls = 0

    def get(self, _model, _identifier):
        return object() if self.parent_exists else None

    def execute(self, _statement):
        return _Rows(self.rows)

    def scalars(self, _statement):
        return _Rows(self.rows)

    def scalar(self, _statement):
        self.scalar_calls += 1
        return len(self.rows)

    def commit(self):
        raise AssertionError("query service must not commit")

    def rollback(self):
        raise AssertionError("query service must not rollback")


def _rollback(**overrides):
    created_at = datetime(2026, 8, 11, tzinfo=timezone.utc)
    values = {
        "id": 10,
        "target_promotion_run_id": 7,
        "status": "succeeded",
        "preview_hash": "a" * 64,
        "preview_schema_version": "1",
        "restored_count": 2,
        "deleted_count": 1,
        "conflict_count": 0,
        "failure_code": None,
        "safe_failure_message": None,
        "started_at": created_at,
        "completed_at": created_at + timedelta(seconds=1),
        "created_at": created_at,
        "actor_username": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rollback_change(**overrides):
    created_at = datetime(2026, 8, 11, tzinfo=timezone.utc)
    values = {
        "id": 100,
        "rollback_run_id": 10,
        "original_audit_id": 50,
        "catalog_product_id": 25,
        "action": "delete",
        "changed_fields": {
            "product_name": {"before": "Product A", "after": None}
        },
        "before_data": {"product_name": "Product A"},
        "after_data": None,
        "created_at": created_at,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_list_catalog_promotion_rollbacks_maps_rows_without_writes():
    from db.catalog_promotion_rollback_query_service import (
        list_catalog_promotion_rollbacks,
    )

    session = _ReadOnlySession([_rollback()])

    result = list_catalog_promotion_rollbacks(session, limit=20, offset=0)

    assert result.total == 1
    assert result.limit == 20
    assert result.offset == 0
    assert result.items[0].rollback_run_id == 10
    assert result.items[0].target_promotion_run_id == 7
    assert result.items[0].actor_username is None
    assert session.scalar_calls == 1


def test_get_catalog_promotion_rollback_detail_maps_preview_fields_or_none():
    from db.catalog_promotion_rollback_query_service import (
        get_catalog_promotion_rollback_detail,
    )

    session = _ReadOnlySession([_rollback()])
    missing_session = _ReadOnlySession([])

    detail = get_catalog_promotion_rollback_detail(
        session,
        rollback_run_id=10,
    )

    assert detail is not None
    assert detail.rollback_run_id == 10
    assert detail.preview_hash == "a" * 64
    assert detail.preview_schema_version == "1"
    assert detail.actor_username is None
    assert get_catalog_promotion_rollback_detail(
        missing_session,
        rollback_run_id=999999,
    ) is None


def test_list_catalog_promotion_rollback_changes_maps_rows_without_writes():
    from db.catalog_promotion_rollback_query_service import (
        list_catalog_promotion_rollback_changes,
    )

    session = _ReadOnlySession([_rollback_change()])

    result = list_catalog_promotion_rollback_changes(
        session,
        rollback_run_id=10,
        limit=20,
        offset=0,
    )

    assert result is not None
    assert result.total == 1
    assert result.limit == 20
    assert result.offset == 0
    assert result.items[0].rollback_change_id == 100
    assert result.items[0].rollback_run_id == 10
    assert result.items[0].original_audit_id == 50
    assert result.items[0].catalog_product_id == 25
    assert result.items[0].action == "delete"
    assert result.items[0].changed_fields == {
        "product_name": {"before": "Product A", "after": None}
    }
    assert result.items[0].before_data == {"product_name": "Product A"}
    assert result.items[0].after_data is None
    assert result.items[0].created_at == datetime(
        2026,
        8,
        11,
        tzinfo=timezone.utc,
    )
    assert session.scalar_calls == 1


def test_list_catalog_promotion_rollback_changes_distinguishes_missing_parent():
    from db.catalog_promotion_rollback_query_service import (
        list_catalog_promotion_rollback_changes,
    )

    result = list_catalog_promotion_rollback_changes(
        _ReadOnlySession([], parent_exists=False),
        rollback_run_id=999999,
        limit=20,
        offset=0,
    )

    assert result is None


@pytest.fixture()
def seeded_rollbacks():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    profile_prefix = f"rollback_query_{uuid4().hex}"
    base_time = datetime(2026, 8, 11, tzinfo=timezone.utc)

    def add_target(index: int) -> CatalogPromotionRun:
        load = ETLLoadRun(
            source_filename=f"rollback-{index}.csv",
            profile_name=f"{profile_prefix}_{index}",
            profile_version="1",
            input_file_sha256=f"{index}" * 64,
            output_file_sha256=f"{index + 3}" * 64,
            loaded_rows=1,
            total_rows=1,
            rejected_rows=0,
            error_counts={},
            reject_details_stored=False,
            created_at=base_time + timedelta(minutes=index),
        )
        session.add(load)
        session.flush()
        promotion = CatalogPromotionRun(
            etl_load_run_id=load.id,
            status="succeeded",
            preview_hash=f"{index}" * 64,
            preview_schema_version="1",
            inspection_version="1",
            inserted_count=1,
            updated_count=0,
            unchanged_count=0,
            blocked_count=0,
            error_count=0,
            warning_count=0,
            started_at=base_time,
            completed_at=base_time + timedelta(seconds=1),
            created_at=base_time,
        )
        session.add(promotion)
        session.flush()
        return promotion

    def add_rollback(
        target: CatalogPromotionRun,
        *,
        status: str,
        created_at: datetime,
        actor_username: str | None,
    ) -> CatalogPromotionRollback:
        rollback = CatalogPromotionRollback(
            target_promotion_run_id=target.id,
            status=status,
            preview_hash=str(target.id % 10) * 64,
            preview_schema_version="1",
            restored_count=2,
            deleted_count=1,
            conflict_count=1 if status == "blocked" else 0,
            failure_code=None if status == "succeeded" else f"{status}_rollback",
            safe_failure_message=(
                None if status == "succeeded" else f"Rollback was {status}."
            ),
            started_at=created_at,
            completed_at=created_at + timedelta(seconds=1),
            created_at=created_at,
            actor_username=actor_username,
        )
        session.add(rollback)
        session.flush()
        return rollback

    oldest_target = add_target(1)
    middle_target = add_target(2)
    newest_target = add_target(3)
    oldest = add_rollback(
        oldest_target,
        status="succeeded",
        created_at=base_time,
        actor_username="operator-old",
    )
    tied_time = base_time + timedelta(minutes=1)
    middle = add_rollback(
        middle_target,
        status="failed",
        created_at=tied_time,
        actor_username=None,
    )
    newest = add_rollback(
        newest_target,
        status="blocked",
        created_at=tied_time,
        actor_username="operator-new",
    )
    session.commit()

    try:
        yield session, oldest, middle, newest
    finally:
        session.rollback()
        session.close()
        with session_factory() as cleanup:
            load_ids = select(ETLLoadRun.id).where(
                ETLLoadRun.profile_name.like(f"{profile_prefix}%")
            )
            promotion_ids = select(CatalogPromotionRun.id).where(
                CatalogPromotionRun.etl_load_run_id.in_(load_ids)
            )
            cleanup.execute(
                delete(CatalogPromotionRollback).where(
                    CatalogPromotionRollback.target_promotion_run_id.in_(
                        promotion_ids
                    )
                )
            )
            cleanup.execute(
                delete(CatalogPromotionRun).where(
                    CatalogPromotionRun.id.in_(promotion_ids)
                )
            )
            cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id.in_(load_ids)))
            cleanup.commit()
        engine.dispose()


@pytest.fixture()
def seeded_rollback_changes(seeded_rollbacks):
    session, _oldest, middle, newest = seeded_rollbacks
    created_at = datetime(2026, 8, 11, 1, tzinfo=timezone.utc)

    delete_audit = CatalogProductChange(
        promotion_run_id=newest.target_promotion_run_id,
        catalog_product_id=900001,
        action="insert",
        changed_fields={"product_name": {"before": None, "after": "Product A"}},
        before_data=None,
        after_data={"product_name": "Product A"},
        created_at=created_at,
    )
    restore_audit = CatalogProductChange(
        promotion_run_id=newest.target_promotion_run_id,
        catalog_product_id=900002,
        action="update",
        changed_fields={
            "product_name": {"before": "Product B", "after": "Product B+"}
        },
        before_data={"product_name": "Product B"},
        after_data={"product_name": "Product B+"},
        created_at=created_at,
    )
    session.add_all([delete_audit, restore_audit])
    session.flush()

    delete_change = CatalogPromotionRollbackChange(
        rollback_run_id=newest.id,
        original_audit_id=delete_audit.id,
        catalog_product_id=delete_audit.catalog_product_id,
        action="delete",
        changed_fields={
            "product_name": {"before": "Product A", "after": None}
        },
        before_data={"product_name": "Product A"},
        after_data=None,
        created_at=created_at,
    )
    restore_change = CatalogPromotionRollbackChange(
        rollback_run_id=newest.id,
        original_audit_id=restore_audit.id,
        catalog_product_id=restore_audit.catalog_product_id,
        action="restore",
        changed_fields={
            "product_name": {"before": "Product B+", "after": "Product B"}
        },
        before_data={"product_name": "Product B+"},
        after_data={"product_name": "Product B"},
        created_at=created_at,
    )
    session.add_all([delete_change, restore_change])
    session.commit()

    try:
        yield session, middle, newest, delete_change, restore_change
    finally:
        session.rollback()
        session.execute(
            delete(CatalogPromotionRollbackChange).where(
                CatalogPromotionRollbackChange.id.in_(
                    [delete_change.id, restore_change.id]
                )
            )
        )
        session.execute(
            delete(CatalogProductChange).where(
                CatalogProductChange.id.in_([delete_audit.id, restore_audit.id])
            )
        )
        session.commit()


def test_list_catalog_promotion_rollbacks_sorts_latest_and_paginates(
    seeded_rollbacks,
):
    from db.catalog_promotion_rollback_query_service import (
        list_catalog_promotion_rollbacks,
    )

    session, oldest, middle, newest = seeded_rollbacks

    first_page = list_catalog_promotion_rollbacks(session, limit=2, offset=0)
    second_page = list_catalog_promotion_rollbacks(session, limit=2, offset=2)

    assert [item.rollback_run_id for item in first_page.items] == [
        newest.id,
        middle.id,
    ]
    assert first_page.total == 3
    assert first_page.limit == 2
    assert first_page.offset == 0
    assert [item.rollback_run_id for item in second_page.items] == [oldest.id]


def test_list_catalog_promotion_rollbacks_filters_items_and_total(
    seeded_rollbacks,
):
    from db.catalog_promotion_rollback_query_service import (
        list_catalog_promotion_rollbacks,
    )

    session, _oldest, middle, newest = seeded_rollbacks

    failed = list_catalog_promotion_rollbacks(
        session,
        limit=20,
        offset=0,
        status="failed",
    )
    target = list_catalog_promotion_rollbacks(
        session,
        limit=20,
        offset=0,
        target_promotion_run_id=newest.target_promotion_run_id,
    )

    assert [item.rollback_run_id for item in failed.items] == [middle.id]
    assert failed.total == 1
    assert [item.rollback_run_id for item in target.items] == [newest.id]
    assert target.total == 1


def test_get_catalog_promotion_rollback_detail_returns_existing_or_none(
    seeded_rollbacks,
):
    from db.catalog_promotion_rollback_query_service import (
        get_catalog_promotion_rollback_detail,
    )

    session, _oldest, middle, _newest = seeded_rollbacks

    detail = get_catalog_promotion_rollback_detail(
        session,
        rollback_run_id=middle.id,
    )

    assert detail is not None
    assert detail.rollback_run_id == middle.id
    assert detail.target_promotion_run_id == middle.target_promotion_run_id
    assert detail.status == "failed"
    assert detail.preview_hash == middle.preview_hash
    assert detail.preview_schema_version == "1"
    assert detail.actor_username is None
    assert get_catalog_promotion_rollback_detail(
        session,
        rollback_run_id=999999999,
    ) is None


def test_list_catalog_promotion_rollback_changes_sorts_and_paginates(
    seeded_rollback_changes,
):
    from db.catalog_promotion_rollback_query_service import (
        list_catalog_promotion_rollback_changes,
    )

    session, _empty, newest, delete_change, restore_change = seeded_rollback_changes

    first_page = list_catalog_promotion_rollback_changes(
        session,
        rollback_run_id=newest.id,
        limit=1,
        offset=0,
    )
    second_page = list_catalog_promotion_rollback_changes(
        session,
        rollback_run_id=newest.id,
        limit=1,
        offset=1,
    )

    assert first_page is not None
    assert [item.rollback_change_id for item in first_page.items] == [
        restore_change.id
    ]
    assert first_page.total == 2
    assert first_page.limit == 1
    assert first_page.offset == 0
    assert second_page is not None
    assert [item.rollback_change_id for item in second_page.items] == [
        delete_change.id
    ]
    assert second_page.total == 2
    assert second_page.limit == 1
    assert second_page.offset == 1


def test_list_catalog_promotion_rollback_changes_returns_empty_for_existing_parent(
    seeded_rollback_changes,
):
    from db.catalog_promotion_rollback_query_service import (
        list_catalog_promotion_rollback_changes,
    )

    session, empty, _newest, _delete_change, _restore_change = seeded_rollback_changes

    result = list_catalog_promotion_rollback_changes(
        session,
        rollback_run_id=empty.id,
        limit=20,
        offset=0,
    )

    assert result is not None
    assert result.items == []
    assert result.total == 0


def test_list_catalog_promotion_rollback_changes_returns_none_for_missing_parent(
    seeded_rollback_changes,
):
    from db.catalog_promotion_rollback_query_service import (
        list_catalog_promotion_rollback_changes,
    )

    session, _empty, _newest, _delete_change, _restore_change = seeded_rollback_changes

    assert list_catalog_promotion_rollback_changes(
        session,
        rollback_run_id=999999999,
        limit=20,
        offset=0,
    ) is None
