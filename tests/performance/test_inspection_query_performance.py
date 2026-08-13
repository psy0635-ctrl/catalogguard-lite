from __future__ import annotations

import json
import os
from contextlib import contextmanager
from statistics import median
from uuid import uuid4

import pytest
from sqlalchemy.engine import Connection

from config.database import get_optional_database_url
from db.session import create_database_engine


RUN_ENVIRONMENT_VARIABLE = "RUN_SQL_PERFORMANCE"
WARMUP_REPETITIONS = 2
MEASURED_REPETITIONS = 7
BENCHMARK_RUN_COUNT = 10000
HISTORY_PAGE_SIZE = 20
# Repository의 목록 조회와 같은 정렬을 사용해야 페이지 비용을 그대로 관찰할 수 있습니다.
HISTORY_COLUMNS = (
    "id, source_filename, file_sha256, inspection_version, total_products, "
    "total_issues, error_count, warning_count, created_at"
)
HISTORY_ORDER_BY = "ORDER BY created_at DESC, id DESC"
# 첫 페이지 대비 깊은 페이지가 최소 몇 배의 buffer를 읽어야 하는지에 대한 하한입니다.
# 실측은 이보다 훨씬 크지만, 환경에 따라 흔들리지 않도록 여유를 두고 낮게 잡습니다.
DEEP_OFFSET_BUFFER_GROWTH_FACTOR = 10


def _collect_plan_nodes(plan: dict) -> list[dict]:
    nodes = [plan]
    for child in plan.get("Plans", []):
        nodes.extend(_collect_plan_nodes(child))
    return nodes


def _measure_query(
    connection: Connection,
    query: str,
    parameters: tuple = (),
) -> dict:
    samples = []
    for repetition in range(WARMUP_REPETITIONS + MEASURED_REPETITIONS):
        payload = connection.exec_driver_sql(
            f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}",
            parameters,
        ).scalar_one()[0]
        plan = payload["Plan"]
        nodes = _collect_plan_nodes(plan)
        sample = {
            "planning_ms": payload["Planning Time"],
            "execution_ms": payload["Execution Time"],
            "plan": [node["Node Type"] for node in nodes],
            "indexes": [
                node["Index Name"] for node in nodes if "Index Name" in node
            ],
            "rows": plan["Actual Rows"],
            "rows_removed": sum(
                node.get("Rows Removed by Filter", 0)
                + node.get("Rows Removed by Index Recheck", 0)
                for node in nodes
            ),
            "shared_hit_blocks": plan.get("Shared Hit Blocks", 0),
            "shared_read_blocks": plan.get("Shared Read Blocks", 0),
        }
        if repetition >= WARMUP_REPETITIONS:
            samples.append(sample)

    last_sample = samples[-1]
    execution_times = [sample["execution_ms"] for sample in samples]
    return {
        "plan": last_sample["plan"],
        "indexes": last_sample["indexes"],
        "rows": last_sample["rows"],
        "rows_removed": last_sample["rows_removed"],
        "execution_ms": {
            "min": min(execution_times),
            "median": median(execution_times),
            "max": max(execution_times),
        },
        "planning_ms_median": median(
            sample["planning_ms"] for sample in samples
        ),
        "shared_hit_blocks_median": median(
            sample["shared_hit_blocks"] for sample in samples
        ),
        "shared_read_blocks_median": median(
            sample["shared_read_blocks"] for sample in samples
        ),
    }


def _seed_inspection_runs(connection: Connection) -> None:
    """목록·pagination 측정에 필요한 inspection_runs만 만들고 채웁니다."""
    connection.exec_driver_sql(
        "CREATE TABLE inspection_runs "
        "(LIKE public.inspection_runs INCLUDING ALL)"
    )
    connection.exec_driver_sql(
        f"""
        INSERT INTO inspection_runs (
            id,
            source_filename,
            file_sha256,
            inspection_version,
            total_products,
            total_issues,
            error_count,
            warning_count,
            created_at
        )
        SELECT
            i,
            CASE
                WHEN i %% 20 = 0 THEN 'sale_catalog_' || i || '.csv'
                ELSE 'catalog_' || (i %% 250) || '.csv'
            END,
            md5(i::text) || md5('catalog-' || i::text),
            CASE WHEN i %% 10 = 0 THEN '3' ELSE '4' END,
            100 + (i %% 901),
            10,
            CASE WHEN i %% 5 = 0 THEN 2 ELSE 0 END,
            CASE WHEN i %% 5 <> 0 AND i %% 3 = 0 THEN 1 ELSE 0 END,
            timestamptz '2026-06-01 00:00:00+00'
                + ((i * 251) %% 2592000) * interval '1 second'
        FROM generate_series(1, {BENCHMARK_RUN_COUNT}) AS generated(i)
        """
    )
    connection.exec_driver_sql("ANALYZE inspection_runs")


