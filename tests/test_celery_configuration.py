from inspect import signature


def test_celery_uses_json_and_task_only_accepts_job_metadata() -> None:
    from workers.celery_app import celery_app
    from workers.inspection_tasks import inspect_csv_task

    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.task_ignore_result is True
    assert list(signature(inspect_csv_task.run).parameters) == [
        "job_id",
        "job_file_path",
    ]
