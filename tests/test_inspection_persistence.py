# 역할: 검수 결과 저장 Service와 Repository가 PostgreSQL에 안전하게 저장하는지 테스트합니다.
import importlib
import sys
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import delete, event, select

from config.database import get_optional_database_url
from core.inspection_service import InspectionSummary, inspect_dataframe
from core.product_template import build_product_template_csv, get_product_template_filename
from core.upload_validator import validate_and_read_uploaded_csv
from db import persistence_service, repositories
from db.models import InspectionResult, InspectionRun
from db.persistence_service import (
    build_result_create_items,
    normalize_source_filename,
    save_inspection_report,
)
from db.session import create_database_engine, create_session_factory


# 테스트에서 반복해서 사용할 정상 상품 한 줄입니다.
BASE_ROW = {
    "product_group_id": "G001",
    "product_id": "P001",
    "product_name": "기본 티셔츠",
    "category": "TOP",
    "color": "BLACK",
    "size": "M",
    "stock": "10",
    "price": "19900",
    "image_path": "image.jpg",
    "description": "안전한 상품 설명",
    "seller": "공식 판매자",
}

CSV_COLUMNS = [
    "product_group_id",
    "product_id",
    "product_name",
    "category",
    "color",
    "size",
    "stock",
    "price",
    "image_path",
    "description",
    "seller",
]


def make_dataframe(rows: list[dict[str, str]] | None = None) -> pd.DataFrame:
    # rows를 넘기지 않으면 기본 정상 상품 1건으로 DataFrame을 만듭니다.
    return pd.DataFrame(rows or [BASE_ROW], columns=CSV_COLUMNS)


def make_report(rows: list[dict[str, str]] | None = None):
    # 실제 검수 흐름을 사용해 테스트용 InspectionReport를 만듭니다.
    return inspect_dataframe(make_dataframe(rows))


def make_invalid_required_field_report():
    # 저장 필수값이 비어 있을 때 Service가 막는지 확인하기 위한 가짜 Report입니다.
    return SimpleNamespace(
        summary=InspectionSummary(
            total_products=1,
            total_issues=1,
            error_count=1,
            warning_count=0,
        ),
        result_dataframe=pd.DataFrame(
            [
                {
                    "검수 상태": "",
                    "오류 항목": "가격 오류",
                    "상품 그룹 ID": "G001",
                    "상품 ID": "P001",
                    "오류 이유": "상품 가격이 0 이하입니다. 현재 가격: 0원.",
                    "수정 권장사항": "0보다 큰 정상 판매 가격을 입력하십시오.",
                    "위험 수준": "높음",
                }
            ]
        ),
    )


@pytest.fixture()
def database_session():
    # 실제 PostgreSQL URL이 없으면 통합 테스트만 건너뛰고 단위 테스트는 계속 실행합니다.
    test_database_url = get_optional_database_url()
    if test_database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 저장 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(test_database_url)
    session_factory = create_session_factory(engine)
    created_source_filenames: list[str] = []
    session = session_factory()

    try:
        yield session, created_source_filenames
    finally:
        session.rollback()
        session.close()

        if created_source_filenames:
            # 테스트가 만든 실행 기록만 파일명으로 찾아 정리합니다.
            with session_factory() as cleanup_session:
                cleanup_session.execute(
                    delete(InspectionRun).where(
                        InspectionRun.source_filename.in_(created_source_filenames)
                    )
                )
                cleanup_session.commit()

        engine.dispose()


def unique_filename(prefix: str = "products") -> str:
    # 여러 테스트가 같은 DB를 써도 파일명이 충돌하지 않도록 UUID를 붙입니다.
    return f"{prefix}_{uuid4().hex}.csv"


def test_normalize_source_filename_strips_windows_and_unix_paths():
    assert (
        normalize_source_filename(r"C:\Users\user\Downloads\products.csv")
        == "products.csv"
    )
    assert normalize_source_filename("/home/user/products.csv") == "products.csv"


def test_normalize_source_filename_uses_default_for_blank_values():
    assert normalize_source_filename("") == "uploaded.csv"
    assert normalize_source_filename("   ") == "uploaded.csv"
    assert normalize_source_filename(None) == "uploaded.csv"


def test_normalize_source_filename_limits_length_and_preserves_extension():
    filename = normalize_source_filename(f"{'a' * 300}.csv")

    assert len(filename) == 255
    assert filename.endswith(".csv")


