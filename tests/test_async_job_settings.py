from pathlib import Path


def test_async_job_settings_use_environment_values(monkeypatch) -> None:
    import config.settings as settings

    monkeypatch.setenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    monkeypatch.setenv("REDIS_JOB_URL", "redis://redis:6379/1")
    monkeypatch.setenv("INSPECTION_JOB_DIR", "/shared/inspection-jobs")
    monkeypatch.setenv("INSPECTION_JOB_TTL_SECONDS", "3600")

    assert settings.get_celery_broker_url() == "redis://redis:6379/0"
    assert settings.get_redis_job_url() == "redis://redis:6379/1"
    assert settings.get_inspection_job_dir() == Path("/shared/inspection-jobs")
    assert settings.get_inspection_job_ttl_seconds() == 3600


def test_async_job_ttl_falls_back_for_invalid_values(monkeypatch) -> None:
    import config.settings as settings

    monkeypatch.setenv("INSPECTION_JOB_TTL_SECONDS", "not-a-number")

    assert (
        settings.get_inspection_job_ttl_seconds()
        == settings.DEFAULT_INSPECTION_JOB_TTL_SECONDS
    )
