# 역할: 검수 결과 저장 Service와 Repository가 PostgreSQL에 안전하게 저장하는지 테스트합니다.
import hashlib
import importlib
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import IntegrityError

from config.database import get_optional_database_url
from config.settings import INSPECTION_VERSION
from core.inspection_service import InspectionSummary, inspect_dataframe
from core.product_template import build_product_template_csv, get_product_template_filename
from core.upload_validator import validate_and_read_uploaded_csv
from db import persistence_service, repositories
from db.models import InspectionResult, InspectionRun
from db.persistence_service import (
    FILE_IDENTITY_UNIQUE_INDEX_NAME,
    InspectionSaveOutcome,
    build_result_create_items,
    find_existing_inspection_run,
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


def make_file_hash(value: bytes = b"same csv bytes") -> str:
    return hashlib.sha256(value).hexdigest()


def save_inspection_report_id(*args, **kwargs) -> int:
    return save_inspection_report(*args, **kwargs).inspection_run_id


def count_inspection_runs(session, *, file_sha256: str | None = None) -> int:
    statement = select(func.count()).select_from(InspectionRun)
    if file_sha256 is not None:
        statement = statement.where(InspectionRun.file_sha256 == file_sha256)
    return int(session.scalar(statement) or 0)


def count_inspection_results(session, *, inspection_run_id: int | None = None) -> int:
    statement = select(func.count()).select_from(InspectionResult)
    if inspection_run_id is not None:
        statement = statement.where(
            InspectionResult.inspection_run_id == inspection_run_id
        )
    return int(session.scalar(statement) or 0)


def create_summary_run(
    session,
    *,
    source_filename: str,
    error_count: int,
    warning_count: int,
    created_at: datetime | None = None,
) -> int:
    inspection_run = repositories.create_inspection_run(
        session,
        source_filename=source_filename,
        total_products=1,
        total_issues=error_count + warning_count,
        error_count=error_count,
        warning_count=warning_count,
    )
    if created_at is not None:
        inspection_run.created_at = created_at
    session.flush()
    return inspection_run.id


class FakePostgresIntegrityOrig(Exception):
    def __init__(self, constraint_name: str):
        super().__init__(constraint_name)
        self.diag = SimpleNamespace(constraint_name=constraint_name)


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def begin(self):
        return FakeTransaction()

    def begin_nested(self):
        return FakeTransaction()


def make_integrity_error(constraint_name: str = FILE_IDENTITY_UNIQUE_INDEX_NAME):
    return IntegrityError(
        "insert failed",
        params={},
        orig=FakePostgresIntegrityOrig(constraint_name),
    )


def test_normalize_source_filename_strips_windows_and_unix_paths():
    assert (
        normalize_source_filename(r"C:\Users\user\Downloads\products.csv")
        == "products.csv"
    )
    assert normalize_source_filename("/home/user/products.csv") == "products.csv"


def test_find_existing_inspection_run_delegates_file_identity_lookup(monkeypatch):
    session = object()
    existing_run = SimpleNamespace(id=42)
    calls = []

    def fake_get_by_identity(session_arg, *, file_sha256, inspection_version):
        calls.append((session_arg, file_sha256, inspection_version))
        return existing_run

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_file_identity",
        fake_get_by_identity,
    )

    result = find_existing_inspection_run(
        session,
        file_sha256=make_file_hash(b"same csv bytes"),
        inspection_version=INSPECTION_VERSION,
    )

    assert result is existing_run
    assert calls == [(session, make_file_hash(b"same csv bytes"), INSPECTION_VERSION)]


@pytest.mark.parametrize(
    ("file_sha256", "inspection_version", "expected"),
    [
        (make_file_hash(b"same bytes"), INSPECTION_VERSION, "existing"),
        (make_file_hash(b"different bytes"), INSPECTION_VERSION, None),
        (make_file_hash(b"same bytes"), "3", None),
        (None, INSPECTION_VERSION, None),
    ],
)
def test_find_existing_inspection_run_preserves_identity_matching(
    monkeypatch,
    file_sha256,
    inspection_version,
    expected,
):
    existing_run = SimpleNamespace(id=42)

    def fake_get_by_identity(session, *, file_sha256, inspection_version):
        if file_sha256 == make_file_hash(b"same bytes") and inspection_version == INSPECTION_VERSION:
            return existing_run
        return None

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_file_identity",
        fake_get_by_identity,
    )

    result = find_existing_inspection_run(
        object(),
        file_sha256=file_sha256,
        inspection_version=inspection_version,
    )

    if expected == "existing":
        assert result is existing_run
    else:
        assert result is None


