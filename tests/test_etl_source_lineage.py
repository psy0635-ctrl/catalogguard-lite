# 역할: ETLLoadRun이 "최초로 어떤 입력 경로에서 만들어졌는지"를 안전하게 기록하는지 검증합니다.
# dedup으로 재사용되는 배치는 최초 source를 유지해야 하므로 이름이 initial_* 입니다.
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from io import StringIO
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import String, delete, select, text

from config.database import get_optional_database_url
from config.settings import (
    ETL_HTTP_FEED_SOURCE_REF,
    ETL_INITIAL_SOURCE_REF_MAX_LENGTH,
    ETL_INITIAL_SOURCE_TYPES,
)
from db.models import ETLLoadRun
from db.session import create_database_engine, create_session_factory
from etl.db_loader import ETLLoadError, load_standard_csv


MIGRATION_REVISION = "20260813_0013"
PREVIOUS_REVISION = "20260810_0012"

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


def _standard_csv(marker: str) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "product_group_id": f"G-{marker}",
            "product_id": f"P-{marker}",
            "product_name": "Lineage Test Product",
            "category": "TOP",
            "color": "BLACK",
            "size": "M",
            "stock": "5",
            "price": "10000",
            "image_path": "image.jpg",
            "sale_price": "",
            "description": "",
            "seller": "",
        }
    )
    return output.getvalue().encode("utf-8")


def _summary(csv_bytes: bytes, marker: str) -> bytes:
    return json.dumps(
        {
            "profile_name": "lineage_test_profile",
            "profile_version": "1",
            "input_filename": f"supplier_{marker}.csv",
            "input_file_sha256": hashlib.sha256(f"supplier {marker}".encode()).hexdigest(),
            "output_file_sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "total_rows": 1,
            "loaded_rows": 1,
            "rejected_rows": 0,
            "error_counts": {},
        }
    ).encode("utf-8")


@pytest.fixture()
def postgres_session_factory():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        yield session_factory
    finally:
        engine.dispose()


def _cleanup(session_factory, input_hash: str) -> None:
    with session_factory() as cleanup:
        cleanup.execute(
            delete(ETLLoadRun).where(ETLLoadRun.input_file_sha256 == input_hash)
        )
        cleanup.commit()


# ---- schema contract -------------------------------------------------------


def test_initial_source_columns_have_expected_shape() -> None:
    columns = ETLLoadRun.__table__.columns
    source_type = columns["initial_source_type"]
    source_ref = columns["initial_source_ref"]

    # 최초 source는 항상 알 수 있어야 하므로 NOT NULL이고, legacy row는 "unknown"으로 채웁니다.
    assert source_type.nullable is False
    assert isinstance(source_type.type, String)
    assert source_type.type.length == 20
    # 영구 server_default를 두면 신규 경로가 값을 잊어도 조용히 unknown으로 저장됩니다.
    assert source_type.server_default is None

    assert source_ref.nullable is True
    assert isinstance(source_ref.type, String)
    assert source_ref.type.length == ETL_INITIAL_SOURCE_REF_MAX_LENGTH


def test_allowed_initial_source_types_are_fixed() -> None:
    assert ETL_INITIAL_SOURCE_TYPES == (
        "unknown",
        "upload",
        "s3",
        "http_feed",
        "cli",
    )


def test_initial_source_type_check_constraint_exists() -> None:
    constraint_names = {
        constraint.name for constraint in ETLLoadRun.__table__.constraints
    }
    assert "ck_etl_load_runs_initial_source_type" in constraint_names


