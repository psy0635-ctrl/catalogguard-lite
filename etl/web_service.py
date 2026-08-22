import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from config.settings import ETL_INITIAL_SOURCE_TYPE_UNKNOWN
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
    actor_username: str | None = None
    # 이번 요청의 source가 아니라, DB에 저장된 이 배치의 최초 source입니다.
    # duplicate(created=False)면 다른 경로로 처음 만들어졌을 수 있습니다.
    initial_source_type: str = ETL_INITIAL_SOURCE_TYPE_UNKNOWN
    initial_source_ref: str | None = None


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
    actor_user_id: int | None = None,
    actor_username: str | None = None,
    initial_source_type: str = ETL_INITIAL_SOURCE_TYPE_UNKNOWN,
    initial_source_ref: str | None = None,
) -> ETLWebRunOutcome:
    # run_pipeline/load_standard_csv are the same functions etl.cli/etl.load_cli call;
    # this only bridges an in-memory upload into their existing file-based contract.
    #
    # session을 함께 넘겨 runtime activation override까지 반영합니다. Web upload,
    # S3, HTTP feed, Airflow DAG가 모두 이 함수 하나를 지나므로, 네 경로가 같은
    # effective active version을 봅니다. 여기서 session을 빠뜨리면 그 경로만 배포
    # 기본값으로 실행되어 "내렸는데 계속 돈다"가 됩니다.
    profile_path = get_profile_path(profile_id, session=session)
    # 위 조회가 session을 autobegin시킵니다. 그대로 두면 아래 load_standard_csv()의
    # with session.begin()이 "A transaction is already begun"으로 실패합니다.
    # 읽기 전용 조회였으므로 여기서 끝내도 잃을 것이 없고, 뒤따르는 run_pipeline()은
    # 파일 I/O라 그동안 idle 트랜잭션을 붙들고 있을 이유도 없습니다.
    #
    # api/routes/inspections.py는 같은 충돌을 별도 session으로 피했지만, 여기서는
    # 호출자(Airflow 포함)가 session 하나만 넘기므로 그 방식을 쓸 수 없습니다.
    session.rollback()

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
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            initial_source_type=initial_source_type,
            initial_source_ref=initial_source_ref,
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
        actor_username=load_run.actor_username,
        rejected_rows=load_run.rejected_rows,
        error_counts=load_run.error_counts,
        initial_source_type=load_run.initial_source_type,
        initial_source_ref=load_run.initial_source_ref,
    )
