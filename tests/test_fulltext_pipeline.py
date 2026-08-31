"""Offline regression tests for screening queues and persistent PDF quotas."""

import os
import tempfile
from types import SimpleNamespace

import pytest

from db.database import DatabaseClient
from pipeline.phase_e import phase_e_llm_relevance
from pipeline.phase_e3 import phase_e3_fulltext_relevance
import pipeline.phase_e2 as phase_e2_module
from processors.paper_relevance import PaperRelevanceChecker


@pytest.fixture
def db():
    """Create an isolated database for quota tests."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    client = DatabaseClient(path)
    client.init_db_papers()
    yield client
    client.close()
    os.unlink(path)


def _paper(db, doi, publisher="aps", pdf_url="https://example.test/a.pdf"):
    db.insert_rss_basicinfo(doi, doi, "https://example.test", "J", publisher, "2026-01-01")
    db.conn.execute("UPDATE papers SET pdf_url = ? WHERE doi = ?", (pdf_url, doi))
    db.conn.commit()


def test_candidate_queue_excludes_medium_d_and_orders_categories(db):
    _paper(db, "10/x/c")
    _paper(db, "10/x/d")
    _paper(db, "10/x/a")
    db.update_relevance_screen("10/x/c", "C", "[]", "high", "", "success", "now")
    db.update_relevance_screen("10/x/d", "D", "[]", "medium", "", "success", "now")
    db.update_relevance_screen("10/x/a", "A", "[]", "high", "", "success", "now")
    candidates = db.get_relevance_screen_candidates()
    assert [row["doi"] for row in candidates] == ["10/x/a", "10/x/c"]


def test_download_quota_persists_failed_attempts_and_publisher_limit(db):
    assert db.claim_fulltext_download("10/x/1", "aps", 3, 2)
    db.finish_fulltext_download("10/x/1", "failed", "timeout")
    assert db.claim_fulltext_download("10/x/2", "aps", 3, 2)
    assert not db.claim_fulltext_download("10/x/3", "aps", 3, 2)
    assert db.claim_fulltext_download("10/x/4", "optica", 3, 2)
    assert not db.claim_fulltext_download("10/x/5", "nature", 3, 2)
    assert db.conn.execute(
        "SELECT COUNT(*) FROM fulltext_download_events"
    ).fetchone()[0] == 3


def test_accepted_paper_audit_does_not_consume_quota(db):
    """A post-redirect Accepted Paper remains audited but frees capacity."""
    assert db.claim_fulltext_download("10/x/accepted", "aps", 1, 1)
    db.finish_fulltext_download(
        "10/x/accepted", "skipped", "not_yet_published: Accepted Paper",
        {"failure_kind": "not_yet_published"},
    )

    assert db.claim_fulltext_download("10/x/published", "aps", 1, 1)


def test_failed_download_history_keeps_doi_and_local_date(db):
    """MinerU failure history exposes DOI-level dates for alerting."""
    db.conn.execute(
        "INSERT INTO fulltext_download_events "
        "(doi, publisher, local_date, attempted_at, status, error) "
        "VALUES (?, ?, ?, ?, 'failed', ?)",
        ("10/x/mineru", "aps", "2026-08-17", "2026-08-17T02:00:00", "timeout"),
    )
    db.conn.commit()

    failures = db.get_fulltext_download_failures("2026-08-17")

    assert failures == [{
        "doi": "10/x/mineru",
        "local_date": "2026-08-17",
        "error": "timeout",
    }]


def test_candidate_queue_prioritizes_new_over_backfill(db):
    """New work must consume quota before historical backfill."""
    _paper(db, "10/x/old")
    _paper(db, "10/x/new")
    for doi in ("10/x/old", "10/x/new"):
        db.update_relevance_screen(
            doi, "A", "[]", "high", "", "success", "now",
        )
    db.conn.execute(
        "UPDATE papers SET relevance_screen_is_backfill = 1 WHERE doi = ?",
        ("10/x/old",),
    )
    db.conn.commit()
    candidates = db.get_relevance_screen_candidates()
    assert [row["doi"] for row in candidates] == ["10/x/new", "10/x/old"]


def test_migration_repairs_legacy_snapshot_backfill_flag(db):
    """An early migrated snapshot must not compete with genuinely new work."""
    _paper(db, "10/x/legacy")
    _paper(db, "10/x/fresh")
    db.conn.execute(
        """UPDATE papers SET relevance_screen_status = 'success',
            relevance_screen_category = 'A', relevance_screen_date = 'old',
            llm_relevance_status = 'success', llm_relevance_category = 'A',
            llm_relevance_date = 'old', relevance_screen_is_backfill = 0
            WHERE doi = '10/x/legacy'"""
    )
    db.conn.execute(
        """UPDATE papers SET relevance_screen_status = 'success',
            relevance_screen_category = 'A', relevance_screen_date = 'new',
            llm_relevance_status = 'success', llm_relevance_category = 'A',
            llm_relevance_date = 'old', relevance_screen_is_backfill = 0
            WHERE doi = '10/x/fresh'"""
    )
    db.conn.commit()

    db.migrate_relevance_screen_snapshot()

    flags = dict(db.conn.execute(
        "SELECT doi, relevance_screen_is_backfill FROM papers"
    ).fetchall())
    assert flags["10/x/legacy"] == 1
    assert flags["10/x/fresh"] == 0


def test_migration_reopens_legacy_abstract_fallback(db):
    """Legacy abstract-only decisions must wait for full-text adjudication."""
    _paper(db, "10/x/legacy-fallback")
    db.update_relevance_screen(
        "10/x/legacy-fallback", "B", '["plasma_diagnostics"]', "medium",
        "screen result", "success", "now",
    )
    db.update_llm_relevance(
        "10/x/legacy-fallback", "B", '["plasma_diagnostics"]', "medium",
        "legacy fallback", "success", "now", basis="abstract_fallback",
    )
    db.update_llm_summary(
        "10/x/legacy-fallback", '{"one_sentence":"old"}', "success", "now",
    )

    db.init_db_papers()
    row = db.conn.execute(
        "SELECT * FROM papers WHERE doi = ?", ("10/x/legacy-fallback",),
    ).fetchone()
    assert row["relevance_screen_status"] == "success"
    assert row["relevance_screen_category"] == "B"
    assert row["llm_relevance_status"] == "pending"
    assert row["llm_relevance_basis"] is None
    assert row["llm_summary_status"] == "pending"


def test_download_quota_rejects_duplicate_doi_same_day(db):
    """Repeated/manual runs cannot reserve one paper twice in one day."""
    assert db.claim_fulltext_download("10/x/1", "aps", 3, 2)
    assert not db.claim_fulltext_download("10/x/1", "aps", 3, 2)
    assert db.conn.execute(
        "SELECT COUNT(*) FROM fulltext_download_events"
    ).fetchone()[0] == 1


def test_phase_e_terminal_medium_d_sets_final_result(db, monkeypatch):
    """A medium/high D must not leave final relevance pending forever."""
    _paper(db, "10/x/reject")
    db.conn.execute(
        "UPDATE papers SET abstract = 'Clearly unrelated work' WHERE doi = ?",
        ("10/x/reject",),
    )
    db.conn.commit()
    monkeypatch.setattr(
        PaperRelevanceChecker,
        "call_deepseek_api",
        lambda *args, **kwargs: (
            '{"PredictedCategory":"D","MatchedSubfields":[],'
            '"Confidence":"medium","Notes":"主旨明确属于领域外。"}'
        ),
    )
    phase_e_llm_relevance(db)
    row = db.conn.execute(
        "SELECT * FROM papers WHERE doi = ?", ("10/x/reject",),
    ).fetchone()
    assert row["relevance_screen_category"] == "D"
    assert row["llm_relevance_status"] == "success"
    assert row["llm_relevance_category"] == "D"
    assert row["llm_relevance_basis"] == "abstract_clear_reject"


def test_phase_e3_waits_for_candidate_pending_download(db):
    """Quota-deferred candidates remain pending instead of falling back."""
    _paper(db, "10/x/wait")
    db.update_relevance_screen(
        "10/x/wait", "A", "[]", "high", "初筛相关", "success", "now",
    )
    phase_e3_fulltext_relevance(db)
    row = db.conn.execute(
        "SELECT * FROM papers WHERE doi = ?", ("10/x/wait",),
    ).fetchone()
    assert row["llm_relevance_status"] == "pending"
    assert row["llm_relevance_basis"] is None


def test_phase_e3_keeps_terminal_parse_failure_pending(db):
    """A failed parse waits for a later MinerU retry or a manually added PDF."""
    _paper(db, "10/x/fallback", pdf_url="")
    db.update_relevance_screen(
        "10/x/fallback", "B", '["plasma_diagnostics"]', "medium",
        "具体仪器映射。", "success", "now",
    )
    db.update_mineru_error(
        "10/x/fallback", "No PDF URL", "skipped", "now",
    )
    phase_e3_fulltext_relevance(db)
    row = db.conn.execute(
        "SELECT * FROM papers WHERE doi = ?", ("10/x/fallback",),
    ).fetchone()
    assert row["llm_relevance_status"] == "pending"
    assert row["llm_relevance_category"] is None
    assert row["llm_relevance_basis"] is None


def test_phase_e2_reuses_imported_pdf_without_pdf_url(db, tmp_path, monkeypatch):
    """A manually imported PDF must bypass the network URL requirement."""
    doi = "10/x/local-pdf"
    _paper(db, doi, pdf_url="")
    db.update_relevance_screen(
        doi, "A", "[]", "high", "screen result", "success", "now",
    )

    mineru_dir = tmp_path / "mineru_output"
    sessions_dir = tmp_path / "sessions"
    safe_doi = doi.replace("/", "_")
    local_pdf = mineru_dir / safe_doi / "paper.pdf"
    local_pdf.parent.mkdir(parents=True)
    local_pdf.write_bytes(b"%PDF-1.7\nlocal test pdf")

    class FakeDownloader:
        """Minimal downloader used to prove no network download is needed."""

        def __init__(self, _session_dir):
            self.page = SimpleNamespace(wait_for_timeout=lambda _delay: None)

        def start_browser(self, _proxy):
            return None

        def download_pdf(self, *_args, **_kwargs):
            raise AssertionError("imported PDF should not be downloaded")

        def close(self):
            return None

    class FakeParser:
        """Minimal MinerU parser that writes the expected output file."""

        def __init__(self, _token):
            return None

        def parse_pdf(self, _pdf_path, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "full.md").write_text("# Local full text", encoding="utf-8")
            return output_dir

    monkeypatch.setattr(phase_e2_module, "MINERU_OUTPUT_DIR", mineru_dir)
    monkeypatch.setattr(phase_e2_module, "BROWSER_SESSION_DIR", sessions_dir)
    monkeypatch.setattr(phase_e2_module, "BasePublisherScraper", FakeDownloader)
    monkeypatch.setattr(phase_e2_module, "MinerUParser", FakeParser)
    monkeypatch.setitem(phase_e2_module.SCRAPER_MAP, "aps", (None, None, None))
    monkeypatch.setattr(phase_e2_module.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(phase_e2_module.CFG, "SKIP_PHASE_E2", False)
    monkeypatch.setattr(phase_e2_module.CFG, "MINERU_TOKEN", "test-token")
    monkeypatch.setattr(phase_e2_module.CFG, "FULLTEXT_DOWNLOAD_DELAY_MIN", 0)
    monkeypatch.setattr(phase_e2_module.CFG, "FULLTEXT_DOWNLOAD_DELAY_MAX", 0)

    phase_e2_module.phase_e2_mineru(db)

    row = db.conn.execute(
        "SELECT mineru_parse_status, mineru_output_dir FROM papers WHERE doi = ?",
        (doi,),
    ).fetchone()
    assert row["mineru_parse_status"] == "success"
    assert row["mineru_output_dir"] == f"mineru_output/{safe_doi}"
