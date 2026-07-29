from __future__ import annotations

import hashlib
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event, Lock
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, func, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from config.database import get_optional_database_url
from db.catalog_promotion_preview_service import preview_catalog_promotion
from db.catalog_promotion_service import (
    CatalogPromotionExecutionFailedError,
    CatalogPromotionExecutionResult,
    execute_catalog_promotion,
)
from db.models import (
    CatalogProduct,
    CatalogProductChange,
    CatalogProductStaging,
    CatalogPromotionRun,
    ETLLoadRun,
    ETLRejectedRow,
    InspectionResult,
    InspectionRun,
)
from db.session import create_database_engine, create_session_factory


EVENT_TIMEOUT_SECONDS = 10
FUTURE_TIMEOUT_SECONDS = 20
BLOCKING_DEADLINE_SECONDS = 10
POLL_INTERVAL_SECONDS = 0.05
SAFE_FAILURE_MESSAGE = "운영 상품 반영 중 오류가 발생했습니다."
SENSITIVE_ERROR_FRAGMENTS = (
    "postgresql://",
    "select",
    "insert into",
    "password",
    "traceback",
)


@dataclass
class WorkerState:
    ready: Event = field(default_factory=Event)
    backend_pid: int | None = None
    setup_error: Exception | None = None


@dataclass(frozen=True)
class WorkerOutcome:
    backend_pid: int
    result: CatalogPromotionExecutionResult | None = None
    error: CatalogPromotionExecutionFailedError | None = None


class FirstCallPause:
    def __init__(self):
        self.entered = Event()
        self.release = Event()
        self.timed_out = Event()
        self._claim_lock = Lock()
        self._claimed = False

    def pause_if_first(self) -> None:
        with self._claim_lock:
            should_pause = not self._claimed
            if should_pause:
                self._claimed = True

        if not should_pause:
            return

        self.entered.set()
        if not self.release.wait(timeout=EVENT_TIMEOUT_SECONDS):
            self.timed_out.set()
            raise RuntimeError("Timed out waiting to release the first worker.")


@pytest.fixture()
def postgres_concurrency():
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip(
            "TEST_DATABASE_URL이 없어 PostgreSQL concurrency 테스트를 실행하지 않음"
        )

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    profile_name = f"promotion_concurrency_{uuid4().hex}"

    with engine.connect() as connection:
        database_name = connection.scalar(text("SELECT current_database()"))
    if "test" not in str(database_name).lower():
        engine.dispose()
        pytest.fail(
            "PostgreSQL concurrency tests require a database whose name contains 'test'."
        )

    try:
        yield engine, session_factory, profile_name
    finally:
        with session_factory() as cleanup:
            load_run_ids = list(
                cleanup.scalars(
                    select(ETLLoadRun.id).where(
                        ETLLoadRun.profile_name == profile_name
                    )
                )
            )
            promotion_run_ids = list(
                cleanup.scalars(
                    select(CatalogPromotionRun.id).where(
                        CatalogPromotionRun.etl_load_run_id.in_(load_run_ids)
                    )
                )
            )
            catalog_product_ids = list(
                cleanup.scalars(
                    select(CatalogProduct.id).where(
                        or_(
                            CatalogProduct.source_etl_load_run_id.in_(
                                load_run_ids
                            ),
                            CatalogProduct.supplier_key == profile_name,
                        )
                    )
                )
            )
            cleanup.execute(
                delete(CatalogProductChange).where(
                    or_(
                        CatalogProductChange.promotion_run_id.in_(
                            promotion_run_ids
                        ),
                        CatalogProductChange.catalog_product_id.in_(
                            catalog_product_ids
                        ),
                    )
                )
            )
            cleanup.execute(
                delete(CatalogPromotionRun).where(
                    CatalogPromotionRun.id.in_(promotion_run_ids)
                )
            )
            cleanup.execute(
                delete(CatalogProduct).where(
                    CatalogProduct.id.in_(catalog_product_ids)
                )
            )
            cleanup.execute(
                delete(CatalogProductStaging).where(
                    CatalogProductStaging.etl_load_run_id.in_(load_run_ids)
                )
            )
            cleanup.execute(
                delete(ETLRejectedRow).where(
                    ETLRejectedRow.etl_load_run_id.in_(load_run_ids)
                )
            )
            cleanup.execute(
                delete(ETLLoadRun).where(ETLLoadRun.id.in_(load_run_ids))
            )
            cleanup.commit()

            assert cleanup.scalar(
                select(func.count())
                .select_from(ETLLoadRun)
                .where(ETLLoadRun.profile_name == profile_name)
            ) == 0
            assert cleanup.scalar(
                select(func.count())
                .select_from(CatalogProduct)
                .where(CatalogProduct.supplier_key == profile_name)
            ) == 0
            assert cleanup.scalar(
                select(func.count())
                .select_from(CatalogPromotionRun)
                .where(CatalogPromotionRun.id.in_(promotion_run_ids))
            ) == 0
            assert cleanup.scalar(
                select(func.count())
                .select_from(CatalogProductChange)
                .where(
                    or_(
                        CatalogProductChange.promotion_run_id.in_(
                            promotion_run_ids
                        ),
                        CatalogProductChange.catalog_product_id.in_(
                            catalog_product_ids
                        ),
                    )
                )
            ) == 0
            assert cleanup.scalar(
                select(func.count())
                .select_from(CatalogProductStaging)
                .where(
                    CatalogProductStaging.etl_load_run_id.in_(load_run_ids)
                )
            ) == 0
            assert cleanup.scalar(
                select(func.count())
                .select_from(ETLRejectedRow)
                .where(ETLRejectedRow.etl_load_run_id.in_(load_run_ids))
            ) == 0
        engine.dispose()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _staging_values(product_id: str, **changes) -> dict[str, object]:
    values: dict[str, object] = {
        "product_group_id": f"G-{product_id}",
        "product_id": product_id,
        "product_name": f"Product {product_id}",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 10,
        "price": 10000,
        "sale_price": None,
        "image_path": f"{product_id}.jpg",
        "description": None,
        "seller": None,
    }
    values.update(changes)
    return values


def _create_load_run(
    session: Session,
    *,
    profile_name: str,
    marker: str,
    products: list[dict[str, object]],
) -> int:
    load_run = ETLLoadRun(
        source_filename=f"{marker}.csv",
        profile_name=profile_name,
        profile_version="1",
        input_file_sha256=_sha256(f"{profile_name}:{marker}:input"),
        output_file_sha256=_sha256(f"{profile_name}:{marker}:output"),
        loaded_rows=len(products),
        total_rows=len(products),
        rejected_rows=0,
        error_counts={},
    )
    session.add(load_run)
    session.flush()
    session.add_all(
        [
            CatalogProductStaging(
                etl_load_run_id=load_run.id,
                **product,
            )
            for product in products
        ]
    )
    session.commit()
    return load_run.id


def _create_catalog_product(
    session: Session,
    *,
    profile_name: str,
    source_load_run_id: int,
    product_id: str,
    **changes,
) -> int:
    values = _staging_values(product_id, **changes)
    external_product_id = str(values.pop("product_id"))
    product = CatalogProduct(
        supplier_key=profile_name,
        external_product_id=external_product_id,
        source_etl_load_run_id=source_load_run_id,
        **values,
    )
    session.add(product)
    session.commit()
    return product.id


def _preview_hash(
    session_factory: sessionmaker[Session],
    load_run_id: int,
) -> str:
    with session_factory() as session:
        preview = preview_catalog_promotion(
            session,
            etl_load_run_id=load_run_id,
        )
        assert preview.promotion_eligible is True
        assert preview.preview_hash is not None
        session.rollback()
        return preview.preview_hash


def _configure_worker_connection(
    connection,
    *,
    application_name: str,
) -> int:
    connection.execute(
        text("SELECT set_config('application_name', :name, false)"),
        {"name": application_name},
    )
    connection.exec_driver_sql("SET lock_timeout = '5s'")
    connection.exec_driver_sql("SET statement_timeout = '15s'")
    connection.exec_driver_sql(
        "SET idle_in_transaction_session_timeout = '15s'"
    )
    backend_pid = connection.scalar(text("SELECT pg_backend_pid()"))
    connection.commit()
    return int(backend_pid)


