"""Run the isolated ETL Chromium browser E2E and its local services."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "e2e" / "etl_browser_vendor.csv"
PROFILE_PATH = ROOT / "config" / "etl" / "sample_marketplace_vendor_v1.json"
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "browser-e2e"


class BrowserE2EError(RuntimeError):
    """Raised when the browser E2E environment cannot be prepared safely."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the isolated CatalogGuard ETL Chromium browser E2E."
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "").strip(),
        help="Test-only PostgreSQL URL; defaults to DATABASE_URL.",
    )
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--streamlit-port", type=int, default=8501)
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help="Failure artifact directory.",
    )
    return parser


def _validate_database_url(database_url: str) -> None:
    if not database_url:
        raise BrowserE2EError(
            "DATABASE_URL is required and must point to a test-only PostgreSQL instance"
        )

    parsed = urlparse(database_url)
    host = (parsed.hostname or "").lower()
    unsafe_tokens = ("railway", "production", "prod", "rds", "aws")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise BrowserE2EError("Browser E2E refuses non-local PostgreSQL hosts")
    if any(token in database_url.lower() for token in unsafe_tokens):
        raise BrowserE2EError("Browser E2E refuses a production-like database URL")


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BrowserE2EError("ETL summary could not be read") from error
    if not isinstance(value, dict):
        raise BrowserE2EError("ETL summary must be a JSON object")
    return value


def _wait_for_http(
    url: str,
    *,
    expected_body: str,
    process: subprocess.Popen[bytes] | None,
    log_path: Path,
    timeout_seconds: float = 60.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise BrowserE2EError(
                f"Service exited before readiness; see {log_path}"
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body = response.read().decode("utf-8", errors="replace")
                if response.status == 200 and expected_body in body:
                    return
                last_error = f"HTTP {response.status}: {body[:200]}"
        except (OSError, urllib.error.URLError) as error:
            last_error = str(error)
        time.sleep(0.5)
    raise BrowserE2EError(f"Readiness timed out for {url}: {last_error}")


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class ETLBrowserE2ERunner:
    def __init__(self, args: argparse.Namespace) -> None:
        _validate_database_url(args.database_url)
        if args.api_port == args.streamlit_port:
            raise BrowserE2EError("API and Streamlit ports must be different")
        if not FIXTURE_PATH.is_file() or not PROFILE_PATH.is_file():
            raise BrowserE2EError("Browser E2E fixture or profile is missing")
        self.args = args
        self.temp_dir = Path(tempfile.mkdtemp(prefix="catalogguard-etl-browser-e2e-"))
        self.artifact_dir = args.artifacts_dir.resolve()
        self.processes: list[tuple[str, subprocess.Popen[bytes], Path]] = []
        self.environment = {
            **os.environ,
            "DATABASE_URL": args.database_url,
            "TEST_DATABASE_URL": args.database_url,
            "CATALOGGUARD_API_BASE_URL": (
                f"http://127.0.0.1:{args.api_port}"
            ),
            "E2E_STREAMLIT_URL": f"http://127.0.0.1:{args.streamlit_port}",
            "E2E_SOURCE_FILENAME": FIXTURE_PATH.name,
            "E2E_ARTIFACT_DIR": str(self.artifact_dir),
            "PYTHONIOENCODING": "utf-8",
        }

    def _run_command(
        self,
        name: str,
        command: list[str],
        *,
        log_name: str,
    ) -> subprocess.CompletedProcess[str]:
        log_path = self.temp_dir / log_name
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        log_path.write_text(
            f"$ {' '.join(command)}\n\n{completed.stdout}\n{completed.stderr}",
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise BrowserE2EError(
                f"{name} failed with exit code {completed.returncode}; see {log_path}"
            )
        return completed

    def _start_service(
        self,
        name: str,
        command: list[str],
        *,
        log_name: str,
    ) -> tuple[subprocess.Popen[bytes], Path]:
        log_path = self.temp_dir / log_name
        log_file = log_path.open("wb")
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=self.environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        log_file.close()
        self.processes.append((name, process, log_path))
        return process, log_path

    def _preserve_failure_artifacts(self) -> None:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        for _, _, log_path in self.processes:
            if log_path.is_file():
                shutil.copy2(log_path, self.artifact_dir / log_path.name)
        for log_path in self.temp_dir.glob("*.log"):
            shutil.copy2(log_path, self.artifact_dir / log_path.name)

    def run(self) -> None:
        failed = True
        try:
            output_path = self.temp_dir / "catalogguard_ready.csv"
            rejects_path = self.temp_dir / "rejected_rows.csv"
            summary_path = self.temp_dir / "etl_summary.json"

            self._run_command(
                "Alembic migration",
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                log_name="alembic.log",
            )
            self._run_command(
                "ETL transformation",
                [
                    sys.executable,
                    "-m",
                    "etl.cli",
                    "--input",
                    str(FIXTURE_PATH),
                    "--profile",
                    str(PROFILE_PATH),
                    "--output",
                    str(output_path),
                    "--rejects",
                    str(rejects_path),
                    "--summary",
                    str(summary_path),
                ],
                log_name="etl.log",
            )
            summary = _read_json(summary_path)
            expected_counts = {
                "total_rows": 3,
                "loaded_rows": 2,
                "rejected_rows": 1,
            }
            if any(summary.get(key) != value for key, value in expected_counts.items()):
                raise BrowserE2EError("Browser E2E fixture produced unexpected ETL counts")
            self._run_command(
                "PostgreSQL ETL load",
                [
                    sys.executable,
                    "-m",
                    "etl.load_cli",
                    "--input",
                    str(output_path),
                    "--rejects",
                    str(rejects_path),
                    "--summary",
                    str(summary_path),
                ],
                log_name="load.log",
            )

            api_process, api_log = self._start_service(
                "FastAPI",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.args.api_port),
                    "--no-access-log",
                ],
                log_name="fastapi.log",
            )
            _wait_for_http(
                f"http://127.0.0.1:{self.args.api_port}/health",
                expected_body='"status":"ok"',
                process=api_process,
                log_path=api_log,
            )
            _wait_for_http(
                f"http://127.0.0.1:{self.args.api_port}/ready",
                expected_body='"status":"ready"',
                process=api_process,
                log_path=api_log,
            )

            streamlit_process, streamlit_log = self._start_service(
                "Streamlit",
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    "app.py",
                    "--server.headless=true",
                    "--server.address=127.0.0.1",
                    f"--server.port={self.args.streamlit_port}",
                    "--browser.gatherUsageStats=false",
                ],
                log_name="streamlit.log",
            )
            _wait_for_http(
                f"http://127.0.0.1:{self.args.streamlit_port}/_stcore/health",
                expected_body="ok",
                process=streamlit_process,
                log_path=streamlit_log,
            )

            self._run_command(
                "Chromium browser E2E",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/e2e/test_etl_browser_e2e.py",
                    "--browser",
                    "chromium",
                    "--tracing",
                    "retain-on-failure",
                    "-o",
                    "addopts=",
                    "-q",
                ],
                log_name="playwright.log",
            )
            failed = False
            print("ETL 변환 성공")
            print("PostgreSQL 적재 성공")
            print("FastAPI readiness 성공")
            print("Streamlit health 성공")
            print("Chromium E2E 성공")
        finally:
            for _, process, _ in reversed(self.processes):
                _terminate_process(process)
            if failed:
                self._preserve_failure_artifacts()
            shutil.rmtree(self.temp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        ETLBrowserE2ERunner(args).run()
    except BrowserE2EError as error:
        print(f"Browser E2E failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
