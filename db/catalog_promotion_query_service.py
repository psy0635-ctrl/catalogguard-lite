from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.fashion_attribute_validator import (
    build_color_comparison_key,
    build_size_comparison_key,
    collapse_comparison_whitespace,
    find_standard_color,
    find_size_system,
    find_standard_size,
)
from db.etl_query_service import (
    LIKE_ESCAPE_CHARACTER,
    escape_like_pattern,
    normalize_etl_filter,
)
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogPromotionRun,
    ETLLoadRun,
)


@dataclass(frozen=True)
class CatalogPromotionRunListItem:
    promotion_run_id: int
    etl_load_run_id: int
    source_filename: str
    profile_name: str
    status: str
    inserted_count: int
    updated_count: int
    unchanged_count: int
    blocked_count: int
    error_count: int
    warning_count: int
    failure_code: str | None
    safe_failure_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    actor_username: str | None = None


@dataclass(frozen=True)
class CatalogPromotionRunList:
    items: list[CatalogPromotionRunListItem]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class CatalogPromotionRunDetail(CatalogPromotionRunListItem):
    preview_hash: str | None = None
    preview_schema_version: str | None = None
    inspection_version: str | None = None


@dataclass(frozen=True)
class CatalogPromotionAuditItem:
    audit_id: int
    promotion_run_id: int
    catalog_product_id: int
    action: str
    changed_fields: dict[str, object]
    before_data: dict[str, object] | None
    after_data: dict[str, object]
    created_at: datetime


@dataclass(frozen=True)
class CatalogPromotionAuditList:
    items: list[CatalogPromotionAuditItem]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class UnknownSizeToken:
    token: str
    count: int


@dataclass(frozen=True)
class UnknownColorToken:
    token: str
    count: int


@dataclass(frozen=True)
class UnknownColorTokenProduct:
    catalog_product_id: int
    supplier_key: str
    external_product_id: str
    product_group_id: str
    product_name: str
    category: str
    color: str
    size: str


@dataclass(frozen=True)
class UnknownColorTokenProductList:
    token: str
    total: int
    items: list[UnknownColorTokenProduct]


@dataclass(frozen=True)
class UnknownSizeTokenProduct:
    catalog_product_id: int
    supplier_key: str
    external_product_id: str
    product_group_id: str
    product_name: str
    category: str
    color: str
    size: str


@dataclass(frozen=True)
class UnknownSizeTokenProductList:
    token: str
    total: int
    items: list[UnknownSizeTokenProduct]


def _unknown_color_comparison_key(raw_color: object) -> str | None:
    if not isinstance(raw_color, str):
        return None

    display_token = collapse_comparison_whitespace(raw_color)
    if not display_token or find_standard_color(display_token) is not None:
        return None
    return build_color_comparison_key(display_token)


def list_unknown_color_tokens(
    session: Session,
    *,
    limit: int,
) -> list[UnknownColorToken]:
    """Return frequent color values not covered by the current color vocabulary."""
    grouped_color_counts = session.execute(
        select(CatalogProduct.color, func.count(CatalogProduct.id))
        .group_by(CatalogProduct.color)
    ).all()

    grouped_tokens: dict[str, tuple[str, int]] = {}
    for raw_color, raw_count in grouped_color_counts:
        report_key = _unknown_color_comparison_key(raw_color)
        if report_key is None:
            continue
        display_token = collapse_comparison_whitespace(raw_color)
        existing = grouped_tokens.get(report_key)
        if existing is None:
            grouped_tokens[report_key] = (display_token, int(raw_count))
            continue

        existing_token, existing_count = existing
        grouped_tokens[report_key] = (
            min(existing_token, display_token, key=lambda token: (token.casefold(), token)),
            existing_count + int(raw_count),
        )

    items = [
        UnknownColorToken(token=token, count=count)
        for token, count in grouped_tokens.values()
    ]
    return sorted(items, key=lambda item: (-item.count, item.token.casefold(), item.token))[
        :limit
    ]


