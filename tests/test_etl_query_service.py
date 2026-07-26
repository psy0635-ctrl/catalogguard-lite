from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from config.database import get_optional_database_url
from db.models import CatalogProductStaging, ETLLoadRun
from db.session import create_database_engine, create_session_factory


@pytest.fixture()
def postgres_session():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 PostgreSQL 통합 테스트를 건너뜁니다.")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    session = session_factory()
    profile_prefix = f"query_test_{uuid4().hex}"
    try:
        yield session, profile_prefix
    finally:
        session.rollback()
        session.close()
        with session_factory() as cleanup:
            cleanup.execute(
                delete(ETLLoadRun).where(ETLLoadRun.profile_name.like(f"{profile_prefix}%"))
            )
            cleanup.commit()
        engine.dispose()


def _add_run(
    session,
    *,
    profile_name,
    source_filename,
    created_at,
    suffix,
    product_count=0,
):
    run = ETLLoadRun(
        source_filename=source_filename,
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256=(suffix * 64)[:64],
        output_file_sha256=(chr(ord(suffix) + 1) * 64)[:64],
        loaded_rows=product_count,
        created_at=created_at,
    )
    session.add(run)
    session.flush()
    for index in range(product_count):
        session.add(
            CatalogProductStaging(
                etl_load_run_id=run.id,
                product_group_id=f"GROUP-{index}",
                product_id=f"SKU-{index}",
                product_name=f"Product {index}",
                category="TOP",
                color="BLACK",
                size="M",
                stock=index,
                price=1000 + index,
                sale_price=None if index == 1 else 900 + index,
                image_path=f"image-{index}.jpg",
                description=None if index == 1 else f"Description {index}",
                seller=None if index == 1 else "Seller",
            )
        )
    session.flush()
    return run


@pytest.fixture()
def seeded_runs(postgres_session):
    session, profile_prefix = postgres_session
    base_time = datetime(2026, 7, 25, 12, tzinfo=timezone.utc)
    newest = _add_run(
        session,
        profile_name=f"{profile_prefix}_fashion",
        source_filename="vendor_products.csv",
        created_at=base_time + timedelta(minutes=1),
        suffix="a",
        product_count=3,
    )
    tied = _add_run(
        session,
        profile_name=f"{profile_prefix}_market",
        source_filename="market_products.csv",
        created_at=base_time + timedelta(minutes=1),
        suffix="b",
        product_count=1,
    )
    older = _add_run(
        session,
        profile_name=f"{profile_prefix}_fashion",
        source_filename="old_products.csv",
        created_at=base_time - timedelta(minutes=1),
        suffix="c",
        product_count=0,
    )
    session.commit()
    return session, profile_prefix, newest, tied, older


def test_list_etl_loads_sorts_newest_then_id_and_applies_pagination(seeded_runs):
    from db.etl_query_service import list_etl_loads

    session, profile_prefix, newest, tied, older = seeded_runs

    result = list_etl_loads(
        session,
        limit=2,
        offset=0,
        profile_name=profile_prefix,
    )

    assert [item.etl_load_run_id for item in result.items] == [tied.id, newest.id]
    assert result.total == 3
    assert result.limit == 2
    assert result.offset == 0

    paged = list_etl_loads(
        session,
        limit=2,
        offset=2,
        profile_name=profile_prefix,
    )
    assert [item.etl_load_run_id for item in paged.items] == [older.id]
    assert paged.total == 3


def test_etl_load_search_is_case_insensitive_and_combines_filters(seeded_runs):
    from db.etl_query_service import list_etl_loads

    session, _profile_prefix, newest, _tied, _older = seeded_runs
    assert [
        item.etl_load_run_id
        for item in list_etl_loads(
            session,
            limit=20,
            offset=0,
            filename="VENDOR",
        ).items
    ] == [newest.id]
    assert list_etl_loads(
        session,
        limit=20,
        offset=0,
        filename="vendor",
        profile_name="FASHION",
    ).total == 1


def test_etl_load_search_treats_like_special_characters_as_literals(seeded_runs):
    from db.etl_query_service import list_etl_loads

    session, profile_prefix, newest, tied, older = seeded_runs
    created_at = older.created_at - timedelta(minutes=1)
    percent_run = _add_run(
        session,
        profile_name=f"{profile_prefix}_percent",
        source_filename="literal%file.csv",
        created_at=created_at,
        suffix="d",
    )
    backslash_run = _add_run(
        session,
        profile_name=f"{profile_prefix}_backslash",
        source_filename="literal\\file.csv",
        created_at=created_at,
        suffix="e",
    )
    plain_run = _add_run(
        session,
        profile_name=f"{profile_prefix}_plain",
        source_filename="plain.csv",
        created_at=created_at,
        suffix="f",
    )

    percent_result = list_etl_loads(
        session,
        limit=20,
        offset=0,
        filename="%",
    )
    assert [item.etl_load_run_id for item in percent_result.items] == [percent_run.id]
    assert percent_result.total == 1

    underscore_result = list_etl_loads(
        session,
        limit=20,
        offset=0,
        filename="_",
    )
    assert [item.etl_load_run_id for item in underscore_result.items] == [
        tied.id,
        newest.id,
        older.id,
    ]
    assert underscore_result.total == 3
    assert plain_run.id not in {
        item.etl_load_run_id for item in underscore_result.items
    }

    backslash_result = list_etl_loads(
        session,
        limit=20,
        offset=0,
        filename="\\",
    )
    assert [item.etl_load_run_id for item in backslash_result.items] == [
        backslash_run.id
    ]
    assert backslash_result.total == 1


def test_get_etl_load_detail_paginates_products_without_mixing_batches(seeded_runs):
    from db.etl_query_service import get_etl_load_detail

    session, _profile_prefix, newest, tied, _older = seeded_runs

    detail = get_etl_load_detail(
        session,
        etl_load_run_id=newest.id,
        product_limit=2,
        product_offset=1,
    )

    assert detail is not None
    assert detail.etl_load_run_id == newest.id
    assert detail.products.total == 3
    assert detail.products.limit == 2
    assert detail.products.offset == 1
    assert [product.product_id for product in detail.products.items] == ["SKU-1", "SKU-2"]
    assert detail.products.items[0].sale_price is None
    assert detail.products.items[0].description is None
    assert detail.products.items[0].seller is None

    assert get_etl_load_detail(
        session,
        etl_load_run_id=tied.id,
        product_limit=20,
        product_offset=0,
    ).products.total == 1
    assert get_etl_load_detail(
        session,
        etl_load_run_id=999999,
        product_limit=20,
        product_offset=0,
    ) is None


def test_query_service_does_not_modify_database(seeded_runs):
    from db.etl_query_service import list_etl_loads

    session, profile_prefix, _newest, _tied, _older = seeded_runs
    before = session.scalar(
        select(ETLLoadRun.loaded_rows).where(
            ETLLoadRun.profile_name == f"{profile_prefix}_fashion",
            ETLLoadRun.source_filename == "vendor_products.csv",
        )
    )

    list_etl_loads(session, limit=20, offset=0, profile_name=profile_prefix)

    after = session.scalar(
        select(ETLLoadRun.loaded_rows).where(
            ETLLoadRun.profile_name == f"{profile_prefix}_fashion",
            ETLLoadRun.source_filename == "vendor_products.csv",
        )
    )
    assert after == before