def _run_worker(
    *,
    engine: Engine,
    session_factory: sessionmaker[Session],
    state: WorkerState,
    application_name: str,
    load_run_id: int,
    expected_preview_hash: str,
) -> WorkerOutcome:
    try:
        with engine.connect() as connection:
            backend_pid = _configure_worker_connection(
                connection,
                application_name=application_name,
            )
            state.backend_pid = backend_pid
            state.ready.set()
            with session_factory(bind=connection) as session:
                try:
                    result = execute_catalog_promotion(
                        session,
                        etl_load_run_id=load_run_id,
                        confirmation=True,
                        expected_preview_hash=expected_preview_hash,
                    )
                except CatalogPromotionExecutionFailedError as error:
                    return WorkerOutcome(
                        backend_pid=backend_pid,
                        error=error,
                    )
                return WorkerOutcome(
                    backend_pid=backend_pid,
                    result=result,
                )
    except Exception as error:
        state.setup_error = error
        state.ready.set()
        raise


def _wait_for_worker_ready(state: WorkerState, *, label: str) -> int:
    assert state.ready.wait(timeout=EVENT_TIMEOUT_SECONDS), (
        f"{label} did not establish its dedicated PostgreSQL connection "
        f"within {EVENT_TIMEOUT_SECONDS} seconds."
    )
    assert state.setup_error is None, (
        f"{label} setup failed with "
        f"{type(state.setup_error).__name__}."
    )
    assert state.backend_pid is not None
    return state.backend_pid


def _wait_for_blocker(
    engine: Engine,
    *,
    waiting_pid: int,
    expected_blocker_pid: int,
) -> tuple[int, ...]:
    deadline = monotonic() + BLOCKING_DEADLINE_SECONDS
    poll_wait = Event()
    last_blockers: tuple[int, ...] = ()
    with engine.connect() as observer:
        observer.exec_driver_sql("SET statement_timeout = '5s'")
        observer.commit()
        while monotonic() < deadline:
            blocker_values = observer.scalar(
                text("SELECT pg_blocking_pids(:waiting_pid)"),
                {"waiting_pid": waiting_pid},
            )
            last_blockers = tuple(int(pid) for pid in blocker_values)
            if expected_blocker_pid in last_blockers:
                return last_blockers
            poll_wait.wait(timeout=POLL_INTERVAL_SECONDS)

    raise AssertionError(
        f"Backend {waiting_pid} was not blocked by backend "
        f"{expected_blocker_pid} within {BLOCKING_DEADLINE_SECONDS} seconds; "
        f"last blockers were {last_blockers}."
    )


def _run_observed_pair(
    *,
    engine: Engine,
    session_factory: sessionmaker[Session],
    pause: FirstCallPause,
    first_load_run_id: int,
    first_hash: str,
    second_load_run_id: int,
    second_hash: str,
    application_prefix: str,
) -> tuple[WorkerOutcome, WorkerOutcome, tuple[int, ...]]:
    first_state = WorkerState()
    second_state = WorkerState()
    executor = ThreadPoolExecutor(
        max_workers=2,
        thread_name_prefix=application_prefix,
    )
    first_future: Future[WorkerOutcome] | None = None
    second_future: Future[WorkerOutcome] | None = None
    try:
        first_future = executor.submit(
            _run_worker,
            engine=engine,
            session_factory=session_factory,
            state=first_state,
            application_name=f"{application_prefix}_first",
            load_run_id=first_load_run_id,
            expected_preview_hash=first_hash,
        )
        first_pid = _wait_for_worker_ready(first_state, label="first worker")
        assert pause.entered.wait(timeout=EVENT_TIMEOUT_SECONDS), (
            "The first worker did not reach the deterministic pause point "
            f"within {EVENT_TIMEOUT_SECONDS} seconds."
        )

        second_future = executor.submit(
            _run_worker,
            engine=engine,
            session_factory=session_factory,
            state=second_state,
            application_name=f"{application_prefix}_second",
            load_run_id=second_load_run_id,
            expected_preview_hash=second_hash,
        )
        second_pid = _wait_for_worker_ready(second_state, label="second worker")
        assert first_pid != second_pid
        blockers = _wait_for_blocker(
            engine,
            waiting_pid=second_pid,
            expected_blocker_pid=first_pid,
        )
        pause.release.set()
        first_outcome = first_future.result(timeout=FUTURE_TIMEOUT_SECONDS)
        second_outcome = second_future.result(timeout=FUTURE_TIMEOUT_SECONDS)
        assert not pause.timed_out.is_set(), (
            "The first worker timed out while waiting for the test to release it."
        )
        return first_outcome, second_outcome, blockers
    finally:
        pause.release.set()
        executor.shutdown(wait=True, cancel_futures=True)


