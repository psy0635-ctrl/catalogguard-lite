# 역할: 같은 공급사의 최신/직전 ETL 배치 비교와 오류 코드 집계 정책을 PostgreSQL로 검증합니다.
from datetime import datetime, timedelta, timezone
from itertools import count
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from config.database import get_optional_database_url
from db.etl_quality_observability_service import (
    DEFAULT_BATCH_LIMIT,
    MAX_BATCH_LIMIT,
    MIN_BATCH_LIMIT,
    get_etl_quality_observability,
    list_etl_quality_observability_profiles,
)
from db.models import ETLLoadRun
from db.session import create_database_engine, create_session_factory


BASE_TIME = datetime(2026, 8, 20, 9, tzinfo=timezone.utc)


@pytest.fixture()
def postgres_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    profile_prefix = f"observability_test_{uuid4().hex}"
    try:
        yield session, profile_prefix
    finally:
        session.rollback()
        session.close()
        with session_factory() as cleanup:
            cleanup.execute(
                delete(ETLLoadRun).where(
                    ETLLoadRun.profile_name.like(f"{profile_prefix}%")
                )
            )
            cleanup.commit()
        engine.dispose()


_hash_counter = count(1)


def _unique_hash() -> str:
    return f"{next(_hash_counter):064d}"


def _add_run(
    session,
    *,
    profile_name,
    minutes,
    total_rows=None,
    rejected_rows=None,
    error_counts=None,
    created_at=None,
):
    """Insert one ETL batch. total_rows=None이면 quality metadata가 없는 legacy batch입니다."""
    loaded_rows = 0 if total_rows is None else total_rows - rejected_rows
    run = ETLLoadRun(
        source_filename="vendor_products.csv",
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256=_unique_hash(),
        output_file_sha256=_unique_hash(),
        loaded_rows=loaded_rows,
        total_rows=total_rows,
        rejected_rows=rejected_rows,
        error_counts=error_counts,
        created_at=created_at or (BASE_TIME + timedelta(minutes=minutes)),
    )
    session.add(run)
    session.flush()
    return run


def _observe(session, profile_name, **kwargs):
    return get_etl_quality_observability(session, profile_name=profile_name, **kwargs)