def test_build_result_create_items_maps_display_columns_and_blank_ids():
    report = make_report(
        [
            {
                **BASE_ROW,
                "product_group_id": "",
                "product_id": "",
                "product_name": "",
                "price": "0",
            }
        ]
    )

    result_items = build_result_create_items(report)

    assert any(item.product_group_id is None for item in result_items)
    assert any(item.product_id is None for item in result_items)
    assert {item.status for item in result_items} == {"오류"}
    assert all(item.reason for item in result_items)
    assert all(item.recommendation for item in result_items)
    assert all(item.risk_level for item in result_items)


def test_build_result_create_items_rejects_blank_required_result_fields():
    report = make_invalid_required_field_report()

    with pytest.raises(ValueError, match="status"):
        build_result_create_items(report)


def test_save_inspection_report_rejects_mismatched_summary_before_db_work(database_session):
    session, created_source_filenames = database_session
    source_filename = unique_filename("mismatch")
    created_source_filenames.append(source_filename)
    report = make_report([{**BASE_ROW, "price": "0"}])
    report.summary.total_issues = report.summary.total_issues + 1

    with pytest.raises(ValueError, match="total_issues"):
        save_inspection_report(session, source_filename=source_filename, report=report)

    assert (
        session.scalar(
            select(InspectionRun).where(InspectionRun.source_filename == source_filename)
        )
        is None
    )


def test_save_inspection_report_persists_run_and_multiple_results(database_session):
    session, created_source_filenames = database_session
    source_filename = unique_filename("products_dev")
    created_source_filenames.append(source_filename)
    report = make_report(
        [
            BASE_ROW,
            {
                **BASE_ROW,
                "product_group_id": "G002",
                "product_id": "P001",
                "product_name": "다른 상품",
                "price": "0",
            },
        ]
    )

    inspection_run_id = save_inspection_report(
        session,
        source_filename=source_filename,
        report=report,
    )

    persisted_run = session.get(InspectionRun, inspection_run_id)
    assert inspection_run_id > 0
    assert persisted_run is not None
    assert persisted_run.source_filename == source_filename
    assert persisted_run.total_products == report.summary.total_products
    assert persisted_run.total_issues == report.summary.total_issues
    assert persisted_run.error_count == report.summary.error_count
    assert persisted_run.warning_count == report.summary.warning_count
    assert len(persisted_run.results) == report.summary.total_issues
    assert all(result.inspection_run_id == inspection_run_id for result in persisted_run.results)
    assert {result.status for result in persisted_run.results} == {"오류"}
    assert "높음" in {result.risk_level for result in persisted_run.results}


def test_save_inspection_report_strips_source_path_before_persisting(database_session):
    session, created_source_filenames = database_session
    stored_filename = unique_filename("path")
    created_source_filenames.append(stored_filename)
    report = make_report([{**BASE_ROW, "price": "0"}])

    inspection_run_id = save_inspection_report(
        session,
        source_filename=rf"C:\Users\user\Downloads\{stored_filename}",
        report=report,
    )

    persisted_run = session.get(InspectionRun, inspection_run_id)
    assert persisted_run.source_filename == stored_filename


def test_save_inspection_report_persists_zero_result_report(database_session):
    session, created_source_filenames = database_session
    source_filename = unique_filename("template")
    created_source_filenames.append(source_filename)
    dataframe = validate_and_read_uploaded_csv(
        get_product_template_filename(),
        build_product_template_csv(),
    )
    report = inspect_dataframe(dataframe)

    inspection_run_id = save_inspection_report(
        session,
        source_filename=source_filename,
        report=report,
    )

    persisted_run = session.get(InspectionRun, inspection_run_id)
    assert persisted_run.total_issues == 0
    assert persisted_run.error_count == 0
    assert persisted_run.warning_count == 0
    assert persisted_run.results == []


def test_save_inspection_report_does_not_store_raw_personal_information(database_session):
    session, created_source_filenames = database_session
    source_filename = unique_filename("privacy")
    created_source_filenames.append(source_filename)
    report = make_report(
        [
            {
                **BASE_ROW,
                "description": (
                    "문의 demo.user@example.com 010-1234-5678 900101-1234567"
                ),
            }
        ]
    )

    inspection_run_id = save_inspection_report(
        session,
        source_filename=source_filename,
        report=report,
    )

    persisted_results = session.scalars(
        select(InspectionResult).where(
            InspectionResult.inspection_run_id == inspection_run_id
        )
    ).all()
    stored_text = " ".join(
        " ".join(
            [
                result.product_group_id or "",
                result.product_id or "",
                result.status,
                result.error_field,
                result.reason,
                result.recommendation,
                result.risk_level,
            ]
        )
        for result in persisted_results
    )

    assert "demo.user@example.com" not in stored_text
    assert "010-1234-5678" not in stored_text
    assert "900101-1234567" not in stored_text
    assert "de*******@example.com" in stored_text
    assert "010-****-5678" in stored_text
    assert "900101-*******" in stored_text


