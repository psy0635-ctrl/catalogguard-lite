"""Chromium coverage for the Streamlit Catalog Reconciliation report."""

from __future__ import annotations

import os
import re
import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest


pytestmark = pytest.mark.e2e


PROFILE_NAME = "browser_e2e_reconciliation_vendor"
SOURCE_FILENAME = "browser_e2e_reconciliation_batch.csv"
CATALOG_SOURCE_FILENAME = "browser_e2e_reconciliation_catalog_source.csv"
PROFILE_VERSION = "e2e-reconciliation"
STREAMLIT_URL = os.environ.get("E2E_STREAMLIT_URL", "http://127.0.0.1:8501")
API_URL = os.environ.get(
    "E2E_API_URL",
    os.environ.get("CATALOGGUARD_API_BASE_URL", "http://127.0.0.1:8000"),
)
E2E_OPERATOR_USERNAME = os.environ.get("E2E_OPERATOR_USERNAME", "")
E2E_OPERATOR_PASSWORD = os.environ.get("E2E_OPERATOR_PASSWORD", "")


@dataclass(frozen=True)
class _LoadRunSnapshot:
    id: int
    source_filename: str
    profile_name: str
    profile_version: str
    input_file_sha256: str
    output_file_sha256: str
    profile_definition_sha256: str | None
    application_commit_sha: str | None
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    error_counts: dict[str, int] | None
    initial_source_type: str
    initial_source_ref: str | None
    actor_user_id: int | None
    actor_username: str | None
    created_at: datetime


@dataclass(frozen=True)
class _StagingSnapshot:
    id: int
    etl_load_run_id: int
    product_group_id: str
    product_id: str
    product_name: str
    category: str
    color: str
    size: str
    stock: int
    price: int
    sale_price: int | None
    image_path: str
    description: str | None
    seller: str | None
    created_at: datetime


@dataclass(frozen=True)
class _CatalogSnapshot:
    id: int
    supplier_key: str
    external_product_id: str
    product_group_id: str
    product_name: str
    category: str
    color: str
    size: str
    stock: int
    price: int
    sale_price: int | None
    image_path: str
    description: str | None
    seller: str | None
    source_etl_load_run_id: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class _ReconciliationFixture:
    catalog_source: _LoadRunSnapshot
    incoming: _LoadRunSnapshot
    staging: tuple[_StagingSnapshot, ...]
    catalog: tuple[_CatalogSnapshot, ...]

    @property
    def load_run_ids(self) -> tuple[int, int]:
        return (self.catalog_source.id, self.incoming.id)

    @property
    def staging_ids(self) -> tuple[int, ...]:
        return tuple(product.id for product in self.staging)

    @property
    def catalog_ids(self) -> tuple[int, ...]:
        return tuple(product.id for product in self.catalog)


def _login_as_operator(page) -> None:
    from playwright.sync_api import expect

    assert E2E_OPERATOR_USERNAME and E2E_OPERATOR_PASSWORD, (
        "E2E_OPERATOR_USERNAME/E2E_OPERATOR_PASSWORD 환경변수가 필요합니다."
    )
    expect(page.locator("body")).to_contain_text(
        "좌측 사이드바에서 로그인한 뒤 이용해 주세요."
    )
    page.get_by_label("아이디").fill(E2E_OPERATOR_USERNAME)
    page.get_by_label("비밀번호").fill(E2E_OPERATOR_PASSWORD)
    page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.get_by_role("tab", name="ETL 적재 이력")).to_be_visible()