def test_returns_only_recent_batches_of_the_requested_profile(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_fashion"
    for minutes in range(1, 5):
        _add_run(
            session,
            profile_name=profile_name,
            minutes=minutes,
            total_rows=100,
            rejected_rows=minutes,
            error_counts={"INVALID_PRICE": minutes},
        )

    result = _observe(session, profile_name, limit=2)

    assert result.profile_name == profile_name
    assert result.limit == 2
    assert result.batch_count == 2
    # recent_batches는 오래된 배치부터 최신 배치 순서입니다.
    assert [item.rejected_rows for item in result.recent_batches] == [3, 4]
    assert result.latest_batch.rejected_rows == 4
    assert result.previous_batch.rejected_rows == 3


def test_excludes_other_profiles_even_when_names_share_a_prefix(postgres_session):
    session, prefix = postgres_session
    target = f"{prefix}_fashion"
    lookalike = f"{prefix}_fashion_outlet"
    _add_run(
        session,
        profile_name=target,
        minutes=1,
        total_rows=100,
        rejected_rows=2,
        error_counts={"INVALID_PRICE": 2},
    )
    _add_run(
        session,
        profile_name=lookalike,
        minutes=2,
        total_rows=100,
        rejected_rows=90,
        error_counts={"MISSING_CATEGORY": 90},
    )

    result = _observe(session, target)

    # 부분 일치였다면 lookalike 배치가 최신으로 잡혀 다른 공급사와 비교하게 됩니다.
    assert result.batch_count == 1
    assert result.latest_batch.rejected_rows == 2
    assert result.previous_batch is None
    assert result.direction == "no_baseline"
    assert [item.error_code for item in result.error_codes] == ["INVALID_PRICE"]


def test_uses_id_to_break_created_at_ties_deterministically(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_tie"
    same_moment = BASE_TIME + timedelta(minutes=5)
    older = _add_run(
        session,
        profile_name=profile_name,
        minutes=0,
        created_at=same_moment,
        total_rows=100,
        rejected_rows=1,
        error_counts={"INVALID_PRICE": 1},
    )
    newer = _add_run(
        session,
        profile_name=profile_name,
        minutes=0,
        created_at=same_moment,
        total_rows=100,
        rejected_rows=2,
        error_counts={"INVALID_PRICE": 2},
    )

    result = _observe(session, profile_name)

    assert newer.id > older.id
    assert result.latest_batch.etl_load_run_id == newer.id
    assert result.previous_batch.etl_load_run_id == older.id


def test_computes_rejection_rate_and_percentage_point_delta(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_delta"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=100,
        rejected_rows=4,
        error_counts={"INVALID_PRICE": 4},
    )
    _add_run(
        session,
        profile_name=profile_name,
        minutes=2,
        total_rows=100,
        rejected_rows=9,
        error_counts={"INVALID_PRICE": 9},
    )

    result = _observe(session, profile_name)

    assert result.previous_batch.rejection_rate == 4.0
    assert result.latest_batch.rejection_rate == 9.0
    # 퍼센트 변화율(125% 증가)이 아니라 퍼센트 포인트 차이(+5.0%p)입니다.
    assert result.rejection_rate_delta == 5.0
    assert result.direction == "worsened"


@pytest.mark.parametrize(
    ("previous_rejected", "latest_rejected", "expected_direction", "expected_delta"),
    [
        (10, 3, "improved", -7.0),
        (5, 5, "unchanged", 0.0),
        (3, 10, "worsened", 7.0),
    ],
)
def test_direction_reports_only_the_change_without_risk_thresholds(
    postgres_session,
    previous_rejected,
    latest_rejected,
    expected_direction,
    expected_delta,
):
    session, prefix = postgres_session
    profile_name = f"{prefix}_{expected_direction}"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=100,
        rejected_rows=previous_rejected,
        error_counts={"INVALID_PRICE": previous_rejected},
    )
    _add_run(
        session,
        profile_name=profile_name,
        minutes=2,
        total_rows=100,
        rejected_rows=latest_rejected,
        error_counts={"INVALID_PRICE": latest_rejected},
    )

    result = _observe(session, profile_name)

    assert result.direction == expected_direction
    assert result.rejection_rate_delta == expected_delta


def test_single_batch_has_no_baseline_and_no_delta(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_single"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=50,
        rejected_rows=5,
        error_counts={"INVALID_STOCK": 5},
    )

    result = _observe(session, profile_name)

    assert result.batch_count == 1
    assert result.latest_batch is not None
    assert result.previous_batch is None
    assert result.rejection_rate_delta is None
    assert result.direction == "no_baseline"


def test_aggregates_error_codes_with_batch_counts_and_deterministic_order(
    postgres_session,
):
    session, prefix = postgres_session
    profile_name = f"{prefix}_errors"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=100,
        rejected_rows=6,
        error_counts={"INVALID_PRICE": 4, "MISSING_CATEGORY": 2},
    )
    _add_run(
        session,
        profile_name=profile_name,
        minutes=2,
        total_rows=100,
        rejected_rows=5,
        error_counts={"INVALID_PRICE": 4, "INVALID_STOCK": 1},
    )
    _add_run(
        session,
        profile_name=profile_name,
        minutes=3,
        total_rows=100,
        rejected_rows=4,
        error_counts={"MISSING_CATEGORY": 1, "AAA_TIE": 3},
    )

    result = _observe(session, profile_name)

    assert [
        (item.error_code, item.total_count, item.affected_batch_count)
        for item in result.error_codes
    ] == [
        ("INVALID_PRICE", 8, 2),
        # total_count가 같으면 error_code 오름차순으로 순서를 고정합니다.
        ("AAA_TIE", 3, 1),
        ("MISSING_CATEGORY", 3, 2),
        ("INVALID_STOCK", 1, 1),
    ]