def _status_counts(
    session: Session,
    load_run_ids: list[int],
) -> dict[str, int]:
    rows = session.execute(
        select(CatalogPromotionRun.status, func.count())
        .where(CatalogPromotionRun.etl_load_run_id.in_(load_run_ids))
        .group_by(CatalogPromotionRun.status)
    )
    return {status: count for status, count in rows}


def _inspection_counts(session: Session) -> tuple[int, int]:
    return (
        session.scalar(select(func.count()).select_from(InspectionRun)),
        session.scalar(select(func.count()).select_from(InspectionResult)),
    )


def test_same_batch_concurrent_requests_wait_on_etl_lock_and_reuse_success(
    postgres_concurrency,
    monkeypatch,
):
    import db.catalog_promotion_service as promotion_service

    engine, session_factory, profile_name = postgres_concurrency
    with session_factory() as setup:
        load_run_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="same-batch",
            products=[_staging_values("P001")],
        )
        inspection_counts_before = _inspection_counts(setup)
    expected_hash = _preview_hash(session_factory, load_run_id)

    pause = FirstCallPause()
    original_insert = promotion_service._insert_catalog_product

    def pause_first_insert(*args, **kwargs):
        pause.pause_if_first()
        return original_insert(*args, **kwargs)

    monkeypatch.setattr(
        promotion_service,
        "_insert_catalog_product",
        pause_first_insert,
    )

    first, second, blockers = _run_observed_pair(
        engine=engine,
        session_factory=session_factory,
        pause=pause,
        first_load_run_id=load_run_id,
        first_hash=expected_hash,
        second_load_run_id=load_run_id,
        second_hash=expected_hash,
        application_prefix="catalogguard_same_batch",
    )

    assert first.backend_pid in blockers
    assert first.result is not None
    assert second.result is not None
    assert first.error is None
    assert second.error is None
    assert first.result.status == "succeeded"
    assert second.result.status == "succeeded"
    assert first.result.created is True
    assert second.result.created is False
    assert first.result.promotion_run_id == second.result.promotion_run_id
    assert first.result.preview_hash == second.result.preview_hash == expected_hash
    assert (
        first.result.inserted_count,
        first.result.updated_count,
        first.result.unchanged_count,
    ) == (1, 0, 0)
    assert (
        second.result.inserted_count,
        second.result.updated_count,
        second.result.unchanged_count,
    ) == (1, 0, 0)

    with session_factory() as verify:
        assert _status_counts(verify, [load_run_id]) == {"succeeded": 1}
        products = list(
            verify.scalars(
                select(CatalogProduct).where(
                    CatalogProduct.supplier_key == profile_name
                )
            )
        )
        assert len(products) == 1
        changes = list(
            verify.scalars(
                select(CatalogProductChange).where(
                    CatalogProductChange.promotion_run_id
                    == first.result.promotion_run_id
                )
            )
        )
        assert len(changes) == 1
        assert changes[0].action == "insert"
        identity_counts = list(
            verify.execute(
                select(
                    CatalogProduct.supplier_key,
                    CatalogProduct.external_product_id,
                    func.count(),
                )
                .where(CatalogProduct.supplier_key == profile_name)
                .group_by(
                    CatalogProduct.supplier_key,
                    CatalogProduct.external_product_id,
                )
            )
        )
        assert identity_counts == [(profile_name, "P001", 1)]
        staging = verify.scalar(
            select(CatalogProductStaging).where(
                CatalogProductStaging.etl_load_run_id == load_run_id
            )
        )
        assert (staging.product_id, staging.price, staging.stock) == (
            "P001",
            10000,
            10,
        )
        load_run = verify.get(ETLLoadRun, load_run_id)
        assert (
            load_run.loaded_rows,
            load_run.total_rows,
            load_run.rejected_rows,
            load_run.error_counts,
        ) == (1, 1, 0, {})
        assert _inspection_counts(verify) == inspection_counts_before


