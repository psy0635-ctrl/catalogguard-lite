import csv
import hashlib
import json
import os
import subprocess
import sys
from io import StringIO
from uuid import uuid4

import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError

from config.database import get_optional_database_url
from db.models import CatalogProductStaging, ETLLoadRun, ETLRejectedRow
from db.session import create_database_engine, create_session_factory
from etl.db_loader import (
    ETLLoadError,
    _build_staging_rows,
    _normalize_summary,
    load_standard_csv,
)


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
    "sale_price",
    "description",
    "seller",
]


def make_standard_csv(rows: list[dict[str, str]]) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def make_summary(csv_bytes: bytes, *, version: str = "1", **changes) -> bytes:
    summary = {
        "profile_name": "test_profile",
        "profile_version": version,
        "input_filename": "supplier.csv",
        "input_file_sha256": hashlib.sha256(b"supplier bytes").hexdigest(),
        "output_file_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "total_rows": 2,
        "loaded_rows": 2,
        "rejected_rows": 0,
        "error_counts": {},
    }
    summary.update(changes)
    return json.dumps(summary).encode("utf-8")


def make_rejects_csv(
    *,
    source_row_number: int = 4,
    description: str = "문의 010-1234-5678 seller@example.com",
) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "source_row_number",
            "error_code",
            "error_field",
            "error_message",
            "sku_code",
            "description",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerow(
        {
            "source_row_number": source_row_number,
            "error_code": '["INVALID_PRICE", "NEGATIVE_STOCK"]',
            "error_field": '["price", "stock"]',
            "error_message": '["bad price", "negative stock"]',
            "sku_code": "SKU-REJECT-1",
            "description": description,
        }
    )
    return output.getvalue().encode("utf-8")


def test_normalize_summary_returns_a_new_trimmed_error_counts_dict_without_mutating_input():
    summary = json.loads(make_summary(b"output"))
    summary["output_file_sha256"] = hashlib.sha256(b"output").hexdigest()
    summary["total_rows"] = 3
    summary["loaded_rows"] = 2
    summary["rejected_rows"] = 1
    summary["error_counts"] = {" INVALID_PRICE ": 1, "NEGATIVE_STOCK": 1}

    normalized = _normalize_summary(summary)

    assert normalized["error_counts"] == {"INVALID_PRICE": 1, "NEGATIVE_STOCK": 1}
    assert summary["error_counts"] == {" INVALID_PRICE ": 1, "NEGATIVE_STOCK": 1}


@pytest.mark.parametrize(
    "value",
    [" " + "a" * 64, "A" * 64, "a" * 63, None, 123],
)
def test_normalize_summary_rejects_noncanonical_profile_definition_hash(value):
    summary = json.loads(make_summary(b"output"))
    summary["profile_definition_sha256"] = value

    with pytest.raises(ETLLoadError, match="profile_definition_sha256"):
        _normalize_summary(summary)


def test_normalize_summary_allows_legacy_summary_without_profile_definition_hash():
    summary = json.loads(make_summary(b"output"))

    normalized = _normalize_summary(summary)

    assert "profile_definition_sha256" not in normalized


@pytest.mark.parametrize("value", ["", "A" * 40, "a" * 39, "a" * 41, "g" * 40, 123, []])
def test_normalize_summary_rejects_noncanonical_application_commit_sha(value):
    summary = json.loads(make_summary(b"output"))
    summary["application_commit_sha"] = value

    with pytest.raises(ETLLoadError, match="application_commit_sha"):
        _normalize_summary(summary)


def test_normalize_summary_allows_missing_or_null_application_commit_sha():
    summary = json.loads(make_summary(b"output"))
    assert "application_commit_sha" not in _normalize_summary(summary)

    summary["application_commit_sha"] = None
    assert _normalize_summary(summary)["application_commit_sha"] is None