def test_find_existing_inspection_run_does_not_hide_repository_errors(monkeypatch):
    def failing_get_by_identity(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_file_identity",
        failing_get_by_identity,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        find_existing_inspection_run(
            object(),
            file_sha256=make_file_hash(b"same bytes"),
            inspection_version=INSPECTION_VERSION,
        )


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


def test_build_result_create_items_maps_fashion_standardization_warnings():
    report = make_report(
        [
            {
                **BASE_ROW,
                "color": "블랙",
                "size": "medium",
            }
        ]
    )

    result_items = build_result_create_items(report)
    items_by_error_field = {
        item.error_field: item
        for item in result_items
    }

    assert {"색상 표기 비표준", "사이즈 표기 비표준"}.issubset(
        items_by_error_field
    )

    color_item = items_by_error_field["색상 표기 비표준"]
    assert color_item.status == "주의"
    assert color_item.reason == "색상 '블랙'은 표준값 'BLACK'으로 통일하는 것이 좋습니다."
    assert color_item.recommendation
    assert color_item.risk_level == "낮음"

    size_item = items_by_error_field["사이즈 표기 비표준"]
    assert size_item.status == "주의"
    assert size_item.reason == "사이즈 'medium'은 표준값 'M'으로 통일하는 것이 좋습니다."
    assert size_item.recommendation
    assert size_item.risk_level == "낮음"


def test_build_result_create_items_maps_duplicate_variant_without_schema_changes():
    report = make_report(
        [
            BASE_ROW,
            {
                **BASE_ROW,
                "product_id": "P002",
                "product_name": "다른 상품",
                "color": "black",
                "size": "medium",
                "image_path": "image2.jpg",
            },
        ]
    )

    result_items = build_result_create_items(report)
    duplicate_items = [
        item
        for item in result_items
        if item.error_field == "상품 옵션 조합 중복"
    ]

    assert len(duplicate_items) == 2
    assert [item.product_id for item in duplicate_items] == ["P001", "P002"]
    assert {item.product_group_id for item in duplicate_items} == {"G001"}
    assert {item.status for item in duplicate_items} == {"오류"}
    assert all("색상 'BLACK', 사이즈 'M'" in item.reason for item in duplicate_items)
    assert all(item.recommendation for item in duplicate_items)
    assert {item.risk_level for item in duplicate_items} == {"중간"}


def test_build_result_create_items_maps_group_category_without_schema_changes():
    report = make_report(
        [
            {
                **BASE_ROW,
                "product_name": "상품 A",
            },
            {
                **BASE_ROW,
                "product_id": "P002",
                "product_name": "상품 B",
                "category": "BOTTOM",
                "color": "WHITE",
                "size": "L",
                "image_path": "image2.jpg",
            },
        ]
    )

    result_items = build_result_create_items(report)
    category_items = [
        item
        for item in result_items
        if item.error_field == "상품 그룹 카테고리 불일치"
    ]

    assert len(category_items) == 2
    assert [item.product_id for item in category_items] == ["P001", "P002"]
    assert {item.product_group_id for item in category_items} == {"G001"}
    assert {item.status for item in category_items} == {"오류"}
    assert all("'TOP', 'BOTTOM'" in item.reason for item in category_items)
    assert all(item.recommendation for item in category_items)
    assert {item.risk_level for item in category_items} == {"중간"}


def test_current_inspection_version_is_five_for_sale_price_rule():
    assert INSPECTION_VERSION == "5"


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
        save_inspection_report_id(session, source_filename=source_filename, report=report)

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
    file_sha256 = make_file_hash(b"first save")
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

    outcome = save_inspection_report(
        session,
        source_filename=source_filename,
        report=report,
        file_sha256=file_sha256,
        inspection_version=INSPECTION_VERSION,
    )
    inspection_run_id = outcome.inspection_run_id

    persisted_run = session.get(InspectionRun, inspection_run_id)
    assert isinstance(outcome, InspectionSaveOutcome)
    assert outcome.created is True
    assert inspection_run_id > 0
    assert persisted_run is not None
    assert persisted_run.source_filename == source_filename
    assert persisted_run.file_sha256 == file_sha256
    assert persisted_run.inspection_version == INSPECTION_VERSION
    assert persisted_run.total_products == report.summary.total_products
    assert persisted_run.total_issues == report.summary.total_issues
    assert persisted_run.error_count == report.summary.error_count
    assert persisted_run.warning_count == report.summary.warning_count
    assert len(persisted_run.results) == report.summary.total_issues
    assert all(result.inspection_run_id == inspection_run_id for result in persisted_run.results)
    assert {result.status for result in persisted_run.results} == {"오류"}
    assert "높음" in {result.risk_level for result in persisted_run.results}


def test_save_inspection_report_returns_existing_run_for_same_hash_and_version(
    database_session,
):
    session, created_source_filenames = database_session
    first_source_filename = unique_filename("duplicate_first")
    second_source_filename = unique_filename("duplicate_second")
    created_source_filenames.extend([first_source_filename, second_source_filename])
    file_sha256 = make_file_hash(first_source_filename.encode("utf-8"))
    report = make_report([{**BASE_ROW, "price": "0"}])

    first_outcome = save_inspection_report(
        session,
        source_filename=first_source_filename,
        report=report,
        file_sha256=file_sha256,
        inspection_version=INSPECTION_VERSION,
    )
    second_outcome = save_inspection_report(
        session,
        source_filename=second_source_filename,
        report=report,
        file_sha256=file_sha256,
        inspection_version=INSPECTION_VERSION,
    )

    assert first_outcome.created is True
    assert second_outcome.created is False
    assert second_outcome.inspection_run_id == first_outcome.inspection_run_id
    assert count_inspection_runs(session, file_sha256=file_sha256) == 1
    assert (
        count_inspection_results(
            session,
            inspection_run_id=first_outcome.inspection_run_id,
        )
        == report.summary.total_issues
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(InspectionRun)
            .where(InspectionRun.source_filename == second_source_filename)
        )
        == 0
    )