def _preserve_browser_failure_artifacts(page) -> None:
    artifact_dir = os.environ.get("E2E_ARTIFACT_DIR", "").strip()
    if not artifact_dir:
        return
    output_dir = Path(artifact_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(output_dir / "failure.png"), full_page=True)
        (output_dir / "page.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass


def _new_session():
    from db.session import create_session_factory
    from sqlalchemy.engine import make_url

    database = make_url(os.environ["DATABASE_URL"])
    assert database.host in {"127.0.0.1", "localhost", "::1"}
    assert "test" in (database.database or "").lower(), "E2E requires a test database"
    assert database.port != 55483, "E2E refuses the school Demo DB port"
    if os.environ["DATABASE_URL"] != os.environ["TEST_DATABASE_URL"]:
        raise AssertionError("E2E database settings disagree")
    return create_session_factory(database_url=os.environ["DATABASE_URL"])()


def _make_hash() -> str:
    return uuid4().hex * 2


def _snapshot_load_run(load_run) -> _LoadRunSnapshot:
    return _LoadRunSnapshot(
        id=load_run.id,
        source_filename=load_run.source_filename,
        profile_name=load_run.profile_name,
        profile_version=load_run.profile_version,
        input_file_sha256=load_run.input_file_sha256,
        output_file_sha256=load_run.output_file_sha256,
        profile_definition_sha256=load_run.profile_definition_sha256,
        application_commit_sha=load_run.application_commit_sha,
        total_rows=load_run.total_rows,
        loaded_rows=load_run.loaded_rows,
        rejected_rows=load_run.rejected_rows,
        error_counts=(dict(load_run.error_counts) if load_run.error_counts else load_run.error_counts),
        initial_source_type=load_run.initial_source_type,
        initial_source_ref=load_run.initial_source_ref,
        actor_user_id=load_run.actor_user_id,
        actor_username=load_run.actor_username,
        created_at=load_run.created_at,
    )


def _snapshot_staging(product) -> _StagingSnapshot:
    return _StagingSnapshot(
        id=product.id,
        etl_load_run_id=product.etl_load_run_id,
        product_group_id=product.product_group_id,
        product_id=product.product_id,
        product_name=product.product_name,
        category=product.category,
        color=product.color,
        size=product.size,
        stock=product.stock,
        price=product.price,
        sale_price=product.sale_price,
        image_path=product.image_path,
        description=product.description,
        seller=product.seller,
        created_at=product.created_at,
    )


def _snapshot_catalog(product) -> _CatalogSnapshot:
    return _CatalogSnapshot(
        id=product.id,
        supplier_key=product.supplier_key,
        external_product_id=product.external_product_id,
        product_group_id=product.product_group_id,
        product_name=product.product_name,
        category=product.category,
        color=product.color,
        size=product.size,
        stock=product.stock,
        price=product.price,
        sale_price=product.sale_price,
        image_path=product.image_path,
        description=product.description,
        seller=product.seller,
        source_etl_load_run_id=product.source_etl_load_run_id,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _product_values(product_id: str, *, stock: int) -> dict[str, object]:
    return {
        "product_group_id": f"GROUP-{product_id}",
        "product_name": f"Reconciliation {product_id}",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": stock,
        "price": 19900,
        "sale_price": 15900,
        "image_path": f"synthetic/{product_id}.jpg",
        "description": f"Synthetic reconciliation fixture {product_id}",
        "seller": "CatalogGuard E2E",
    }


def _create_reconciliation_fixture() -> _ReconciliationFixture:
    """Create exactly the parents and products required for this read-only report."""
    from db.models import CatalogProduct, CatalogProductStaging, ETLLoadRun

    with _new_session() as session:
        catalog_source = ETLLoadRun(
            source_filename=CATALOG_SOURCE_FILENAME,
            profile_name=PROFILE_NAME,
            profile_version=PROFILE_VERSION,
            input_file_sha256=_make_hash(),
            output_file_sha256=_make_hash(),
            total_rows=0,
            loaded_rows=0,
            rejected_rows=0,
            error_counts={},
            created_at=datetime(2026, 1, 2, 10, tzinfo=timezone.utc),
        )
        incoming = ETLLoadRun(
            source_filename=SOURCE_FILENAME,
            profile_name=PROFILE_NAME,
            profile_version=PROFILE_VERSION,
            input_file_sha256=_make_hash(),
            output_file_sha256=_make_hash(),
            total_rows=4,
            loaded_rows=3,
            rejected_rows=1,
            error_counts={"invalid_price": 1},
            created_at=datetime(2026, 1, 2, 11, tzinfo=timezone.utc),
        )
        session.add_all((catalog_source, incoming))
        session.flush()

        staging = (
            CatalogProductStaging(
                etl_load_run_id=incoming.id,
                product_id="REC-NEW-001",
                **_product_values("REC-NEW-001", stock=5),
            ),
            CatalogProductStaging(
                etl_load_run_id=incoming.id,
                product_id="REC-CHANGED-001",
                **_product_values("REC-CHANGED-001", stock=7),
            ),
            CatalogProductStaging(
                etl_load_run_id=incoming.id,
                product_id="REC-SAME-001",
                **_product_values("REC-SAME-001", stock=12),
            ),
        )
        catalog = (
            CatalogProduct(
                supplier_key=PROFILE_NAME,
                external_product_id="REC-CHANGED-001",
                source_etl_load_run_id=catalog_source.id,
                **_product_values("REC-CHANGED-001", stock=10),
            ),
            CatalogProduct(
                supplier_key=PROFILE_NAME,
                external_product_id="REC-SAME-001",
                source_etl_load_run_id=catalog_source.id,
                **_product_values("REC-SAME-001", stock=12),
            ),
            CatalogProduct(
                supplier_key=PROFILE_NAME,
                external_product_id="REC-OLD-001",
                source_etl_load_run_id=catalog_source.id,
                **_product_values("REC-OLD-001", stock=3),
            ),
        )
        session.add_all((*staging, *catalog))
        session.flush()
        fixture = _ReconciliationFixture(
            catalog_source=_snapshot_load_run(catalog_source),
            incoming=_snapshot_load_run(incoming),
            staging=tuple(_snapshot_staging(product) for product in staging),
            catalog=tuple(_snapshot_catalog(product) for product in catalog),
        )
        session.commit()
    return fixture


def _assert_fixture_unchanged(fixture: _ReconciliationFixture) -> None:
    from sqlalchemy import select

    from db.models import (
        CatalogProduct,
        CatalogProductChange,
        CatalogProductStaging,
        CatalogPromotionRun,
        ETLLoadRun,
    )

    with _new_session() as session:
        load_runs = {
            row.id: _snapshot_load_run(row)
            for row in session.scalars(
                select(ETLLoadRun).where(ETLLoadRun.id.in_(fixture.load_run_ids))
            )
        }
        staging = {
            row.id: _snapshot_staging(row)
            for row in session.scalars(
                select(CatalogProductStaging).where(
                    CatalogProductStaging.id.in_(fixture.staging_ids)
                )
            )
        }
        catalog = {
            row.id: _snapshot_catalog(row)
            for row in session.scalars(
                select(CatalogProduct).where(CatalogProduct.id.in_(fixture.catalog_ids))
            )
        }
        promotion_run_ids = list(
            session.scalars(
                select(CatalogPromotionRun.id).where(
                    CatalogPromotionRun.etl_load_run_id == fixture.incoming.id
                )
            )
        )
        assert promotion_run_ids == []
        assert list(
            session.scalars(
                select(CatalogProductChange.id).where(
                    CatalogProductChange.promotion_run_id.in_(promotion_run_ids)
                )
            )
        ) == []

    assert load_runs == {
        fixture.catalog_source.id: fixture.catalog_source,
        fixture.incoming.id: fixture.incoming,
    }
    assert staging == {product.id: product for product in fixture.staging}
    assert catalog == {product.id: product for product in fixture.catalog}


def _cleanup_reconciliation_fixture(fixture: _ReconciliationFixture) -> None:
    from sqlalchemy import delete, select

    from db.models import CatalogProduct, CatalogProductStaging, ETLLoadRun

    with _new_session() as session:
        # CatalogProduct has a RESTRICT FK to its source run, so delete exact
        # child rows first. The IDs were retained during fixture setup.
        session.execute(delete(CatalogProduct).where(CatalogProduct.id.in_(fixture.catalog_ids)))
        session.execute(
            delete(CatalogProductStaging).where(
                CatalogProductStaging.id.in_(fixture.staging_ids)
            )
        )
        session.execute(delete(ETLLoadRun).where(ETLLoadRun.id == fixture.incoming.id))
        session.execute(
            delete(ETLLoadRun).where(ETLLoadRun.id == fixture.catalog_source.id)
        )
        session.commit()

    with _new_session() as session:
        assert list(
            session.scalars(select(CatalogProduct.id).where(CatalogProduct.id.in_(fixture.catalog_ids)))
        ) == []
        assert list(
            session.scalars(
                select(CatalogProductStaging.id).where(
                    CatalogProductStaging.id.in_(fixture.staging_ids)
                )
            )
        ) == []
        assert list(
            session.scalars(select(ETLLoadRun.id).where(ETLLoadRun.id.in_(fixture.load_run_ids)))
        ) == []


def _api_headers(page) -> dict[str, str]:
    response = page.request.post(
        f"{API_URL}/api/v1/auth/login",
        data={"username": E2E_OPERATOR_USERNAME, "password": E2E_OPERATOR_PASSWORD},
    )
    assert response.ok, response.text()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _dataframe_grid_with_column(page, column_name: str):
    """Locate a Streamlit dataframe through ARIA roles, not generated classes."""
    return page.locator("table[role='grid']").filter(
        has=page.locator(
            "th[role='columnheader']",
            has_text=re.compile(rf"^{re.escape(column_name)}$"),
        )
    )


def _metric_label(page, label: str):
    """Match the semantic metric paragraph, excluding repeated grid cells."""
    return page.locator("p").filter(has_text=re.compile(rf"^{re.escape(label)}$"))


def _assert_api_reconciliation(page, fixture: _ReconciliationFixture) -> None:
    response = page.request.get(
        f"{API_URL}/api/v1/etl-loads/{fixture.incoming.id}/catalog-reconciliation",
        headers=_api_headers(page),
        params={"limit": "50", "offset": "0"},
    )
    assert response.ok, response.text()
    assert response.json() == {
        "etl_load_run_id": fixture.incoming.id,
        "supplier_key": PROFILE_NAME,
        "total_rows": 4,
        "loaded_rows": 3,
        "rejected_rows": 1,
        "new_count": 1,
        "changed_count": 1,
        "unchanged_count": 1,
        "not_observed_in_batch_count": 1,
        "field_change_counts": {"stock": 1},
        "items": [
            {"external_product_id": "REC-NEW-001", "status": "new", "changed_fields": {}},
            {
                "external_product_id": "REC-CHANGED-001",
                "status": "changed",
                "changed_fields": {"stock": {"before": 10, "after": 7}},
            },
            {"external_product_id": "REC-SAME-001", "status": "unchanged", "changed_fields": {}},
            {
                "external_product_id": "REC-OLD-001",
                "status": "not_observed_in_batch",
                "changed_fields": {},
            },
        ],
        "total": 4,
        "limit": 50,
        "offset": 0,
    }


def _run_reconciliation_scenario(page, fixture: _ReconciliationFixture) -> None:
    from playwright.sync_api import expect

    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    page.goto(STREAMLIT_URL, wait_until="domcontentloaded")
    expect(page.locator("body")).to_contain_text("CatalogGuard Lite")
    expect(page.locator("body")).not_to_contain_text("StreamlitAPIException")
    _login_as_operator(page)
    page.get_by_role("tab", name="ETL 적재 이력").click()

    page.get_by_label("원본 파일명").fill(SOURCE_FILENAME)
    page.get_by_label("공급사 프로필").fill(PROFILE_NAME)
    page.get_by_role("button", name="조회", exact=True).click()
    expect(page.locator("body")).to_contain_text(SOURCE_FILENAME)
    expect(page.locator("body")).to_contain_text(PROFILE_NAME)

    batch_selector = page.get_by_role("combobox", name="적재 배치 선택")
    expect(batch_selector).to_be_visible()
    batch_selector.click()
    page.get_by_role(
        "option",
        name=re.compile(rf"{fixture.incoming.id} · {re.escape(SOURCE_FILENAME)}"),
    ).click()
    page.get_by_role("button", name="상세 조회", exact=True).click()

    expect(page.get_by_text("적재 배치 상세", exact=True)).to_be_visible()
    expect(page.get_by_text("상품 동기화 차이", exact=True)).to_be_visible()
    # The item dataframe repeats the Korean status names in grid cells. Scope
    # metric labels to their semantic paragraph instead of a generated class.
    for label in ("신규", "변경", "동일", "이번 배치 미관측"):
        expect(_metric_label(page, label)).to_have_count(1)
        expect(_metric_label(page, label)).to_be_visible()
    # Other ETL sections can legitimately contain the text "1". The four
    # metric labels above establish the UI boundary; the exact values are
    # established by the API payload below without coupling to page-wide text.
    assert page.locator("p").filter(has_text=re.compile(r"^1$")).count() >= 4
    expect(page.locator("body")).to_contain_text("삭제 또는 판매 종료를 의미하지 않으며")
    expect(page.locator("body")).to_contain_text("자동 삭제 대상으로 판단하지 않습니다")
    expect(page.locator("body")).to_contain_text("원본 입력 중 1개 행이 ETL 변환 과정에서 제외되었습니다")
    expect(page.locator("body")).to_contain_text("정상 staging 상품만 운영 카탈로그와 비교")
    expect(page.locator("body")).to_contain_text("reject 때문에 비교에서 빠진 상품이 포함될 수 있습니다")

    expect(page.get_by_text("필드별 변경 건수", exact=True)).to_be_visible()
    field_grid = _dataframe_grid_with_column(page, "변경 건수")
    expect(field_grid).to_have_count(1)
    expect(field_grid).to_contain_text("stock")
    expect(field_grid).to_contain_text("1")

    # The selected batch's staging-detail grid uses the same "상품 ID" header.
    # Identify the reconciliation grid by its complete deterministic fixture
    # content rather than DOM order or a generated Streamlit selector.
    item_grid_texts = _dataframe_grid_with_column(page, "상품 ID").all_inner_texts()
    expected_item_values = (
        "REC-NEW-001",
        "REC-CHANGED-001",
        "REC-SAME-001",
        "REC-OLD-001",
        "신규",
        "변경",
        "동일",
        "이번 배치 미관측",
        "stock",
    )
    assert any(
        all(value in grid_text for value in expected_item_values)
        for grid_text in item_grid_texts
    )
    expect(page.locator("body")).to_contain_text("전체 4개 상품")

    _assert_api_reconciliation(page, fixture)
    _assert_fixture_unchanged(fixture)
    assert not console_errors, f"Unexpected browser console errors: {console_errors}"
    assert not page_errors, f"Unexpected browser page errors: {page_errors}"


def test_catalog_reconciliation_in_real_browser(page):
    fixture = _create_reconciliation_fixture()
    try:
        _run_reconciliation_scenario(page, fixture)
    except BaseException:
        _preserve_browser_failure_artifacts(page)
        raise
    finally:
        _cleanup_reconciliation_fixture(fixture)


def _save_evidence(name, data):
    directory = os.environ.get("E2E_RECONCILIATION_EVIDENCE_DIR")
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        (Path(directory) / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _database_snapshot():
    """Hash all ORM table contents without writing credentials or raw rows to artifacts."""
    from db.base import Base
    import db.models
    snapshot = {}
    with _new_session() as session:
        for table in Base.metadata.sorted_tables:
            rows = [dict(row._mapping) for row in session.execute(
                table.select().order_by(*table.primary_key.columns)
            )]
            raw = json.dumps(rows, sort_keys=True, default=str).encode()
            snapshot[table.name] = {"rows": len(rows), "sha256": hashlib.sha256(raw).hexdigest()}
    return snapshot


def test_catalog_reconciliation_csv_download_in_real_browser(page, tmp_path):
    """Download all 208 rows and filtered 52 rows through the real UI/API/DB."""
    import csv
    import io
    from playwright.sync_api import expect

    baseline = _database_snapshot()
    fixture = _create_paginated_reconciliation_fixture()
    evidence = []
    try:
        before = _database_snapshot()
        page.goto(STREAMLIT_URL, wait_until="domcontentloaded")
        _login_as_operator(page)
        page.get_by_role("tab", name="ETL 적재 이력").click()
        page.get_by_label("원본 파일명").fill("browser_e2e_reconciliation")
        page.get_by_label("공급사 프로필").fill(PROFILE_NAME)
        page.get_by_role("button", name="조회", exact=True).click()

        def select_batch(run_id, filename):
            page.get_by_role("combobox", name=re.compile("적재 배치 선택$")).click()
            page.get_by_role("option", name=re.compile(rf"^{run_id} · {re.escape(filename)}")).click()
            expect(page.get_by_text("상품 동기화 차이", exact=True)).not_to_be_visible()
            page.get_by_role("button", name="상세 조회", exact=True).click()
            expect(page.get_by_text("상품 동기화 차이", exact=True)).to_be_visible()

        def choose_filter(label):
            page.get_by_role("combobox", name=re.compile("상품 동기화 차이 상태$")).click()
            page.get_by_role("option", name=label, exact=True).click()

        prepare = page.get_by_role("button", name="상품 동기화 차이 전체 CSV 준비", exact=True)
        download_button = page.get_by_role("button", name="상품 동기화 차이 전체 CSV 다운로드", exact=True)
        select_batch(fixture.incoming.id, SOURCE_FILENAME)
        expect(download_button).not_to_be_visible()
        expect(page.get_by_text("상품 1 / 5 페이지 · 전체 208개 상품", exact=True)).to_be_visible()
        page.get_by_role("button", name="동기화 차이 다음", exact=True).click()
        expect(page.get_by_text("상품 2 / 5 페이지 · 전체 208개 상품", exact=True)).to_be_visible()
        for code, label, count, kind in (
            ("all", None, 208, None), ("new", "신규", 52, "NEW"),
            ("changed", "변경", 52, "CHANGED"), ("unchanged", "동일", 52, "SAME"),
            ("not_observed_in_batch", "이번 배치 미관측", 52, "OLD"),
        ):
            if label:
                choose_filter(label)
                expect(download_button).not_to_be_visible()
            prepare.click()
            expect(download_button).to_be_visible()
            if code == "all":
                expect(page.get_by_text("상품 2 / 5 페이지 · 전체 208개 상품", exact=True)).to_be_visible()
            with page.expect_download() as download_info:
                download_button.click()
            download = download_info.value
            filename = f"catalogguard_reconciliation_{fixture.incoming.id}_{code}.csv"
            assert download.suggested_filename == filename
            path = tmp_path / filename
            download.save_as(path)
            payload = path.read_bytes()
            assert payload.startswith(b"\xef\xbb\xbf")
            rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
            assert len(rows) == count
            assert list(rows[0]) == ["상품 ID", "상태", "변경 필드"]
            assert len({row["상품 ID"] for row in rows}) == count
            if label:
                assert {row["상태"] for row in rows} == {label}
                assert [row["상품 ID"] for row in rows] == [f"REC-{kind}-{i:03d}" for i in range(1, 53)]
            # The existing CSV sanitizer also protects the display placeholder '-'.
            expected_fields = {"stock"} if code == "changed" else {"'-"}
            if code == "all":
                expected_fields.add("stock")
            assert {row["변경 필드"] for row in rows} == expected_fields
            evidence.append({"status": code, "rows": len(rows), "filename": filename,
                             "sha256": hashlib.sha256(payload).hexdigest(), "bom": True})
        page.get_by_role("button", name="동기화 차이 다음", exact=True).click()
        expect(download_button).not_to_be_visible()
        select_batch(fixture.catalog_source.id, CATALOG_SOURCE_FILENAME)
        expect(download_button).not_to_be_visible()
        choose_filter("신규")
        expect(page.get_by_text("선택한 상태에 해당하는 상품이 없습니다.", exact=True)).to_be_visible()
        prepare.click()
        expect(page.get_by_text("다운로드할 상품 동기화 차이가 없습니다.", exact=True)).to_be_visible()
        expect(download_button).not_to_be_visible()
        assert _database_snapshot() == before
        _save_evidence("csv-download-results.json", {"downloads": evidence, "read_only": True})
    except Exception:
        _preserve_browser_failure_artifacts(page)
        raise
    finally:
        _cleanup_reconciliation_fixture(fixture)
    assert _database_snapshot() == baseline


def _create_paginated_reconciliation_fixture():
    """52 products per status exercise the real 50-item UI page size."""
    from db.models import CatalogProduct, CatalogProductStaging, ETLLoadRun
    fixture = _create_reconciliation_fixture()
    with _new_session() as session:
        incoming = session.get(ETLLoadRun, fixture.incoming.id)
        incoming.loaded_rows, incoming.total_rows = 156, 157
        source = session.get(ETLLoadRun, fixture.catalog_source.id)
        source.total_rows = source.rejected_rows = source.error_counts = None
        staging, catalog = [], []
        for number in range(2, 53):
            for kind, stock in (("NEW", 5), ("CHANGED", 7), ("SAME", 12)):
                product_id = f"REC-{kind}-{number:03d}"
                staging.append(CatalogProductStaging(
                    etl_load_run_id=incoming.id, product_id=product_id,
                    **_product_values(product_id, stock=stock),
                ))
            for kind, stock in (("CHANGED", 10), ("SAME", 12), ("OLD", 3)):
                product_id = f"REC-{kind}-{number:03d}"
                catalog.append(CatalogProduct(
                    supplier_key=PROFILE_NAME, external_product_id=product_id,
                    source_etl_load_run_id=source.id,
                    **_product_values(product_id, stock=stock),
                ))
        catalog.append(CatalogProduct(
            supplier_key=PROFILE_NAME + "_other", external_product_id="REC-NEW-001",
            source_etl_load_run_id=source.id,
            **_product_values("REC-NEW-001", stock=999),
        ))
        session.add_all([*staging, *catalog])
        session.flush()
        result = replace(
            fixture, incoming=_snapshot_load_run(incoming), catalog_source=_snapshot_load_run(source),
            staging=fixture.staging + tuple(_snapshot_staging(row) for row in staging),
            catalog=fixture.catalog + tuple(_snapshot_catalog(row) for row in catalog),
        )
        session.commit()
    return result


@contextmanager
def _duplicate_identity(fixture):
    """A deliberate fixture write, separate from read-only API snapshot phases."""
    from sqlalchemy import delete
    from db.models import CatalogProductStaging
    with _new_session() as session:
        duplicate = CatalogProductStaging(
            etl_load_run_id=fixture.incoming.id, product_id="REC-NEW-001",
            **_product_values("REC-NEW-001", stock=5),
        )
        session.add(duplicate)
        session.flush()
        duplicate_id = duplicate.id
        session.commit()
    try:
        yield
    finally:
        with _new_session() as session:
            session.execute(delete(CatalogProductStaging).where(CatalogProductStaging.id == duplicate_id))
            session.commit()


def test_catalog_reconciliation_status_filters_with_postgresql():
    import requests
    from sqlalchemy import event
    from db.catalog_reconciliation_service import build_catalog_reconciliation_report

    baseline = _database_snapshot()
    fixture = _create_paginated_reconciliation_fixture()
    records = []
    try:
        before = _database_snapshot()
        http = requests.Session()
        login = http.post(f"{API_URL}/api/v1/auth/login", json={
            "username": E2E_OPERATOR_USERNAME, "password": E2E_OPERATOR_PASSWORD,
        }, timeout=10)
        assert login.status_code == 200
        http.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        endpoint = f"{API_URL}/api/v1/etl-loads/{fixture.incoming.id}/catalog-reconciliation"
        statuses = {"new": "NEW", "changed": "CHANGED", "unchanged": "SAME", "not_observed_in_batch": "OLD"}
        all_items = []
        for status, kind in statuses.items():
            full = http.get(endpoint, params={"status": status, "limit": 100}, timeout=10)
            assert full.status_code == 200
            expected = full.json()["items"]
            assert [row["external_product_id"] for row in expected] == [f"REC-{kind}-{i:03d}" for i in range(1, 53)]
            assert all(row["status"] == status for row in expected)
            all_items.extend(expected)
            for offset in (0, 1, 51, 52, 99):
                response = http.get(endpoint, params={"status": status, "limit": 1, "offset": offset}, timeout=10)
                assert response.status_code == 200
                data = response.json()
                assert data["items"] == expected[offset:offset + 1]
                assert data["total"] == 52 and data["offset"] == offset and data["limit"] == 1
                assert [data[key + "_count"] for key in statuses] == [52] * 4
                assert data["field_change_counts"] == {"stock": 52}
                assert (data["total_rows"], data["loaded_rows"], data["rejected_rows"]) == (157, 156, 1)
                records.append({"status": status, "offset": offset, "total": data["total"], "items": data["items"]})
        for offset in (0, 1, 50, 51, 52, 100, 103, 104, 155, 156, 200, 207, 208, 999):
            data = http.get(endpoint, params={"limit": 1, "offset": offset}, timeout=10).json()
            assert data["total"] == 208 and data["items"] == all_items[offset:offset + 1]
        pages = [http.get(endpoint, params={"limit": 50, "offset": offset}, timeout=10).json()["items"]
                 for offset in range(0, 208, 50)]
        assert [item for page in pages for item in page] == all_items
        source_endpoint = f"{API_URL}/api/v1/etl-loads/{fixture.catalog_source.id}/catalog-reconciliation"
        for status in ("new", "changed", "unchanged"):
            data = http.get(source_endpoint, params={"status": status}, timeout=10).json()
            assert data["items"] == [] and data["total"] == 0
            assert data["not_observed_in_batch_count"] == 156
        assert http.get(endpoint, params={"status": "deleted"}, timeout=10).status_code == 422
        assert http.get(endpoint.replace(f"/{fixture.incoming.id}/", "/2147483647/"), timeout=10).status_code == 404
        assert requests.get(endpoint, timeout=10).status_code == 401

        # Execute the real service inside a PostgreSQL read-only transaction and inspect SQL.
        with _new_session() as session:
            connection = session.connection()
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            statements = []
            def record_sql(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)
            event.listen(connection, "before_cursor_execute", record_sql)
            page = build_catalog_reconciliation_report(session, etl_load_run_id=fixture.incoming.id,
                status="not_observed_in_batch", limit=1, offset=51)
            assert [row.external_product_id for row in page.items] == ["REC-OLD-052"]
            assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
            assert any("count(" in statement.lower() for statement in statements)
            assert any("LIMIT" in statement and "OFFSET" in statement for statement in statements)
        assert _database_snapshot() == before
        with _duplicate_identity(fixture):
            duplicate_before = _database_snapshot()
            response = http.get(endpoint, params={"status": "new"}, timeout=10)
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "duplicate_product_identity"
            assert _database_snapshot() == duplicate_before
        assert _database_snapshot() == before
        _save_evidence("postgresql-results.json", {"queries": records, "before": before,
            "after": _database_snapshot(), "read_only_sql": statements,
            "expected_errors": {"unauthenticated": 401, "missing": 404, "duplicate": 409, "invalid_status": 422}})
    finally:
        _cleanup_reconciliation_fixture(fixture)
    assert _database_snapshot() == baseline


def test_catalog_reconciliation_status_filter_browser_pagination_and_recovery(page):
    from playwright.sync_api import expect

    baseline = _database_snapshot()
    fixture = _create_paginated_reconciliation_fixture()
    errors, page_errors, failed_requests, http_errors, warnings = [], [], [], [], []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error"
            else warnings.append(msg.text) if msg.type == "warning" else None)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("requestfailed", lambda request: failed_requests.append({"method": request.method, "failure": request.failure}))
    page.on("response", lambda response: http_errors.append(response.status) if response.status >= 400 else None)
    checks = []

    def choose_filter(label):
        page.get_by_role("combobox", name=re.compile("상품 동기화 차이 상태$")).click()
        page.get_by_role("option", name=label, exact=True).click()

    def select_batch(run_id, filename):
        page.get_by_role("combobox", name=re.compile("적재 배치 선택$")).click()
        page.get_by_role("option", name=re.compile(rf"^{run_id} · {re.escape(filename)}")).click()
        expect(page.get_by_text("상품 동기화 차이", exact=True)).not_to_be_visible()
        page.get_by_role("button", name="상세 조회", exact=True).click()
        expect(page.get_by_text("상품 동기화 차이", exact=True)).to_be_visible()

    def assert_summary():
        for label in ("신규", "변경", "동일", "이번 배치 미관측"):
            metric = page.locator('[data-testid="stMetric"]').filter(has=_metric_label(page, label))
            expect(metric.locator('[data-testid="stMetricValue"]')).to_have_text("52")
        grid = _dataframe_grid_with_column(page, "변경 건수")
        expect(grid).to_contain_text("stock")
        expect(grid).to_contain_text("52")
        expect(page.locator("body")).to_contain_text("원본 입력 중 1개 행이 ETL 변환 과정에서 제외되었습니다")
        expect(page.locator("body")).to_contain_text("삭제 또는 판매 종료를 의미하지 않으며")

    try:
        before = _database_snapshot()
        page.goto(STREAMLIT_URL, wait_until="domcontentloaded")
        _login_as_operator(page)
        page.get_by_role("tab", name="ETL 적재 이력").click()
        page.get_by_label("원본 파일명").fill("browser_e2e_reconciliation")
        page.get_by_label("공급사 프로필").fill(PROFILE_NAME)
        page.get_by_role("button", name="조회", exact=True).click()
        select_batch(fixture.incoming.id, SOURCE_FILENAME)
        expect(page.get_by_text("상품 1 / 5 페이지 · 전체 208개 상품", exact=True)).to_be_visible()
        filter_box = page.locator('[data-testid="stSelectbox"]').filter(
            has=page.get_by_role("combobox", name=re.compile("상품 동기화 차이 상태$")))
        expect(filter_box).to_contain_text("전체")
        assert_summary()
        checks.append("default_all_208")
        page.get_by_role("button", name="동기화 차이 다음", exact=True).click()
        expect(page.get_by_text("상품 2 / 5 페이지 · 전체 208개 상품", exact=True)).to_be_visible()
        for label, kind in (("신규", "NEW"), ("변경", "CHANGED"), ("동일", "SAME"), ("이번 배치 미관측", "OLD")):
            choose_filter(label)
            expect(page.get_by_text("상품 1 / 2 페이지 · 전체 52개 상품", exact=True)).to_be_visible()
            assert_summary()
            item_grid = _dataframe_grid_with_column(page, "상태").filter(has_text=f"REC-{kind}-001")
            expect(item_grid).to_have_count(1)
            page.get_by_role("button", name="동기화 차이 다음", exact=True).click()
            expect(page.get_by_text("상품 2 / 2 페이지 · 전체 52개 상품", exact=True)).to_be_visible()
            grid = _dataframe_grid_with_column(page, "상태").filter(
                has=page.locator("th[role='columnheader']").filter(
                    has_text=re.compile(r"^상품 ID$")
                )
            )
            expect(grid).to_have_count(1)
            expect(grid).to_contain_text(f"REC-{kind}-051")
            expect(grid).to_contain_text(f"REC-{kind}-052")
            expect(page.get_by_role("button", name="동기화 차이 다음", exact=True)).to_be_disabled()
            page.get_by_role("button", name="동기화 차이 이전", exact=True).click()
            expect(page.get_by_text("상품 1 / 2 페이지 · 전체 52개 상품", exact=True)).to_be_visible()
            checks.append(label + "_52_next_previous")
            # Changing the next filter from page 2 must also reset offset to zero.
            page.get_by_role("button", name="동기화 차이 다음", exact=True).click()
            expect(page.get_by_text("상품 2 / 2 페이지 · 전체 52개 상품", exact=True)).to_be_visible()
        choose_filter("전체")
        expect(page.get_by_text("상품 1 / 5 페이지 · 전체 208개 상품", exact=True)).to_be_visible()
        checks.append("back_to_all_resets_offset")

        # A controlled API 409, produced only by a deliberate test-fixture write.
        with _duplicate_identity(fixture):
            failure_before = _database_snapshot()
            choose_filter("변경")
            expect(page.get_by_role("button", name="동기화 차이 다시 조회", exact=True)).to_be_visible()
            expect(page.get_by_text(re.compile("상품 동기화 차이를 불러오지 못했습니다"))).to_be_visible()
            assert _database_snapshot() == failure_before
        page.get_by_role("button", name="동기화 차이 다시 조회", exact=True).click()
        expect(page.get_by_text("상품 1 / 2 페이지 · 전체 52개 상품", exact=True)).to_be_visible()
        assert_summary()
        checks.append("expected_api_409_then_successful_retry")

        select_batch(fixture.catalog_source.id, CATALOG_SOURCE_FILENAME)
        expect(filter_box).to_contain_text("전체")
        expect(page.locator("body")).to_contain_text("품질 요약")
        from ui.etl_load_history import CATALOG_RECONCILIATION_LEGACY_QUALITY_NOTICE
        expect(page.get_by_text(CATALOG_RECONCILIATION_LEGACY_QUALITY_NOTICE, exact=True)).to_be_visible()
        choose_filter("신규")
        expect(page.get_by_text("선택한 상태에 해당하는 상품이 없습니다.", exact=True)).to_be_visible()
        # The empty staging table and filtered reconciliation list both have zero products.
        empty_captions = page.get_by_text("상품 1 / 1 페이지 · 전체 0개 상품", exact=True)
        expect(empty_captions).to_have_count(2)
        for caption in empty_captions.all():
            expect(caption).to_be_visible()
        expect(page.get_by_role("button", name="동기화 차이 다음", exact=True)).to_be_disabled()
        checks.append("different_legacy_batch_all_reset_and_empty_filter")
        select_batch(fixture.incoming.id, SOURCE_FILENAME)
        expect(filter_box).to_contain_text("전체")
        expect(page.get_by_text("상품 1 / 5 페이지 · 전체 208개 상품", exact=True)).to_be_visible()
        assert_summary()
        assert not page.locator('[data-testid="stException"]').count()
        assert not errors and not page_errors and not failed_requests and not http_errors
        assert _database_snapshot() == before
        _assert_fixture_unchanged(fixture)
        _save_evidence("browser-status-filter-results.json", {
            "checks": checks, "console_errors": errors, "page_errors": page_errors,
            "failed_requests": failed_requests, "browser_http_errors": http_errors,
            "renderer_warnings": warnings, "before": before, "after": _database_snapshot(),
        })
    except BaseException:
        _preserve_browser_failure_artifacts(page)
        raise
    finally:
        _cleanup_reconciliation_fixture(fixture)
    assert _database_snapshot() == baseline
