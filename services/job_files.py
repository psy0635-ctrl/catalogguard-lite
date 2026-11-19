from __future__ import annotations

from pathlib import Path
from uuid import UUID

from config.settings import get_inspection_job_dir


def _job_id_text(job_id: str | UUID) -> str:
    return str(UUID(str(job_id)))


def get_job_file_path(job_id: str | UUID, *, directory: Path | None = None) -> Path:
    job_id_text = _job_id_text(job_id)
    return (directory or get_inspection_job_dir()).resolve() / f"{job_id_text}.csv"


def write_job_file(
    job_id: str | UUID, file_bytes: bytes, *, directory: Path | None = None,
) -> Path:
    final_path = get_job_file_path(job_id, directory=directory)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = final_path.with_name(f".{final_path.stem}.tmp")
    try:
        temporary_path.write_bytes(file_bytes)
        temporary_path.replace(final_path)
    except OSError:
        # A failed atomic publish must not leave uploaded CSV content behind.
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return final_path


def is_safe_job_file_path(
    job_id: str | UUID, file_path: str | Path, *, directory: Path | None = None,
) -> bool:
    try:
        candidate = Path(file_path).resolve()
        expected = get_job_file_path(job_id, directory=directory)
    except (OSError, TypeError, ValueError):
        return False
    return candidate == expected


def delete_job_file(
    job_id: str | UUID, file_path: str | Path | None = None, *, directory: Path | None = None,
) -> None:
    path = get_job_file_path(job_id, directory=directory) if file_path is None else Path(file_path)
    if not is_safe_job_file_path(job_id, path, directory=directory):
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass
