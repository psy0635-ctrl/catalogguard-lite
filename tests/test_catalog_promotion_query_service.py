from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from config.database import get_optional_database_url
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogPromotionRun,
    ETLLoadRun,
)
from db.session import create_database_engine, create_session_factory


class _Rows:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ReadOnlyListSession:
    def __init__(self, rows):
        self.rows = rows
        self.execute_calls = 0
        self.scalar_calls = 0

    def execute(self, _statement):
        self.execute_calls += 1
        return _Rows(self.rows)

    def scalar(self, _statement):
        self.scalar_calls += 1
        return len(self.rows)

    def commit(self):
        raise AssertionError("query service must not commit")

    def rollback(self):
        raise AssertionError("query service must not rollback")


class _ScalarRows:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _UnknownColorProductSession:
    def __init__(self, *, raw_colors, products, total):
        self._scalar_results = [raw_colors, products]
        self.total = total
        self.scalars_statements = []
        self.scalar_statements = []

    def scalars(self, statement):
        self.scalars_statements.append(statement)
        return _ScalarRows(self._scalar_results.pop(0))

    def scalar(self, statement):
        self.scalar_statements.append(statement)
        return self.total

    def commit(self):
        raise AssertionError("query service must not commit")

    def rollback(self):
        raise AssertionError("query service must not rollback")


class _VocabularyCoverageSession:
    def __init__(self, color_counts, size_counts):
        self._grouped_results = [
            *(('color', raw_value, count) for raw_value, count in color_counts),
            *(('size', raw_value, count) for raw_value, count in size_counts),
        ]
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Rows(self._grouped_results)

    def commit(self):
        raise AssertionError("query service must not commit")

    def rollback(self):
        raise AssertionError("query service must not rollback")

    def flush(self):
        raise AssertionError("query service must not flush")

    def add(self, _item):
        raise AssertionError("query service must not add")

    def delete(self, _item):
        raise AssertionError("query service must not delete")


class _SupplierVocabularyCoverageSession:
    def __init__(self, grouped_counts):
        self.grouped_counts = grouped_counts
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Rows(self.grouped_counts)

    def commit(self):
        raise AssertionError("query service must not commit")

    def rollback(self):
        raise AssertionError("query service must not rollback")

    def flush(self):
        raise AssertionError("query service must not flush")

    def add(self, _item):
        raise AssertionError("query service must not add")

    def delete(self, _item):
        raise AssertionError("query service must not delete")

    def update(self, _item):
        raise AssertionError("query service must not update")


def test_list_unknown_size_tokens_groups_only_unknown_catalog_sizes_deterministically():
    from db.catalog_promotion_query_service import list_unknown_size_tokens

    session = _ReadOnlyListSession(
        [
            ("4XL", 10),
            ("4xl", 5),
            (" 4XL ", 2),
            ("OS", 6),
            ("XXXXL", 6),
            ("4 XL", 4),
            ("4-XL", 3),
            ("4/XL", 2),
            ("M", 100),
            ("2XL", 90),
            ("ONE SIZE", 80),
            ("F", 70),
            ("95", 60),
            ("270", 50),
            ("", 40),
            ("   ", 30),
        ]
    )

    result = list_unknown_size_tokens(session, limit=3)

    assert [(item.token, item.count) for item in result] == [
        ("4XL", 17),
        ("OS", 6),
        ("XXXXL", 6),
    ]


def test_list_unknown_size_tokens_keeps_unregistered_separator_variants_separate():
    from db.catalog_promotion_query_service import list_unknown_size_tokens

    session = _ReadOnlyListSession(
        [("4XL", 1), ("4 XL", 1), ("4-XL", 1), ("4/XL", 1)]
    )

    result = list_unknown_size_tokens(session, limit=20)

    assert [(item.token, item.count) for item in result] == [
        ("4 XL", 1),
        ("4-XL", 1),
        ("4/XL", 1),
        ("4XL", 1),
    ]