def list_unknown_color_token_products(
    session: Session,
    *,
    token: str,
    limit: int,
) -> UnknownColorTokenProductList:
    """Return operational catalog products affected by one unknown color token."""
    display_token = collapse_comparison_whitespace(token)
    comparison_key = _unknown_color_comparison_key(display_token)
    if comparison_key is None:
        return UnknownColorTokenProductList(token=display_token, total=0, items=[])

    raw_colors = [
        raw_color
        for raw_color in session.scalars(select(CatalogProduct.color).distinct()).all()
        if _unknown_color_comparison_key(raw_color) == comparison_key
    ]
    if not raw_colors:
        return UnknownColorTokenProductList(token=display_token, total=0, items=[])

    color_filter = CatalogProduct.color.in_(raw_colors)
    total = int(
        session.scalar(
            select(func.count()).select_from(CatalogProduct).where(color_filter)
        )
        or 0
    )
    products = list(
        session.scalars(
            select(CatalogProduct)
            .where(color_filter)
            .order_by(
                CatalogProduct.supplier_key.asc(),
                CatalogProduct.external_product_id.asc(),
                CatalogProduct.id.asc(),
            )
            .limit(limit)
        ).all()
    )
    return UnknownColorTokenProductList(
        token=display_token,
        total=total,
        items=[
            UnknownColorTokenProduct(
                catalog_product_id=product.id,
                supplier_key=product.supplier_key,
                external_product_id=product.external_product_id,
                product_group_id=product.product_group_id,
                product_name=product.product_name,
                category=product.category,
                color=product.color,
                size=product.size,
            )
            for product in products
        ],
    )


def _is_unknown_size_token(size: object) -> bool:
    if not isinstance(size, str):
        return False

    normalized_size = collapse_comparison_whitespace(size)
    return bool(
        normalized_size
        and find_standard_size(normalized_size) is None
        and find_size_system(normalized_size) is None
    )


def list_unknown_size_token_products(
    session: Session,
    *,
    token: str,
    limit: int,
) -> UnknownSizeTokenProductList:
    """Return current catalog products using one unknown size comparison key."""
    display_token = collapse_comparison_whitespace(token)
    if not _is_unknown_size_token(display_token):
        return UnknownSizeTokenProductList(token=display_token, total=0, items=[])

    comparison_key = build_size_comparison_key(display_token)
    if comparison_key is None:
        return UnknownSizeTokenProductList(token=display_token, total=0, items=[])

    raw_sizes = [
        raw_size
        for raw_size in session.scalars(select(CatalogProduct.size).distinct()).all()
        if _is_unknown_size_token(raw_size)
        and build_size_comparison_key(raw_size) == comparison_key
    ]
    if not raw_sizes:
        return UnknownSizeTokenProductList(token=display_token, total=0, items=[])

    size_filter = CatalogProduct.size.in_(raw_sizes)
    total = int(
        session.scalar(
            select(func.count()).select_from(CatalogProduct).where(size_filter)
        )
        or 0
    )
    products = list(
        session.scalars(
            select(CatalogProduct)
            .where(size_filter)
            .order_by(
                CatalogProduct.supplier_key.asc(),
                CatalogProduct.external_product_id.asc(),
                CatalogProduct.id.asc(),
            )
            .limit(limit)
        ).all()
    )
    return UnknownSizeTokenProductList(
        token=display_token,
        total=total,
        items=[
            UnknownSizeTokenProduct(
                catalog_product_id=product.id,
                supplier_key=product.supplier_key,
                external_product_id=product.external_product_id,
                product_group_id=product.product_group_id,
                product_name=product.product_name,
                category=product.category,
                color=product.color,
                size=product.size,
            )
            for product in products
        ],
    )


def list_unknown_size_tokens(
    session: Session,
    *,
    limit: int,
) -> list[UnknownSizeToken]:
    """Return the most frequent non-standard, non-numeric catalog size tokens."""
    grouped_size_counts = session.execute(
        select(CatalogProduct.size, func.count(CatalogProduct.id))
        .group_by(CatalogProduct.size)
    ).all()

    grouped_tokens: dict[str, tuple[str, int]] = {}
    for raw_size, raw_count in grouped_size_counts:
        if not _is_unknown_size_token(raw_size):
            continue

        report_key = build_size_comparison_key(raw_size)
        if report_key is None:
            continue
        display_token = collapse_comparison_whitespace(raw_size)
        existing = grouped_tokens.get(report_key)
        if existing is None:
            grouped_tokens[report_key] = (display_token, int(raw_count))
            continue

        existing_token, existing_count = existing
        grouped_tokens[report_key] = (
            min(existing_token, display_token, key=lambda token: (token.casefold(), token)),
            existing_count + int(raw_count),
        )

    items = [
        UnknownSizeToken(token=token, count=count)
        for token, count in grouped_tokens.values()
    ]
    return sorted(items, key=lambda item: (-item.count, item.token.casefold(), item.token))[
        :limit
    ]


