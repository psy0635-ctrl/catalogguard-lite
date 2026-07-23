"""현재 동기식 CSV 검수 흐름의 시간과 Python peak memory를 측정합니다."""

import argparse
import csv
from datetime import datetime, timezone
import io
import json
import platform
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from config.settings import CSV_TEMPLATE_COLUMNS, MAX_CSV_ROWS  # noqa: E402
from core.inspection_service import (  # noqa: E402
    InspectionReport,
    inspect_uploaded_csv,
)


DEFAULT_ROWS = [100, 1_000, 5_000, 10_000]
DEFAULT_REPEAT = 3
DEFAULT_SEED = 20260720
WARMUP_COUNT = 1
BENCHMARK_FILENAME = "benchmark_products.csv"
BENCHMARK_RESULT_FIELDS = (
    "rows",
    "csv_size_bytes",
    "issue_count",
    "single_min_seconds",
    "single_median_seconds",
    "single_max_seconds",
    "double_median_seconds",
    "double_to_single_ratio",
    "rows_per_second",
    "peak_memory_bytes",
)

_CATEGORY_DATA = {
    "TOP": ("벤치마크 티셔츠", 19_900),
    "BOTTOM": ("벤치마크 팬츠", 39_900),
    "OUTER": ("벤치마크 재킷", 79_900),
}
_CATEGORIES = tuple(_CATEGORY_DATA)
_COLORS = ("BLACK", "WHITE", "NAVY", "BEIGE", "GRAY")
_SIZES = ("S", "M", "L", "XL")


def _product_name(category: str, row_index: int) -> str:
    label, _ = _CATEGORY_DATA[category]
    return f"{label} {row_index:05d}"


def _different_value(value: str, choices: tuple[str, ...]) -> str:
    return next(choice for choice in choices if choice != value)


def _apply_synthetic_scenarios(rows: list[dict[str, str]]) -> None:
    """100행 단위로 각 검수 시나리오를 한 번씩 넣습니다."""
    for block_start in range(0, len(rows), 100):
        # 완전 중복 상품: 식별자와 이미지 외 핵심 비교 필드를 이전 행과 같게 만듭니다.
        if block_start + 2 < len(rows):
            source = rows[block_start + 1]
            target = rows[block_start + 2]
            for field in ("product_name", "category", "color", "size", "price"):
                target[field] = source[field]

        # 중복 product_id는 상품 내용 자체는 다른 두 행에 적용합니다.
        if block_start + 5 < len(rows):
            rows[block_start + 5]["product_id"] = rows[block_start + 4]["product_id"]

        if block_start + 10 < len(rows):
            rows[block_start + 10]["color"] = "블랙"

        if block_start + 20 < len(rows):
            rows[block_start + 20]["size"] = "medium"

        # 같은 그룹의 서로 다른 상품에 같은 색상·사이즈 조합을 부여합니다.
        if block_start + 31 < len(rows):
            source = rows[block_start + 30]
            target = rows[block_start + 31]
            target["product_group_id"] = source["product_group_id"]
            target["category"] = source["category"]
            target["product_name"] = _product_name(source["category"], block_start + 31)
            target["color"] = source["color"]
            target["size"] = source["size"]

        # 같은 그룹이지만 카테고리와 옵션은 명확히 다른 두 상품을 만듭니다.
        if block_start + 41 < len(rows):
            source = rows[block_start + 40]
            target = rows[block_start + 41]
            target["product_group_id"] = source["product_group_id"]
            target["color"] = _different_value(source["color"], _COLORS)
            target["size"] = _different_value(source["size"], _SIZES)

        if block_start + 50 < len(rows):
            rows[block_start + 50]["price"] = "9999999"

        if block_start + 60 < len(rows):
            rows[block_start + 60]["description"] = (
                "BENCHMARK SYNTHETIC 외부결제 탐지 문구"
            )

        if block_start + 70 < len(rows):
            # .invalid 도메인은 실제 사용자 주소가 아닌 명백한 테스트 전용 값입니다.
            rows[block_start + 70]["description"] = (
                "BENCHMARK SYNTHETIC benchmark-user@example.invalid"
            )