def test_different_batches_wait_on_catalog_lock_and_loser_becomes_stale(
    postgres_concurrency,
    monkeypatch,
):
    import db.catalog_promotion_service as promotion_service

    engine, session_factory, profile_name = postgres_concurrency
    with session_factory() as setup:
        source_load_run_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="update-source",
            products=[],
        )
        product_id = _create_catalog_product(
            setup,
            profile_name=profile_name,
            source_load_run_id=source_load_run_id,
            product_id="P001",
            price=10000,
        )
        batch_a_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="update-a",
            products=[
                _staging_values(
                    "P001",
                    price=20000,
                    description="batch-a",
                )
            ],
        )
        batch_b_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="update-b",
            products=[
                _staging_values(
                    "P001",
                    price=30000,
                    description="batch-b",
                )
            ],
        )
        inspection_counts_before = _inspection_counts(setup)

    batch_a_hash = _preview_hash(session_factory, batch_a_id)
    batch_b_hash = _preview_hash(session_factory, batch_b_id)
    pause = FirstCallPause()
    original_update = promotion_service._update_catalog_product

    def pause_first_update(*args, **kwargs):
        pause.pause_if_first()
        return original_update(*args, **kwargs)

    monkeypatch.setattr(
        promotion_service,
        "_update_catalog_product",
        pause_first_update,
    )

    winner, loser, blockers = _run_observed_pair(
        engine=engine,
        session_factory=session_factory,
        pause=pause,
        first_load_run_id=batch_a_id,
        first_hash=batch_a_hash,
        second_load_run_id=batch_b_id,
        second_hash=batch_b_hash,
        application_prefix="catalogguard_same_identity_update",
    )

    assert winner.backend_pid in blockers
    assert winner.result is not None
    assert winner.error is None
    assert winner.result.status == "succeeded"
    assert winner.result.created is True
    assert winner.result.updated_count == 1
    assert loser.result is not None
    assert loser.error is None
    assert loser.result.status == "blocked"
    assert loser.result.created is True
    assert loser.result.failure_code == "preview_stale"

    with session_factory() as verify:
        product = verify.get(CatalogProduct, product_id)
        assert (
            product.supplier_key,
            product.external_product_id,
            product.price,
            product.description,
            product.source_etl_load_run_id,
        ) == (
            profile_name,
            "P001",
            20000,
            "batch-a",
            batch_a_id,
        )
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProduct)
            .where(CatalogProduct.supplier_key == profile_name)
        ) == 1
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(
                CatalogProductChange.promotion_run_id
                == winner.result.promotion_run_id,
                CatalogProductChange.action == "update",
            )
        ) == 1
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(
                CatalogProductChange.promotion_run_id
                == loser.result.promotion_run_id
            )
        ) == 0
        assert _status_counts(
            verify,
            [batch_a_id, batch_b_id],
        ) == {
            "blocked": 1,
            "succeeded": 1,
        }
        staging_rows = list(
            verify.execute(
                select(
                    CatalogProductStaging.etl_load_run_id,
                    CatalogProductStaging.price,
                    CatalogProductStaging.description,
                )
                .where(
                    CatalogProductStaging.etl_load_run_id.in_(
                        [batch_a_id, batch_b_id]
                    )
                )
                .order_by(CatalogProductStaging.etl_load_run_id)
            )
        )
        assert staging_rows == [
            (batch_a_id, 20000, "batch-a"),
            (batch_b_id, 30000, "batch-b"),
        ]
        for load_run_id in (batch_a_id, batch_b_id):
            load_run = verify.get(ETLLoadRun, load_run_id)
            assert (
                load_run.loaded_rows,
                load_run.total_rows,
                load_run.rejected_rows,
                load_run.error_counts,
            ) == (1, 1, 0, {})
        assert _inspection_counts(verify) == inspection_counts_before