def _apply_run_filters(
    statement,
    *,
    status: str | None = None,
    etl_load_run_id: int | None = None,
    filename: str | None = None,
    profile_name: str | None = None,
):
    if status is not None:
        statement = statement.where(CatalogPromotionRun.status == status)
    if etl_load_run_id is not None:
        statement = statement.where(
            CatalogPromotionRun.etl_load_run_id == etl_load_run_id
        )
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


def _to_run_list_item(
    run: CatalogPromotionRun,
    load_run: ETLLoadRun,
) -> CatalogPromotionRunListItem:
    return CatalogPromotionRunListItem(
        promotion_run_id=run.id,
        etl_load_run_id=run.etl_load_run_id,
        source_filename=load_run.source_filename,
        profile_name=load_run.profile_name,
        status=run.status,
        inserted_count=run.inserted_count,
        updated_count=run.updated_count,
        unchanged_count=run.unchanged_count,
        blocked_count=run.blocked_count,
        error_count=run.error_count,
        warning_count=run.warning_count,
        failure_code=run.failure_code,
        safe_failure_message=run.safe_failure_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        actor_username=run.actor_username,
    )


def list_catalog_promotions(
    session: Session,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
    etl_load_run_id: int | None = None,
    filename: str | None = None,
    profile_name: str | None = None,
) -> CatalogPromotionRunList:
    items_statement = _apply_run_filters(
        select(CatalogPromotionRun, ETLLoadRun).join(
            ETLLoadRun,
            ETLLoadRun.id == CatalogPromotionRun.etl_load_run_id,
        ),
        status=status,
        etl_load_run_id=etl_load_run_id,
        filename=filename,
        profile_name=profile_name,
    ).order_by(CatalogPromotionRun.created_at.desc(), CatalogPromotionRun.id.desc())
    rows = session.execute(items_statement.limit(limit).offset(offset)).all()

    total_statement = _apply_run_filters(
        select(func.count())
        .select_from(CatalogPromotionRun)
        .join(ETLLoadRun, ETLLoadRun.id == CatalogPromotionRun.etl_load_run_id),
        status=status,
        etl_load_run_id=etl_load_run_id,
        filename=filename,
        profile_name=profile_name,
    )
    total = int(session.scalar(total_statement) or 0)
    return CatalogPromotionRunList(
        items=[_to_run_list_item(run, load_run) for run, load_run in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_catalog_promotion_detail(
    session: Session,
    *,
    promotion_run_id: int,
) -> CatalogPromotionRunDetail | None:
    row = session.execute(
        select(CatalogPromotionRun, ETLLoadRun)
        .join(ETLLoadRun, ETLLoadRun.id == CatalogPromotionRun.etl_load_run_id)
        .where(CatalogPromotionRun.id == promotion_run_id)
    ).first()
    if row is None:
        return None

    run, load_run = row
    item = _to_run_list_item(run, load_run)
    return CatalogPromotionRunDetail(
        **item.__dict__,
        preview_hash=run.preview_hash,
        preview_schema_version=run.preview_schema_version,
        inspection_version=run.inspection_version,
    )


def _to_audit_item(change: CatalogProductChange) -> CatalogPromotionAuditItem:
    return CatalogPromotionAuditItem(
        audit_id=change.id,
        promotion_run_id=change.promotion_run_id,
        catalog_product_id=change.catalog_product_id,
        action=change.action,
        changed_fields=dict(change.changed_fields),
        before_data=(
            None if change.before_data is None else dict(change.before_data)
        ),
        after_data=dict(change.after_data),
        created_at=change.created_at,
    )


def list_catalog_promotion_audits(
    session: Session,
    *,
    promotion_run_id: int,
    limit: int,
    offset: int,
) -> CatalogPromotionAuditList | None:
    if session.get(CatalogPromotionRun, promotion_run_id) is None:
        return None

    items_statement = (
        select(CatalogProductChange)
        .where(CatalogProductChange.promotion_run_id == promotion_run_id)
        .order_by(
            CatalogProductChange.created_at.desc(),
            CatalogProductChange.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    items = list(session.scalars(items_statement).all())
    total = int(
        session.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(CatalogProductChange.promotion_run_id == promotion_run_id)
        )
        or 0
    )
    return CatalogPromotionAuditList(
        items=[_to_audit_item(change) for change in items],
        total=total,
        limit=limit,
        offset=offset,
    )