ROWS = [
    {
        "product_group_id": "G001",
        "product_id": "P001",
        "product_name": "첫 상품",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": "3",
        "price": "12000",
        "image_path": "image-1.jpg",
        "sale_price": "10000",
        "description": "설명",
        "seller": "판매자",
    },
    {
        "product_group_id": "G002",
        "product_id": "P002",
        "product_name": "둘째 상품",
        "category": "BOTTOM",
        "color": "WHITE",
        "size": "L",
        "stock": "0",
        "price": "20000",
        "image_path": "image-2.jpg",
        "sale_price": "",
        "description": "",
        "seller": "",
    },
]


@pytest.fixture()
def postgres_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    profile_name = f"test_profile_{uuid4().hex}"
    try:
        yield session, profile_name
    finally:
        session.rollback()
        session.close()
        with session_factory() as cleanup:
            cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.profile_name == profile_name))
            cleanup.commit()
        engine.dispose()


def test_staging_models_define_required_columns_and_constraints():
    assert ETLLoadRun.__tablename__ == "etl_load_runs"
    assert CatalogProductStaging.__tablename__ == "catalog_products_staging"
    assert ETLLoadRun.__table__.c.loaded_rows.nullable is False
    assert CatalogProductStaging.__table__.c.sale_price.nullable is True
    assert CatalogProductStaging.__table__.c.description.nullable is True
    assert CatalogProductStaging.__table__.c.seller.nullable is True
    constraint_names = {
        constraint.name
        for table in (ETLLoadRun.__table__, CatalogProductStaging.__table__)
        for constraint in table.constraints
        if constraint.name
    }
    assert {
        "ck_etl_load_runs_loaded_rows_non_negative",
        "ck_catalog_products_staging_stock_non_negative",
        "ck_catalog_products_staging_price_non_negative",
        "ck_catalog_products_staging_sale_price_non_negative",
    }.issubset(constraint_names)


