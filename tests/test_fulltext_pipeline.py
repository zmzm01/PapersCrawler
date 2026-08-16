"""Offline regression tests for screening queues and persistent PDF quotas."""

import os
import tempfile

import pytest

from db.database import DatabaseClient
from pipeline.phase_e import phase_e_llm_relevance
from pipeline.phase_e3 import phase_e3_fulltext_relevance
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
