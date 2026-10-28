"""Real downloads against a temporary Streamlit server and fake API; no DB needed."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest


@pytest.mark.e2e
def test_integrity_json_download_preserves_prepared_csv_in_chromium(tmp_path):
    from playwright.sync_api import sync_playwright

    root = Path(__file__).resolve().parents[2]
    app_path = tmp_path / "integrity_app.py"
    app_path.write_text(
        "import sys\n"
        f"sys.path[:0] = {[str(root), str(root / 'tests')]!r}\n"
        "import streamlit as st\n"
        "from test_etl_load_history_ui import FilteredReconciliationClient, _reconciliation_filter_test_app\n"
        "if 'fake_client' not in st.session_state:\n"
        "    st.session_state.fake_client = FilteredReconciliationClient()\n"
        "_reconciliation_filter_test_app(st.session_state.fake_client)\n",
        encoding="utf-8",
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log_path = tmp_path / "streamlit.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(app_path),
             "--server.address=127.0.0.1", f"--server.port={port}",
             "--server.headless=true", "--browser.gatherUsageStats=false"],
            cwd=root, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urlopen(base_url + "/_stcore/health", timeout=1) as response:
                        assert response.status == 200
                    break
                except (URLError, TimeoutError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        pytest.fail(log_path.read_text(encoding="utf-8"))
                    time.sleep(0.1)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page(accept_downloads=True)
                    page.goto(base_url)
                    csv_button = page.get_by_role("button", name="상품 동기화 차이 전체 CSV 다운로드", exact=True)
                    json_button = page.get_by_role("button", name="CSV 무결성 검증 보고서 다운로드", exact=True)
                    page.get_by_role("button", name="상품 동기화 차이 전체 CSV 준비", exact=True).click()
                    json_button.wait_for()
                    with page.expect_download() as download:
                        csv_button.click()
                    csv_download = download.value
                    csv_bytes = Path(csv_download.path()).read_bytes()
                    with page.expect_download() as download:
                        json_button.click()
                    json_download = download.value
                    manifest_bytes = Path(json_download.path()).read_bytes()
                    manifest = json.loads(manifest_bytes.decode("utf-8"))
                    assert manifest["csv_file_name"] == csv_download.suggested_filename
                    assert json_download.suggested_filename == "catalogguard_reconciliation_42_all.integrity.json"
                    assert manifest["csv_sha256"] == hashlib.sha256(csv_bytes).hexdigest()
                    assert manifest["row_count"] == len(list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))) == 5
                    # Download JSON twice, then CSV again: the same prepared pair remains.
                    with page.expect_download() as download:
                        json_button.click()
                    assert Path(download.value.path()).read_bytes() == manifest_bytes
                    with page.expect_download() as download:
                        csv_button.click()
                    assert Path(download.value.path()).read_bytes() == csv_bytes
                    assert csv_button.is_visible() and json_button.is_visible()
                finally:
                    browser.close()
        finally:
            process.terminate()
            process.wait(timeout=15)
