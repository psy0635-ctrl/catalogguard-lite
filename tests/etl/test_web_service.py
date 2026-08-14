import csv
import io
import os
import tempfile
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from config.database import get_optional_database_url
from config.settings import MAX_UPLOAD_SIZE_BYTES
from core.upload_validator import CsvUploadValidationError
from db.models import CatalogProductStaging, ETLLoadRun
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


def valid_row(sku: str) -> list[str]:
    return [sku, "테스트 상품", "TOP", "브랜드", "12000", "10000", "BLACK", "M", "3", "설명", "image.jpg"]


def invalid_row(sku: str) -> list[str]:
    return [sku, "오류 상품", "TOP", "브랜드", "무료", "", "BLACK", "M", "1", "설명", "image.jpg"]


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