def test_save_inspection_report_allows_same_filename_with_different_hash(
    database_session,
):
    session, created_source_filenames = database_session
    source_filename = unique_filename("same_name")
    created_source_filenames.append(source_filename)
    report = make_report([{**BASE_ROW, "price": "0"}])

    first_outcome = save_inspection_report(
        session,
        source_filename=source_filename,
        report=report,
        file_sha256=make_file_hash(b"first bytes"),
        inspection_version=INSPECTION_VERSION,
    )
    second_outcome = save_inspection_report(
        session,
        source_filename=source_filename,
        report=report,
        file_sha256=make_file_hash(b"second bytes"),
        inspection_version=INSPECTION_VERSION,
    )

    assert first_outcome.created is True
    assert second_outcome.created is True
    assert second_outcome.inspection_run_id != first_outcome.inspection_run_id


def test_save_inspection_report_allows_same_hash_with_different_version(
    database_session,
):
    session, created_source_filenames = database_session
    first_source_filename = unique_filename("version_first")
    second_source_filename = unique_filename("version_second")
    created_source_filenames.extend([first_source_filename, second_source_filename])
    file_sha256 = make_file_hash(b"versioned bytes")
    report = make_report([{**BASE_ROW, "price": "0"}])

    first_outcome = save_inspection_report(
        session,
        source_filename=first_source_filename,
        report=report,
        file_sha256=file_sha256,
        inspection_version="3",
    )
    second_outcome = save_inspection_report(
        session,
        source_filename=second_source_filename,
        report=report,
        file_sha256=file_sha256,
        inspection_version=INSPECTION_VERSION,
    )

    assert first_outcome.created is True
    assert second_outcome.created is True
    assert second_outcome.inspection_run_id != first_outcome.inspection_run_id