def generate_product_rows(
    row_count: int,
    *,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, str]]:
    """고정 seed로 재현 가능한 가상 상품 행을 생성합니다."""
    if row_count <= 0:
        raise ValueError("rows must contain positive integers")

    random_source = random.Random(seed)
    rows = []
    for row_index in range(row_count):
        category = _CATEGORIES[row_index % len(_CATEGORIES)]
        _, base_price = _CATEGORY_DATA[category]
        price = base_price + random_source.randrange(-20, 21) * 100
        row = {
            "product_group_id": f"BENCH-G{row_index:05d}",
            "product_id": f"BENCH-P{row_index:05d}",
            "product_name": _product_name(category, row_index),
            "category": category,
            "color": random_source.choice(_COLORS),
            "size": random_source.choice(_SIZES),
            "stock": str(random_source.randrange(0, 101)),
            "price": str(price),
            "sale_price": "",
            "image_path": f"benchmark/images/product_{row_index:05d}.jpg",
            "description": "BENCHMARK SYNTHETIC CATALOG ITEM",
            "seller": f"BENCHMARK_SELLER_{row_index % 10:02d}",
        }
        rows.append({column: row[column] for column in CSV_TEMPLATE_COLUMNS})

    _apply_synthetic_scenarios(rows)
    return rows


