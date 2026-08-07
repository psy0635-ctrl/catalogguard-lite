from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import CatalogProductStaging, ETLLoadRun, ETLRejectedRow


LIKE_ESCAPE_CHARACTER = "\\"


@dataclass(frozen=True)
class ETLLoadListItem:
    etl_load_run_id: int
    source_filename: str
    profile_name: str
    profile_version: str
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    created_at: datetime
    actor_username: str | None = None


@dataclass(frozen=True)
class ETLLoadList:
    items: list[ETLLoadListItem]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class ETLStagingProduct:
    staging_product_id: int
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
class ETLStagingProductList:
    items: list[ETLStagingProduct]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class ETLLoadDetail:
    etl_load_run_id: int
    source_filename: str
    profile_name: str
    profile_version: str
    input_file_sha256: str
    output_file_sha256: str
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    error_counts: dict[str, int] | None
    reject_details_stored: bool
    created_at: datetime
    products: ETLStagingProductList
    actor_username: str | None = None


@dataclass(frozen=True)
class ETLRejectError:
    code: str
    field: str
    message: str


@dataclass(frozen=True)
class ETLRejectedRowItem:
    rejected_row_id: int
    source_row_number: int
    errors: list[ETLRejectError]
    masked_source_data: dict[str, str]
    created_at: datetime


@dataclass(frozen=True)
class ETLRejectedRowList:
    available: bool
    items: list[ETLRejectedRowItem]
    total: int
    limit: int
    offset: int


def normalize_etl_filter(value: str | None) -> str | None:
    cleaned = "" if value is None else value.strip()
    return cleaned or None


def escape_like_pattern(value: str) -> str:
    return (
        value.replace(LIKE_ESCAPE_CHARACTER, LIKE_ESCAPE_CHARACTER * 2)
        .replace("%", f"{LIKE_ESCAPE_CHARACTER}%")
        .replace("_", f"{LIKE_ESCAPE_CHARACTER}_")
    )


def _apply_etl_load_filters(
    statement,
    *,
    filename: str | None = None,
    profile_name: str | None = None,
):
    for column, value in (
        (ETLLoadRun.source_filename, filename),
        (ETLLoadRun.profile_name, profile_name),
    ):
        normalized = normalize_etl_filter(value)
        if normalized is not None:
            pattern = f"%{escape_like_pattern(normalized)}%"
            statement = statement.where(
                column.ilike(pattern, escape=LIKE_ESCAPE_CHARACTER)
            )
    return statement


def _to_load_list_item(load_run: ETLLoadRun) -> ETLLoadListItem:
    return ETLLoadListItem(
        etl_load_run_id=load_run.id,
        source_filename=load_run.source_filename,
        profile_name=load_run.profile_name,
        profile_version=load_run.profile_version,
        total_rows=load_run.total_rows,
        loaded_rows=load_run.loaded_rows,
        rejected_rows=load_run.rejected_rows,
        created_at=load_run.created_at,
        actor_username=load_run.actor_username,
    )


def _to_product(product: CatalogProductStaging) -> ETLStagingProduct:
    return ETLStagingProduct(
        staging_product_id=product.id,
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


def list_etl_loads(
    session: Session,
    *,
    limit: int,
    offset: int,
    filename: str | None = None,
    profile_name: str | None = None,
) -> ETLLoadList:
    items_statement = _apply_etl_load_filters(
        select(ETLLoadRun),
        filename=filename,
        profile_name=profile_name,
    ).order_by(ETLLoadRun.created_at.desc(), ETLLoadRun.id.desc())
    load_runs = list(session.scalars(items_statement.limit(limit).offset(offset)).all())

    total_statement = _apply_etl_load_filters(
        select(func.count()).select_from(ETLLoadRun),
        filename=filename,
        profile_name=profile_name,
    )
    total = int(session.scalar(total_statement) or 0)
    return ETLLoadList(
        items=[_to_load_list_item(load_run) for load_run in load_runs],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_etl_load_detail(
    session: Session,
    *,
    etl_load_run_id: int,
    product_limit: int,
    product_offset: int,
) -> ETLLoadDetail | None:
    load_run = session.get(ETLLoadRun, etl_load_run_id)
    if load_run is None:
        return None

    products_statement = (
        select(CatalogProductStaging)
        .where(CatalogProductStaging.etl_load_run_id == etl_load_run_id)
        .order_by(CatalogProductStaging.id.asc())
        .limit(product_limit)
        .offset(product_offset)
    )
    products = list(session.scalars(products_statement).all())
    total_statement = select(func.count()).select_from(CatalogProductStaging).where(
        CatalogProductStaging.etl_load_run_id == etl_load_run_id
    )
    total = int(session.scalar(total_statement) or 0)
    return ETLLoadDetail(
        etl_load_run_id=load_run.id,
        source_filename=load_run.source_filename,
        profile_name=load_run.profile_name,
        profile_version=load_run.profile_version,
        input_file_sha256=load_run.input_file_sha256,
        output_file_sha256=load_run.output_file_sha256,
        total_rows=load_run.total_rows,
        loaded_rows=load_run.loaded_rows,
        rejected_rows=load_run.rejected_rows,
        error_counts=load_run.error_counts,
        reject_details_stored=load_run.reject_details_stored,
        created_at=load_run.created_at,
        actor_username=load_run.actor_username,
        products=ETLStagingProductList(
            items=[_to_product(product) for product in products],
            total=total,
            limit=product_limit,
            offset=product_offset,
        ),
    )


def _to_rejected_row(row: ETLRejectedRow) -> ETLRejectedRowItem:
    return ETLRejectedRowItem(
        rejected_row_id=row.id,
        source_row_number=row.source_row_number,
        errors=[ETLRejectError(**error) for error in row.errors],
        masked_source_data=dict(row.masked_source_data),
        created_at=row.created_at,
    )


def list_etl_rejections(
    session: Session,
    *,
    etl_load_run_id: int,
    limit: int,
    offset: int,
) -> ETLRejectedRowList | None:
    load_run = session.get(ETLLoadRun, etl_load_run_id)
    if load_run is None:
        return None
    if not load_run.reject_details_stored:
        return ETLRejectedRowList(
            available=False,
            items=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    rows_statement = (
        select(ETLRejectedRow)
        .where(ETLRejectedRow.etl_load_run_id == etl_load_run_id)
        .order_by(ETLRejectedRow.source_row_number.asc(), ETLRejectedRow.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(session.scalars(rows_statement).all())
    total_statement = select(func.count()).select_from(ETLRejectedRow).where(
        ETLRejectedRow.etl_load_run_id == etl_load_run_id
    )
    total = int(session.scalar(total_statement) or 0)
    return ETLRejectedRowList(
        available=True,
        items=[_to_rejected_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
