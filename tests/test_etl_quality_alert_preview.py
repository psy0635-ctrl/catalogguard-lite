import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.main import app
from conftest import clear_current_user_override, override_current_user
from db.session import get_session


ENDPOINT = "/api/v1/etl-loads/12/quality-alert-preview"


@pytest.fixture()
def preview_client():
    # Minimal SQLite projection of the PostgreSQL table. Omitting the PostgreSQL
    # constraints lets this test exercise corrupt historical values defensively.
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE etl_load_runs (id INTEGER PRIMARY KEY, profile_name TEXT, "
            "total_rows INTEGER, loaded_rows INTEGER, rejected_rows INTEGER, "
            "error_counts TEXT, source_filename TEXT, actor_username TEXT)"
        )
    queries = []

    def override_session():
        with Session(engine) as session:
            yield session

    override_current_user(role="viewer")
    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app), engine, queries
    finally:
        clear_current_user_override()
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


@pytest.mark.parametrize(
    "total,loaded,rejected,error_counts,rate,count,status,codes,display_rate",
    [
        (1000, 920, 80, "{}", "5", None, "ALERT", ["rejection_rate_exceeded"], 8.0),
        (1000, 950, 50, "{}", "5", None, "PASS", [], 5.0),
        (1000, 1000, 0, "{}", "0", 0, "PASS", [], 0.0),
        (1000, 950, 50, "{}", "5", 49, "ALERT", ["rejected_rows_exceeded"], 5.0),
        (1000, 950, 50, "{}", "5.00", 50, "PASS", [], 5.0),
        (1000, 920, 80, "{}", "5", 75, "ALERT",
         ["rejection_rate_exceeded", "rejected_rows_exceeded"], 8.0),
        (None, 50, None, None, "5", None, "INSUFFICIENT_DATA", [], None),
        (0, 0, 0, "{}", "5", None, "INSUFFICIENT_DATA", [], None),
        (100, 90, 20, "{}", "100", None, "INSUFFICIENT_DATA", [], None),
        (100, 101, -1, "{}", "100", None, "INSUFFICIENT_DATA", [], None),
        (100, 95, 5, None, "5", None, "INSUFFICIENT_DATA", [], None),
        (10000, 9498, 502, "{}", "5.01", None, "ALERT", ["rejection_rate_exceeded"], 5.02),
        (19999, 18999, 1000, "{}", "5", None, "ALERT", ["rejection_rate_exceeded"], 5.0),
        (20001, 19001, 1000, "{}", "5", None, "PASS", [], 5.0),
        (1000, 0, 1000, "{}", "100", None, "PASS", [], 100.0),
    ],
)
def test_preview_reads_only_one_summary_and_returns_exact_verdict(
    preview_client, total, loaded, rejected, error_counts, rate, count, status, codes, display_rate,
):
    client, engine, queries = preview_client
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO etl_load_runs VALUES (12, ?, ?, ?, ?, ?, ?, ?)",
            ("synthetic_vendor", total, loaded, rejected, error_counts,
             r"C:\sensitive\synthetic.csv", "synthetic_private_user"),
        )

    def capture_sql(_conn, _cursor, statement, _params, _context, _executemany):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", capture_sql)
    response = client.post(ENDPOINT, json={
        "max_rejection_rate": rate, "max_rejected_rows": count,
    })

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]
    result = response.json()
    assert set(result) == {
        "etl_load_run_id", "profile_name", "total_rows", "loaded_rows",
        "rejected_rows", "rejection_rate", "thresholds", "status",
        "violations", "data_issue",
    }
    assert result["etl_load_run_id"] == 12
    assert result["profile_name"] == "synthetic_vendor"
    assert (result["total_rows"], result["loaded_rows"], result["rejected_rows"]) == (
        total, loaded, rejected,
    )
    assert result["thresholds"] == {"max_rejection_rate": rate, "max_rejected_rows": count}
    assert result["status"] == status
    assert result["rejection_rate"] == display_rate
    assert [violation["code"] for violation in result["violations"]] == codes
    assert all(violation["message"] for violation in result["violations"])
    assert bool(result["data_issue"]) == (status == "INSUFFICIENT_DATA")
    if rate == "5" and rejected == 80:
        assert "3%p" in result["violations"][0]["message"]
    if count is not None and rejected > count:
        assert f"{rejected - count}건" in result["violations"][-1]["message"]
    assert "synthetic_private_user" not in response.text
    assert "synthetic.csv" not in response.text
    assert len(queries) == 1
    assert queries[0].lstrip().startswith("SELECT")
    assert "FROM etl_load_runs" in queries[0]
    assert "source_filename" not in queries[0]
    assert "actor_username" not in queries[0]


@pytest.mark.parametrize("payload", [
    {},
    {"max_rejection_rate": -0.01},
    {"max_rejection_rate": 100.01},
    {"max_rejection_rate": "5.001"},
    {"max_rejection_rate": "NaN"},
    {"max_rejection_rate": True},
    {"max_rejection_rate": 5, "max_rejected_rows": -1},
    {"max_rejection_rate": 5, "max_rejected_rows": 1.5},
    {"max_rejection_rate": 5, "max_rejected_rows": True},
    {"max_rejection_rate": 5, "max_rejected_rows": "1"},
])
def test_preview_rejects_invalid_criteria(preview_client, payload):
    client, _, _ = preview_client
    response = client.post(ENDPOINT, json=payload)
    assert response.status_code == 422
    assert response.headers["X-Request-ID"]
    assert response.json()["detail"][0]["loc"][0] == "body"


def test_preview_returns_404_for_missing_batch(preview_client):
    client, _, _ = preview_client
    response = client.post(ENDPOINT, json={"max_rejection_rate": 5})
    assert response.status_code == 404
    assert response.json()["detail"] == "ETL 적재 배치를 찾을 수 없습니다."


def test_preview_does_not_echo_rejected_input(preview_client):
    client, _, _ = preview_client
    marker = "synthetic-sensitive-input"
    response = client.post(ENDPOINT, json={
        "max_rejection_rate": marker,
        marker: marker,
    })
    assert response.status_code == 422
    assert marker not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "max_rejection_rate"]
    assert response.headers["X-Request-ID"]


def test_preview_requires_authentication(preview_client):
    client, _, _ = preview_client
    clear_current_user_override()
    response = client.post(ENDPOINT, json={"max_rejection_rate": 5})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_preview_rejects_roles_outside_the_existing_read_policy(preview_client):
    client, _, _ = preview_client
    override_current_user(role="unsupported")
    response = client.post(ENDPOINT, json={"max_rejection_rate": 5})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"
