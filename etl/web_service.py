import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from core.upload_validator import validate_csv_file_size, validate_csv_filename
from db.models import ETLLoadRun
from etl.db_loader import load_standard_csv
from etl.pipeline import run_pipeline
from etl.profile_loader import get_profile_path


@dataclass(frozen=True)
class ETLWebRunOutcome:
    etl_load_run_id: int
    created: bool
    profile_name: str
    profile_version: str
    source_filename: str
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    error_counts: dict[str, int] | None


def _leaf_filename(filename: str) -> str:
    # validate_csv_filename()과 같은 방식으로 디렉터리 구분자를 제거해,
    # 업로드 파일명이 실제 서버 경로 구성에는 쓰이지 않고 임시 디렉터리 안의
    # 파일 이름 한 조각으로만 쓰이게 합니다.
    return filename.replace("\\", "/").split("/")[-1].strip()


def run_web_etl(
    session: Session,
    *,
    profile_id: str,
    source_filename: str,
    input_bytes: bytes,
) -> ETLWebRunOutcome:
    # run_pipeline/load_standard_csv are the same functions etl.cli/etl.load_cli call;
    # this only bridges an in-memory upload into their existing file-based contract.
    profile_path = get_profile_path(profile_id)

    validate_csv_filename(source_filename)
    validate_csv_file_size(input_bytes)

    with tempfile.TemporaryDirectory(prefix="catalogguard_web_etl_") as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / _leaf_filename(source_filename)
        output_path = temp_path / "catalogguard_ready.csv"
        rejects_path = temp_path / "rejected_rows.csv"
        summary_path = temp_path / "summary.json"
        input_path.write_bytes(input_bytes)

        run_pipeline(input_path, profile_path, output_path, rejects_path, summary_path)

        outcome = load_standard_csv(
            session,
            output_path.read_bytes(),
            summary_path.read_bytes(),
            standard_csv_filename=output_path.name,
            rejects_csv_bytes=rejects_path.read_bytes(),
            rejects_csv_filename=rejects_path.name,
        )

    load_run = session.get(ETLLoadRun, outcome.etl_load_run_id)
    return ETLWebRunOutcome(
        etl_load_run_id=outcome.etl_load_run_id,
        created=outcome.created,
        profile_name=load_run.profile_name,
        profile_version=load_run.profile_version,
        source_filename=load_run.source_filename,
        total_rows=load_run.total_rows,
        loaded_rows=load_run.loaded_rows,
        rejected_rows=load_run.rejected_rows,
        error_counts=load_run.error_counts,
    )