def test_list_unknown_color_tokens_groups_unknown_values_and_excludes_known_colors():
    from core.fashion_attribute_validator import find_standard_color
    from db.catalog_promotion_query_service import list_unknown_color_tokens

    for known in (
        "BLACK", "black", "블랙", "검정", "검정색", "WHITE", "white",
        "GRAY", "gray", "grey", "그레이", "NAVY", "navy", "네이비",
        "BEIGE", "beige", "베이지",
    ):
        assert find_standard_color(known) is not None
    assert find_standard_color("MELANGE GRAY") is None
    assert find_standard_color("CHARCOAL") is None

    session = _ReadOnlyListSession(
        [
            ("BLACK", 100), ("black", 3), ("블랙", 2), ("검정", 1),
            ("WHITE", 80), ("gray", 70), ("grey", 60), ("그레이", 50),
            ("NAVY", 40), ("", 20), ("   ", 10), ("\t", 5),
            ("MELANGE GRAY", 2), ("melange gray", 3),
            ("melange   gray", 4), ("CHARCOAL", 8), ("MINT", 8),
        ]
    )

    result = list_unknown_color_tokens(session, limit=20)

    assert [(item.token, item.count) for item in result] == [
        ("MELANGE GRAY", 9), ("CHARCOAL", 8), ("MINT", 8),
    ]
    assert session.execute_calls == 1

    assert [
        (item.token, item.count)
        for item in list_unknown_color_tokens(
            _ReadOnlyListSession(
                [
                    ("MINT", 8), ("CHARCOAL", 8), ("melange   gray", 4),
                    ("melange gray", 3), ("MELANGE GRAY", 2),
                ]
            ),
            limit=2,
        )
    ] == [("MELANGE GRAY", 9), ("CHARCOAL", 8)]


def test_list_unknown_color_tokens_keeps_unregistered_separator_variants_separate():
    from db.catalog_promotion_query_service import list_unknown_color_tokens

    result = list_unknown_color_tokens(
        _ReadOnlyListSession(
            [("MELANGE GRAY", 2), ("MELANGE-GRAY", 2), ("MELANGE/GRAY", 2)]
        ),
        limit=20,
    )

    assert [(item.token, item.count) for item in result] == [
        ("MELANGE GRAY", 2), ("MELANGE-GRAY", 2), ("MELANGE/GRAY", 2),
    ]


def test_list_unknown_color_token_products_matches_only_the_selected_comparison_key():
    from db.catalog_promotion_query_service import list_unknown_color_token_products

    products = [
        SimpleNamespace(
            id=2,
            supplier_key="alpha",
            external_product_id="SKU-002",
            product_group_id="GROUP-02",
            product_name="후드",
            category="TOP",
            color="melange   gray",
            size="M",
        ),
        SimpleNamespace(
            id=5,
            supplier_key="beta",
            external_product_id="SKU-001",
            product_group_id="GROUP-01",
            product_name="셔츠",
            category="TOP",
            color="MELANGE GRAY",
            size="L",
        ),
    ]
    session = _UnknownColorProductSession(
        raw_colors=[
            "MELANGE GRAY",
            "melange gray",
            "melange   gray",
            "MELANGE-GRAY",
            "MELANGE/GRAY",
            "BLACK",
        ],
        products=products,
        total=3,
    )

    result = list_unknown_color_token_products(
        session, token="  MeLaNgE   GrAy ", limit=2
    )

    assert result.token == "MeLaNgE GrAy"
    assert result.total == 3
    assert [item.catalog_product_id for item in result.items] == [2, 5]
    assert [item.color for item in result.items] == [
        "melange   gray",
        "MELANGE GRAY",
    ]
    assert len(session.scalars_statements) == 2
    assert len(session.scalar_statements) == 1

    product_statement = session.scalars_statements[1]
    assert [clause.element.name for clause in product_statement._order_by_clauses] == [
        "supplier_key",
        "external_product_id",
        "id",
    ]
    assert product_statement._limit_clause.value == 2
    assert product_statement.compile().params["color_1"] == [
        "MELANGE GRAY",
        "melange gray",
        "melange   gray",
    ]


def test_list_unknown_color_token_products_returns_empty_for_known_color_without_query():
    from db.catalog_promotion_query_service import list_unknown_color_token_products

    session = _UnknownColorProductSession(raw_colors=[], products=[], total=0)

    result = list_unknown_color_token_products(session, token=" black ", limit=20)

    assert result.token == "black"
    assert result.total == 0
    assert result.items == []
    assert session.scalars_statements == []
    assert session.scalar_statements == []