def test_save_inspection_report_ignores_legacy_null_file_hash_rows(database_session):
    session, created_source_filenames = database_session
    legacy_source_filename = unique_filename("legacy_null")
    hashed_source_filename = unique_filename("legacy_hashed")
    created_source_filenames.extend([legacy_source_filename, hashed_source_filename])
    file_sha256 = make_file_hash(b"legacy bytes")
    report = make_report([{**BASE_ROW, "price": "0"}])

    legacy_outcome = save_inspection_report(
        session,
        source_filename=legacy_source_filename,
        report=report,
        file_sha256=None,
        inspection_version=INSPECTION_VERSION,
    )
    hashed_outcome = save_inspection_report(
        session,
        source_filename=hashed_source_filename,
        report=report,
        file_sha256=file_sha256,
        inspection_version=INSPECTION_VERSION,
    )

    assert legacy_outcome.created is True
    assert hashed_outcome.created is True
    assert hashed_outcome.inspection_run_id != legacy_outcome.inspection_run_id


def test_save_inspection_report_strips_source_path_before_persisting(database_session):
    session, created_source_filenames = database_session
    stored_filename = unique_filename("path")
    created_source_filenames.append(stored_filename)
    report = make_report([{**BASE_ROW, "price": "0"}])

    inspection_run_id = save_inspection_report_id(
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

    inspection_run_id = save_inspection_report_id(
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

    inspection_run_id = save_inspection_report_id(
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
        save_inspection_report_id(
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


def test_save_inspection_report_returns_existing_run_after_file_identity_integrity_error(
    monkeypatch,
):
    session = FakeSession()
    file_sha256 = make_file_hash(b"race bytes")
    existing_run = SimpleNamespace(id=77)
    lookup_results = [None, existing_run]

    def fake_get_by_identity(session_arg, *, file_sha256, inspection_version):
        return lookup_results.pop(0)

    def fake_create_inspection_run(*args, **kwargs):
        raise make_integrity_error()

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_file_identity",
        fake_get_by_identity,
        raising=False,
    )
    monkeypatch.setattr(
        persistence_service.repositories,
        "create_inspection_run",
        fake_create_inspection_run,
        raising=False,
    )

    outcome = save_inspection_report(
        session,
        source_filename="products.csv",
        report=make_report([{**BASE_ROW, "price": "0"}]),
        file_sha256=file_sha256,
        inspection_version=INSPECTION_VERSION,
    )

    assert outcome == InspectionSaveOutcome(inspection_run_id=77, created=False)


def test_save_inspection_report_reraises_file_identity_integrity_error_without_existing_run(
    monkeypatch,
):
    session = FakeSession()

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_file_identity",
        lambda *args, **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        persistence_service.repositories,
        "create_inspection_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(make_integrity_error()),
        raising=False,
    )

    with pytest.raises(IntegrityError):
        save_inspection_report(
            session,
            source_filename="products.csv",
            report=make_report([{**BASE_ROW, "price": "0"}]),
            file_sha256=make_file_hash(b"race bytes"),
            inspection_version=INSPECTION_VERSION,
        )


def test_save_inspection_report_does_not_hide_other_integrity_errors(monkeypatch):
    session = FakeSession()
    lookup_results = [None, SimpleNamespace(id=77)]

    monkeypatch.setattr(
        persistence_service.repositories,
        "get_inspection_run_by_file_identity",
        lambda *args, **kwargs: lookup_results.pop(0),
        raising=False,
    )
    monkeypatch.setattr(
        persistence_service.repositories,
        "create_inspection_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            make_integrity_error("ck_inspection_runs_total_products_non_negative")
        ),
        raising=False,
    )

    with pytest.raises(IntegrityError):
        save_inspection_report(
            session,
            source_filename="products.csv",
            report=make_report([{**BASE_ROW, "price": "0"}]),
            file_sha256=make_file_hash(b"race bytes"),
            inspection_version=INSPECTION_VERSION,
        )


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


def test_list_inspections_passes_created_at_bounds_to_repository(monkeypatch):
    session = object()
    start_bound = datetime(2026, 6, 30, 15, 0, tzinfo=timezone.utc)
    end_bound = datetime(2026, 7, 5, 15, 0, tzinfo=timezone.utc)
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

    def fake_list_inspection_runs(
        session_arg,
        *,
        limit,
        offset,
        filename=None,
        created_at_start=None,
        created_at_end_exclusive=None,
    ):
        calls.append(
            (
                "list",
                session_arg,
                limit,
                offset,
                filename,
                created_at_start,
                created_at_end_exclusive,
            )
        )
        return runs

    def fake_count_inspection_runs(
        session_arg,
        *,
        filename=None,
        created_at_start=None,
        created_at_end_exclusive=None,
    ):
        calls.append(
            (
                "count",
                session_arg,
                filename,
                created_at_start,
                created_at_end_exclusive,
            )
        )
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
        created_at_start=start_bound,
        created_at_end_exclusive=end_bound,
    )

    assert listing.total == 1
    assert [item.source_filename for item in listing.items] == ["products_dev.csv"]
    assert calls == [
        ("list", session, 10, 0, "products", start_bound, end_bound),
        ("count", session, "products", start_bound, end_bound),
    ]


