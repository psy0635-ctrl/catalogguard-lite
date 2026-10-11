import csv
import hashlib
import io
import os
import tempfile
from uuid import uuid4

import pytest
from openpyxl import Workbook
from sqlalchemy import delete, select

from config.database import get_optional_database_url
from config.settings import MAX_UPLOAD_SIZE_BYTES
from core.upload_validator import CsvUploadValidationError
from db.models import CatalogProductStaging, ETLLoadRun, ETLRejectedRow
from db.session import create_database_engine, create_session_factory
from etl.db_loader import ETLLoadError
from etl.pipeline import ETLPipelineError
from etl.profile_loader import ETLProfileNotFoundError
from etl.web_service import run_web_etl


FASHION_PROFILE_COLUMNS = [
    "vendor_sku",
    "item_name",
    "main_category",
    "brand_name",
    "list_price",
    "discount_price",
    "colour",
    "size_name",
    "quantity",
    "description_text",
    "image_link",
]


def build_supplier_csv(rows: list[list[str]], *, unique_marker: str) -> bytes:
    del unique_marker  # kept for call-site clarity; uniqueness lives in the SKU values
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FASHION_PROFILE_COLUMNS)
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def build_supplier_xlsx(rows: list[list[str]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(FASHION_PROFILE_COLUMNS)
    for row in rows:
        worksheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def valid_row(sku: str) -> list[str]:
    return [sku, "테스트 상품", "TOP", "브랜드", "12000", "10000", "BLACK", "M", "3", "설명", "image.jpg"]


@pytest.mark.parametrize("input_format", ["csv", "xlsx"])
def test_web_etl_rejects_reserved_metadata_before_database_load(input_format):
    from tests.conftest import FakeSessionWithoutRuntimeOverrides

    header = [*FASHION_PROFILE_COLUMNS, "Error_Message"]
    row = [*valid_row("SYNTHETIC-001"), "synthetic-private-value"]
    if input_format == "csv":
        output = io.StringIO(newline="")
        csv.writer(output).writerows([header, row])
        input_bytes = output.getvalue().encode("utf-8")
    else:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(header)
        worksheet.append(row)
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        input_bytes = output.getvalue()
    before_dirs = _list_temp_etl_dirs()

    with pytest.raises(ETLPipelineError, match="reserved ETL rejection metadata columns") as error:
        run_web_etl(
            FakeSessionWithoutRuntimeOverrides(),
            profile_id="sample_fashion_vendor_v1",
            source_filename=f"supplier.{input_format}",
            input_bytes=input_bytes,
            allowed_input_formats=("csv", "xlsx"),
        )

    assert "synthetic-private-value" not in str(error.value)
    assert _list_temp_etl_dirs() == before_dirs


def invalid_row(sku: str) -> list[str]:
    return [sku, "오류 상품", "TOP", "브랜드", "무료", "", "BLACK", "M", "1", "설명", "image.jpg"]


@pytest.mark.parametrize("input_format", ["csv", "xlsx"])
@pytest.mark.parametrize("reject", [False, True])
def test_preflight_reuses_pipeline_without_loading_and_cleans_files(monkeypatch, input_format, reject):
    from contextlib import nullcontext
    from dataclasses import asdict
    from tests.conftest import FakeSessionWithoutRuntimeOverrides
    from etl import web_service

    class ReadOnlySession(FakeSessionWithoutRuntimeOverrides):
        no_autoflush = nullcontext()

        def rollback(self):
            pytest.fail("Preflight must preserve the caller's transaction")

    def forbidden_load(*args, **kwargs):
        pytest.fail("Preflight must never load the database")

    monkeypatch.setattr(web_service, "load_standard_csv", forbidden_load)
    rows = [valid_row("SYNTHETIC-001")]
    if reject:
        bad = invalid_row("SYNTHETIC-002")
        bad[8] = "-1"
        rows.append(bad)
    content = (build_supplier_xlsx(rows) if input_format == "xlsx" else
               build_supplier_csv(rows, unique_marker="synthetic"))
    before = _list_temp_etl_dirs()
    result = web_service.preflight_web_etl(
        ReadOnlySession(), profile_id="sample_fashion_vendor_v1",
        source_filename=f"vendor.{input_format}", input_bytes=content,
    )
    assert asdict(result) == {
        "profile_name": "sample_fashion_vendor", "profile_version": "2",
        "total_rows": len(rows), "loaded_rows": 1, "rejected_rows": int(reject),
        "error_counts": {"INVALID_PRICE": 1, "NEGATIVE_STOCK": 1} if reject else {},
    }
    assert _list_temp_etl_dirs() == before


@pytest.mark.parametrize("content", [
    b"vendor_sku\nSKU\n",
    b"vendor_sku,vendor_sku\nSKU,SKU\n",
    b"", b"not-an-xlsx",
])
def test_preflight_invalid_input_cleans_files(content):
    from contextlib import nullcontext
    from tests.conftest import FakeSessionWithoutRuntimeOverrides
    from etl import web_service

    session = FakeSessionWithoutRuntimeOverrides()
    session.no_autoflush = nullcontext()
    before = _list_temp_etl_dirs()
    with pytest.raises((ETLPipelineError, CsvUploadValidationError)):
        web_service.preflight_web_etl(
            session, profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.xlsx" if content == b"not-an-xlsx" else "vendor.csv",
            input_bytes=content,
        )
    assert _list_temp_etl_dirs() == before


@pytest.mark.parametrize("failure", [False, True])
def test_preflight_preserves_pending_orm_and_core_writes_without_autoflush(failure):
    from sqlalchemy import create_engine, event, insert
    from sqlalchemy.orm import Session
    from db.models import User, ETLProfileActivation
    from etl.web_service import preflight_web_etl

    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    ETLProfileActivation.__table__.create(engine)
    try:
        with Session(engine, autoflush=True) as session:
            session.add_all([
                User(id=1, username="synthetic-1", password_hash="synthetic", role="viewer"),
                User(id=2, username="synthetic-2", password_hash="synthetic", role="viewer"),
            ])
            session.commit()
            dirty = session.get(User, 1)
            deleted = session.get(User, 2)
            dirty.username = "pending-update"
            session.delete(deleted)
            pending = User(id=3, username="pending-new", password_hash="synthetic", role="viewer")
            session.add(pending)
            with session.no_autoflush:
                session.execute(insert(User).values(id=4, username="pending-core", password_hash="synthetic", role="viewer"))
            transaction = session.get_transaction()
            statements = []
            def capture(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)
            event.listen(engine, "before_cursor_execute", capture)
            try:
                content = b"bad header\nvalue\n" if failure else build_supplier_csv([valid_row("SYNTHETIC")], unique_marker="test")
                if failure:
                    with pytest.raises(ETLPipelineError):
                        preflight_web_etl(session, profile_id="sample_fashion_vendor_v1", source_filename="vendor.csv", input_bytes=content)
                else:
                    assert preflight_web_etl(session, profile_id="sample_fashion_vendor_v1", source_filename="vendor.csv", input_bytes=content).loaded_rows == 1
                assert session.get_transaction() is transaction
                assert pending in session.new
                assert dirty in session.dirty
                assert deleted in session.deleted
                assert statements and all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
                with session.no_autoflush:
                    assert session.scalars(select(User.username).where(User.id == 4)).one() == "pending-core"
                    assert session.scalars(select(User.username).where(User.id == 1)).one() == "synthetic-1"
                    assert session.scalars(select(User.id).where(User.id == 2)).one() == 2
                    assert session.scalars(select(User.id).where(User.id == 3)).one_or_none() is None
            finally:
                event.remove(engine, "before_cursor_execute", capture)
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure", [False, True])
def test_preflight_postgres_all_tables_unchanged(postgres_session, failure):
    from db.base import Base
    from etl.web_service import preflight_web_etl
    session, _ = postgres_session
    def snapshot():
        return {table.name: sorted(repr(tuple(row)) for row in session.execute(select(table)))
                for table in Base.metadata.sorted_tables}
    # Include populated ingestion/rejection tables, not just an empty database.
    seed = run_web_etl(session, profile_id="sample_fashion_vendor_v1", source_filename="seed.csv",
                       input_bytes=build_supplier_csv([valid_row("SYNTHETIC"), invalid_row("SYNTHETIC-BAD")], unique_marker="test"))
    try:
        before = snapshot()
        content = b"bad header\nvalue\n" if failure else build_supplier_csv([valid_row("SYNTHETIC")], unique_marker="test")
        if failure:
            with pytest.raises(ETLPipelineError):
                preflight_web_etl(session, profile_id="sample_fashion_vendor_v1", source_filename="vendor.csv", input_bytes=content)
        else:
            result = preflight_web_etl(session, profile_id="sample_fashion_vendor_v1", source_filename="vendor.csv", input_bytes=content)
            assert result.loaded_rows == 1
        assert snapshot() == before
    finally:
        _cleanup_runs(postgres_session[1], [seed.etl_load_run_id])


def test_preflight_uses_active_version_and_real_run_rechecks_activation(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from db.models import ETLProfileActivation
    from etl.profile_loader import ETLProfileInactiveError
    from etl import web_service
    engine = create_engine("sqlite://")
    ETLProfileActivation.__table__.create(engine)
    try:
        with Session(engine) as session:
            override = ETLProfileActivation(id=1, profile_id="sample_fashion_vendor_v1", active_version="1")
            session.add(override)
            session.commit()
            content = build_supplier_csv([valid_row("SYNTHETIC")], unique_marker="test")
            assert web_service.preflight_web_etl(session, profile_id=override.profile_id, source_filename="vendor.csv", input_bytes=content).profile_version == "1"
            override.active_version = None
            session.commit()
            def forbidden(*args, **kwargs):
                pytest.fail("Inactive profile must not reach the loader")
            monkeypatch.setattr(web_service, "load_standard_csv", forbidden)
            with pytest.raises(ETLProfileInactiveError):
                web_service.run_web_etl(session, profile_id=override.profile_id, source_filename="vendor.csv", input_bytes=content)
            with pytest.raises(ETLProfileInactiveError):
                web_service.preflight_web_etl(session, profile_id=override.profile_id, source_filename="vendor.csv", input_bytes=content)
    finally:
        engine.dispose()


@pytest.mark.parametrize("case", ["reserved", "unsupported", "oversize", "unknown_profile", "price_policy"])
def test_preflight_existing_validation_and_price_policy(case):
    from contextlib import nullcontext
    from conftest import FakeSessionWithoutRuntimeOverrides
    from etl.web_service import preflight_web_etl
    session = FakeSessionWithoutRuntimeOverrides()
    session.no_autoflush = nullcontext()
    row = valid_row("SYNTHETIC")
    row[4] = "12,34"
    content = build_supplier_csv([row], unique_marker="test")
    filename, profile = "vendor.csv", "sample_fashion_vendor_v1"
    if case == "reserved":
        output = io.StringIO()
        csv.writer(output).writerows([[*FASHION_PROFILE_COLUMNS, "error_code"], [*row, "synthetic-private"]])
        content = output.getvalue().encode()
    elif case == "unsupported":
        filename = "vendor.txt"
    elif case == "oversize":
        content = b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)
    elif case == "unknown_profile":
        profile = "unknown"
    before = _list_temp_etl_dirs()
    if case == "price_policy":
        result = preflight_web_etl(session, profile_id=profile, source_filename=filename, input_bytes=content)
        assert result.loaded_rows == 1 and result.error_counts == {}
    else:
        with pytest.raises((ETLPipelineError, CsvUploadValidationError, ETLProfileNotFoundError)):
            preflight_web_etl(session, profile_id=profile, source_filename=filename, input_bytes=content)
    assert _list_temp_etl_dirs() == before


@pytest.fixture()
def postgres_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session, session_factory
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _cleanup_runs(session_factory, run_ids: list[int]) -> None:
    if not run_ids:
        return
    with session_factory() as cleanup:
        cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id.in_(run_ids)))
        cleanup.commit()


