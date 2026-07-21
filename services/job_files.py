from __future__ import annotations

from pathlib import Path
from uuid import UUID

from config.settings import get_inspection_job_dir


def _job_id_text(job_id: str | UUID) -> str:
    return str(UUID(str(job_id)))


def get_job_file_path(job_id: str | UUID) -> Path:
    job_id_text = _job_id_text(job_id)
    return get_inspection_job_dir().resolve() / f"{job_id_text}.csv"


def write_job_file(job_id: str | UUID, file_bytes: bytes) -> Path:
    job_directory = get_inspection_job_dir().resolve()
    job_directory.mkdir(parents=True, exist_ok=True)

    final_path = get_job_file_path(job_id)
    temporary_path = job_directory / f".{_job_id_text(job_id)}.tmp"
    temporary_path.write_bytes(file_bytes)
    temporary_path.replace(final_path)
    return final_path


def is_safe_job_file_path(job_id: str | UUID, file_path: str | Path) -> bool:
    try:
        candidate = Path(file_path).resolve()
        expected = get_job_file_path(job_id)
    except (OSError, TypeError, ValueError):
        return False
    return candidate == expected


def delete_job_file(job_id: str | UUID, file_path: str | Path | None = None) -> None:
    path = get_job_file_path(job_id) if file_path is None else Path(file_path)
    if not is_safe_job_file_path(job_id, path):
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass
