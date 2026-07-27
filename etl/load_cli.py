import argparse
import sys
from pathlib import Path

from config.database import DatabaseConfigurationError
from db.session import get_session_factory
from etl.db_loader import ETLLoadError, load_standard_csv


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CatalogGuard 표준 CSV PostgreSQL staging 적재")
    parser.add_argument("--input", required=True, type=Path, help="표준 CSV 파일")
    parser.add_argument("--summary", required=True, type=Path, help="ETL 요약 JSON 파일")
    parser.add_argument("--rejects", type=Path, help="reject CSV file")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    try:
        standard_csv_bytes = arguments.input.read_bytes()
        rejects_csv_bytes = (
            arguments.rejects.read_bytes() if arguments.rejects is not None else None
        )
        summary_json_bytes = arguments.summary.read_bytes()
        with get_session_factory()() as session:
            outcome = load_standard_csv(
                session,
                standard_csv_bytes,
                summary_json_bytes,
                standard_csv_filename=arguments.input.name,
                rejects_csv_bytes=rejects_csv_bytes,
                rejects_csv_filename=(
                    arguments.rejects.name
                    if arguments.rejects is not None
                    else "rejected_rows.csv"
                ),
            )
    except ETLLoadError as error:
        print(f"DB 적재 실패: {error}", file=sys.stderr)
        return 1
    except (DatabaseConfigurationError, OSError):
        print("DB 적재 실패: 입력 파일 또는 데이터베이스 설정을 확인할 수 없습니다", file=sys.stderr)
        return 1
    except Exception:
        print("DB 적재 실패: 데이터베이스 적재 중 오류가 발생했습니다", file=sys.stderr)
        return 1

    print("DB 적재 완료")
    print(f"적재 배치 ID: {outcome.etl_load_run_id}")
    print(f"신규 적재: {'yes' if outcome.created else 'no'}")
    print(
        f"전체 행: {outcome.total_rows if outcome.total_rows is not None else '기록 없음'}"
    )
    print(f"정상 상품 행: {outcome.loaded_rows}")
    print(
        f"거부 행: {outcome.rejected_rows if outcome.rejected_rows is not None else '기록 없음'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