def _list_temp_etl_dirs() -> set[str]:
    base = tempfile.gettempdir()
    try:
        return {name for name in os.listdir(base) if name.startswith("catalogguard_web_etl_")}
    except OSError:
        return set()


def test_run_web_etl_persists_batch_and_staging_products(postgres_session):
    session, session_factory = postgres_session
    marker = uuid4().hex
    csv_bytes = build_supplier_csv([valid_row(f"SKU-{marker}-1"), valid_row(f"SKU-{marker}-2")], unique_marker=marker)

    before_dirs = _list_temp_etl_dirs()
    result = run_web_etl(
        session,
        profile_id="sample_fashion_vendor_v1",
        source_filename="vendor_products.csv",
        input_bytes=csv_bytes,
    )
    after_dirs = _list_temp_etl_dirs()

    try:
        assert result.created is True
        assert result.profile_name == "sample_fashion_vendor"
        assert result.profile_version == "2"
        assert result.source_filename == "vendor_products.csv"
        assert result.total_rows == 2
        assert result.loaded_rows == 2
        assert result.rejected_rows == 0

        run = session.get(ETLLoadRun, result.etl_load_run_id)
        assert run is not None
        products = session.scalars(
            select(CatalogProductStaging).where(
                CatalogProductStaging.etl_load_run_id == result.etl_load_run_id
            )
        ).all()
        assert len(products) == 2
        assert after_dirs - before_dirs == set()
    finally:
        _cleanup_runs(session_factory, [result.etl_load_run_id])


def test_run_web_etl_xlsx_requires_opt_in_and_preserves_identity_and_dedup(postgres_session):
    session, session_factory = postgres_session
    marker = uuid4().hex
    xlsx_bytes = build_supplier_xlsx(
        [
            valid_row(f"SKU-{marker}-1"),
            [None] * len(FASHION_PROFILE_COLUMNS),
            invalid_row(f"SKU-{marker}-2"),
        ]
    )

    with pytest.raises(CsvUploadValidationError, match="CSV"):
        run_web_etl(
            session,
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor_products.xlsx",
            input_bytes=xlsx_bytes,
        )

    first = run_web_etl(
        session,
        profile_id="sample_fashion_vendor_v1",
        source_filename="vendor_products.xlsx",
        input_bytes=xlsx_bytes,
        allowed_input_formats=("csv", "xlsx"),
    )
    try:
        with session_factory() as second_session:
            second = run_web_etl(
                second_session,
                profile_id="sample_fashion_vendor_v1",
                source_filename="renamed.xlsx",
                input_bytes=xlsx_bytes,
                allowed_input_formats=("csv", "xlsx"),
            )
        assert first.created is True
        assert second.created is False
        assert second.etl_load_run_id == first.etl_load_run_id
        assert first.source_filename == "vendor_products.xlsx"
        run = session.get(ETLLoadRun, first.etl_load_run_id)
        assert run.input_file_sha256 == hashlib.sha256(xlsx_bytes).hexdigest()
        assert run.source_filename == "vendor_products.xlsx"
        products = session.scalars(
            select(CatalogProductStaging).where(
                CatalogProductStaging.etl_load_run_id == first.etl_load_run_id
            )
        ).all()
        assert len(products) == 1
        rejects = session.scalars(
            select(ETLRejectedRow).where(
                ETLRejectedRow.etl_load_run_id == first.etl_load_run_id
            )
        ).all()
        assert len(rejects) == 1
        assert rejects[0].source_row_number == 4
    finally:
        _cleanup_runs(session_factory, [first.etl_load_run_id])