def test_lineage_migration_is_the_single_alembic_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert list(script.get_heads()) == [MIGRATION_REVISION]
    revision = script.get_revision(MIGRATION_REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION


def test_dedup_identity_does_not_include_source_metadata() -> None:
    # source가 다르다는 이유로 새 배치가 생기면 기존 idempotency 계약이 깨집니다.
    [unique_index] = [
        index
        for index in ETLLoadRun.__table__.indexes
        if index.name == "ux_etl_load_runs_input_profile_version"
    ]
    assert [column.name for column in unique_index.columns] == [
        "input_file_sha256",
        "profile_name",
        "profile_version",
    ]


# ---- loader contract -------------------------------------------------------


def test_new_run_records_the_initial_source(postgres_session_factory) -> None:
    session_factory = postgres_session_factory
    marker = uuid4().hex
    csv_bytes = _standard_csv(marker)
    summary_bytes = _summary(csv_bytes, marker)
    input_hash = json.loads(summary_bytes)["input_file_sha256"]

    try:
        with session_factory() as session:
            outcome = load_standard_csv(
                session,
                csv_bytes,
                summary_bytes,
                initial_source_type="upload",
                initial_source_ref="catalog.csv",
            )
        assert outcome.created is True

        with session_factory() as verify:
            run = verify.get(ETLLoadRun, outcome.etl_load_run_id)
            assert run.initial_source_type == "upload"
            assert run.initial_source_ref == "catalog.csv"
    finally:
        _cleanup(session_factory, input_hash)


def test_loader_defaults_to_unknown_when_no_source_is_given(
    postgres_session_factory,
) -> None:
    session_factory = postgres_session_factory
    marker = uuid4().hex
    csv_bytes = _standard_csv(marker)
    summary_bytes = _summary(csv_bytes, marker)
    input_hash = json.loads(summary_bytes)["input_file_sha256"]

    try:
        with session_factory() as session:
            outcome = load_standard_csv(session, csv_bytes, summary_bytes)

        with session_factory() as verify:
            run = verify.get(ETLLoadRun, outcome.etl_load_run_id)
            assert run.initial_source_type == "unknown"
            assert run.initial_source_ref is None
    finally:
        _cleanup(session_factory, input_hash)


def test_unknown_source_type_is_rejected_before_touching_the_database(
    postgres_session_factory,
) -> None:
    session_factory = postgres_session_factory
    marker = uuid4().hex
    csv_bytes = _standard_csv(marker)
    summary_bytes = _summary(csv_bytes, marker)
    input_hash = json.loads(summary_bytes)["input_file_sha256"]

    try:
        with session_factory() as session:
            with pytest.raises(ETLLoadError):
                load_standard_csv(
                    session,
                    csv_bytes,
                    summary_bytes,
                    initial_source_type="random_source",
                )

        with session_factory() as verify:
            existing = verify.scalar(
                select(ETLLoadRun).where(ETLLoadRun.input_file_sha256 == input_hash)
            )
            assert existing is None
    finally:
        _cleanup(session_factory, input_hash)


def test_over_length_source_ref_is_truncated_not_a_driver_error(
    postgres_session_factory,
) -> None:
    session_factory = postgres_session_factory
    marker = uuid4().hex
    csv_bytes = _standard_csv(marker)
    summary_bytes = _summary(csv_bytes, marker)
    input_hash = json.loads(summary_bytes)["input_file_sha256"]
    long_ref = "a" * (ETL_INITIAL_SOURCE_REF_MAX_LENGTH + 50)

    try:
        with session_factory() as session:
            outcome = load_standard_csv(
                session,
                csv_bytes,
                summary_bytes,
                initial_source_type="s3",
                initial_source_ref=long_ref,
            )

        with session_factory() as verify:
            run = verify.get(ETLLoadRun, outcome.etl_load_run_id)
            assert len(run.initial_source_ref) == ETL_INITIAL_SOURCE_REF_MAX_LENGTH
    finally:
        _cleanup(session_factory, input_hash)


def test_blank_source_ref_is_stored_as_null(postgres_session_factory) -> None:
    session_factory = postgres_session_factory
    marker = uuid4().hex
    csv_bytes = _standard_csv(marker)
    summary_bytes = _summary(csv_bytes, marker)
    input_hash = json.loads(summary_bytes)["input_file_sha256"]

    try:
        with session_factory() as session:
            outcome = load_standard_csv(
                session,
                csv_bytes,
                summary_bytes,
                initial_source_type="cli",
                initial_source_ref="   ",
            )

        with session_factory() as verify:
            run = verify.get(ETLLoadRun, outcome.etl_load_run_id)
            assert run.initial_source_type == "cli"
            assert run.initial_source_ref is None
    finally:
        _cleanup(session_factory, input_hash)


# ---- the contract this whole feature exists for ----------------------------


def test_duplicate_ingest_from_another_source_keeps_the_initial_source(
    postgres_session_factory,
) -> None:
    """같은 bytes가 다른 경로로 다시 들어와도 최초 source가 덮어써지면 안 됩니다."""
    session_factory = postgres_session_factory
    marker = uuid4().hex
    csv_bytes = _standard_csv(marker)
    summary_bytes = _summary(csv_bytes, marker)
    input_hash = json.loads(summary_bytes)["input_file_sha256"]

    try:
        with session_factory() as session:
            first = load_standard_csv(
                session,
                csv_bytes,
                summary_bytes,
                initial_source_type="upload",
                initial_source_ref="first.csv",
            )
        assert first.created is True

        with session_factory() as session:
            second = load_standard_csv(
                session,
                csv_bytes,
                summary_bytes,
                initial_source_type="http_feed",
                initial_source_ref=ETL_HTTP_FEED_SOURCE_REF,
            )

        # dedup 계약은 그대로입니다: 새 배치를 만들지 않고 기존 배치를 돌려줍니다.
        assert second.created is False
        assert second.etl_load_run_id == first.etl_load_run_id

        with session_factory() as verify:
            run = verify.get(ETLLoadRun, first.etl_load_run_id)
            # "last seen source"가 아니라 "initial source"입니다.
            assert run.initial_source_type == "upload"
            assert run.initial_source_ref == "first.csv"
    finally:
        _cleanup(session_factory, input_hash)


def test_duplicate_outcome_reports_the_stored_initial_source(
    postgres_session_factory,
) -> None:
    session_factory = postgres_session_factory
    marker = uuid4().hex
    csv_bytes = _standard_csv(marker)
    summary_bytes = _summary(csv_bytes, marker)
    input_hash = json.loads(summary_bytes)["input_file_sha256"]

    try:
        with session_factory() as session:
            load_standard_csv(
                session,
                csv_bytes,
                summary_bytes,
                initial_source_type="s3",
                initial_source_ref="vendor-a/products.csv",
            )

        with session_factory() as session:
            duplicate = load_standard_csv(
                session,
                csv_bytes,
                summary_bytes,
                initial_source_type="upload",
                initial_source_ref="something-else.csv",
            )

        # 호출자가 "내가 방금 보낸 source"가 아니라 "저장된 최초 source"를 보게 해야 합니다.
        assert duplicate.created is False
        assert duplicate.initial_source_type == "s3"
        assert duplicate.initial_source_ref == "vendor-a/products.csv"
    finally:
        _cleanup(session_factory, input_hash)


# ---- legacy rows -----------------------------------------------------------


def test_legacy_rows_are_backfilled_as_unknown(postgres_session_factory) -> None:
    """migration 이전 row는 실제 출처 정보가 없으므로 추측하지 않고 unknown으로 남습니다."""
    session_factory = postgres_session_factory
    marker = uuid4().hex
    input_hash = hashlib.sha256(f"legacy {marker}".encode()).hexdigest()

    try:
        with session_factory() as session:
            # migration이 만든 DEFAULT 없이, 컬럼을 생략한 INSERT가 legacy row를 흉내 냅니다.
            session.execute(
                text(
                    """
                    INSERT INTO etl_load_runs (
                        source_filename, profile_name, profile_version,
                        input_file_sha256, output_file_sha256, loaded_rows,
                        initial_source_type
                    ) VALUES (
                        :filename, :profile, '1', :input_hash, :output_hash, 0, 'unknown'
                    )
                    """
                ),
                {
                    "filename": f"legacy_{marker}.csv",
                    "profile": "legacy_profile",
                    "input_hash": input_hash,
                    "output_hash": hashlib.sha256(f"out {marker}".encode()).hexdigest(),
                },
            )
            session.commit()

        with session_factory() as verify:
            run = verify.scalar(
                select(ETLLoadRun).where(ETLLoadRun.input_file_sha256 == input_hash)
            )
            assert run.initial_source_type == "unknown"
            assert run.initial_source_ref is None
    finally:
        _cleanup(session_factory, input_hash)


def test_database_rejects_a_source_type_outside_the_allowed_set(
    postgres_session_factory,
) -> None:
    """application validation을 우회해도 DB constraint가 마지막 방어선이어야 합니다."""
    session_factory = postgres_session_factory
    marker = uuid4().hex
    input_hash = hashlib.sha256(f"constraint {marker}".encode()).hexdigest()

    with session_factory() as session:
        with pytest.raises(Exception) as error:
            session.execute(
                text(
                    """
                    INSERT INTO etl_load_runs (
                        source_filename, profile_name, profile_version,
                        input_file_sha256, output_file_sha256, loaded_rows,
                        initial_source_type
                    ) VALUES (
                        :filename, 'p', '1', :input_hash, :output_hash, 0, 'not_a_source'
                    )
                    """
                ),
                {
                    "filename": f"bad_{marker}.csv",
                    "input_hash": input_hash,
                    "output_hash": hashlib.sha256(f"o {marker}".encode()).hexdigest(),
                },
            )
            session.commit()
        assert "ck_etl_load_runs_initial_source_type" in str(error.value)
        session.rollback()


# ---- CLI ------------------------------------------------------------------


def test_cli_db_load_records_cli_source_with_no_actor(tmp_path) -> None:
    """CLI는 로그인 actor가 없지만 출처는 분명합니다. 두 개념은 별개로 기록돼야 합니다."""
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL CLI 테스트를 건너뜁니다.")

    marker = uuid4().hex
    csv_bytes = _standard_csv(marker)
    summary = json.loads(_summary(csv_bytes, marker))
    summary["profile_name"] = f"cli_lineage_{marker[:12]}"
    input_path = tmp_path / "ready.csv"
    summary_path = tmp_path / "summary.json"
    input_path.write_bytes(csv_bytes)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

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
        env={**os.environ, "DATABASE_URL": database_url},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    engine = create_database_engine(database_url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as verify:
            run = verify.scalar(
                select(ETLLoadRun).where(
                    ETLLoadRun.profile_name == summary["profile_name"]
                )
            )
            assert run is not None
            assert run.initial_source_type == "cli"
            # --input은 원본 공급사 파일이 아니라 표준 CSV라, ref로 남기면 출처를 오해하게 만듭니다.
            assert run.initial_source_ref is None
            # actor와 source는 별개입니다. CLI는 로그인 사용자가 없어 actor만 NULL입니다.
            assert run.actor_user_id is None
            assert run.actor_username is None
        with session_factory() as cleanup:
            cleanup.execute(
                delete(ETLLoadRun).where(
                    ETLLoadRun.profile_name == summary["profile_name"]
                )
            )
            cleanup.commit()
    finally:
        engine.dispose()
