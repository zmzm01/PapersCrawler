"""
Tests: MinerU PDF parser — upload Content-Type, retry behavior.

These tests verify that _upload_file() uses the correct Content-Type
and retry logic per MinerU's official docs §2: "No Content-Type header
is required when uploading files", and the official example uses
``requests.put(urls[i], data=f)`` without any custom headers.
"""

import sys
import os
import json
import time
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import requests

from processors.mineru_paper_parser import MinerUParser


# ---- Fixtures ----

@pytest.fixture
def parser():
    """MinerUParser instance with a dummy token."""
    return MinerUParser("test-token")


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a small valid-looking PDF for upload tests."""
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return pdf


# ---- _upload_file: Content-Type ----

def test_upload_file_no_custom_content_type(parser, sample_pdf):
    """_upload_file must NOT send Content-Type: application/json or
    application/pdf.  OSS pre-signed URLs are signed with
    application/octet-stream; any other Content-Type causes 403.

    This test matches the MinerU official example:
        requests.put(urls[i], data=f)
    """
    sent_headers = {}

    def _capture_put(url, **kwargs):
        sent_headers.update(kwargs.get("headers", {}))
        # Infer Content-Type from data if not explicitly set
        data = kwargs.get("data", b"")
        resp = mock.MagicMock(spec=requests.Response)
        resp.status_code = 200
        return resp

    with mock.patch("requests.put", side_effect=_capture_put):
        parser._upload_file("https://oss.example.com/upload", sample_pdf)

    # Should NOT have application/json
    ct = sent_headers.get("Content-Type", "")
    assert "application/json" not in ct, (
        f"Should not send JSON Content-Type to OSS, got: {ct}"
    )
    # Should NOT have application/pdf (explicit — let requests default)
    assert "application/pdf" not in ct, (
        f"Should not send explicit application/pdf, got: {ct}"
    )


def test_upload_file_uses_module_level_put(parser, sample_pdf):
    """_upload_file must call requests.put() (module-level), NOT
    self._session.put().  self._session has Content-Type: application/json
    which breaks OSS signatures.
    """
    session_put_called = False
    module_put_called = False

    original_session_put = parser._session.put

    def _track_session_put(url, **kwargs):
        nonlocal session_put_called
        session_put_called = True
        return original_session_put(url, **kwargs)

    def _track_module_put(url, **kwargs):
        nonlocal module_put_called
        module_put_called = True
        resp = mock.MagicMock(spec=requests.Response)
        resp.status_code = 200
        return resp

    parser._session.put = _track_session_put
    with mock.patch("requests.put", side_effect=_track_module_put):
        parser._upload_file("https://oss.example.com/upload", sample_pdf)

    assert module_put_called, "Should use requests.put() (module-level)"
    assert not session_put_called, (
        "Should NOT use self._session.put() (has JSON Content-Type)"
    )


# ---- _upload_file: Retry behavior ----

def test_upload_file_retry_on_403(parser, sample_pdf):
    """_upload_file should retry up to MAX_RETRIES on 403."""
    call_count = [0]

    def _failing_put(url, **kwargs):
        call_count[0] += 1
        resp = mock.MagicMock(spec=requests.Response)
        resp.status_code = 403
        return resp

    with mock.patch("requests.put", side_effect=_failing_put):
        with pytest.raises(RuntimeError, match="文件上传失败"):
            parser._upload_file("https://oss.example.com/upload", sample_pdf)

    assert call_count[0] == 3, f"Expected 3 retries on 403, got {call_count[0]}"


def test_upload_file_retry_on_connection_error(parser, sample_pdf):
    """_upload_file should retry on connection errors."""
    call_count = [0]

    def _failing_put(url, **kwargs):
        call_count[0] += 1
        raise requests.ConnectionError("Connection refused")

    with mock.patch("requests.put", side_effect=_failing_put):
        with pytest.raises(RuntimeError, match="文件上传失败"):
            parser._upload_file("https://oss.example.com/upload", sample_pdf)

    assert call_count[0] == 3, f"Expected 3 retries on ConnectionError, got {call_count[0]}"


def test_upload_file_success_on_second_attempt(parser, sample_pdf):
    """_upload_file should succeed if second attempt works (no exception)."""
    call_count = [0]

    def _partially_failing_put(url, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            resp = mock.MagicMock(spec=requests.Response)
            resp.status_code = 403
            return resp
        resp = mock.MagicMock(spec=requests.Response)
        resp.status_code = 200
        return resp

    with mock.patch("requests.put", side_effect=_partially_failing_put):
        # Should not raise
        parser._upload_file("https://oss.example.com/upload", sample_pdf)

    assert call_count[0] == 2, f"Expected 2 attempts (fail then succeed), got {call_count[0]}"


# ---- _create_batch & _poll_batch: session is used correctly ----

def test_create_batch_uses_session(parser):
    """_create_batch must use self._session (needs Content-Type: application/json
    and Authorization header for MinerU API).
    """
    session_request_called = False

    def _track(method, url, **kwargs):
        nonlocal session_request_called
        session_request_called = True
        assert method == "post"
        resp = mock.MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.json.return_value = {
            "code": 0,
            "data": {"batch_id": "test-batch", "file_urls": ["https://oss.test/upload"]},
        }
        return resp

    with mock.patch.object(parser._session, 'request', side_effect=_track):
        batch_id, urls = parser._create_batch("test.pdf")

    assert session_request_called, "_create_batch must use self._session"
    assert batch_id == "test-batch"
    assert len(urls) == 1


def test_create_batch_session_has_json_header(parser):
    """The session used by _create_batch must have Content-Type: application/json
    (required by MinerU API).  This is the SAME session whose headers MUST NOT
    leak into _upload_file.
    """
    ct = parser._session.headers.get("Content-Type", "")
    assert "application/json" in ct, (
        f"_session should have JSON Content-Type for MinerU API, got: {ct}"
    )