def test_different_batches_same_new_identity_wait_and_loser_fails_safely(
    postgres_concurrency,
    monkeypatch,
):
    import db.catalog_promotion_service as promotion_service

    engine, session_factory, profile_name = postgres_concurrency
    with session_factory() as setup:
        batch_a_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="insert-a",
            products=[
                _staging_values(
                    "P001",
                    product_name="Product from A",
                    price=20000,
                    description="batch-a",
                )
            ],
        )
        batch_b_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="insert-b",
            products=[
                _staging_values(
                    "P001",
                    product_name="Product from B",
                    price=30000,
                    description="batch-b",
                )
            ],
        )
        inspection_counts_before = _inspection_counts(setup)

    batch_a_hash = _preview_hash(session_factory, batch_a_id)
    batch_b_hash = _preview_hash(session_factory, batch_b_id)
    pause = FirstCallPause()
    original_create_change = promotion_service._create_catalog_product_change

    def pause_first_insert_audit(*args, **kwargs):
        pause.pause_if_first()
        return original_create_change(*args, **kwargs)

    monkeypatch.setattr(
        promotion_service,
        "_create_catalog_product_change",
        pause_first_insert_audit,
    )

    winner, loser, blockers = _run_observed_pair(
        engine=engine,
        session_factory=session_factory,
        pause=pause,
        first_load_run_id=batch_a_id,
        first_hash=batch_a_hash,
        second_load_run_id=batch_b_id,
        second_hash=batch_b_hash,
        application_prefix="catalogguard_same_identity_insert",
    )

    assert winner.backend_pid in blockers
    assert winner.result is not None
    assert winner.error is None
    assert winner.result.status == "succeeded"
    assert winner.result.created is True
    assert winner.result.inserted_count == 1
    assert loser.result is None
    assert loser.error is not None
    assert loser.error.promotion_run_id is not None
    assert str(loser.error) == SAFE_FAILURE_MESSAGE
    loser_error_text = str(loser.error).lower()
    assert all(
        fragment not in loser_error_text
        for fragment in SENSITIVE_ERROR_FRAGMENTS
    )

    with session_factory() as verify:
        product = verify.scalar(
            select(CatalogProduct).where(
                CatalogProduct.supplier_key == profile_name,
                CatalogProduct.external_product_id == "P001",
            )
        )
        assert (
            product.product_name,
            product.price,
            product.description,
            product.source_etl_load_run_id,
        ) == (
            "Product from A",
            20000,
            "batch-a",
            batch_a_id,
        )
        identity_counts = list(
            verify.execute(
                select(
                    CatalogProduct.supplier_key,
                    CatalogProduct.external_product_id,
                    func.count(),
                )
                .where(CatalogProduct.supplier_key == profile_name)
                .group_by(
                    CatalogProduct.supplier_key,
                    CatalogProduct.external_product_id,
                )
            )
        )
        assert identity_counts == [(profile_name, "P001", 1)]
        changes = list(
            verify.scalars(
                select(CatalogProductChange).where(
                    CatalogProductChange.catalog_product_id == product.id
                )
            )
        )
        assert len(changes) == 1
        assert changes[0].action == "insert"
        assert changes[0].promotion_run_id == winner.result.promotion_run_id

        failed_run = verify.get(
            CatalogPromotionRun,
            loser.error.promotion_run_id,
        )
        assert failed_run.etl_load_run_id == batch_b_id
        assert failed_run.status == "failed"
        assert failed_run.failure_code == "promotion_apply_failed"
        assert failed_run.safe_failure_message == SAFE_FAILURE_MESSAGE
        failed_message = failed_run.safe_failure_message.lower()
        assert all(
            fragment not in failed_message
            for fragment in SENSITIVE_ERROR_FRAGMENTS
        )
        assert _status_counts(
            verify,
            [batch_a_id, batch_b_id],
        ) == {
            "failed": 1,
            "succeeded": 1,
        }
        staging_rows = list(
            verify.execute(
                select(
                    CatalogProductStaging.etl_load_run_id,
                    CatalogProductStaging.product_name,
                    CatalogProductStaging.price,
                )
                .where(
                    CatalogProductStaging.etl_load_run_id.in_(
                        [batch_a_id, batch_b_id]
                    )
                )
                .order_by(CatalogProductStaging.etl_load_run_id)
            )
        )
        assert staging_rows == [
            (batch_a_id, "Product from A", 20000),
            (batch_b_id, "Product from B", 30000),
        ]
        for load_run_id in (batch_a_id, batch_b_id):
            load_run = verify.get(ETLLoadRun, load_run_id)
            assert (
                load_run.loaded_rows,
                load_run.total_rows,
                load_run.rejected_rows,
                load_run.error_counts,
            ) == (1, 1, 0, {})
        assert _inspection_counts(verify) == inspection_counts_before