def test_save_inspection_report_rolls_back_when_result_insert_fails(
    database_session,
    monkeypatch,
):
    # 상세 결과 저장 중 실패하면 부모 run도 남지 않아야 합니다.
    session, created_source_filenames = database_session
    source_filename = unique_filename("rollback")
    created_source_filenames.append(source_filename)
    report = make_report([{**BASE_ROW, "price": "0"}])

    def failing_create_inspection_results(session, *, inspection_run_id, result_items):
        session.add(
            InspectionResult(
                inspection_run_id=inspection_run_id,
                product_group_id="G001",
                product_id="P001",
                status="오류",
                error_field="가격 오류",
                reason="상품 가격이 0 이하입니다. 현재 가격: 0원.",
                recommendation="0보다 큰 정상 판매 가격을 입력하십시오.",
                risk_level="높음",
            )
        )
        session.flush()
        raise RuntimeError("forced result insert failure")

    monkeypatch.setattr(
        persistence_service.repositories,
        "create_inspection_results",
        failing_create_inspection_results,
    )

    with pytest.raises(RuntimeError, match="forced result insert failure"):
        save_inspection_report(
            session,
            source_filename=source_filename,
            report=report,
        )

    with session.begin():
        persisted_run_count = session.scalar(
            select(InspectionRun)
            .where(InspectionRun.source_filename == source_filename)
            .limit(1)
        )
        assert persisted_run_count is None


def test_get_inspection_detail_returns_none_when_run_is_missing(monkeypatch):
    session = object()
    calls = []

    def fake_get_inspection_run_by_id(session_arg, *, inspection_run_id):
        calls.append((session_arg, inspection_run_id))
        return None

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_id",
        fake_get_inspection_run_by_id,
        raising=False,
    )

    detail = persistence_service.get_inspection_detail(
        session,
        inspection_run_id=999999,
    )

    assert detail is None
    assert calls == [(session, 999999)]


def test_get_inspection_detail_maps_repository_rows(monkeypatch):
    session = object()
    created_at = pd.Timestamp("2026-07-04T12:30:00+09:00").to_pydatetime()
    run = SimpleNamespace(
        id=11,
        source_filename="products_dev.csv",
        total_products=5,
        total_issues=2,
        error_count=1,
        warning_count=1,
        created_at=created_at,
    )
    result_rows = [
        SimpleNamespace(
            product_group_id="G002",
            product_id="P003",
            status="오류",
            error_field="상품 ID 중복",
            reason="동일한 상품 ID가 여러 상품에 사용되었습니다.",
            recommendation="각 상품에 고유한 상품 ID를 입력하십시오.",
            risk_level="높음",
        ),
        SimpleNamespace(
            product_group_id="G003",
            product_id="P004",
            status="주의",
            error_field="품절 상품",
            reason="재고가 0개인 품절 상품입니다.",
            recommendation="판매 상태와 재입고 여부를 확인하세요.",
            risk_level="낮음",
        ),
    ]
    calls = []

    def fake_get_inspection_run_by_id(session_arg, *, inspection_run_id):
        calls.append(("run", session_arg, inspection_run_id))
        return run

    def fake_get_inspection_results_by_run_id(session_arg, *, inspection_run_id):
        calls.append(("results", session_arg, inspection_run_id))
        return result_rows

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_id",
        fake_get_inspection_run_by_id,
        raising=False,
    )
    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_results_by_run_id",
        fake_get_inspection_results_by_run_id,
        raising=False,
    )

    detail = persistence_service.get_inspection_detail(
        session,
        inspection_run_id=11,
    )

    assert detail.inspection_run_id == 11
    assert detail.source_filename == "products_dev.csv"
    assert detail.created_at == created_at
    assert detail.total_products == 5
    assert detail.total_issues == 2
    assert detail.error_count == 1
    assert detail.warning_count == 1
    assert [item.status for item in detail.results] == ["오류", "주의"]
    assert detail.results[0].error_field == "상품 ID 중복"
    assert calls == [
        ("run", session, 11),
        ("results", session, 11),
    ]