def test_list_unknown_size_token_products_matches_existing_size_comparison_policy():
    from db.catalog_promotion_query_service import list_unknown_size_token_products

    products = [
        SimpleNamespace(
            id=2, supplier_key="vendor_a", external_product_id="SKU-1",
            product_group_id="GROUP-1", product_name="후드", category="TOP",
            color="BLACK", size=" 4XL ",
        ),
        SimpleNamespace(
            id=4, supplier_key="vendor_a", external_product_id="SKU-1",
            product_group_id="GROUP-1", product_name="후드", category="TOP",
            color="BLACK", size="4xl",
        ),
    ]
    session = _UnknownColorProductSession(
        raw_colors=["4XL", "4xl", " 4XL ", "4-XL", "4/XL", "4 XL", "M", "95"],
        products=products,
        total=7,
    )

    result = list_unknown_size_token_products(session, token=" 4XL ", limit=2)

    assert result.token == "4XL"
    assert result.total == 7
    assert [item.catalog_product_id for item in result.items] == [2, 4]
    assert [item.size for item in result.items] == [" 4XL ", "4xl"]
    assert len(session.scalars_statements) == 2
    assert len(session.scalar_statements) == 1
    product_statement = session.scalars_statements[1]
    assert [clause.element.name for clause in product_statement._order_by_clauses] == [
        "supplier_key", "external_product_id", "id",
    ]
    assert product_statement._limit_clause.value == 2
    assert set(product_statement.compile().params["size_1"]) == {"4XL", "4xl", " 4XL "}


@pytest.mark.parametrize("token", ["M", "95", "   "])
def test_list_unknown_size_token_products_returns_empty_without_query_for_known_size(token):
    from db.catalog_promotion_query_service import list_unknown_size_token_products

    session = _UnknownColorProductSession(raw_colors=[], products=[], total=0)

    result = list_unknown_size_token_products(session, token=token, limit=20)

    assert result.total == 0
    assert result.items == []
    assert session.scalars_statements == []
    assert session.scalar_statements == []


def test_get_catalog_vocabulary_coverage_classifies_grouped_values_read_only():
    from db.catalog_promotion_query_service import get_catalog_vocabulary_coverage

    session = _VocabularyCoverageSession(
        color_counts=[
            ("BLACK", 2), ("black", 1), ("블랙", 3),
            ("CHARCOAL", 4), ("MINT", 2), ("", 1), ("   ", 1), (None, 1),
        ],
        size_counts=[
            ("M", 2), ("medium", 3), ("FREE", 2),
            ("95", 1), ("100", 1), ("4XL", 2), ("OS", 1),
            ("", 1), ("   ", 1), (None, 1),
        ],
    )

    result = get_catalog_vocabulary_coverage(session)

    assert result.catalog_product_count == 15
    assert result.color.non_empty_count == 12
    assert result.color.recognized_count == 6
    assert result.color.unknown_count == 6
    assert result.color.empty_count == 3
    assert result.size.non_empty_count == 12
    assert result.size.recognized_count == 9
    assert result.size.standard_count == 7
    assert result.size.numeric_count == 2
    assert result.size.unknown_count == 3
    assert result.size.empty_count == 3
    assert len(session.statements) == 1
    assert result.catalog_product_count == (
        result.color.non_empty_count + result.color.empty_count
    )
    assert result.catalog_product_count == (
        result.size.non_empty_count + result.size.empty_count
    )
    statement_sql = str(session.statements[0])
    assert "UNION ALL" in statement_sql
    assert statement_sql.count("GROUP BY") == 2


def test_catalog_vocabulary_unknown_counts_match_unknown_token_reports():
    from db.catalog_promotion_query_service import (
        get_catalog_vocabulary_coverage,
        list_unknown_color_tokens,
        list_unknown_size_tokens,
    )

    color_counts = [("BLACK", 2), ("CHARCOAL", 4), ("MINT", 2), ("", 1)]
    size_counts = [("M", 2), ("95", 1), ("4XL", 2), ("OS", 1), ("", 1)]
    coverage = get_catalog_vocabulary_coverage(
        _VocabularyCoverageSession(color_counts, size_counts)
    )
    colors = list_unknown_color_tokens(_ReadOnlyListSession(color_counts), limit=100)
    sizes = list_unknown_size_tokens(_ReadOnlyListSession(size_counts), limit=100)

    assert coverage.color.unknown_count == sum(item.count for item in colors) == 6
    assert coverage.size.unknown_count == sum(item.count for item in sizes) == 3