def _seed_benchmark_tables(connection: Connection) -> str:
    _seed_inspection_runs(connection)
    connection.exec_driver_sql(
        "CREATE TABLE inspection_results "
        "(LIKE public.inspection_results INCLUDING ALL)"
    )
    connection.exec_driver_sql(
        """
        INSERT INTO inspection_results (
            id,
            inspection_run_id,
            product_group_id,
            product_id,
            status,
            error_field,
            reason,
            recommendation,
            risk_level,
            created_at
        )
        SELECT
            ((run.id - 1) * 10) + result_number,
            run.id,
            'group-' || (run.id %% 500),
            'product-' || run.id || '-' || result_number,
            CASE WHEN result_number %% 4 = 0 THEN 'ERROR' ELSE 'WARNING' END,
            'price',
            'benchmark reason',
            'benchmark recommendation',
            CASE WHEN result_number %% 4 = 0 THEN 'HIGH' ELSE 'MEDIUM' END,
            run.created_at + result_number * interval '1 millisecond'
        FROM inspection_runs AS run
        CROSS JOIN generate_series(1, 10) AS generated(result_number)
        """
    )
    connection.exec_driver_sql("ANALYZE inspection_results")
    return connection.exec_driver_sql(
        "SELECT md5('5000') || md5('catalog-' || '5000')"
    ).scalar_one()


def _require_benchmark_database() -> str:
    """opt-in 환경변수와 전용 test/perf DB가 모두 준비된 경우에만 계속합니다."""
    if os.environ.get(RUN_ENVIRONMENT_VARIABLE) != "1":
        pytest.skip(f"Set {RUN_ENVIRONMENT_VARIABLE}=1 to run the SQL benchmark")

    test_database_url = get_optional_database_url()
    if test_database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for the SQL benchmark")
    return test_database_url


@contextmanager
def _isolated_benchmark_schema(test_database_url: str):
    # 업무 데이터가 있는 public schema를 건드리지 않도록 UUID schema를 만들고 끝나면 지웁니다.
    engine = create_database_engine(test_database_url)
    schema_name = f"inspection_perf_{uuid4().hex}"
    quoted_schema_name = engine.dialect.identifier_preparer.quote(schema_name)

    try:
        with engine.begin() as connection:
            database_name = connection.exec_driver_sql(
                "SELECT current_database()"
            ).scalar_one()
            assert any(
                token in database_name.lower() for token in ("test", "perf")
            ), "The performance benchmark requires a dedicated test/perf database"

            connection.exec_driver_sql(f"CREATE SCHEMA {quoted_schema_name}")
            connection.exec_driver_sql(
                f"SET LOCAL search_path TO {quoted_schema_name}, public"
            )
            try:
                yield connection
            finally:
                connection.exec_driver_sql(
                    f"DROP SCHEMA {quoted_schema_name} CASCADE"
                )
    finally:
        engine.dispose()