def test_get_inspection_detail_handles_zero_result_run(monkeypatch):
    session = object()
    run = SimpleNamespace(
        id=12,
        source_filename="template.csv",
        total_products=1,
        total_issues=0,
        error_count=0,
        warning_count=0,
        created_at=pd.Timestamp("2026-07-04T12:30:00+09:00").to_pydatetime(),
    )

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_id",
        lambda session, *, inspection_run_id: run,
        raising=False,
    )
    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_results_by_run_id",
        lambda session, *, inspection_run_id: [],
        raising=False,
    )

    detail = persistence_service.get_inspection_detail(
        session,
        inspection_run_id=12,
    )

    assert detail.total_issues == 0
    assert detail.error_count == 0
    assert detail.warning_count == 0
    assert detail.results == []


def test_list_inspections_maps_repository_rows_and_total(monkeypatch):
    session = object()
    created_at = pd.Timestamp("2026-07-04T12:30:00+09:00").to_pydatetime()
    runs = [
        SimpleNamespace(
            id=12,
            source_filename="template.csv",
            total_products=1,
            total_issues=0,
            error_count=0,
            warning_count=0,
            created_at=created_at,
        ),
        SimpleNamespace(
            id=11,
            source_filename="products_dev.csv",
            total_products=5,
            total_issues=2,
            error_count=1,
            warning_count=1,
            created_at=created_at,
        ),
    ]
    calls = []

    def fake_list_inspection_runs(session_arg, *, limit, offset, filename=None):
        if filename is None:
            calls.append(("list", session_arg, limit, offset))
        else:
            calls.append(("list", session_arg, limit, offset, filename))
        return runs

    def fake_count_inspection_runs(session_arg, *, filename=None):
        if filename is None:
            calls.append(("count", session_arg))
        else:
            calls.append(("count", session_arg, filename))
        return 37

    monkeypatch.setattr(
        persistence_service.repositories,
        "list_inspection_runs",
        fake_list_inspection_runs,
        raising=False,
    )
    monkeypatch.setattr(
        persistence_service.repositories,
        "count_inspection_runs",
        fake_count_inspection_runs,
        raising=False,
    )

    listing = persistence_service.list_inspections(session, limit=10, offset=20)

    assert listing.total == 37
    assert listing.limit == 10
    assert listing.offset == 20
    assert [item.inspection_run_id for item in listing.items] == [12, 11]
    assert listing.items[0].source_filename == "template.csv"
    assert listing.items[1].error_count == 1
    assert listing.items[1].warning_count == 1
    assert calls == [
        ("list", session, 10, 20),
        ("count", session),
    ]


def test_list_inspections_passes_filename_to_repository(monkeypatch):
    session = object()
    created_at = pd.Timestamp("2026-07-04T12:30:00+09:00").to_pydatetime()
    runs = [
        SimpleNamespace(
            id=11,
            source_filename="products_dev.csv",
            total_products=5,
            total_issues=2,
            error_count=1,
            warning_count=1,
            created_at=created_at,
        ),
    ]
    calls = []

    def fake_list_inspection_runs(session_arg, *, limit, offset, filename=None):
        calls.append(("list", session_arg, limit, offset, filename))
        return runs

    def fake_count_inspection_runs(session_arg, *, filename=None):
        calls.append(("count", session_arg, filename))
        return 1

    monkeypatch.setattr(
        persistence_service.repositories,
        "list_inspection_runs",
        fake_list_inspection_runs,
        raising=False,
    )
    monkeypatch.setattr(
        persistence_service.repositories,
        "count_inspection_runs",
        fake_count_inspection_runs,
        raising=False,
    )

    listing = persistence_service.list_inspections(
        session,
        limit=10,
        offset=0,
        filename="products",
    )

    assert listing.total == 1
    assert [item.source_filename for item in listing.items] == ["products_dev.csv"]
    assert calls == [
        ("list", session, 10, 0, "products"),
        ("count", session, "products"),
    ]


