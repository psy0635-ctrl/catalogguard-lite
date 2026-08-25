"""Chromium coverage for the Streamlit Catalog Reconciliation report."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
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
