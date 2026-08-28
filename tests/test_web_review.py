"""Integration tests for the manual relevance review WebUI."""

import asyncio
import importlib

from starlette.requests import Request

from db.database import DatabaseClient, FetchStatus


web_app = importlib.import_module("web.app")


def _seed_review_paper(database_path, data_dir):
    """Create one full-text relevance paper in a temporary database."""
    doi = "10.0000/web-review"
    output_dir = "mineru_output/web-review"
    with DatabaseClient(database_path) as database:
        database.init_db_papers()
        database.insert_rss_basicinfo(
            doi, "Web Review Paper", "https://example.com/paper",
            "Journal", "publisher", "2026-08-20",
        )
        database.update_relevance_screen(
            doi, "B", "[]", "medium", "screen reason",
            FetchStatus.SUCCESS.value, "2026-08-20",
        )
        database.update_mineru_result(
            doi, "# Full text", output_dir,
            FetchStatus.SUCCESS.value, "2026-08-20",
        )
        database.update_llm_relevance(
            doi, "B", "[]", "medium", "final reason",
            FetchStatus.SUCCESS.value, "2026-08-20", basis="fulltext",
        )
    fulltext_path = data_dir / output_dir / "full.md"
    fulltext_path.parent.mkdir(parents=True)
    fulltext_path.write_text("# Full text evidence", encoding="utf-8")
    return doi


def _make_request(path):
    """Build the minimal Starlette request scope used by route tests."""
    return Request({
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "root_path": "",
        "http_version": "1.1",
    })


def test_manual_review_queue_and_detail_render(tmp_path, monkeypatch):
    """Queue and detail pages show the seeded paper and safe full text."""
    database_path = tmp_path / "papers.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    doi = _seed_review_paper(database_path, data_dir)
    monkeypatch.setattr(web_app, "DB_PATH", database_path)
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)

    queue_response = asyncio.run(
        web_app.relevance_review_page(_make_request("/relevance-review"))
    )
    detail_response = asyncio.run(
        web_app.relevance_review_detail(
            _make_request(f"/relevance-review/{doi}"), doi,
        )
    )

    assert queue_response.status_code == 200
    assert "Web Review Paper" in queue_response.body.decode()
    assert detail_response.status_code == 200
    assert "Full text evidence" in detail_response.body.decode()


def test_manual_review_post_appends_audit_record(tmp_path, monkeypatch):
    """POST saves a review while leaving the LLM category unchanged."""
    database_path = tmp_path / "papers.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    doi = _seed_review_paper(database_path, data_dir)
    monkeypatch.setattr(web_app, "DB_PATH", database_path)
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)

    response = asyncio.run(web_app.save_relevance_review(
        web_app.RelevanceReviewPayload(
            doi=doi,
            decision="A",
            reviewer="alice",
            notes="正文证据支持直接相关",
        )
    ))

    assert response.status_code == 200
    assert response.body == b'{"ok":true,"review_id":1}'
    with DatabaseClient(database_path) as database:
        row = database.get_relevance_review_queue(status_filter="reviewed")[0]
        assert row["review_decision"] == "A"
        assert row["llm_relevance_category"] == "B"


def test_papers_summary_filter_queries_before_pagination(tmp_path, monkeypatch):
    """The WebUI summary filter excludes pending summaries and keeps counts aligned."""
    database_path = tmp_path / "papers.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    doi = _seed_review_paper(database_path, data_dir)
    with DatabaseClient(database_path) as database:
        database.update_llm_summary(
            doi, '{"one_sentence":"done"}', FetchStatus.SUCCESS.value, "2026-08-20",
        )
        database.insert_rss_basicinfo(
            "10.0000/web-pending", "Pending Summary Paper",
            "https://example.com/pending", "Journal", "publisher", "2026-08-20",
        )
        database.update_llm_relevance(
            "10.0000/web-pending", "B", "[]", "medium", "reason",
            FetchStatus.SUCCESS.value, "2026-08-20", basis="fulltext",
        )
    monkeypatch.setattr(web_app, "DB_PATH", database_path)
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)

    response = asyncio.run(web_app.papers_page(
        _make_request("/papers?category=all&has_summary=true"),
        category="all", has_summary=True,
    ))

    body = response.body.decode()
    assert response.status_code == 200
    assert "Web Review Paper" in body
    assert "Pending Summary Paper" not in body