def test_list_inspections_handles_empty_repository_result(monkeypatch):
    session = object()

    monkeypatch.setattr(
        persistence_service.repositories,
        "list_inspection_runs",
        lambda session, *, limit, offset, filename=None: [],
        raising=False,
    )
    monkeypatch.setattr(
        persistence_service.repositories,
        "count_inspection_runs",
        lambda session, *, filename=None: 0,
        raising=False,
    )

    listing = persistence_service.list_inspections(session, limit=20, offset=0)

    assert listing.items == []
    assert listing.total == 0
    assert listing.limit == 20
    assert listing.offset == 0


def test_repository_list_inspection_runs_returns_recent_runs_with_limit(
    database_session,
):
    session, created_source_filenames = database_session
    first_source_filename = unique_filename("list_first")
    second_source_filename = unique_filename("list_second")
    created_source_filenames.extend([first_source_filename, second_source_filename])
    report = make_report([{**BASE_ROW, "price": "0"}])
    first_run_id = save_inspection_report(
        session,
        source_filename=first_source_filename,
        report=report,
    )
    second_run_id = save_inspection_report(
        session,
        source_filename=second_source_filename,
        report=report,
    )

    runs = repositories.list_inspection_runs(session, limit=2, offset=0)

    assert [run.id for run in runs] == [second_run_id, first_run_id]


def test_repository_list_inspection_runs_applies_offset(database_session):
    session, created_source_filenames = database_session
    first_source_filename = unique_filename("list_offset_first")
    second_source_filename = unique_filename("list_offset_second")
    created_source_filenames.extend([first_source_filename, second_source_filename])
    report = make_report([{**BASE_ROW, "price": "0"}])
    first_run_id = save_inspection_report(
        session,
        source_filename=first_source_filename,
        report=report,
    )
    second_run_id = save_inspection_report(
        session,
        source_filename=second_source_filename,
        report=report,
    )

    first_page = repositories.list_inspection_runs(session, limit=1, offset=0)
    second_page = repositories.list_inspection_runs(session, limit=1, offset=1)

    assert [run.id for run in first_page] == [second_run_id]
    assert [run.id for run in second_page] == [first_run_id]


def test_repository_list_and_count_filter_by_filename_with_pagination(
    database_session,
):
    session, created_source_filenames = database_session
    token = f"search_{uuid4().hex}"
    first_source_filename = f"{token}_products_first.csv"
    second_source_filename = f"{token}_products_second.csv"
    third_source_filename = f"{token}_template.csv"
    created_source_filenames.extend(
        [first_source_filename, second_source_filename, third_source_filename]
    )
    report = make_report([{**BASE_ROW, "price": "0"}])
    first_run_id = save_inspection_report(
        session,
        source_filename=first_source_filename,
        report=report,
    )
    second_run_id = save_inspection_report(
        session,
        source_filename=second_source_filename,
        report=report,
    )
    save_inspection_report(
        session,
        source_filename=third_source_filename,
        report=report,
    )
    filename_query = f"{token.upper()}_PRODUCTS"

    first_page = repositories.list_inspection_runs(
        session,
        limit=1,
        offset=0,
        filename=filename_query,
    )
    second_page = repositories.list_inspection_runs(
        session,
        limit=1,
        offset=1,
        filename=filename_query,
    )

    assert repositories.count_inspection_runs(session, filename=filename_query) == 2
    assert [run.id for run in first_page] == [second_run_id]
    assert [run.id for run in second_page] == [first_run_id]


def test_repository_filename_filter_returns_empty_when_no_match(database_session):
    session, _ = database_session
    token = f"missing_{uuid4().hex}"

    runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        filename=token,
    )

    assert runs == []
    assert repositories.count_inspection_runs(session, filename=token) == 0


def test_repository_filename_filter_treats_like_wildcards_as_literals(
    database_session,
):
    session, created_source_filenames = database_session
    token = f"literal_{uuid4().hex}"
    percent_source_filename = f"{token}_literal_%_file.csv"
    other_source_filename = f"{token}_literal_X_file.csv"
    created_source_filenames.extend([percent_source_filename, other_source_filename])
    report = make_report([{**BASE_ROW, "price": "0"}])
    percent_run_id = save_inspection_report(
        session,
        source_filename=percent_source_filename,
        report=report,
    )
    save_inspection_report(
        session,
        source_filename=other_source_filename,
        report=report,
    )

    runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        filename=f"{token}_literal_%",
    )

    assert [run.id for run in runs] == [percent_run_id]
    assert repositories.count_inspection_runs(
        session,
        filename=f"{token}_literal_%",
    ) == 1


