"""Real tests for src/download.py.

These tests use a local HTTP server and temporary files so they can run
offline and do not depend on external network availability.
"""

import hashlib
import os
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import pytest
import requests

# Import the functions under test. Importing src.download also imports
# PySide6.QtCore, so we provide a QCoreApplication fixture below.
from src.download import _download_file, _verify_file


@pytest.fixture(scope="module", autouse=True)
def qcore_app():
    """Ensure a QCoreApplication exists for any Qt objects created during tests."""
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


class _SimpleHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that serves a fixed payload."""

    payload = b"Hello, DraggyEncoder!"
    user_agents = []

    def do_GET(self):  # noqa: N802
        _SimpleHandler.user_agents.append(self.headers.get("User-Agent"))
        if self.path == "/fail":
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format, *args):
        # Silence server logs during tests.
        pass


@pytest.fixture(scope="module")
def http_server():
    """Start a local HTTP server and yield its base URL."""
    _SimpleHandler.user_agents.clear()
    server = HTTPServer(("127.0.0.1", 0), _SimpleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_verify_file_with_size(tmp_path):
    file_path = tmp_path / "test.bin"
    file_path.write_bytes(b"12345")

    assert _verify_file(str(file_path)) is True
    assert _verify_file(str(file_path), expected_size=5) is True
    assert _verify_file(str(file_path), expected_size=4) is False


def test_verify_file_with_sha256(tmp_path):
    file_path = tmp_path / "test.bin"
    data = b"draggy"
    file_path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()

    assert _verify_file(str(file_path), expected_sha256=digest) is True
    assert _verify_file(str(file_path), expected_sha256="0" * 64) is False


def test_verify_file_missing(tmp_path):
    assert _verify_file(str(tmp_path / "missing.bin")) is False


def test_download_file_success(http_server, tmp_path):
    dest = tmp_path / "downloaded.bin"
    url = f"{http_server}/resource"

    result = _download_file(url, str(dest))

    assert result is True
    assert dest.read_bytes() == _SimpleHandler.payload


def test_download_file_skip_existing_valid_file(http_server, tmp_path):
    dest = tmp_path / "existing.bin"
    dest.write_bytes(_SimpleHandler.payload)
    progress_calls = []
    log_calls = []

    result = _download_file(
        f"{http_server}/resource",
        str(dest),
        progress_callback=progress_calls.append,
        log_callback=log_calls.append,
        expected_size=len(_SimpleHandler.payload),
    )

    assert result is True
    assert any("already downloaded" in msg for msg in log_calls)
    assert progress_calls == [100]


def test_download_file_atomic_write(http_server, tmp_path):
    dest = tmp_path / "atomic.bin"
    part_file = tmp_path / "atomic.bin.part"
    url = f"{http_server}/resource"

    result = _download_file(url, str(dest))

    assert result is True
    assert dest.exists()
    assert not part_file.exists()


def test_download_file_integrity_check_fails(http_server, tmp_path):
    dest = tmp_path / "bad.bin"
    url = f"{http_server}/resource"

    result = _download_file(
        url,
        str(dest),
        expected_size=999999,
        retries=1,
    )

    assert result is False
    assert not dest.exists()


def test_download_file_retries_on_failure(http_server, tmp_path):
    dest = tmp_path / "retry.bin"
    url = f"{http_server}/fail"

    with mock.patch("src.download.time.sleep") as mock_sleep:
        result = _download_file(url, str(dest), retries=3)

    assert result is False
    assert mock_sleep.call_count == 2  # sleeps after attempts 1 and 2
    # Verify exponential backoff values: 1s and 2s.
    assert mock_sleep.call_args_list[0][0][0] == 1
    assert mock_sleep.call_args_list[1][0][0] == 2


def test_download_file_retries_then_succeeds(tmp_path):
    """Simulate a transient failure followed by a successful download."""
    dest = tmp_path / "retry_success.bin"
    payload = b"success after retry"

    class FakeResponse:
        def __init__(self, content, status_code=200):
            self._content = content
            self.headers = {"content-length": str(len(content))}
            self.status_code = status_code

        def iter_content(self, chunk_size=8192):
            for i in range(0, len(self._content), chunk_size):
                yield self._content[i:i + chunk_size]

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.exceptions.HTTPError("Server error")

    call_count = 0

    def fake_get(url, stream=True, timeout=None, headers=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise requests.exceptions.ConnectionError("transient failure")
        return FakeResponse(payload)

    with mock.patch("src.download.requests.get", side_effect=fake_get) as mock_get:
        with mock.patch("src.download.time.sleep") as mock_sleep:
            result = _download_file("http://example.com/file", str(dest), retries=3)

    assert result is True
    assert dest.read_bytes() == payload
    assert call_count == 2
    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args_list[0][0][0] == 1  # first backoff is 1 second


def test_download_file_cleans_up_part_after_final_failure(http_server, tmp_path):
    dest = tmp_path / "cleanup.bin"
    part = tmp_path / "cleanup.bin.part"
    url = f"{http_server}/fail"

    result = _download_file(url, str(dest), retries=1)

    assert result is False
    assert not dest.exists()
    assert not part.exists()


def test_download_file_redownloads_if_sha256_mismatch(http_server, tmp_path):
    dest = tmp_path / "sha_mismatch.bin"
    dest.write_bytes(b"stale data")
    url = f"{http_server}/resource"

    result = _download_file(
        url,
        str(dest),
        expected_sha256="0" * 64,
        retries=1,
    )

    assert result is False
    # The original stale file must remain untouched because the atomic
    # replace only happens after a successful integrity check.
    assert dest.read_bytes() == b"stale data"


def test_download_file_progress_callback(http_server, tmp_path):
    dest = tmp_path / "progress.bin"
    url = f"{http_server}/resource"
    progress = []

    result = _download_file(url, str(dest), progress_callback=progress.append)

    assert result is True
    assert 100 in progress


def test_download_file_backoff_capped(http_server, tmp_path):
    """Backoff should never exceed the 30-second cap."""
    dest = tmp_path / "cap.bin"
    url = f"{http_server}/fail"

    with mock.patch("src.download.time.sleep") as mock_sleep:
        _download_file(url, str(dest), retries=5)

    for call in mock_sleep.call_args_list:
        assert call[0][0] <= 30


def test_download_deoldify_model_passes_expected_size_and_sha256(tmp_path, monkeypatch):
    """Verify that model metadata is forwarded to _download_file and that the models directory is created."""
    import src.download as download_module

    captured = {}

    def fake_download_file(url, dest_path, progress_callback=None, log_callback=None, label="Downloading", expected_size=None, expected_sha256=None, retries=3):
        captured["expected_size"] = expected_size
        captured["expected_sha256"] = expected_sha256
        return True

    monkeypatch.setattr(download_module, "_download_file", fake_download_file)
    monkeypatch.setattr(download_module.g, "bin_dir", str(tmp_path))

    from src.ai_tools import COLORIZE_MODELS
    first_key = next(iter(COLORIZE_MODELS))
    result = download_module.download_deoldify_model(model_key=first_key)

    assert result is True
    assert captured["expected_size"] == COLORIZE_MODELS[first_key].get("expected_size")
    assert captured["expected_sha256"] == COLORIZE_MODELS[first_key].get("expected_sha256")
    assert (tmp_path / "models").exists()


def test_deoldify_model_sizes_are_populated():
    """Ensure the real file sizes from the GitHub release API are present."""
    from src.ai_tools import COLORIZE_MODELS

    assert COLORIZE_MODELS["deoldify-artistic"]["expected_size"] == 254789257
    assert COLORIZE_MODELS["deoldify-artistic-fp16"]["expected_size"] == 127421195


def test_download_file_sends_user_agent(http_server, tmp_path):
    _SimpleHandler.user_agents.clear()
    dest = tmp_path / "ua.bin"
    url = f"{http_server}/resource"

    result = _download_file(url, str(dest))

    assert result is True
    assert _SimpleHandler.user_agents == ["DraggyEncoder/1.0"]


def test_download_file_redownloads_if_existing_size_mismatch(http_server, tmp_path):
    dest = tmp_path / "mismatch.bin"
    dest.write_bytes(b"wrong")
    url = f"{http_server}/resource"

    result = _download_file(url, str(dest), expected_size=len(_SimpleHandler.payload))

    assert result is True
    assert dest.read_bytes() == _SimpleHandler.payload