def test_list_inspections_passes_status_filter_to_repository(monkeypatch):
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

    def fake_list_inspection_runs(
        session_arg,
        *,
        limit,
        offset,
        filename=None,
        created_at_start=None,
        created_at_end_exclusive=None,
        status_filter=None,
    ):
        calls.append(
            (
                "list",
                session_arg,
                limit,
                offset,
                filename,
                created_at_start,
                created_at_end_exclusive,
                status_filter,
            )
        )
        return runs

    def fake_count_inspection_runs(
        session_arg,
        *,
        filename=None,
        created_at_start=None,
        created_at_end_exclusive=None,
        status_filter=None,
    ):
        calls.append(
            (
                "count",
                session_arg,
                filename,
                created_at_start,
                created_at_end_exclusive,
                status_filter,
            )
        )
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
        status_filter="error",
    )

    assert listing.total == 1
    assert [item.source_filename for item in listing.items] == ["products_dev.csv"]
    assert calls == [
        ("list", session, 10, 0, "products", None, None, "error"),
        ("count", session, "products", None, None, "error"),
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
    first_run_id = save_inspection_report_id(
        session,
        source_filename=first_source_filename,
        report=report,
    )
    second_run_id = save_inspection_report_id(
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
    first_run_id = save_inspection_report_id(
        session,
        source_filename=first_source_filename,
        report=report,
    )
    second_run_id = save_inspection_report_id(
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
    first_run_id = save_inspection_report_id(
        session,
        source_filename=first_source_filename,
        report=report,
    )
    second_run_id = save_inspection_report_id(
        session,
        source_filename=second_source_filename,
        report=report,
    )
    save_inspection_report_id(
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
    percent_run_id = save_inspection_report_id(
        session,
        source_filename=percent_source_filename,
        report=report,
    )
    save_inspection_report_id(
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


def test_repository_list_and_count_filter_by_created_at_bounds(database_session):
    session, created_source_filenames = database_session
    token = f"date_range_{uuid4().hex}"
    before_source_filename = f"{token}_before.csv"
    start_source_filename = f"{token}_start.csv"
    inside_source_filename = f"{token}_inside.csv"
    end_source_filename = f"{token}_end.csv"
    created_source_filenames.extend(
        [
            before_source_filename,
            start_source_filename,
            inside_source_filename,
            end_source_filename,
        ]
    )
    report = make_report([{**BASE_ROW, "price": "0"}])
    before_run_id = save_inspection_report_id(
        session,
        source_filename=before_source_filename,
        report=report,
    )
    start_run_id = save_inspection_report_id(
        session,
        source_filename=start_source_filename,
        report=report,
    )
    inside_run_id = save_inspection_report_id(
        session,
        source_filename=inside_source_filename,
        report=report,
    )
    end_run_id = save_inspection_report_id(
        session,
        source_filename=end_source_filename,
        report=report,
    )
    created_at_values = {
        before_run_id: datetime(2026, 6, 30, 14, 59, 59, tzinfo=timezone.utc),
        start_run_id: datetime(2026, 6, 30, 15, 0, 0, tzinfo=timezone.utc),
        inside_run_id: datetime(2026, 7, 5, 14, 59, 59, tzinfo=timezone.utc),
        end_run_id: datetime(2026, 7, 5, 15, 0, 0, tzinfo=timezone.utc),
    }
    for run_id, created_at in created_at_values.items():
        session.get(InspectionRun, run_id).created_at = created_at
    session.commit()

    runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        filename=token,
        created_at_start=datetime(2026, 6, 30, 15, 0, 0, tzinfo=timezone.utc),
        created_at_end_exclusive=datetime(2026, 7, 5, 15, 0, 0, tzinfo=timezone.utc),
    )

    assert [run.id for run in runs] == [inside_run_id, start_run_id]
    assert (
        repositories.count_inspection_runs(
            session,
            filename=token,
            created_at_start=datetime(2026, 6, 30, 15, 0, 0, tzinfo=timezone.utc),
            created_at_end_exclusive=datetime(
                2026,
                7,
                5,
                15,
                0,
                0,
                tzinfo=timezone.utc,
            ),
        )
        == 2
    )


def test_repository_list_and_count_filter_by_status_categories(database_session):
    session, created_source_filenames = database_session
    token = f"status_{uuid4().hex}"
    error_source_filename = f"{token}_error.csv"
    warning_source_filename = f"{token}_warning.csv"
    normal_source_filename = f"{token}_normal.csv"
    mixed_source_filename = f"{token}_mixed.csv"
    created_source_filenames.extend(
        [
            error_source_filename,
            warning_source_filename,
            normal_source_filename,
            mixed_source_filename,
        ]
    )
    error_run_id = create_summary_run(
        session,
        source_filename=error_source_filename,
        error_count=2,
        warning_count=0,
    )
    warning_run_id = create_summary_run(
        session,
        source_filename=warning_source_filename,
        error_count=0,
        warning_count=3,
    )
    normal_run_id = create_summary_run(
        session,
        source_filename=normal_source_filename,
        error_count=0,
        warning_count=0,
    )
    mixed_run_id = create_summary_run(
        session,
        source_filename=mixed_source_filename,
        error_count=1,
        warning_count=4,
    )
    session.commit()

    all_runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        filename=token,
    )
    error_runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        filename=token,
        status_filter="error",
    )
    warning_runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        filename=token,
        status_filter="warning",
    )
    normal_runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        filename=token,
        status_filter="normal",
    )

    assert repositories.count_inspection_runs(session, filename=token) == 4
    assert {run.id for run in all_runs} == {
        error_run_id,
        warning_run_id,
        normal_run_id,
        mixed_run_id,
    }
    assert [run.id for run in error_runs] == [mixed_run_id, error_run_id]
    assert [run.id for run in warning_runs] == [warning_run_id]
    assert [run.id for run in normal_runs] == [normal_run_id]
    assert (
        repositories.count_inspection_runs(
            session,
            filename=token,
            status_filter="error",
        )
        == 2
    )
    assert (
        repositories.count_inspection_runs(
            session,
            filename=token,
            status_filter="warning",
        )
        == 1
    )
    assert (
        repositories.count_inspection_runs(
            session,
            filename=token,
            status_filter="normal",
        )
        == 1
    )