def test_error_code_aggregation_follows_the_limit_window(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_window"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=100,
        rejected_rows=7,
        error_counts={"OLD_ONLY": 7},
    )
    for minutes in (2, 3):
        _add_run(
            session,
            profile_name=profile_name,
            minutes=minutes,
            total_rows=100,
            rejected_rows=1,
            error_counts={"INVALID_PRICE": 1},
        )

    result = _observe(session, profile_name, limit=2)

    assert result.batch_count == 2
    assert [item.error_code for item in result.error_codes] == ["INVALID_PRICE"]


def test_excludes_legacy_batches_without_quality_metadata(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_legacy"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=100,
        rejected_rows=9,
        error_counts={"INVALID_PRICE": 9},
    )
    # legacy batch를 "거부 0건"으로 읽으면 품질이 좋아진 것처럼 보이게 됩니다.
    _add_run(session, profile_name=profile_name, minutes=2)

    result = _observe(session, profile_name)

    assert result.batch_count == 1
    assert result.latest_batch.rejected_rows == 9
    assert result.previous_batch is None
    assert result.direction == "no_baseline"


def test_zero_total_rows_batch_uses_zero_rejection_rate(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_empty_batch"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=100,
        rejected_rows=5,
        error_counts={"INVALID_PRICE": 5},
    )
    _add_run(
        session,
        profile_name=profile_name,
        minutes=2,
        total_rows=0,
        rejected_rows=0,
        error_counts={},
    )

    result = _observe(session, profile_name)

    assert result.latest_batch.total_rows == 0
    assert result.latest_batch.rejection_rate == 0.0
    assert result.rejection_rate_delta == -5.0
    assert result.direction == "improved"
    assert [item.error_code for item in result.error_codes] == ["INVALID_PRICE"]


def test_returns_safe_empty_response_when_profile_has_no_batches(postgres_session):
    session, prefix = postgres_session

    result = _observe(session, f"{prefix}_missing")

    assert result.batch_count == 0
    assert result.latest_batch is None
    assert result.previous_batch is None
    assert result.rejection_rate_delta is None
    assert result.direction == "no_baseline"
    assert result.error_codes == []
    assert result.recent_batches == []


def test_trims_profile_name_and_rejects_blank_or_out_of_range_limit(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_trim"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=10,
        rejected_rows=1,
        error_counts={"INVALID_PRICE": 1},
    )

    trimmed = _observe(session, f"  {profile_name}  ")
    assert trimmed.profile_name == profile_name
    assert trimmed.batch_count == 1

    for blank in ("", "   "):
        with pytest.raises(ValueError):
            _observe(session, blank)
    for invalid_limit in (MIN_BATCH_LIMIT - 1, MAX_BATCH_LIMIT + 1, True, 2.0):
        with pytest.raises(ValueError):
            _observe(session, profile_name, limit=invalid_limit)


def test_default_limit_matches_quality_trend_and_query_does_not_write(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_readonly"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=10,
        rejected_rows=1,
        error_counts={"INVALID_PRICE": 1},
    )
    session.commit()
    before = session.scalar(select(func.count()).select_from(ETLLoadRun))

    result = _observe(session, profile_name)

    assert result.limit == DEFAULT_BATCH_LIMIT == 10
    assert (MIN_BATCH_LIMIT, MAX_BATCH_LIMIT) == (1, 50)
    assert session.scalar(select(func.count()).select_from(ETLLoadRun)) == before


# ---- 비교 가능한 공급사 목록 -------------------------------------------------