@pytest.mark.performance
def test_inspection_query_plans_with_representative_data() -> None:
    test_database_url = _require_benchmark_database()

    with _isolated_benchmark_schema(test_database_url) as connection:
        file_sha256 = _seed_benchmark_tables(connection)

        queries = {
            "same_csv": (
                "SELECT id, source_filename, file_sha256, inspection_version, "
                "total_products, total_issues, error_count, warning_count, created_at "
                "FROM inspection_runs "
                "WHERE file_sha256 = %s AND inspection_version = %s LIMIT 1",
                (file_sha256, "3"),
            ),
            "history": (
                "SELECT id, source_filename, file_sha256, inspection_version, "
                "total_products, total_issues, error_count, warning_count, created_at "
                "FROM inspection_runs "
                "ORDER BY created_at DESC, id DESC LIMIT 20 OFFSET 0",
                (),
            ),
            "history_count": (
                "SELECT count(*) FROM inspection_runs",
                (),
            ),
            "detail_run": (
                "SELECT id, source_filename, file_sha256, inspection_version, "
                "total_products, total_issues, error_count, warning_count, created_at "
                "FROM inspection_runs WHERE id = %s",
                (5000,),
            ),
            "detail_results": (
                "SELECT id, inspection_run_id, product_group_id, product_id, "
                "status, error_field, reason, recommendation, risk_level, created_at "
                "FROM inspection_results "
                "WHERE inspection_run_id = %s ORDER BY id ASC",
                (5000,),
            ),
        }
        report = {
            "rows": {
                "inspection_runs": BENCHMARK_RUN_COUNT,
                "inspection_results": BENCHMARK_RUN_COUNT * 10,
            },
            "repetitions": {
                "warmup": WARMUP_REPETITIONS,
                "measured": MEASURED_REPETITIONS,
            },
            "queries": {
                name: _measure_query(connection, *query)
                for name, query in queries.items()
            },
        }

        assert "Index Scan" in report["queries"]["same_csv"]["plan"]
        assert "Seq Scan" not in report["queries"]["history"]["plan"]
        assert "Index Scan" in report["queries"]["detail_run"]["plan"]
        assert any(
            node in report["queries"]["detail_results"]["plan"]
            for node in ("Index Scan", "Bitmap Index Scan")
        )
        assert report["queries"]["detail_results"]["rows"] == 10

        print(json.dumps(report, ensure_ascii=False, indent=2))


@pytest.mark.performance
def test_inspection_history_deep_offset_cost_growth() -> None:
    """깊은 페이지일수록 DB가 더 많은 buffer를 읽어야 하는 특성을 고정합니다.

    OFFSET pagination은 건너뛸 행을 실제로 읽고 버립니다. 그래서 페이지가
    깊어지면 계획이 같아도 처리량이 늘어납니다. 절대 실행 시간은 CPU와 캐시
    상태에 흔들리므로 관찰용으로만 출력하고, 계약은 buffer 증가로 고정합니다.
    """
    test_database_url = _require_benchmark_database()

    # 목록 조회만 보므로 상세 결과 10만 건은 만들지 않습니다.
    with _isolated_benchmark_schema(test_database_url) as connection:
        _seed_inspection_runs(connection)

        offsets = (0, 1000, 5000)
        history_query = (
            f"SELECT {HISTORY_COLUMNS} FROM inspection_runs "
            f"{HISTORY_ORDER_BY} LIMIT {HISTORY_PAGE_SIZE} OFFSET %s"
        )
        measurements = {
            f"offset_{offset}": _measure_query(
                connection,
                history_query,
                (offset,),
            )
            for offset in offsets
        }
        # filename 부분 문자열 검색은 관찰용으로만 함께 기록합니다.
        # planner가 어떤 노드를 고르는지는 계약으로 고정하지 않습니다.
        measurements["filename_contains"] = _measure_query(
            connection,
            f"SELECT {HISTORY_COLUMNS} FROM inspection_runs "
            "WHERE source_filename ILIKE %s ESCAPE '\\' "
            f"{HISTORY_ORDER_BY} LIMIT {HISTORY_PAGE_SIZE} OFFSET 0",
            ("%sale%",),
        )

        report = {
            "rows": {"inspection_runs": BENCHMARK_RUN_COUNT},
            "page_size": HISTORY_PAGE_SIZE,
            "repetitions": {
                "warmup": WARMUP_REPETITIONS,
                "measured": MEASURED_REPETITIONS,
            },
            "deep_offset": measurements,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))

        # 어느 페이지든 요청한 만큼의 행은 정상적으로 돌려줘야 합니다.
        for offset in offsets:
            assert measurements[f"offset_{offset}"]["rows"] == HISTORY_PAGE_SIZE
        assert measurements["filename_contains"]["rows"] == HISTORY_PAGE_SIZE

        first_page_buffers = measurements["offset_0"]["shared_hit_blocks_median"]
        middle_page_buffers = measurements["offset_1000"]["shared_hit_blocks_median"]
        deep_page_buffers = measurements["offset_5000"]["shared_hit_blocks_median"]

        # 페이지가 깊어질수록 읽는 buffer가 단조 증가해야 합니다.
        assert first_page_buffers < middle_page_buffers < deep_page_buffers
        # 깊은 페이지의 처리량 증가가 "측정 노이즈 수준"이 아님을 고정합니다.
        assert deep_page_buffers > (
            first_page_buffers * DEEP_OFFSET_BUFFER_GROWTH_FACTOR
        )