def test_repository_status_filter_combines_with_filename_date_and_pagination(
    database_session,
):
    session, created_source_filenames = database_session
    token = f"status_combo_{uuid4().hex}"
    alpha_first = f"{token}_alpha_first.csv"
    alpha_second = f"{token}_alpha_second.csv"
    beta_second = f"{token}_beta_second.csv"
    alpha_warning = f"{token}_alpha_warning.csv"
    alpha_before = f"{token}_alpha_before.csv"
    alpha_after = f"{token}_alpha_after.csv"
    created_source_filenames.extend(
        [
            alpha_first,
            alpha_second,
            beta_second,
            alpha_warning,
            alpha_before,
            alpha_after,
        ]
    )
    first_run_id = create_summary_run(
        session,
        source_filename=alpha_first,
        error_count=1,
        warning_count=0,
        created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    second_run_id = create_summary_run(
        session,
        source_filename=alpha_second,
        error_count=2,
        warning_count=0,
        created_at=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
    )
    beta_run_id = create_summary_run(
        session,
        source_filename=beta_second,
        error_count=1,
        warning_count=0,
        created_at=datetime(2026, 7, 2, 13, 0, tzinfo=timezone.utc),
    )
    create_summary_run(
        session,
        source_filename=alpha_warning,
        error_count=0,
        warning_count=1,
        created_at=datetime(2026, 7, 2, 14, 0, tzinfo=timezone.utc),
    )
    before_run_id = create_summary_run(
        session,
        source_filename=alpha_before,
        error_count=1,
        warning_count=0,
        created_at=datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc),
    )
    after_run_id = create_summary_run(
        session,
        source_filename=alpha_after,
        error_count=1,
        warning_count=0,
        created_at=datetime(2026, 7, 3, 0, 0, tzinfo=timezone.utc),
    )
    session.commit()

    filename_status_runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        filename=f"{token}_alpha",
        status_filter="error",
    )
    date_status_runs = repositories.list_inspection_runs(
        session,
        limit=10,
        offset=0,
        created_at_start=datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc),
        created_at_end_exclusive=datetime(2026, 7, 3, 0, 0, tzinfo=timezone.utc),
        status_filter="error",
    )
    first_page = repositories.list_inspection_runs(
        session,
        limit=1,
        offset=0,
        filename=f"{token}_alpha",
        created_at_start=datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc),
        created_at_end_exclusive=datetime(2026, 7, 3, 0, 0, tzinfo=timezone.utc),
        status_filter="error",
    )
    second_page = repositories.list_inspection_runs(
        session,
        limit=1,
        offset=1,
        filename=f"{token}_alpha",
        created_at_start=datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc),
        created_at_end_exclusive=datetime(2026, 7, 3, 0, 0, tzinfo=timezone.utc),
        status_filter="error",
    )

    assert {run.id for run in filename_status_runs} == {
        first_run_id,
        second_run_id,
        before_run_id,
        after_run_id,
    }
    assert {run.id for run in date_status_runs} == {
        first_run_id,
        second_run_id,
        beta_run_id,
    }
    assert [run.id for run in first_page] == [second_run_id]
    assert [run.id for run in second_page] == [first_run_id]
    assert (
        repositories.count_inspection_runs(
            session,
            filename=f"{token}_alpha",
            created_at_start=datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc),
            created_at_end_exclusive=datetime(2026, 7, 3, 0, 0, tzinfo=timezone.utc),
            status_filter="error",
        )
        == 2
    )
    assert (
        repositories.count_inspection_runs(
            session,
            filename=token,
            status_filter="normal",
        )
        == 0
    )


