"""Coverage for WebUI helpers and read-only/report routes."""

import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

import web.app as web_app


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("cloudflare challenge", "Bot / Cloudflare"),
        ("NonResearchPageError", "Non-research article"),
        ("connection refused", "Network / Timeout"),
        ("HTTP 429", "LLM API Error"),
        ("MinerU parse_pdf failed", "MinerU Error"),
        ("No dc.type metadata", "Page Parse Error"),
        ("404 not found", "Data Missing"),
        ("publisher disabled", "Publisher Disabled"),
        ("other", "Other"),
        ("", "Unknown"),
    ],
)
def test_classify_error_categories(message, expected):
    """Dashboard error classification maps representative messages."""
    assert web_app._classify_error(message) == expected


def test_timeago_and_safe_fulltext_resolution(tmp_path, monkeypatch):
    """Relative times and MinerU paths handle all boundary cases."""
    now = time.time()
    assert web_app._timeago(0) == ""
    assert web_app._timeago(now - 10) == "just now"
    assert web_app._timeago(now - 120).endswith("m ago")
    assert web_app._timeago(now - 7200).endswith("h ago")
    assert web_app._timeago(now - 172800).endswith("d ago")
    assert web_app._timeago(now - 1209600).endswith("w ago")
    data_dir = tmp_path / "data"
    fulltext = data_dir / "mineru" / "paper" / "full.md"
    fulltext.parent.mkdir(parents=True)
    fulltext.write_text("full", encoding="utf-8")
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    assert web_app._resolve_mineru_fulltext("mineru/paper") == fulltext
    assert web_app._resolve_mineru_fulltext("") is None
    assert web_app._resolve_mineru_fulltext("../outside") is None
    fulltext.unlink()
    assert web_app._resolve_mineru_fulltext("mineru/paper") is None


def test_pipeline_status_and_weekly_stats(monkeypatch):
    """Dashboard data functions close the database and classify errors."""

    class Cursor:
        def fetchone(self):
            return (2,)

        def fetchall(self):
            return []

    class FakeDB:
        def __init__(self, path):
            self.conn = SimpleNamespace(
                execute=lambda *args: Cursor(), close=lambda: None
            )

        def init_db_papers(self):
            return None

        def get_all_papers(self):
            return [1, 2]

        def get_phase_stats(self):
            return [
                {
                    "label": "Phase C",
                    "status_counts": {"failed": 1},
                    "error_texts": ["cloudflare"],
                }
            ]

    monkeypatch.setattr(web_app, "DatabaseClient", FakeDB)
    result = web_app._pipeline_status()
    assert result["total"] == 2
    assert result["pending_report"] == 2
    assert result["phases"]["Phase C"]["failed_breakdown"] == {"Bot / Cloudflare": 1}
    weekly = asyncio.run(web_app.pipeline_weekly_stats())
    assert weekly["ok"] is True
    assert len(weekly["days"]) == 7


def test_basic_routes_and_report_file_routes(tmp_path, monkeypatch):
    """Redirect, report listing, data and download routes cover success/errors."""
    auto = tmp_path / "auto"
    user = tmp_path / "user"
    data = tmp_path / "data"
    auto.mkdir()
    user.mkdir()
    data.mkdir()
    report = auto / "report_20260824.md"
    report.write_text("## Paper\n**DOI** 10/x\n", encoding="utf-8")
    monkeypatch.setattr(web_app, "AUTO_REPORT_DIR", auto)
    monkeypatch.setattr(web_app, "USER_REPORT_DIR", user)
    monkeypatch.setattr(web_app, "DATA_DIR", data)
    monkeypatch.setattr(
        web_app,
        "templates",
        SimpleNamespace(TemplateResponse=lambda *args, **kwargs: args[2]),
    )
    reports = web_app._list_reports()
    assert reports[0]["paper_count"] == 1
    assert asyncio.run(web_app.root_redirect()).status_code == 302
    assert asyncio.run(web_app.report_list()).body.startswith(b'{"ok":true')
    data_response = asyncio.run(web_app.report_data(report.name))
    assert data_response.status_code == 200
    assert asyncio.run(web_app.report_data("missing.md")).status_code == 404
    assert asyncio.run(web_app.report_data("../secret.md")).status_code == 400
    download_response = asyncio.run(web_app.download_report(report.name))
    assert download_response.filename == report.name
    assert asyncio.run(web_app.download_report("missing.md")).status_code == 404
    assert asyncio.run(web_app.download_report("../secret.md")).status_code == 400
    page = asyncio.run(web_app.report_page(SimpleNamespace(), show=""))
    assert page["selected_filename"] == report.name


def test_review_validation_and_missing_detail(tmp_path, monkeypatch):
    """Review API rejects malformed payloads and missing papers cleanly."""

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def init_db_papers(self):
            return None

        def get_relevance_review_queue(self, **kwargs):
            return []

        def count_relevance_review_queue(self, **kwargs):
            return 0

    monkeypatch.setattr(web_app, "DatabaseClient", lambda path: FakeDB())
    request = SimpleNamespace()
    missing = asyncio.run(web_app.relevance_review_detail(request, "10/missing"))
    assert missing.status_code == 404
    empty = asyncio.run(
        web_app.save_relevance_review(
            web_app.RelevanceReviewPayload(doi="", decision="A")
        )
    )
    assert empty.status_code == 422
    long_notes = asyncio.run(
        web_app.save_relevance_review(
            web_app.RelevanceReviewPayload(doi="x", decision="A", notes="x" * 20001)
        )
    )
    assert long_notes.status_code == 422
    long_reviewer = asyncio.run(
        web_app.save_relevance_review(
            web_app.RelevanceReviewPayload(doi="x", decision="A", reviewer="x" * 201)
        )
    )
    assert long_reviewer.status_code == 422


def test_security_headers_middleware():
    """HTTP middleware adds all security response headers."""

    async def call_next(_request):
        return JSONResponse({"ok": True})

    response = asyncio.run(
        web_app.security_headers_middleware(SimpleNamespace(), call_next)
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["permissions-policy"]
