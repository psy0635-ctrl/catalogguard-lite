from pathlib import Path


def test_job_file_is_server_named_and_removed_after_cleanup(tmp_path, monkeypatch) -> None:
    import services.job_files as job_files

    monkeypatch.setenv("INSPECTION_JOB_DIR", str(tmp_path))
    job_id = "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"

    path = job_files.write_job_file(job_id, b"csv bytes")

    assert path == tmp_path / f"{job_id}.csv"
    assert path.read_bytes() == b"csv bytes"
    assert job_files.is_safe_job_file_path(job_id, path)
    assert not job_files.is_safe_job_file_path(job_id, tmp_path / "../outside.csv")

    job_files.delete_job_file(job_id, path)

    assert not path.exists()


def test_job_file_cleanup_does_not_follow_untrusted_path(tmp_path, monkeypatch) -> None:
    import services.job_files as job_files

    monkeypatch.setenv("INSPECTION_JOB_DIR", str(tmp_path / "jobs"))
    outside_path = tmp_path / "outside.csv"
    outside_path.write_bytes(b"must remain")
    job_id = "8d4c3d84-cf1d-4cdb-83a4-4ebf9d6bf5f6"

    job_files.delete_job_file(job_id, outside_path)

    assert outside_path.read_bytes() == b"must remain"