def test_repository_list_inspection_runs_does_not_query_results_table(
    database_session,
):
    session, created_source_filenames = database_session
    source_filename = unique_filename("no_results_join")
    created_source_filenames.append(source_filename)
    save_inspection_report_id(
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

    save_inspection_report_id(
        session,
        source_filename=first_source_filename,
        report=report,
    )
    save_inspection_report_id(
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
    inspection_run_id = save_inspection_report_id(
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
    first_run_id = save_inspection_report_id(
        session,
        source_filename=first_source_filename,
        report=first_report,
    )
    second_run_id = save_inspection_report_id(
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
    inspection_run_id = save_inspection_report_id(
        session,
        source_filename=source_filename,
        report=report,
    )

    results = repositories.get_inspection_results_by_run_id(
        session,
        inspection_run_id=inspection_run_id,
    )

    assert results == []


def test_get_inspection_detail_executes_two_selects_without_n_plus_one(
    database_session,
):
    session, created_source_filenames = database_session
    source_filename = unique_filename("detail_query_count")
    created_source_filenames.append(source_filename)
    report = make_report(
        [
            {**BASE_ROW, "price": "0"},
            {
                **BASE_ROW,
                "product_group_id": "G002",
                "product_id": "P002",
                "price": "0",
            },
        ]
    )
    inspection_run_id = save_inspection_report_id(
        session,
        source_filename=source_filename,
        report=report,
    )
    session.expunge_all()
    select_statements: list[str] = []

    def collect_selects(conn, cursor, statement, parameters, context, executemany):
        normalized_statement = statement.lstrip().lower()
        if normalized_statement.startswith("select"):
            select_statements.append(normalized_statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", collect_selects)
    try:
        detail = persistence_service.get_inspection_detail(
            session,
            inspection_run_id=inspection_run_id,
        )
    finally:
        event.remove(engine, "before_cursor_execute", collect_selects)

    assert detail is not None
    assert len(detail.results) == report.summary.total_issues
    assert len(select_statements) == 2
    assert "inspection_runs" in select_statements[0]
    assert "inspection_results" in select_statements[1]


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