def generate_csv_bytes(
    row_count: int,
    *,
    seed: int = DEFAULT_SEED,
) -> bytes:
    """가상 상품 행을 UTF-8 CSV bytes로 직렬화합니다."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=CSV_TEMPLATE_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(generate_product_rows(row_count, seed=seed))
    return output.getvalue().encode("utf-8")


def validate_benchmark_inputs(rows: Sequence[int], repeat: int) -> None:
    if repeat <= 0:
        raise ValueError("repeat must be a positive integer")
    if not rows:
        raise ValueError("rows must contain at least one value")
    if any(row_count <= 0 for row_count in rows):
        raise ValueError("rows must contain positive integers")
    if any(row_count > MAX_CSV_ROWS for row_count in rows):
        raise ValueError(f"rows cannot exceed the project limit of {MAX_CSV_ROWS:,}")


def inspect_csv_bytes(csv_bytes: bytes) -> InspectionReport:
    """공통 검수 Service의 업로드 bytes 진입점을 그대로 호출합니다."""
    return inspect_uploaded_csv(BENCHMARK_FILENAME, csv_bytes)


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def measure_inspection(
    row_count: int,
    *,
    repeat: int = DEFAULT_REPEAT,
    seed: int = DEFAULT_SEED,
) -> dict[str, int | float]:
    """한 행 수의 단일·연속 2회 시간과 Python peak memory를 측정합니다."""
    validate_benchmark_inputs([row_count], repeat)
    csv_bytes = generate_csv_bytes(row_count, seed=seed)

    warmup_report = inspect_csv_bytes(csv_bytes)
    issue_count = warmup_report.summary.total_issues
    del warmup_report

    single_durations = []
    for _ in range(repeat):
        started_at = time.perf_counter()
        report = inspect_csv_bytes(csv_bytes)
        single_durations.append(time.perf_counter() - started_at)
        del report

    double_durations = []
    for _ in range(repeat):
        started_at = time.perf_counter()
        first_report = inspect_csv_bytes(csv_bytes)
        second_report = inspect_csv_bytes(csv_bytes)
        double_durations.append(time.perf_counter() - started_at)
        del first_report, second_report

    # tracemalloc은 Python이 추적하는 할당 기준입니다. 운영체제 전체 프로세스
    # 메모리와 다르며 Pandas/C 확장 메모리를 완전히 반영하지 못할 수 있습니다.
    tracemalloc.start()
    try:
        memory_report = inspect_csv_bytes(csv_bytes)
        _, peak_memory_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    del memory_report

    single_median_seconds = statistics.median(single_durations)
    double_median_seconds = statistics.median(double_durations)
    return {
        "rows": row_count,
        "csv_size_bytes": len(csv_bytes),
        "issue_count": issue_count,
        "single_min_seconds": min(single_durations),
        "single_median_seconds": single_median_seconds,
        "single_max_seconds": max(single_durations),
        "double_median_seconds": double_median_seconds,
        "double_to_single_ratio": _safe_ratio(
            double_median_seconds,
            single_median_seconds,
        ),
        "rows_per_second": _safe_ratio(row_count, single_median_seconds),
        "peak_memory_bytes": peak_memory_bytes,
    }


def run_benchmarks(
    rows: Sequence[int],
    *,
    repeat: int = DEFAULT_REPEAT,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, int | float]]:
    validate_benchmark_inputs(rows, repeat)
    return [
        measure_inspection(row_count, repeat=repeat, seed=seed)
        for row_count in rows
    ]


def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def build_benchmark_report(
    results: Sequence[dict[str, int | float]],
    *,
    repeat: int,
    warmup: int = WARMUP_COUNT,
) -> dict[str, object]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "git_sha": _get_git_sha(),
        "repeat": repeat,
        "warmup": warmup,
        "results": list(results),
    }


def save_benchmark_report(
    output_path: str | Path,
    report: dict[str, object],
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def format_results_table(results: Sequence[dict[str, int | float]]) -> str:
    headers = (
        "Rows",
        "CSV MiB",
        "Issues",
        "Single Min",
        "Single Median",
        "Single Max",
        "Double Median",
        "Double/Single",
        "Rows/sec",
        "Peak MiB",
    )
    display_rows = [
        (
            f"{int(result['rows']):,}",
            f"{result['csv_size_bytes'] / (1024 * 1024):.3f}",
            f"{int(result['issue_count']):,}",
            f"{result['single_min_seconds']:.6f}",
            f"{result['single_median_seconds']:.6f}",
            f"{result['single_max_seconds']:.6f}",
            f"{result['double_median_seconds']:.6f}",
            f"{result['double_to_single_ratio']:.2f}",
            f"{result['rows_per_second']:,.1f}",
            f"{result['peak_memory_bytes'] / (1024 * 1024):.3f}",
        )
        for result in results
    ]
    widths = [
        max(len(header), *(len(row[index]) for row in display_rows))
        for index, header in enumerate(headers)
    ]
    lines = [
        " | ".join(header.rjust(widths[index]) for index, header in enumerate(headers)),
        "-+-".join("-" * width for width in widths),
    ]
    lines.extend(
        " | ".join(value.rjust(widths[index]) for index, value in enumerate(row))
        for row in display_rows
    )
    return "\n".join(lines)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CatalogGuard Lite 동기 CSV 검수 성능을 재현 가능하게 측정합니다.",
    )
    parser.add_argument(
        "--rows",
        nargs="+",
        type=int,
        default=DEFAULT_ROWS,
        metavar="N",
        help="측정할 CSV 행 수 목록 (기본값: 100 1000 5000 10000)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=DEFAULT_REPEAT,
        metavar="N",
        help="단일 및 연속 2회 측정의 반복 횟수 (기본값: 3)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="메타데이터와 결과를 저장할 선택적 JSON 경로",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        validate_benchmark_inputs(args.rows, args.repeat)
    except ValueError as error:
        parser.error(str(error))

    results = run_benchmarks(args.rows, repeat=args.repeat)
    print(format_results_table(results))
    print(
        "\nPeak MiB는 tracemalloc이 추적한 Python 메모리 기준이며, "
        "운영체제 전체 프로세스 및 Pandas/C 확장 메모리와 다를 수 있습니다."
    )

    if args.output is not None:
        report = build_benchmark_report(
            results,
            repeat=args.repeat,
            warmup=WARMUP_COUNT,
        )
        save_benchmark_report(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