def test_list_supplier_vocabulary_coverage_groups_by_supplier_in_one_read_only_statement():
    from db.catalog_promotion_query_service import (
        get_catalog_vocabulary_coverage,
        list_supplier_vocabulary_coverage,
    )

    grouped_counts = [
        ("supplier-a", "color", "BLACK", 3),
        ("supplier-a", "color", "CHARCOAL", 2),
        ("supplier-a", "color", "", 1),
        ("supplier-a", "size", "M", 2),
        ("supplier-a", "size", "95", 2),
        ("supplier-a", "size", "4XL", 1),
        ("supplier-a", "size", "", 1),
        ("supplier-b", "color", "BLACK", 2),
        ("supplier-b", "color", "CHARCOAL", 7),
        ("supplier-b", "color", None, 1),
        ("supplier-b", "size", "FREE", 3),
        ("supplier-b", "size", "100", 2),
        ("supplier-b", "size", "OS", 3),
        ("supplier-b", "size", None, 2),
    ]
    session = _SupplierVocabularyCoverageSession(grouped_counts)

    suppliers = list_supplier_vocabulary_coverage(session)

    assert [item.supplier_key for item in suppliers] == ["supplier-a", "supplier-b"]
    supplier_a, supplier_b = suppliers
    assert supplier_a.catalog_product_count == 6
    assert supplier_a.color.recognized_count == 3
    assert supplier_a.color.unknown_count == 2
    assert supplier_a.color.empty_count == 1
    assert supplier_a.size.standard_count == 2
    assert supplier_a.size.numeric_count == 2
    assert supplier_a.size.unknown_count == 1
    assert supplier_a.size.empty_count == 1
    assert supplier_b.catalog_product_count == 10
    assert supplier_b.color.unknown_count == 7
    assert supplier_b.size.standard_count == 3
    assert supplier_b.size.numeric_count == 2
    assert supplier_b.size.unknown_count == 3
    assert supplier_b.size.empty_count == 2
    for supplier in suppliers:
        assert supplier.catalog_product_count == (
            supplier.color.non_empty_count + supplier.color.empty_count
        )
        assert supplier.color.non_empty_count == (
            supplier.color.recognized_count + supplier.color.unknown_count
        )
        assert supplier.catalog_product_count == (
            supplier.size.non_empty_count + supplier.size.empty_count
        )
        assert supplier.size.non_empty_count == (
            supplier.size.standard_count
            + supplier.size.numeric_count
            + supplier.size.unknown_count
        )
        assert supplier.size.recognized_count == (
            supplier.size.standard_count + supplier.size.numeric_count
        )

    assert len(session.statements) == 1
    statement_sql = str(session.statements[0])
    assert "UNION ALL" in statement_sql
    assert "GROUP BY catalog_products.supplier_key, catalog_products.color" in statement_sql
    assert "GROUP BY catalog_products.supplier_key, catalog_products.size" in statement_sql

    all_color_counts = {}
    all_size_counts = {}
    for _supplier_key, kind, raw_value, count in grouped_counts:
        counts = all_color_counts if kind == "color" else all_size_counts
        counts[raw_value] = counts.get(raw_value, 0) + count
    overall = get_catalog_vocabulary_coverage(
        _VocabularyCoverageSession(
            list(all_color_counts.items()), list(all_size_counts.items())
        )
    )
    assert sum(item.catalog_product_count for item in suppliers) == overall.catalog_product_count
    assert sum(item.color.unknown_count for item in suppliers) == overall.color.unknown_count
    assert sum(item.size.unknown_count for item in suppliers) == overall.size.unknown_count


def test_list_supplier_vocabulary_coverage_returns_empty_for_empty_catalog():
    from db.catalog_promotion_query_service import list_supplier_vocabulary_coverage

    session = _SupplierVocabularyCoverageSession([])

    assert list_supplier_vocabulary_coverage(session) == []
    assert len(session.statements) == 1


