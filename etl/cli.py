import argparse
import sys
from pathlib import Path

from etl.pipeline import ETLPipelineError, run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="공급사 CSV를 CatalogGuard Lite 표준 CSV로 변환합니다."
    )
    parser.add_argument("--input", required=True, type=Path, help="공급사 원본 CSV 파일")
    parser.add_argument("--profile", required=True, type=Path, help="공급사 매핑 프로필 JSON 파일")
    parser.add_argument("--output", required=True, type=Path, help="표준 CatalogGuard CSV 파일")
    parser.add_argument("--rejects", required=True, type=Path, help="변환 오류 행 CSV 파일")
    parser.add_argument("--summary", required=True, type=Path, help="처리 요약 JSON 파일")
    return parser


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path.name


def main(argv: list[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    try:
        result = run_pipeline(
            arguments.input,
            arguments.profile,
            arguments.output,
            arguments.rejects,
            arguments.summary,
        )
    except ETLPipelineError as error:
        print(f"ETL 실패: {error}", file=sys.stderr)
        return 1

    print("ETL 완료")
    print(f"전체 행: {result.total_rows}")
    print(f"정상 변환: {result.loaded_rows}")
    print(f"오류 행: {result.rejected_rows}")
    print(f"표준 CSV: {_display_path(arguments.output)}")
    print(f"오류 CSV: {_display_path(arguments.rejects)}")
    print(f"요약 JSON: {_display_path(arguments.summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