def test_run_web_etl_with_partial_rejects_loads_normal_rows_only(postgres_session):
    session, session_factory = postgres_session
    marker = uuid4().hex
    csv_bytes = build_supplier_csv(
        [valid_row(f"SKU-{marker}-1"), invalid_row(f"SKU-{marker}-2")],
        unique_marker=marker,
    )

    result = run_web_etl(
        session,
        profile_id="sample_fashion_vendor_v1",
        source_filename="vendor_mixed.csv",
        input_bytes=csv_bytes,
    )
    try:
        assert result.total_rows == 2
        assert result.loaded_rows == 1
        assert result.rejected_rows == 1
        assert result.error_counts

        products = session.scalars(
            select(CatalogProductStaging).where(
                CatalogProductStaging.etl_load_run_id == result.etl_load_run_id
            )
        ).all()
        assert len(products) == 1
    finally:
        _cleanup_runs(session_factory, [result.etl_load_run_id])


def test_run_web_etl_with_all_rejects_fails_the_same_way_the_cli_load_step_does(
    postgres_session,
):
    # etl.db_loader.load_standard_csv (shared with the CLI's etl.load_cli) refuses a
    # standard CSV with zero product rows, so an all-reject batch cannot be staged at
    # all -- this mirrors existing CLI behavior exactly rather than special-casing it.
    session, session_factory = postgres_session
    marker = uuid4().hex
    csv_bytes = build_supplier_csv([invalid_row(f"SKU-{marker}-1")], unique_marker=marker)

    with pytest.raises(ETLLoadError):
        run_web_etl(
            session,
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor_all_reject.csv",
            input_bytes=csv_bytes,
        )