def test_load_standard_csv_persists_batch_and_products(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary = make_summary(csv_bytes)
    summary_data = json.loads(summary)
    summary_data["profile_name"] = profile_name

    outcome = load_standard_csv(session, csv_bytes, json.dumps(summary_data).encode())

    assert outcome.created is True
    assert outcome.loaded_rows == 2
    run = session.get(ETLLoadRun, outcome.etl_load_run_id)
    assert run is not None
    assert run.profile_name == profile_name
    assert run.total_rows == 2
    assert run.rejected_rows == 0
    assert run.error_counts == {}
    assert len(run.products) == 2
    assert run.products[1].sale_price is None


def test_load_standard_csv_persists_reject_rows_as_structured_masked_json(
    postgres_session,
):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    rejects_bytes = make_rejects_csv()
    summary_data = json.loads(
        make_summary(
            csv_bytes,
            profile_name=profile_name,
            total_rows=3,
            loaded_rows=2,
            rejected_rows=1,
            error_counts={"INVALID_PRICE": 1, "NEGATIVE_STOCK": 1},
            rejects_file_sha256=hashlib.sha256(rejects_bytes).hexdigest(),
        )
    )

    outcome = load_standard_csv(
        session,
        csv_bytes,
        json.dumps(summary_data).encode(),
        rejects_csv_bytes=rejects_bytes,
        rejects_csv_filename="rejected_rows.csv",
    )

    run = session.get(ETLLoadRun, outcome.etl_load_run_id)
    assert run is not None
    assert run.reject_details_stored is True
    assert run.rejects_file_sha256 == hashlib.sha256(rejects_bytes).hexdigest()
    assert len(run.reject_items) == 1
    rejected = run.reject_items[0]
    assert rejected.source_row_number == 4
    assert rejected.errors == [
        {"code": "INVALID_PRICE", "field": "price", "message": "bad price"},
        {
            "code": "NEGATIVE_STOCK",
            "field": "stock",
            "message": "negative stock",
        },
    ]
    assert rejected.masked_source_data["description"] == (
        "문의 010-****-5678 se****@example.com"
    )
    assert "010-1234-5678" not in json.dumps(rejected.masked_source_data)
    assert "seller@example.com" not in json.dumps(rejected.masked_source_data)


def test_reject_summary_requires_reject_file_when_hash_is_present(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary_data = json.loads(
        make_summary(
            csv_bytes,
            profile_name=profile_name,
            total_rows=3,
            loaded_rows=2,
            rejected_rows=1,
            error_counts={"INVALID_PRICE": 1},
            rejects_file_sha256="a" * 64,
        )
    )

    with pytest.raises(ETLLoadError):
        load_standard_csv(session, csv_bytes, json.dumps(summary_data).encode())


def test_zero_reject_summary_stores_validated_empty_reject_file(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    output = StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(
        [
            "source_row_number",
            "error_code",
            "error_field",
            "error_message",
            "sku_code",
        ]
    )
    rejects_bytes = output.getvalue().encode("utf-8")
    summary_data = json.loads(
        make_summary(
            csv_bytes,
            profile_name=profile_name,
            rejects_file_sha256=hashlib.sha256(rejects_bytes).hexdigest(),
        )
    )

    outcome = load_standard_csv(
        session,
        csv_bytes,
        json.dumps(summary_data).encode(),
        rejects_csv_bytes=rejects_bytes,
        rejects_csv_filename="rejected_rows.csv",
    )

    run = session.get(ETLLoadRun, outcome.etl_load_run_id)
    assert run.reject_details_stored is True
    assert run.reject_items == []


def test_reject_storage_failure_rolls_back_batch_and_products(postgres_session, monkeypatch):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    rejects_bytes = make_rejects_csv()
    summary_data = json.loads(
        make_summary(
            csv_bytes,
            profile_name=profile_name,
            total_rows=3,
            loaded_rows=2,
            rejected_rows=1,
            error_counts={"INVALID_PRICE": 1},
            rejects_file_sha256=hashlib.sha256(rejects_bytes).hexdigest(),
        )
    )

    from etl import db_loader

    def fail_reject_insert(*args, **kwargs):
        raise RuntimeError("simulated reject insert failure")

    monkeypatch.setattr(db_loader, "_add_rejected_rows", fail_reject_insert)
    with pytest.raises(RuntimeError):
        load_standard_csv(
            session,
            csv_bytes,
            json.dumps(summary_data).encode(),
            rejects_csv_bytes=rejects_bytes,
        )
    session.rollback()

    assert session.scalar(
        select(ETLLoadRun.id).where(ETLLoadRun.profile_name == profile_name)
    ) is None


def test_repeated_identity_returns_existing_batch_without_duplicate_products(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary_data = json.loads(make_summary(csv_bytes))
    summary_data["profile_name"] = profile_name
    summary = json.dumps(summary_data).encode()

    first = load_standard_csv(session, csv_bytes, summary)
    second = load_standard_csv(session, csv_bytes, summary)

    assert first.created is True
    assert second.created is False
    assert second.etl_load_run_id == first.etl_load_run_id
    assert session.scalar(
        select(ETLLoadRun).where(ETLLoadRun.profile_name == profile_name)
    ).loaded_rows == 2
    assert session.scalar(
        select(CatalogProductStaging.id).where(
            CatalogProductStaging.etl_load_run_id == first.etl_load_run_id
        ).limit(1)
    ) is not None
    assert session.scalar(
        select(text("count(*)")).select_from(CatalogProductStaging).where(
            CatalogProductStaging.etl_load_run_id == first.etl_load_run_id
        )
    ) == 2


def test_duplicate_with_different_known_profile_definition_is_rejected(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    first_summary = json.loads(make_summary(csv_bytes))
    first_summary.update(
        profile_name=profile_name,
        profile_definition_sha256="a" * 64,
    )
    second_summary = {**first_summary, "profile_definition_sha256": "b" * 64}

    first = load_standard_csv(session, csv_bytes, json.dumps(first_summary).encode())

    with pytest.raises(ETLLoadError, match="프로필 정의"):
        load_standard_csv(session, csv_bytes, json.dumps(second_summary).encode())

    persisted = session.get(ETLLoadRun, first.etl_load_run_id)
    assert persisted is not None
    assert persisted.profile_definition_sha256 == "a" * 64


def test_duplicate_legacy_null_profile_definition_remains_unchanged(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    legacy_summary = json.loads(make_summary(csv_bytes))
    legacy_summary["profile_name"] = profile_name
    known_summary = {**legacy_summary, "profile_definition_sha256": "a" * 64}

    first = load_standard_csv(session, csv_bytes, json.dumps(legacy_summary).encode())
    second = load_standard_csv(session, csv_bytes, json.dumps(known_summary).encode())

    assert second.created is False
    assert second.etl_load_run_id == first.etl_load_run_id
    assert second.profile_definition_sha256 is None
    assert session.get(ETLLoadRun, first.etl_load_run_id).profile_definition_sha256 is None


def test_application_commit_sha_is_saved_and_duplicate_does_not_backfill_legacy_null(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    legacy_summary = json.loads(make_summary(csv_bytes, profile_name=profile_name))
    known_summary = {**legacy_summary, "application_commit_sha": "a" * 40}

    first = load_standard_csv(session, csv_bytes, json.dumps(legacy_summary).encode())
    duplicate = load_standard_csv(session, csv_bytes, json.dumps(known_summary).encode())

    assert duplicate.created is False
    assert duplicate.application_commit_sha is None
    assert session.get(ETLLoadRun, first.etl_load_run_id).application_commit_sha is None


def test_application_commit_sha_is_saved_for_a_new_batch(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary = json.loads(make_summary(csv_bytes, profile_name=profile_name))
    summary["application_commit_sha"] = "a" * 40

    outcome = load_standard_csv(session, csv_bytes, json.dumps(summary).encode())

    assert outcome.application_commit_sha == "a" * 40
    assert session.get(ETLLoadRun, outcome.etl_load_run_id).application_commit_sha == "a" * 40


def test_profile_version_change_creates_new_batch(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    first_summary = json.loads(make_summary(csv_bytes, version="1"))
    first_summary["profile_name"] = profile_name
    second_summary = json.loads(make_summary(csv_bytes, version="2"))
    second_summary["profile_name"] = profile_name

    first = load_standard_csv(session, csv_bytes, json.dumps(first_summary).encode())
    second = load_standard_csv(session, csv_bytes, json.dumps(second_summary).encode())

    assert first.created is True
    assert second.created is True
    assert second.etl_load_run_id != first.etl_load_run_id


@pytest.mark.parametrize(
    "summary_change",
    [
        {"output_file_sha256": "0" * 64},
        {"loaded_rows": 1},
    ],
)
def test_invalid_output_identity_or_row_count_does_not_change_db(postgres_session, summary_change):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary_data = json.loads(make_summary(csv_bytes))
    summary_data["profile_name"] = profile_name
    summary_data.update(summary_change)

    with pytest.raises(ETLLoadError):
        load_standard_csv(session, csv_bytes, json.dumps(summary_data).encode())

    assert session.scalar(
        select(ETLLoadRun.id).where(ETLLoadRun.profile_name == profile_name)
    ) is None


def test_invalid_standard_csv_does_not_change_db(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = b"product_id,product_name\nP001,invalid\n"
    summary = make_summary(csv_bytes, loaded_rows=1, profile_name=profile_name)

    with pytest.raises(ETLLoadError):
        load_standard_csv(session, csv_bytes, summary)

    assert session.scalar(
        select(ETLLoadRun.id).where(ETLLoadRun.profile_name == profile_name)
    ) is None


def test_product_storage_failure_rolls_back_batch(postgres_session, monkeypatch):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary_data = json.loads(make_summary(csv_bytes))
    summary_data["profile_name"] = profile_name

    from etl import db_loader

    def fail_product_insert(*args, **kwargs):
        raise RuntimeError("simulated product insert failure")

    monkeypatch.setattr(db_loader, "_add_staging_products", fail_product_insert)
    with pytest.raises(RuntimeError):
        load_standard_csv(session, csv_bytes, json.dumps(summary_data).encode())
    session.rollback()

    assert session.scalar(
        select(ETLLoadRun.id).where(ETLLoadRun.profile_name == profile_name)
    ) is None


@pytest.mark.parametrize(
    "summary_change",
    [
        {"total_rows": True},
        {"loaded_rows": "2"},
        {"rejected_rows": -1},
        {"total_rows": 3, "rejected_rows": 2},
        {"error_counts": []},
        {"error_counts": {" ": 1}},
        {"error_counts": {"INVALID_PRICE": True}},
        {"error_counts": {"INVALID_PRICE": 0}},
        {"rejected_rows": 0, "error_counts": {"INVALID_PRICE": 1}},
        {"rejected_rows": 1, "error_counts": {}},
    ],
)
def test_invalid_quality_summary_is_rejected_before_database_write(
    postgres_session, summary_change
):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary_data = json.loads(make_summary(csv_bytes))
    summary_data["profile_name"] = profile_name
    summary_data.update(summary_change)

    with pytest.raises(ETLLoadError):
        load_standard_csv(session, csv_bytes, json.dumps(summary_data).encode())

    assert session.scalar(
        select(ETLLoadRun.id).where(ETLLoadRun.profile_name == profile_name)
    ) is None


def test_quality_summary_allows_multiple_error_codes_for_one_rejected_row(
    postgres_session,
):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary_data = json.loads(make_summary(csv_bytes))
    summary_data.update(
        profile_name=profile_name,
        total_rows=3,
        rejected_rows=1,
        error_counts={" NEGATIVE_STOCK ": 1, "INVALID_PRICE": 1},
    )

    outcome = load_standard_csv(session, csv_bytes, json.dumps(summary_data).encode())

    run = session.get(ETLLoadRun, outcome.etl_load_run_id)
    assert run.error_counts == {"NEGATIVE_STOCK": 1, "INVALID_PRICE": 1}


@pytest.mark.parametrize("field", ["stock", "price", "sale_price"])
def test_negative_numeric_values_are_rejected_by_database(postgres_session, field):
    session, profile_name = postgres_session
    run = ETLLoadRun(
        source_filename="supplier.csv",
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256=hashlib.sha256(b"supplier bytes").hexdigest(),
        output_file_sha256=hashlib.sha256(b"output bytes").hexdigest(),
        loaded_rows=1,
    )
    session.add(run)
    session.flush()
    product_data = {
        "etl_load_run_id": run.id,
        "product_group_id": "G001",
        "product_id": "P001",
        "product_name": "상품",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 1,
        "price": 100,
        "sale_price": None,
        "image_path": "image.jpg",
    }
    product_data[field] = -1

    with pytest.raises(IntegrityError):
        session.add(CatalogProductStaging(**product_data))
        session.flush()
    session.rollback()
    assert session.scalar(
        select(ETLLoadRun.id).where(ETLLoadRun.profile_name == profile_name)
    ) is None


def test_deleting_batch_deletes_staging_products(postgres_session):
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv(ROWS)
    summary_data = json.loads(make_summary(csv_bytes))
    summary_data["profile_name"] = profile_name
    outcome = load_standard_csv(session, csv_bytes, json.dumps(summary_data).encode())

    session.delete(session.get(ETLLoadRun, outcome.etl_load_run_id))
    session.commit()

    assert session.scalar(
        select(CatalogProductStaging.id).where(
            CatalogProductStaging.etl_load_run_id == outcome.etl_load_run_id
        )
    ) is None


def test_cli_reports_success_and_hides_database_url(tmp_path):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL CLI 테스트를 건너뜁니다.")
    csv_bytes = make_standard_csv(ROWS)
    input_path = tmp_path / "ready.csv"
    summary_path = tmp_path / "summary.json"
    input_path.write_bytes(csv_bytes)
    summary_data = json.loads(make_summary(csv_bytes))
    summary_data["profile_name"] = f"cli_profile_{uuid4().hex}"
    summary_path.write_text(json.dumps(summary_data), encoding="utf-8")
    env = {**os.environ, "DATABASE_URL": database_url}

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "etl.load_cli",
            "--input",
            str(input_path),
            "--summary",
            str(summary_path),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "DB 적재 완료" in result.stdout
    assert "상품 행: 2" in result.stdout
    assert database_url not in result.stdout + result.stderr

    engine = create_database_engine(database_url)
    try:
        with create_session_factory(engine)() as cleanup:
            cleanup.execute(
                delete(ETLLoadRun).where(
                    ETLLoadRun.profile_name == summary_data["profile_name"]
                )
            )
            cleanup.commit()
    finally:
        engine.dispose()


def test_cli_accepts_rejects_file_and_persists_reject_details(tmp_path):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL???ㅼ젙?섏? ?딆븘 PostgreSQL CLI ?뚯뒪?몃? 嫄대꼫?곷땲??")
    csv_bytes = make_standard_csv(ROWS)
    rejects_bytes = make_rejects_csv()
    input_path = tmp_path / "ready.csv"
    rejects_path = tmp_path / "rejected_rows.csv"
    summary_path = tmp_path / "summary.json"
    input_path.write_bytes(csv_bytes)
    rejects_path.write_bytes(rejects_bytes)
    summary_data = json.loads(
        make_summary(
            csv_bytes,
            profile_name=f"cli_reject_profile_{uuid4().hex}",
            total_rows=3,
            loaded_rows=2,
            rejected_rows=1,
            error_counts={"INVALID_PRICE": 1, "NEGATIVE_STOCK": 1},
            rejects_file_sha256=hashlib.sha256(rejects_bytes).hexdigest(),
        )
    )
    summary_path.write_text(json.dumps(summary_data), encoding="utf-8")
    env = {**os.environ, "DATABASE_URL": database_url}

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "etl.load_cli",
            "--input",
            str(input_path),
            "--rejects",
            str(rejects_path),
            "--summary",
            str(summary_path),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "거부 행: 1" in result.stdout
    engine = create_database_engine(database_url)
    try:
        with create_session_factory(engine)() as cleanup:
            run = cleanup.scalar(
                select(ETLLoadRun).where(
                    ETLLoadRun.profile_name == summary_data["profile_name"]
                )
            )
            assert run is not None
            assert run.reject_details_stored is True
            assert len(run.reject_items) == 1
            cleanup.delete(run)
            cleanup.commit()
    finally:
        engine.dispose()


def test_cli_reports_safe_failure_without_database_url(tmp_path):
    csv_bytes = make_standard_csv(ROWS)
    input_path = tmp_path / "ready.csv"
    summary_path = tmp_path / "summary.json"
    input_path.write_bytes(csv_bytes)
    summary_path.write_bytes(make_summary(csv_bytes))
    env = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "etl.load_cli",
            "--input",
            str(input_path),
            "--summary",
            str(summary_path),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "DATABASE_URL" not in result.stderr
    assert "postgresql" not in result.stderr.lower()


def test_alembic_head_contains_staging_tables_when_database_is_configured(postgres_session):
    session, _ = postgres_session
    names = set(inspect(session.bind).get_table_names())
    assert {"etl_load_runs", "catalog_products_staging"}.issubset(names)


def test_alembic_downgrade_removes_only_staging_tables_and_upgrade_restores_them(
    monkeypatch,
):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 Alembic 통합 테스트를 건너뜁니다.")

    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")
    engine = create_database_engine(database_url)
    try:
        before_downgrade = set(inspect(engine).get_table_names())
        command.downgrade(alembic_config, "20260705_0002")
        after_downgrade = set(inspect(engine).get_table_names())
        assert {"inspection_runs", "inspection_results"}.issubset(after_downgrade)
        assert {"etl_load_runs", "catalog_products_staging"}.isdisjoint(after_downgrade)
        command.upgrade(alembic_config, "head")
        after_upgrade = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {"etl_load_runs", "catalog_products_staging"}.issubset(before_downgrade)
    assert {"etl_load_runs", "catalog_products_staging"}.issubset(after_upgrade)


# 아래는 ETL 적재도 검수와 같은 카테고리별 필수 속성 정책을 쓰는지 확인합니다.
def bag_row(**changes) -> dict[str, str]:
    row = {
        "product_group_id": "G900",
        "product_id": "P900",
        "product_name": "레더 토트백",
        "category": "BAG",
        "color": "BLACK",
        "size": "",
        "stock": "5",
        "price": "59000",
        "image_path": "bag.jpg",
        "sale_price": "",
        "description": "",
        "seller": "",
    }
    row.update(changes)
    return row


def test_build_staging_rows_allows_blank_size_for_bag():
    rows = _build_staging_rows(pd.DataFrame([bag_row()], columns=CSV_COLUMNS))

    assert len(rows) == 1
    assert rows[0]["category"] == "BAG"
    assert rows[0]["size"] == ""


@pytest.mark.parametrize("category", ["TOP", "BOTTOM", "OUTER", "SHOES"])
def test_build_staging_rows_still_fails_on_blank_size_for_apparel(category):
    dataframe = pd.DataFrame([bag_row(category=category)], columns=CSV_COLUMNS)

    with pytest.raises(ETLLoadError, match="필수 상품 값이 비어 있습니다"):
        _build_staging_rows(dataframe)


@pytest.mark.parametrize("blank_field", ["color", "image_path", "product_name"])
def test_build_staging_rows_still_fails_on_other_blank_required_fields_for_bag(blank_field):
    dataframe = pd.DataFrame([bag_row(**{blank_field: ""})], columns=CSV_COLUMNS)

    with pytest.raises(ETLLoadError, match="필수 상품 값이 비어 있습니다"):
        _build_staging_rows(dataframe)


@pytest.mark.parametrize("category", ["ACCESSORY", "bag", ""])
def test_build_staging_rows_keeps_blank_size_required_for_non_canonical_category(category):
    # 허용 목록에 없거나 canonical이 아닌 카테고리는 BAG로 추정하지 않습니다.
    dataframe = pd.DataFrame([bag_row(category=category)], columns=CSV_COLUMNS)

    with pytest.raises(ETLLoadError, match="필수 상품 값이 비어 있습니다"):
        _build_staging_rows(dataframe)


def test_load_standard_csv_persists_bag_row_without_size(postgres_session):
    # size 컬럼은 NOT NULL이지만 빈 문자열은 저장할 수 있어 migration이 필요하지 않습니다.
    session, profile_name = postgres_session
    csv_bytes = make_standard_csv([bag_row(), ROWS[0]])
    summary_data = json.loads(make_summary(csv_bytes))
    summary_data["profile_name"] = profile_name

    outcome = load_standard_csv(session, csv_bytes, json.dumps(summary_data).encode())

    assert outcome.created is True
    run = session.get(ETLLoadRun, outcome.etl_load_run_id)
    stored = {product.product_id: product for product in run.products}
    assert stored["P900"].size == ""
    assert stored["P900"].category == "BAG"
    assert stored["P001"].size == "M"


def test_same_supplier_input_is_reloaded_under_new_profile_version(postgres_session):
    # 같은 공급사 입력이라도 profile version이 다르면 새 배치로 적재되어야
    # BAG 정책 변경 전 결과를 그대로 재사용하지 않습니다.
    session, profile_name = postgres_session
    old_csv = make_standard_csv([ROWS[0]])
    old_summary = json.loads(
        make_summary(old_csv, version="1", total_rows=1, loaded_rows=1)
    )
    old_summary["profile_name"] = profile_name

    new_csv = make_standard_csv([ROWS[0], bag_row()])
    new_summary = json.loads(make_summary(new_csv, version="2"))
    new_summary["profile_name"] = profile_name
    # 같은 공급사 파일에서 나온 결과이므로 input hash는 동일합니다.
    assert old_summary["input_file_sha256"] == new_summary["input_file_sha256"]

    old_run = load_standard_csv(session, old_csv, json.dumps(old_summary).encode())
    new_run = load_standard_csv(session, new_csv, json.dumps(new_summary).encode())

    assert old_run.created is True
    assert new_run.created is True
    assert new_run.etl_load_run_id != old_run.etl_load_run_id

    # 기존 version 1 이력은 그대로 보존됩니다.
    stored_old = session.get(ETLLoadRun, old_run.etl_load_run_id)
    assert stored_old.profile_version == "1"
    assert [product.product_id for product in stored_old.products] == ["P001"]

    stored_new = session.get(ETLLoadRun, new_run.etl_load_run_id)
    assert stored_new.profile_version == "2"
    assert {product.product_id for product in stored_new.products} == {"P001", "P900"}
    assert {
        product.product_id: product.size for product in stored_new.products
    }["P900"] == ""