def test_list_unknown_size_tokens_processes_ten_thousand_grouped_catalog_sizes_in_one_query():
    from db.catalog_promotion_query_service import list_unknown_size_tokens

    session = _ReadOnlyListSession(
        [(f"CUSTOM-{index:05d}", 1) for index in range(10_000)]
        + [("4XL", 10_001)]
    )

    result = list_unknown_size_tokens(session, limit=1)

    assert [(item.token, item.count) for item in result] == [("4XL", 10_001)]
    assert session.execute_calls == 1
    assert session.scalar_calls == 0


def test_list_catalog_promotions_maps_joined_rows_without_writes():
    from db.catalog_promotion_query_service import list_catalog_promotions

    created_at = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    promotion = SimpleNamespace(
        id=21,
        etl_load_run_id=12,
        status="succeeded",
        inserted_count=2,
        updated_count=1,
        unchanged_count=3,
        blocked_count=0,
        error_count=0,
        warning_count=1,
        failure_code=None,
        safe_failure_message=None,
        started_at=created_at,
        completed_at=created_at + timedelta(seconds=1),
        created_at=created_at,
        actor_username="operator_user",
    )
    load = SimpleNamespace(
        source_filename="vendor.csv",
        profile_name="sample_vendor",
    )
    session = _ReadOnlyListSession([(promotion, load)])

    result = list_catalog_promotions(session, limit=20, offset=0)

    assert result.total == 1
    assert result.items[0].promotion_run_id == 21
    assert result.items[0].source_filename == "vendor.csv"
    assert result.items[0].inserted_count == 2
    assert result.items[0].status == "succeeded"
    assert session.scalar_calls == 1


@pytest.fixture()
def seeded_promotions():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    profile_prefix = f"promotion_query_{uuid4().hex}"
    base_time = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)

    def add_load(index: int, filename: str) -> ETLLoadRun:
        load = ETLLoadRun(
            source_filename=filename,
            profile_name=f"{profile_prefix}_{index}",
            profile_version="1",
            input_file_sha256=f"{index}" * 64,
            output_file_sha256=f"{index + 3}" * 64,
            loaded_rows=1,
            total_rows=1,
            rejected_rows=0,
            error_counts={},
            reject_details_stored=False,
            created_at=base_time + timedelta(minutes=index),
        )
        session.add(load)
        session.flush()
        return load

    def add_promotion(
        load: ETLLoadRun,
        *,
        status: str,
        created_at: datetime,
        inserted_count: int = 0,
        updated_count: int = 0,
        unchanged_count: int = 0,
        failure_code: str | None = None,
        safe_failure_message: str | None = None,
    ) -> CatalogPromotionRun:
        run = CatalogPromotionRun(
            etl_load_run_id=load.id,
            status=status,
            preview_hash="a" * 64,
            preview_schema_version="1",
            inspection_version="1",
            inserted_count=inserted_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            blocked_count=1 if status == "blocked" else 0,
            error_count=0,
            warning_count=0,
            failure_code=failure_code,
            safe_failure_message=safe_failure_message,
            started_at=created_at,
            completed_at=created_at + timedelta(seconds=1),
            created_at=created_at,
        )
        session.add(run)
        session.flush()
        return run

    oldest_load = add_load(1, "old-vendor.csv")
    failed_load = add_load(2, "failed-vendor.csv")
    newest_load = add_load(3, "new-vendor.csv")
    oldest = add_promotion(
        oldest_load,
        status="succeeded",
        created_at=base_time,
        inserted_count=1,
    )
    failed = add_promotion(
        failed_load,
        status="failed",
        created_at=base_time + timedelta(minutes=1),
        failure_code="promotion_apply_failed",
        safe_failure_message="Promotion could not be completed.",
    )
    newest = add_promotion(
        newest_load,
        status="blocked",
        created_at=base_time + timedelta(minutes=2),
        failure_code="preview_stale",
        safe_failure_message="Preview is stale.",
    )

    product = CatalogProduct(
        supplier_key=oldest_load.profile_name,
        external_product_id="SKU-001",
        product_group_id="GROUP-001",
        product_name="Product 1",
        category="TOP",
        color="BLACK",
        size="M",
        stock=5,
        price=1000,
        sale_price=900,
        image_path="image.jpg",
        description=None,
        seller="Seller",
        source_etl_load_run_id=oldest_load.id,
    )
    session.add(product)
    session.flush()
    for index in range(3):
        session.add(
            CatalogProductChange(
                promotion_run_id=oldest.id,
                catalog_product_id=product.id,
                action="update",
                changed_fields={
                    "stock": {"before": index, "after": index + 1}
                },
                before_data={"external_product_id": "SKU-001", "stock": index},
                after_data={"external_product_id": "SKU-001", "stock": index + 1},
                created_at=base_time + timedelta(seconds=index),
            )
        )
    session.commit()

    try:
        yield session, profile_prefix, oldest, failed, newest
    finally:
        session.rollback()
        session.close()
        with session_factory() as cleanup:
            load_ids = select(ETLLoadRun.id).where(
                ETLLoadRun.profile_name.like(f"{profile_prefix}%")
            )
            promotion_ids = select(CatalogPromotionRun.id).where(
                CatalogPromotionRun.etl_load_run_id.in_(load_ids)
            )
            cleanup.execute(
                delete(CatalogProductChange).where(
                    CatalogProductChange.promotion_run_id.in_(promotion_ids)
                )
            )
            cleanup.execute(
                delete(CatalogProduct).where(
                    CatalogProduct.source_etl_load_run_id.in_(load_ids)
                )
            )
            cleanup.execute(
                delete(CatalogPromotionRun).where(
                    CatalogPromotionRun.etl_load_run_id.in_(load_ids)
                )
            )
            cleanup.execute(delete(ETLLoadRun).where(ETLLoadRun.id.in_(load_ids)))
            cleanup.commit()
        engine.dispose()