def test_reverse_staging_order_avoids_deadlock_and_winner_updates_both_products(
    postgres_concurrency,
    monkeypatch,
):
    import db.catalog_promotion_service as promotion_service

    engine, session_factory, profile_name = postgres_concurrency
    with session_factory() as setup:
        source_load_run_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="reverse-source",
            products=[],
        )
        product_ids = [
            _create_catalog_product(
                setup,
                profile_name=profile_name,
                source_load_run_id=source_load_run_id,
                product_id=product_id,
                price=10000,
            )
            for product_id in ("P001", "P002")
        ]
        batch_a_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="reverse-a",
            products=[
                _staging_values(
                    "P001",
                    price=21000,
                    description="batch-a",
                ),
                _staging_values(
                    "P002",
                    price=22000,
                    description="batch-a",
                ),
            ],
        )
        batch_b_id = _create_load_run(
            setup,
            profile_name=profile_name,
            marker="reverse-b",
            products=[
                _staging_values(
                    "P002",
                    price=32000,
                    description="batch-b",
                ),
                _staging_values(
                    "P001",
                    price=31000,
                    description="batch-b",
                ),
            ],
        )
        inspection_counts_before = _inspection_counts(setup)

    batch_a_hash = _preview_hash(session_factory, batch_a_id)
    batch_b_hash = _preview_hash(session_factory, batch_b_id)
    pause = FirstCallPause()
    original_update = promotion_service._update_catalog_product

    def pause_first_update(*args, **kwargs):
        pause.pause_if_first()
        return original_update(*args, **kwargs)

    monkeypatch.setattr(
        promotion_service,
        "_update_catalog_product",
        pause_first_update,
    )

    winner, loser, blockers = _run_observed_pair(
        engine=engine,
        session_factory=session_factory,
        pause=pause,
        first_load_run_id=batch_a_id,
        first_hash=batch_a_hash,
        second_load_run_id=batch_b_id,
        second_hash=batch_b_hash,
        application_prefix="catalogguard_reverse_identity_update",
    )

    assert winner.backend_pid in blockers
    assert winner.result is not None
    assert winner.error is None
    assert winner.result.status == "succeeded"
    assert winner.result.updated_count == 2
    assert loser.result is not None
    assert loser.error is None
    assert loser.result.status == "blocked"
    assert loser.result.failure_code == "preview_stale"

    with session_factory() as verify:
        products = list(
            verify.scalars(
                select(CatalogProduct)
                .where(CatalogProduct.id.in_(product_ids))
                .order_by(CatalogProduct.external_product_id)
            )
        )
        assert [
            (
                product.external_product_id,
                product.price,
                product.description,
                product.source_etl_load_run_id,
            )
            for product in products
        ] == [
            ("P001", 21000, "batch-a", batch_a_id),
            ("P002", 22000, "batch-a", batch_a_id),
        ]
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(
                CatalogProductChange.promotion_run_id
                == winner.result.promotion_run_id,
                CatalogProductChange.action == "update",
            )
        ) == 2
        assert verify.scalar(
            select(func.count())
            .select_from(CatalogProductChange)
            .where(
                CatalogProductChange.promotion_run_id
                == loser.result.promotion_run_id
            )
        ) == 0
        assert _status_counts(
            verify,
            [batch_a_id, batch_b_id],
        ) == {
            "blocked": 1,
            "succeeded": 1,
        }
        assert _inspection_counts(verify) == inspection_counts_before
