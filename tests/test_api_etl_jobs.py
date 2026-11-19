from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

from celery.exceptions import Retry
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select

from api.dependencies import get_current_user
from api.main import app
from config.database import get_optional_database_url
from db.models import ETLJob, ETLLoadRun, User
from db.session import create_database_engine, create_session_factory, get_session
from conftest import FakeAuthenticatedUser
from services import etl_job_service
from workers import etl_tasks



PROFILE = "sample_marketplace_vendor_v1"
ENDPOINT = "/api/v1/etl-jobs"
FIXTURE = Path(__file__).parent / "fixtures/e2e/etl_browser_vendor.csv"


@pytest.fixture
def job_api(tmp_path, monkeypatch):
    database_url = get_optional_database_url()
    if database_url is None:
        pytest.skip("PostgreSQL TEST_DATABASE_URL is required for ETL job transactions")

    engine = create_database_engine(database_url)
    factory = create_session_factory(engine)
    test_id = uuid4().hex
    filename = f"async-etl-{test_id}.csv"
    username = f"etl-{test_id}"
    with factory.begin() as session:
        user = User(username=username, role="operator", password_hash="unused")
        session.add(user)
        session.flush()
        actor = FakeAuthenticatedUser(username=username, user_id=user.id)

    def request_session():
        with factory() as session:
            yield session

    monkeypatch.setenv("INSPECTION_JOB_DIR", str(tmp_path))
    monkeypatch.setattr(etl_tasks, "get_session_factory", lambda: factory)
    monkeypatch.setitem(app.dependency_overrides, get_session, request_session)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: actor)
    published = []
    monkeypatch.setattr(etl_job_service, "enqueue_etl_job", published.append)
    upload = (filename, FIXTURE.read_bytes().replace(b"E2E-100", test_id.encode()), "text/csv")
    try:
        with TestClient(app) as client:
            yield client, factory, actor, upload, published
    finally:
        with factory.begin() as session:
            session.execute(delete(ETLJob).where(ETLJob.actor_username == username))
            session.execute(delete(ETLLoadRun).where(ETLLoadRun.actor_username == username))
            session.execute(delete(User).where(User.username == username))
        engine.dispose()


def submit(client, upload, profile=PROFILE):
    return client.post(ENDPOINT, files={"file": upload}, data={"profile_id": profile})


def test_job_validation_and_queue_failure_leave_no_job_or_input(job_api, monkeypatch):
    client, factory, actor, upload, published = job_api
    actor.role = "viewer"
    assert submit(client, upload).status_code == 403
    actor.role = "operator"
    assert submit(client, upload, profile="../unknown").json()["detail"]["code"] == "unsupported_profile"
    for bad in (("supplier.xlsx", upload[1]), ("supplier.csv", b"")):
        response = submit(client, bad)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_upload"
    assert published == []

    def fail_publish(job_id):
        published.append(job_id)
        assert etl_job_service.etl_job_file(job_id).is_file()
        raise OSError("broker failed after an uncertain publish")

    monkeypatch.setattr(etl_job_service, "enqueue_etl_job", fail_publish)
    response = submit(client, upload)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "etl_job_unavailable"
    job_id, = published
    assert client.get(f"{ENDPOINT}/{job_id}").status_code == 404
    assert not list(etl_job_service.etl_job_directory().iterdir())
    # A message delivered despite the publish failure is a no-op.
    etl_tasks.run_web_etl_job.run(str(job_id))
    with factory() as session:
        assert session.get(ETLJob, job_id) is None
        assert session.scalar(select(ETLLoadRun).where(ETLLoadRun.actor_user_id == actor.id)) is None


def test_concurrent_delivery_and_terminal_replay_share_one_result(job_api, monkeypatch):
    client, factory, actor, upload, published = job_api
    response = submit(client, upload)
    assert response.status_code == 202
    url = response.json()["status_url"]
    assert response.headers["location"] == url
    assert client.get(url).json()["status"] == "queued"
    job_id, = published
    assert UUID(response.json()["job_id"]) == job_id

    started, resume = Event(), Event()
    calls = []
    original = etl_tasks.run_web_etl

    def pause_execution(*args, **kwargs):
        calls.append(kwargs["profile_id"])
        started.set()
        assert resume.wait(timeout=15)
        return original(*args, **kwargs)

    monkeypatch.setattr(etl_tasks, "run_web_etl", pause_execution)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(etl_tasks.run_web_etl_job.run, str(job_id))
        try:
            assert started.wait(timeout=10)
            actor.role = "viewer"
            assert client.get(url).json()["status"] == "running"
            duplicate = pool.submit(etl_tasks.run_web_etl_job.run, str(job_id))
        finally:
            resume.set()
        first.result(timeout=15)
        duplicate.result(timeout=15)

    result = client.get(url).json()
    assert result["status"] == "succeeded" and result["created"] is True
    batch_id = result["etl_load_run_id"]
    batch = client.get(f"/api/v1/etl-loads/{batch_id}").json()
    assert batch["etl_load_run_id"] == batch_id
    assert (batch["total_rows"], batch["loaded_rows"], batch["rejected_rows"]) == (4, 2, 2)
    assert not etl_job_service.etl_job_file(job_id).exists()
    etl_tasks.run_web_etl_job.run(str(job_id))
    assert client.get(url).json() == result
    assert calls == [PROFILE]
    with factory() as session:
        assert list(session.scalars(
            select(ETLLoadRun.id).where(ETLLoadRun.actor_user_id == actor.id)
        )) == [batch_id]


def test_interruption_after_loader_commit_rolls_back_batch_and_keeps_input(job_api, monkeypatch):
    client, factory, actor, upload, published = job_api
    response = submit(client, upload)
    assert response.status_code == 202
    job_id, = published
    original = etl_tasks.run_web_etl

    def interrupt_after_load(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated pre-commit interruption")

    with monkeypatch.context() as patch:
        patch.setattr(etl_tasks, "run_web_etl", interrupt_after_load)
        with pytest.raises(Retry):
            etl_tasks.run_web_etl_job.apply(args=(str(job_id),), throw=True)
    assert etl_job_service.etl_job_file(job_id).exists()
    with factory() as session:
        job = session.get(ETLJob, job_id)
        assert job.status == "running" and job.etl_load_run_id is None
        assert session.scalar(select(ETLLoadRun).where(ETLLoadRun.actor_user_id == actor.id)) is None

    etl_tasks.run_web_etl_job.run(str(job_id))
    assert client.get(response.json()["status_url"]).json()["status"] == "succeeded"
    assert not etl_job_service.etl_job_file(job_id).exists()