def _observable_profiles(session, prefix):
    """이 테스트가 만든 profile만 남깁니다. 조회 자체는 전체 이력을 대상으로 합니다."""
    result = list_etl_quality_observability_profiles(session)
    return [
        item.profile_name
        for item in result.items
        if item.profile_name.startswith(prefix)
    ]


def test_lists_profiles_that_have_quality_available_batches(postgres_session):
    session, prefix = postgres_session
    _add_run(
        session,
        profile_name=f"{prefix}_fashion",
        minutes=1,
        total_rows=100,
        rejected_rows=4,
        error_counts={"INVALID_PRICE": 4},
    )

    assert _observable_profiles(session, prefix) == [f"{prefix}_fashion"]


def test_excludes_profiles_that_only_have_legacy_batches(postgres_session):
    session, prefix = postgres_session
    _add_run(
        session,
        profile_name=f"{prefix}_with_quality",
        minutes=1,
        total_rows=100,
        rejected_rows=4,
        error_counts={"INVALID_PRICE": 4},
    )
    # quality metadata가 없는 배치뿐이면 비교할 것이 없으므로 후보가 아닙니다.
    _add_run(session, profile_name=f"{prefix}_legacy_only", minutes=2)

    assert _observable_profiles(session, prefix) == [f"{prefix}_with_quality"]


def test_returns_each_profile_once_regardless_of_batch_count(postgres_session):
    session, prefix = postgres_session
    profile_name = f"{prefix}_repeated"
    for minutes in range(1, 4):
        _add_run(
            session,
            profile_name=profile_name,
            minutes=minutes,
            total_rows=100,
            rejected_rows=minutes,
            error_counts={"INVALID_PRICE": minutes},
        )

    assert _observable_profiles(session, prefix) == [profile_name]


def test_sorts_profiles_ascending_by_name(postgres_session):
    session, prefix = postgres_session
    for suffix in ("charlie", "alpha", "bravo"):
        _add_run(
            session,
            profile_name=f"{prefix}_{suffix}",
            minutes=1,
            total_rows=100,
            rejected_rows=1,
            error_counts={"INVALID_PRICE": 1},
        )

    assert _observable_profiles(session, prefix) == [
        f"{prefix}_alpha",
        f"{prefix}_bravo",
        f"{prefix}_charlie",
    ]


def test_returns_empty_list_when_no_quality_batch_exists(postgres_session):
    session, prefix = postgres_session
    _add_run(session, profile_name=f"{prefix}_legacy", minutes=1)

    assert _observable_profiles(session, prefix) == []


def test_includes_profiles_missing_from_the_configured_registry(postgres_session):
    session, prefix = postgres_session
    from etl.profile_loader import list_etl_profiles

    retired_profile = f"{prefix}_retired_vendor"
    _add_run(
        session,
        profile_name=retired_profile,
        minutes=1,
        total_rows=100,
        rejected_rows=6,
        error_counts={"INVALID_PRICE": 6},
    )

    # registry에서 내려간 공급사라도 품질 데이터가 남아 있으면 계속 비교할 수 있어야 합니다.
    assert retired_profile not in {
        profile["id"] for profile in list_etl_profiles()
    }
    assert _observable_profiles(session, prefix) == [retired_profile]


def test_profile_listing_returns_exact_db_values_and_does_not_write(postgres_session):
    session, prefix = postgres_session
    # 대소문자와 좌우 공백을 그대로 보존해야 정확 일치 비교 조회에 다시 넣을 수 있습니다.
    profile_name = f"{prefix}_Mixed_Case"
    _add_run(
        session,
        profile_name=profile_name,
        minutes=1,
        total_rows=10,
        rejected_rows=1,
        error_counts={"INVALID_PRICE": 1},
    )
    session.commit()
    before = session.scalar(select(func.count()).select_from(ETLLoadRun))

    listed = _observable_profiles(session, prefix)

    assert listed == [profile_name]
    assert get_etl_quality_observability(
        session, profile_name=listed[0]
    ).batch_count == 1
    assert session.scalar(select(func.count()).select_from(ETLLoadRun)) == before


