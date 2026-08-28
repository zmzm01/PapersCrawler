"""Coverage for MinerU polling, extraction and convenience APIs."""

import io
import zipfile
from types import SimpleNamespace

import pytest
import requests

import processors.mineru_paper_parser as mineru


def test_request_retry_context_and_parse_flow(tmp_path, monkeypatch):
    """Retry helper, context manager and parse orchestration are deterministic."""
    parser = mineru.MinerUParser("token")
    responses = [type("Response", (), {"raise_for_status": lambda self: None})()]

    def request_with_one_failure(*args, **kwargs):
        if len(responses) == 1:
            responses.append(None)
            raise requests.ConnectionError("offline")
        return responses.pop(0)

    monkeypatch.setattr(parser._session, "request", request_with_one_failure)
    monkeypatch.setattr(
        mineru, "time", SimpleNamespace(sleep=lambda _delay: None, time=lambda: 0.0)
    )
    assert parser._request_with_retry("get", "https://example") is not None
    parser.close()
    parser.close()

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    output = tmp_path / "out"
    parser = mineru.MinerUParser("token")
    parser._create_batch = lambda filename: ("batch", ["upload"])
    parser._upload_file = lambda url, path: None
    parser._poll_batch = lambda batch, filename: "zip"
    parser._download_and_extract = lambda url, directory: (
        directory / "full.md"
    ).write_text("full", encoding="utf-8")
    assert parser.parse_pdf(pdf, output) == output
    with pytest.raises(FileNotFoundError):
        parser.parse_pdf(tmp_path / "missing.pdf")
    monkeypatch.setattr(mineru, "MinerUParser", lambda token: parser)
    assert mineru.parse_paper(pdf, "token", output) == output


def test_mineru_batch_poll_and_zip_extract(tmp_path, monkeypatch):
    """Batch errors, pending progress, success and zip extraction are covered."""
    parser = mineru.MinerUParser("token")
    parser._request_with_retry = lambda *args, **kwargs: type(
        "Response",
        (),
        {
            "json": lambda self: {"code": 1, "msg": "bad"},
        },
    )()
    with pytest.raises(RuntimeError, match="获取上传地址"):
        parser._create_batch("paper.pdf")

    states = iter(
        [
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "file_name": "paper.pdf",
                            "state": "running",
                            "extract_progress": {
                                "extracted_pages": 1,
                                "total_pages": 2,
                            },
                        }
                    ]
                },
            },
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "file_name": "paper.pdf",
                            "state": "done",
                            "full_zip_url": "https://zip",
                        }
                    ]
                },
            },
        ]
    )
    parser._request_with_retry = lambda *args, **kwargs: type(
        "Response", (), {"json": lambda self: next(states)}
    )()
    times = iter([0.0, 0.0, 0.1, 0.1, 0.1])
    fake_clock = SimpleNamespace(time=lambda: next(times), sleep=lambda _delay: None)
    monkeypatch.setattr(mineru, "time", fake_clock)
    assert parser._poll_batch("batch", "paper.pdf") == "https://zip"

    failed = {
        "code": 0,
        "data": {
            "extract_result": [
                {
                    "file_name": "paper.pdf",
                    "state": "failed",
                    "err_code": "E",
                    "err_msg": "bad pdf",
                }
            ]
        },
    }
    parser._request_with_retry = lambda *args, **kwargs: type(
        "Response", (), {"json": lambda self: failed}
    )()
    fake_clock.time = lambda: 0.0
    with pytest.raises(RuntimeError, match="bad pdf"):
        parser._poll_batch("batch", "paper.pdf")

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("full.md", "# full")
        archive.writestr("images/x.txt", "image")
    response = type(
        "Response",
        (),
        {
            "raise_for_status": lambda self: None,
            "iter_content": lambda self, chunk_size: [payload.getvalue(), b""],
        },
    )()
    parser._request_with_retry = lambda *args, **kwargs: response
    destination = tmp_path / "extract"
    parser._download_and_extract("https://zip", destination)
    assert (destination / "full.md").read_text(encoding="utf-8") == "# full"