def test_list_unknown_size_tokens_counts_current_catalog_snapshot_rows(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import list_unknown_size_tokens

    session, _, oldest, _, _ = seeded_promotions
    product = session.scalar(
        select(CatalogProduct).where(
            CatalogProduct.source_etl_load_run_id == oldest.etl_load_run_id
        )
    )
    assert product is not None

    product.size = "4XL"
    session.add(
        CatalogProduct(
            supplier_key=product.supplier_key,
            external_product_id="SKU-002",
            product_group_id="GROUP-001",
            product_name="Product 2",
            category="TOP",
            color="WHITE",
            size="4xl",
            stock=3,
            price=1200,
            sale_price=None,
            image_path="image-2.jpg",
            description=None,
            seller="Seller",
            source_etl_load_run_id=oldest.etl_load_run_id,
        )
    )
    session.flush()

    result = list_unknown_size_tokens(session, limit=20)

    assert [(item.token, item.count) for item in result] == [("4XL", 2)]


def test_list_catalog_promotions_sorts_latest_and_uses_sql_pagination(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import list_catalog_promotions

    session, profile_prefix, oldest, failed, newest = seeded_promotions

    first_page = list_catalog_promotions(
        session,
        limit=2,
        offset=0,
        filename="vendor",
        profile_name=profile_prefix,
    )
    second_page = list_catalog_promotions(
        session,
        limit=2,
        offset=2,
        filename="vendor",
        profile_name=profile_prefix,
    )

    assert [item.promotion_run_id for item in first_page.items] == [
        newest.id,
        failed.id,
    ]
    assert first_page.items[0].source_filename == "new-vendor.csv"
    assert first_page.total == 3
    assert first_page.limit == 2
    assert first_page.offset == 0
    assert [item.promotion_run_id for item in second_page.items] == [oldest.id]


def test_list_catalog_promotions_filters_status_and_etl_load_run(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import list_catalog_promotions

    session, _profile_prefix, _oldest, failed, newest = seeded_promotions

    failed_result = list_catalog_promotions(
        session,
        limit=20,
        offset=0,
        status="failed",
    )
    load_result = list_catalog_promotions(
        session,
        limit=20,
        offset=0,
        etl_load_run_id=newest.etl_load_run_id,
    )

    assert [item.promotion_run_id for item in failed_result.items] == [failed.id]
    assert [item.promotion_run_id for item in load_result.items] == [newest.id]


def test_get_catalog_promotion_detail_returns_existing_run_or_none(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import get_catalog_promotion_detail

    session, _profile_prefix, _oldest, failed, _newest = seeded_promotions

    detail = get_catalog_promotion_detail(
        session,
        promotion_run_id=failed.id,
    )

    assert detail is not None
    assert detail.promotion_run_id == failed.id
    assert detail.etl_load_run_id == failed.etl_load_run_id
    assert detail.source_filename == "failed-vendor.csv"
    assert detail.status == "failed"
    assert detail.failure_code == "promotion_apply_failed"
    assert detail.safe_failure_message == "Promotion could not be completed."
    assert get_catalog_promotion_detail(
        session,
        promotion_run_id=999999999,
    ) is None


def test_list_catalog_promotion_audits_isolated_paginated_and_empty(
    seeded_promotions,
):
    from db.catalog_promotion_query_service import list_catalog_promotion_audits

    session, _profile_prefix, oldest, failed, _newest = seeded_promotions

    first_page = list_catalog_promotion_audits(
        session,
        promotion_run_id=oldest.id,
        limit=2,
        offset=0,
    )
    second_page = list_catalog_promotion_audits(
        session,
        promotion_run_id=oldest.id,
        limit=2,
        offset=2,
    )
    empty = list_catalog_promotion_audits(
        session,
        promotion_run_id=failed.id,
        limit=20,
        offset=0,
    )

    assert first_page is not None
    assert first_page.total == 3
    assert len(first_page.items) == 2
    assert all(item.promotion_run_id == oldest.id for item in first_page.items)
    assert first_page.items[0].audit_id > first_page.items[1].audit_id
    assert second_page is not None
    assert len(second_page.items) == 1
    assert empty is not None
    assert empty.items == []
    assert empty.total == 0
    assert list_catalog_promotion_audits(
        session,
        promotion_run_id=999999999,
        limit=20,
        offset=0,
    ) is None


def test_catalog_promotion_queries_do_not_modify_database(seeded_promotions):
    from db.catalog_promotion_query_service import (
        get_catalog_promotion_detail,
        list_catalog_promotion_audits,
        list_catalog_promotions,
    )

    session, profile_prefix, oldest, _failed, _newest = seeded_promotions
    before_runs = session.scalar(
        select(CatalogPromotionRun).where(CatalogPromotionRun.id == oldest.id)
    ).inserted_count
    before_audits = session.scalar(
        select(CatalogProductChange).where(
            CatalogProductChange.promotion_run_id == oldest.id
        )
    ).changed_fields

    list_catalog_promotions(
        session,
        limit=20,
        offset=0,
        profile_name=profile_prefix,
    )
    get_catalog_promotion_detail(session, promotion_run_id=oldest.id)
    list_catalog_promotion_audits(
        session,
        promotion_run_id=oldest.id,
        limit=20,
        offset=0,
    )

    assert session.get(CatalogPromotionRun, oldest.id).inserted_count == before_runs
    assert session.scalar(
        select(CatalogProductChange).where(
            CatalogProductChange.promotion_run_id == oldest.id
        )
    ).changed_fields == before_audits


@pytest.mark.parametrize("attribute, token, known", [("color", "CHARCOAL", "BLACK"), ("size", "4XL", "M")])
def test_unknown_tokens_filter_suppliers_before_grouping(attribute, token, known):
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import Session
    from db import catalog_promotion_query_service as service

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE catalog_products (id INTEGER PRIMARY KEY, supplier_key TEXT, color TEXT, size TEXT)"))
        values = []
        for supplier, count in [("supplier-a", 2), ("supplier-b", 7)]:
            for value in [token] * count + [known, "", "   ", "95" if attribute == "size" else known]:
                values.append({"supplier": supplier, "value": value})
        connection.execute(text(f"INSERT INTO catalog_products (supplier_key, {attribute}) VALUES (:supplier, :value)"), values)
    statements = []
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, statement, parameters, context, many: statements.append(statement))
    report = getattr(service, f"list_unknown_{attribute}_tokens")
    with Session(engine) as session:
        for supplier, expected in [("supplier-a", 2), ("supplier-b", 7), (None, 9), ("missing", 0)]:
            before = len(statements)
            items = report(session, limit=20, supplier_key=supplier)
            assert [(item.token, item.count) for item in items] == ([(token, expected)] if expected else [])
            assert len(statements) == before + 1
            if supplier is not None:
                assert "WHERE catalog_products.supplier_key =" in statements[-1]
    engine.dispose()