def test_run_web_etl_duplicate_input_returns_existing_run_without_creating_new_row(
    postgres_session,
):
    # Two separate sessions, matching how two independent HTTP requests would each
    # get their own session from the FastAPI get_session dependency.
    session, session_factory = postgres_session
    marker = uuid4().hex
    csv_bytes = build_supplier_csv([valid_row(f"SKU-{marker}-1")], unique_marker=marker)

    first = run_web_etl(
        session,
        profile_id="sample_fashion_vendor_v1",
        source_filename="vendor.csv",
        input_bytes=csv_bytes,
    )
    try:
        with session_factory() as second_session:
            second = run_web_etl(
                second_session,
                profile_id="sample_fashion_vendor_v1",
                source_filename="vendor.csv",
                input_bytes=csv_bytes,
            )
        assert first.created is True
        assert second.created is False
        assert second.etl_load_run_id == first.etl_load_run_id

        with session_factory() as verify_session:
            matching_run_ids = verify_session.scalars(
                select(ETLLoadRun.id).where(
                    ETLLoadRun.profile_name == "sample_fashion_vendor",
                    ETLLoadRun.source_filename == "vendor.csv",
                )
            ).all()
            assert matching_run_ids == [first.etl_load_run_id]
    finally:
        _cleanup_runs(session_factory, [first.etl_load_run_id])


def test_run_web_etl_rejects_unknown_profile_without_touching_the_database(postgres_session):
    session, session_factory = postgres_session

    with pytest.raises(ETLProfileNotFoundError):
        run_web_etl(
            session,
            profile_id="../../config/etl/sample_fashion_vendor_v1.json",
            source_filename="vendor.csv",
            input_bytes=b"anything",
        )

    assert len(session.new) == 0
    assert len(session.dirty) == 0


def test_run_web_etl_rejects_empty_upload_without_creating_a_run(postgres_session):
    session, session_factory = postgres_session
    before_dirs = _list_temp_etl_dirs()

    with pytest.raises(CsvUploadValidationError):
        run_web_etl(
            session,
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            input_bytes=b"",
        )

    after_dirs = _list_temp_etl_dirs()
    assert after_dirs - before_dirs == set()


def test_run_web_etl_rejects_oversized_upload_without_running_the_pipeline(
    postgres_session, monkeypatch
):
    session, session_factory = postgres_session
    calls = []
    import etl.web_service as web_service_module

    monkeypatch.setattr(
        web_service_module,
        "run_pipeline",
        lambda *args, **kwargs: calls.append(1) or (_ for _ in ()).throw(AssertionError("run_pipeline should not be called")),
    )

    oversized_bytes = b"a,b\n" + b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)
    with pytest.raises(CsvUploadValidationError):
        run_web_etl(
            session,
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            input_bytes=oversized_bytes,
        )
    assert calls == []


def test_run_web_etl_rejects_malformed_supplier_csv_without_creating_a_run(postgres_session):
    session, session_factory = postgres_session
    before_dirs = _list_temp_etl_dirs()

    with pytest.raises(ETLPipelineError):
        run_web_etl(
            session,
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            input_bytes=b"only_one_column_header\nvalue\n",
        )

    after_dirs = _list_temp_etl_dirs()
    assert after_dirs - before_dirs == set()


def test_run_web_etl_cleans_up_temp_files_after_pipeline_failure(postgres_session):
    session, session_factory = postgres_session
    before_dirs = _list_temp_etl_dirs()

    with pytest.raises(ETLPipelineError):
        run_web_etl(
            session,
            profile_id="sample_fashion_vendor_v1",
            source_filename="vendor.csv",
            input_bytes=b"not,the,right,columns\n1,2,3,4\n",
        )

    after_dirs = _list_temp_etl_dirs()
    assert after_dirs - before_dirs == set()
