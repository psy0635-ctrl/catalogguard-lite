# 역할: POST /api/v1/inspections가 monkeypatch 없이 실제 PostgreSQL Session으로
# 신규 CSV를 저장하고, 동일 CSV를 재사용하며, 저장 실패 시 전체 rollback되는지 검증합니다.
#
# 기존 tests/test_api_inspections.py는 find_existing_inspection_run/save_inspection_report를
# 전부 monkeypatch하므로, route가 같은 요청 범위 Session을 두 번 건드리면서 생기는
# "A transaction is already begun on this Session" 회귀를 잡지 못했습니다. 이 파일은
# 실제 Session/실제 persistence_service를 그대로 사용해 그 상호작용을 검증합니다.
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from api.main import app
from config.database import get_optional_database_url
from core.security import create_access_token
from db import persistence_service
from db.auth_service import create_user
from db.models import InspectionResult, InspectionRun, User
from db.session import create_database_engine, create_session_factory


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_JWT_SECRET", "test-only-secret-value")


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


def _unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _cleanup_users(session_factory, usernames: list[str]) -> None:
    if not usernames:
        return
    with session_factory() as cleanup:
        cleanup.execute(delete(User).where(User.username.in_(usernames)))
        cleanup.commit()


def _cleanup_inspection_runs(session_factory, source_filenames: list[str]) -> None:
    if not source_filenames:
        return
    with session_factory() as cleanup:
        # InspectionResult는 inspection_runs FK가 ondelete="CASCADE"라 run만 지우면 함께 삭제됩니다.
        cleanup.execute(
            delete(InspectionRun).where(
                InspectionRun.source_filename.in_(source_filenames)
            )
        )
        cleanup.commit()


@pytest.fixture()
def operator_token(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("txn_operator")
    create_user(session, username=username, password="synthetic-pw-txn-1", role="operator")
    token, _ = create_access_token(subject=username, role="operator")
    try:
        yield token
    finally:
        _cleanup_users(session_factory, [username])


@pytest.fixture()
def viewer_token(postgres_session):
    session, session_factory = postgres_session
    username = _unique_username("txn_viewer")
    create_user(session, username=username, password="synthetic-pw-txn-2", role="viewer")
    token, _ = create_access_token(subject=username, role="viewer")
    try:
        yield token
    finally:
        _cleanup_users(session_factory, [username])


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _build_valid_csv(marker: str) -> bytes:
    # price=0은 기존 검수 규칙에서 "가격 오류"로 판정되어 InspectionResult가 1건 생성됩니다.
    # (tests/test_inspection_persistence.py의 BASE_ROW 변형과 동일한 방식)
    # inspection_run만 저장되고 inspection_results는 비어 있는 상태를 회귀로 오인하지
    # 않도록, 결과가 반드시 1건 이상 생기는 CSV를 사용합니다.
    header = "product_group_id,product_id,product_name,category,color,size,stock,price,image_path\n"
    row = f"G-{marker},P-{marker},Transaction Regression Product,TOP,BLACK,M,5,0,https://example.test/{marker}.jpg\n"
    return (header + row).encode("utf-8")


def _post_csv(token: str, csv_bytes: bytes, *, filename: str):
    return client.post(
        "/api/v1/inspections",
        headers=_auth_headers(token),
        files={"file": (filename, csv_bytes, "text/csv")},
    )


def _count_runs(session_factory, *, source_filename: str) -> int:
    with session_factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(InspectionRun)
                .where(InspectionRun.source_filename == source_filename)
            )
            or 0
        )


def _count_results(session_factory, *, inspection_run_id: int) -> int:
    with session_factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(InspectionResult)
                .where(InspectionResult.inspection_run_id == inspection_run_id)
            )
            or 0
        )


def test_operator_can_save_new_csv_without_transaction_error(
    postgres_session, operator_token
):
    # 회귀 확인 전: 이 요청은 route의 사전 중복조회와 save_inspection_report가 같은
    # request-scoped Session을 공유해 "A transaction is already begun on this Session"로
    # 500이 발생했습니다. 별도 Session으로 분리한 뒤에는 정상 200을 반환해야 합니다.
    _, session_factory = postgres_session
    marker = uuid4().hex
    filename = f"txn_regression_new_{marker}.csv"
    csv_bytes = _build_valid_csv(marker)

    try:
        response = _post_csv(operator_token, csv_bytes, filename=filename)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] is True
        run_id = body["inspection_run_id"]
        assert isinstance(run_id, int)

        # 응답을 만든 Session이 아니라 완전히 새 Session/커넥션으로 다시 조회해
        # 실제로 commit됐는지 확인합니다(같은 Session의 identity map만 보고 판단하지 않음).
        assert _count_runs(session_factory, source_filename=filename) == 1
        assert _count_results(session_factory, inspection_run_id=run_id) == 1
    finally:
        _cleanup_inspection_runs(session_factory, [filename])


def test_operator_duplicate_csv_reuses_existing_run_without_new_rows(
    postgres_session, operator_token
):
    _, session_factory = postgres_session
    marker = uuid4().hex
    filename = f"txn_regression_dup_{marker}.csv"
    csv_bytes = _build_valid_csv(marker)

    try:
        first_response = _post_csv(operator_token, csv_bytes, filename=filename)
        assert first_response.status_code == 200, first_response.text
        first_body = first_response.json()
        assert first_body["created"] is True
        run_id = first_body["inspection_run_id"]

        second_response = _post_csv(operator_token, csv_bytes, filename=filename)
        assert second_response.status_code == 200, second_response.text
        second_body = second_response.json()

        assert second_body["created"] is False
        assert second_body["inspection_run_id"] == run_id
        # 동일 CSV/버전이면 새 row가 생기지 않고 기존 run 하나만 남아야 합니다.
        assert _count_runs(session_factory, source_filename=filename) == 1
        assert _count_results(session_factory, inspection_run_id=run_id) == 1
    finally:
        _cleanup_inspection_runs(session_factory, [filename])


def test_operator_save_failure_rolls_back_run_and_results(
    postgres_session, operator_token, monkeypatch
):
    # 상세 결과 저장 중 실패를 강제로 만들어, run만 남는 부분 저장이 없는지 확인합니다.
    # (tests/test_inspection_persistence.py의 동일 패턴을 HTTP 경로에도 적용)
    _, session_factory = postgres_session
    marker = uuid4().hex
    filename = f"txn_regression_fail_{marker}.csv"
    csv_bytes = _build_valid_csv(marker)

    def failing_create_inspection_results(session, *, inspection_run_id, result_items):
        raise RuntimeError("forced result insert failure for regression test")

    monkeypatch.setattr(
        persistence_service.repositories,
        "create_inspection_results",
        failing_create_inspection_results,
    )

    try:
        response = _post_csv(operator_token, csv_bytes, filename=filename)

        assert response.status_code == 500
        # 부분 저장이 없어야 합니다: run과 results 둘 다 0건.
        assert _count_runs(session_factory, source_filename=filename) == 0
    finally:
        _cleanup_inspection_runs(session_factory, [filename])


def test_anonymous_new_csv_post_returns_401():
    marker = uuid4().hex
    csv_bytes = _build_valid_csv(marker)

    response = client.post(
        "/api/v1/inspections",
        files={"file": (f"txn_anon_{marker}.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 401


def test_viewer_new_csv_post_returns_403(viewer_token):
    marker = uuid4().hex
    csv_bytes = _build_valid_csv(marker)

    response = _post_csv(viewer_token, csv_bytes, filename=f"txn_viewer_{marker}.csv")

    assert response.status_code == 403