@pytest.mark.parametrize("counts", [None, [], {"": 3, " ": 1, "BOOL": True, "ZERO": 0, "NEG": -1, "FLOAT": 1.5, "STR": "2"}])
def test_error_mapping_preserves_malformed_metadata_skip_policy(counts):
    from types import SimpleNamespace
    from db.etl_quality_observability_service import _aggregate_error_codes
    assert _aggregate_error_codes([SimpleNamespace(id=1, error_counts=counts, reject_details_stored=False)]) == []


def test_error_mapping_single_pass_newest_order_and_no_writes():
    from types import SimpleNamespace
    runs = [SimpleNamespace(id=3, created_at=BASE_TIME, total_rows=10, loaded_rows=5,
                rejected_rows=5, error_counts={"PRICE": 3, "STOCK": 2}, reject_details_stored=True),
            SimpleNamespace(id=2, created_at=BASE_TIME, total_rows=10, loaded_rows=7,
                rejected_rows=3, error_counts={"PRICE": 3}, reject_details_stored=False)]
    class ReadOnlySession:
        calls = []
        def scalars(self, statement):
            self.calls.append(statement)
            return SimpleNamespace(all=lambda: runs)
        def commit(self):
            raise AssertionError("read only")
        def flush(self):
            raise AssertionError("read only")
    session = ReadOnlySession()
    result = _observe(session, "synthetic")
    assert len(session.calls) == 1
    price, stock = result.error_codes
    assert (price.total_count, price.affected_batch_count) == (6, 2)
    assert [(b.etl_load_run_id, b.count, b.reject_details_stored) for b in price.batches] == [(3, 3, True), (2, 3, False)]
    assert [(b.etl_load_run_id, b.count) for b in stock.batches] == [(3, 2)]
    assert [item.etl_load_run_id for item in result.recent_batches] == [2, 3]


def test_postgres_mapping_to_existing_reject_jsonb_filter(postgres_session):
    from sqlalchemy import event
    from db.models import ETLRejectedRow
    from db.etl_query_service import list_etl_rejections
    session, prefix = postgres_session
    runs = [_add_run(session, profile_name=prefix, minutes=i, total_rows=10,
                    rejected_rows=2, error_counts={"INVALID_PRICE": 1, "STOCK": 1}) for i in (1, 2)]
    for run in runs:
        run.reject_details_stored = True
        run.rejects_file_sha256 = _unique_hash()
        for number, code in [(2, "INVALID_PRICE"), (3, "STOCK")]:
            session.add(ETLRejectedRow(etl_load_run_id=run.id, source_row_number=number,
                errors=[{"code": code, "field": "price", "message": "synthetic"}],
                masked_source_data={"product_id": f"SYNTHETIC-{run.id}-{number}"}))
    session.flush()
    statements = []
    connection = session.connection()
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(connection, "before_cursor_execute", capture)
    try:
        observation = _observe(session, prefix)
        assert len(statements) == 1
        price = next(item for item in observation.error_codes if item.error_code == "INVALID_PRICE")
        assert [batch.etl_load_run_id for batch in price.batches] == [runs[1].id, runs[0].id]
        assert sum(batch.count for batch in price.batches) == price.total_count == 2
        for batch in price.batches:
            rows = list_etl_rejections(session, etl_load_run_id=batch.etl_load_run_id,
                                       error_code=price.error_code, limit=1, offset=0)
            assert rows.total == batch.count == 1
            assert rows.items[0].source_row_number == 2
            assert rows.items[0].masked_source_data == {"product_id": f"SYNTHETIC-{batch.etl_load_run_id}-2"}
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        assert not session.new and not session.dirty and not session.deleted
    finally:
        event.remove(connection, "before_cursor_execute", capture)