def test_repository_list_inspection_runs_does_not_query_results_table(
    database_session,
):
    session, created_source_filenames = database_session
    source_filename = unique_filename("no_results_join")
    created_source_filenames.append(source_filename)
    save_inspection_report(
        session,
        source_filename=source_filename,
        report=make_report([{**BASE_ROW, "price": "0"}]),
    )
    statements: list[str] = []

    def collect_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", collect_statement)
    try:
        repositories.list_inspection_runs(
            session,
            limit=10,
            offset=0,
            filename=source_filename,
        )
    finally:
        event.remove(engine, "before_cursor_execute", collect_statement)

    assert not any("inspection_results" in statement for statement in statements)


def test_repository_count_inspection_runs_counts_created_runs(database_session):
    session, created_source_filenames = database_session
    before_count = repositories.count_inspection_runs(session)
    session.rollback()
    first_source_filename = unique_filename("count_first")
    second_source_filename = unique_filename("count_second")
    created_source_filenames.extend([first_source_filename, second_source_filename])
    report = make_report([{**BASE_ROW, "price": "0"}])

    save_inspection_report(
        session,
        source_filename=first_source_filename,
        report=report,
    )
    save_inspection_report(
        session,
        source_filename=second_source_filename,
        report=report,
    )

    assert repositories.count_inspection_runs(session) == before_count + 2


def test_repository_get_inspection_run_by_id_returns_saved_run(database_session):
    session, created_source_filenames = database_session
    source_filename = unique_filename("lookup")
    created_source_filenames.append(source_filename)
    report = make_report([{**BASE_ROW, "price": "0"}])
    inspection_run_id = save_inspection_report(
        session,
        source_filename=source_filename,
        report=report,
    )

    persisted_run = repositories.get_inspection_run_by_id(
        session,
        inspection_run_id=inspection_run_id,
    )

    assert persisted_run is not None
    assert persisted_run.id == inspection_run_id
    assert persisted_run.source_filename == source_filename


def test_repository_get_inspection_run_by_id_returns_none_for_missing_run(
    database_session,
):
    session, _ = database_session

    assert (
        repositories.get_inspection_run_by_id(
            session,
            inspection_run_id=-1,
        )
        is None
    )


def test_repository_get_inspection_results_by_run_id_filters_and_orders_results(
    database_session,
):
    session, created_source_filenames = database_session
    first_source_filename = unique_filename("lookup_results_first")
    second_source_filename = unique_filename("lookup_results_second")
    created_source_filenames.extend([first_source_filename, second_source_filename])
    first_report = make_report(
        [
            BASE_ROW,
            {
                **BASE_ROW,
                "product_group_id": "G002",
                "product_id": "P001",
                "product_name": "다른 상품",
                "price": "0",
            },
        ]
    )
    second_report = make_report([{**BASE_ROW, "price": "0"}])
    first_run_id = save_inspection_report(
        session,
        source_filename=first_source_filename,
        report=first_report,
    )
    second_run_id = save_inspection_report(
        session,
        source_filename=second_source_filename,
        report=second_report,
    )

    results = repositories.get_inspection_results_by_run_id(
        session,
        inspection_run_id=first_run_id,
    )

    assert results
    assert [result.id for result in results] == sorted(result.id for result in results)
    assert all(result.inspection_run_id == first_run_id for result in results)
    assert all(result.inspection_run_id != second_run_id for result in results)


def test_repository_get_inspection_results_by_run_id_returns_empty_list(
    database_session,
):
    session, created_source_filenames = database_session
    source_filename = unique_filename("lookup_empty")
    created_source_filenames.append(source_filename)
    dataframe = validate_and_read_uploaded_csv(
        get_product_template_filename(),
        build_product_template_csv(),
    )
    report = inspect_dataframe(dataframe)
    inspection_run_id = save_inspection_report(
        session,
        source_filename=source_filename,
        report=report,
    )

    results = repositories.get_inspection_results_by_run_id(
        session,
        inspection_run_id=inspection_run_id,
    )

    assert results == []


def test_persistence_imports_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("app", None)

    streamlit_app = importlib.import_module("app")
    api_module = importlib.import_module("api.main")
    db_models = importlib.import_module("db.models")
    persistence_module = importlib.import_module("db.persistence_service")

    assert streamlit_app is not None
    assert api_module.app.title == "CatalogGuard Lite API"
    assert db_models.InspectionRun.__tablename__ == "inspection_runs"
    assert hasattr(persistence_module, "save_inspection_report")
