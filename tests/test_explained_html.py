"""
Tests: Explained HTML report generator (report_explainer.py)

Coverage:
  - _format_weekday() — all 7 weekdays
  - _collect_dashboard_data() — structure, counts, ordering
  - write_explained_html() — happy path with real DB + template
  - Template variable contract — phase_status (5 items, correct names),
    weekly (7 items, ascending dates)
  - Edge cases: empty DB, no data for a day
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def db():
    """Create an in-memory DatabaseClient with a fresh ``papers`` table."""
    from db.database import DatabaseClient

    client = DatabaseClient(":memory:")
    client.init_db_papers()
    yield client
    client.close()


@pytest.fixture
def db_with_data(db):
    """Insert controlled test data into the in-memory database.

    Paper 1 — 20260720: all success, category A       → reportable on that day
    Paper 2 — 20260721: Crossref OK, Publisher failed → total_failed
    Paper 3 — 20260722: all success, category B       → reportable
    Paper 4 — 20260723: all pending                   → other
    Paper 5 — 20260724: A relevance, no summary       → pending_report
    Paper 6 — 20260725: all success, category C       → other (not reportable)
    Paper 7 — 20260726: all success, category A       → reportable
    """
    cursor = db.conn.cursor()
    papers = [
        ("10.1000/p1", "Paper 1", "pub_a", "20260720",
         "success", "success", "success", "A", "success", "success"),
        ("10.1000/p2", "Paper 2", "pub_b", "20260721",
         "success", "failed", "pending", None, "pending", "pending"),
        ("10.1000/p3", "Paper 3", "pub_a", "20260722",
         "success", "success", "success", "B", "success", "success"),
        ("10.1000/p4", "Paper 4", "pub_c", "20260723",
         "pending", "pending", "pending", None, "pending", "pending"),
        ("10.1000/p5", "Paper 5", "pub_a", "20260724",
         "success", "success", "success", "A", "pending", "pending"),
        ("10.1000/p6", "Paper 6", "pub_b", "20260725",
         "success", "success", "success", "C", "success", "success"),
        ("10.1000/p7", "Paper 7", "pub_a", "20260726",
         "success", "success", "success", "A", "success", "success"),
    ]
    cursor.executemany("""
        INSERT INTO papers (
            doi, title, publisher, created_date,
            cr_metadata_fetched_status, publisher_page_fetched_status,
            llm_relevance_status, llm_relevance_category,
            mineru_parse_status, llm_summary_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, papers)
    db.conn.commit()
    return db


# ======================================================================
# _format_weekday tests
# ======================================================================

class TestFormatWeekday:
    """Cover all 7 days of the week."""

    def test_monday(self):
        from processors.report_explainer import _format_weekday
        assert _format_weekday(date(2026, 7, 20)) == "Mon"

    def test_tuesday(self):
        from processors.report_explainer import _format_weekday
        assert _format_weekday(date(2026, 7, 21)) == "Tue"

    def test_wednesday(self):
        from processors.report_explainer import _format_weekday
        assert _format_weekday(date(2026, 7, 22)) == "Wed"

    def test_thursday(self):
        from processors.report_explainer import _format_weekday
        assert _format_weekday(date(2026, 7, 23)) == "Thu"

    def test_friday(self):
        from processors.report_explainer import _format_weekday
        assert _format_weekday(date(2026, 7, 24)) == "Fri"

    def test_saturday(self):
        from processors.report_explainer import _format_weekday
        assert _format_weekday(date(2026, 7, 25)) == "Sat"

    def test_sunday(self):
        from processors.report_explainer import _format_weekday
        assert _format_weekday(date(2026, 7, 26)) == "Sun"


# ======================================================================
# _collect_dashboard_data tests
# ======================================================================

class TestCollectDashboardData:
    """Structure, ordering, and count correctness."""

    def test_structure_with_data(self, db_with_data):
        """Returned dict must contain all required keys."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        expected_keys = {
            "date_str", "total_papers", "pending_report", "publishers_count",
            "phases_count", "phase_status", "weekly",
            "relevance_prompt", "summary_prompt", "generated_at",
        }
        assert set(data.keys()) == expected_keys, (
            f"Missing keys: {expected_keys - set(data.keys())}"
        )

    def test_counts(self, db_with_data):
        """Verify numeric aggregates match the fixture."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        assert data["total_papers"] == 7
        # pending_report = summary success + A/B relevance + not reported → p1, p3, p7
        assert data["pending_report"] == 3
        # Distinct publishers: pub_a, pub_b, pub_c
        assert data["publishers_count"] == 3
        assert data["phases_count"] == 5

    @pytest.mark.parametrize("expected_names", [
        ["CrossRef", "Publisher", "Relevance", "MinerU", "Summary"],
    ])
    def test_phase_status_names(self, db_with_data, expected_names):
        """Phase names must appear in the required order."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        names = [p["name"] for p in data["phase_status"]]
        assert names == expected_names

    def test_phase_status_length(self, db_with_data):
        """Exactly 5 phase entries."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        assert len(data["phase_status"]) == 5

    def test_phase_status_counts(self, db_with_data):
        """CrossRef: 7 success; Publisher: 5 success, 1 failed, 1 pending."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        phases = {p["name"]: p for p in data["phase_status"]}

        # CrossRef: 6 success (p4 pending), 1 pending
        assert phases["CrossRef"]["success"] == 6
        assert phases["CrossRef"]["failed"] == 0
        assert phases["CrossRef"]["skipped"] == 0
        assert phases["CrossRef"]["pending"] == 1

        # Publisher: p2 failed, p4 pending, rest success
        assert phases["Publisher"]["success"] == 5
        assert phases["Publisher"]["failed"] == 1
        assert phases["Publisher"]["pending"] == 1

        # Relevance: p2 pending, rest success (but p2's status is 'pending')
        # success: p1,p3,p5,p6,p7 = 5; pending: p2,p4 = 2
        assert phases["Relevance"]["success"] == 5
        assert phases["Relevance"]["pending"] == 2

        # Summary: p1 success, p2 pending, p3 success, p4 pending,
        #          p5 pending, p6 success, p7 success → 4 success, 3 pending
        assert phases["Summary"]["success"] == 4
        assert phases["Summary"]["pending"] == 3

    def test_weekly_length(self, db_with_data):
        """Exactly 7 entries (7 days)."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        assert len(data["weekly"]) == 7

    def test_weekly_ascending_dates(self, db_with_data):
        """Weekly dates must be in ascending order (earliest first)."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        dates = [w["date"] for w in data["weekly"]]
        assert dates == sorted(dates), "Weekly dates not in ascending order"
        # First date should be 20260720
        assert dates[0] == "20260720"
        assert dates[-1] == "20260726"

    def test_weekly_weekdays(self, db_with_data):
        """Verify weekday abbreviations for the known range."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        weekdays = [w["weekday"] for w in data["weekly"]]
        expected = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        assert weekdays == expected

    def test_weekly_reportable_counts(self, db_with_data):
        """Reportable papers (A/B + summary success) per day."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        by_date = {w["date"]: w for w in data["weekly"]}

        # 2026-07-20: paper 1 (A, success) → reportable=1
        assert by_date["20260720"]["reportable"] == 1
        # 2026-07-21: paper 2 (failed) → reportable=0
        assert by_date["20260721"]["reportable"] == 0
        # 2026-07-22: paper 3 (B, success) → reportable=1
        assert by_date["20260722"]["reportable"] == 1
        # 2026-07-23: paper 4 (all pending) → reportable=0
        assert by_date["20260723"]["reportable"] == 0
        # 2026-07-24: paper 5 (A, no summary) → reportable=0
        assert by_date["20260724"]["reportable"] == 0
        # 2026-07-25: paper 6 (C, success) → reportable=0
        assert by_date["20260725"]["reportable"] == 0
        # 2026-07-26: paper 7 (A, success) → reportable=1
        assert by_date["20260726"]["reportable"] == 1

    def test_weekly_failed_counts(self, db_with_data):
        """Papers with any phase failed."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        by_date = {w["date"]: w for w in data["weekly"]}

        # Only paper 2 (2026-07-21) has a failed phase
        assert by_date["20260721"]["total_failed"] == 1
        assert by_date["20260720"]["total_failed"] == 0

    def test_empty_db(self, db):
        """Empty database must return zeroes but valid structure."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db, "2026-07-26")
        assert data["total_papers"] == 0
        assert data["pending_report"] == 0
        assert data["publishers_count"] == 0
        assert len(data["phase_status"]) == 5
        assert len(data["weekly"]) == 7
        for p in data["phase_status"]:
            assert p["success"] == 0
            assert p["failed"] == 0
            assert p["skipped"] == 0
            assert p["pending"] == 0
        for w in data["weekly"]:
            assert w["reportable"] == 0
            assert w["total_failed"] == 0
            assert w["other"] == 0


# ======================================================================
# write_explained_html tests
# ======================================================================

class TestWriteExplainedHtml:
    """Integration-level tests with real template rendering."""

    def test_happy_path(self, db_with_data, tmp_path):
        """Write to a temp file and verify it's non-empty with expected strings."""
        from processors.report_explainer import write_explained_html

        html_path = tmp_path / "report_2026-07-26_explained.html"

        # Mock prompt rendering to avoid config dependencies
        mock_prompts = {
            "relevance": "RELEVANCE_PROMPT_MARKER",
            "summary": "SUMMARY_PROMPT_MARKER",
        }
        with patch(
            "processors.report_explainer.render_all_prompts",
            return_value=mock_prompts,
        ):
            write_explained_html(db_with_data, html_path)

        assert html_path.exists(), "HTML file was not created"
        content = html_path.read_text(encoding="utf-8")
        assert len(content) > 1024, (
            f"HTML too small: {len(content)} bytes"
        )

        # Check for required content
        assert "报告解释" in content or "report" in content.lower()
        assert "CrossRef" in content
        assert "Publisher" in content
        assert "Relevance" in content
        assert "MinerU" in content
        assert "Summary" in content
        assert "RELEVANCE_PROMPT_MARKER" in content
        assert "SUMMARY_PROMPT_MARKER" in content
        assert "2026-07-26" in content
        assert "Mon" in content or "Tue" in content

    def test_write_with_empty_db(self, db, tmp_path):
        """Empty database must still produce a valid HTML file."""
        from processors.report_explainer import write_explained_html

        html_path = tmp_path / "report_2026-07-26_explained.html"

        with patch(
            "processors.report_explainer.render_all_prompts",
            return_value={"relevance": "", "summary": ""},
        ):
            write_explained_html(db, html_path)

        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert len(content) > 500
        # All-zero dashboard should still render
        assert "0" in content

    def test_render_failure_propagates(self, db, tmp_path):
        """If template rendering fails, the exception propagates up.

        (The caller in phase_g.py wraps this in try/except, so propagation
        is the correct behavior.)
        """
        from processors.report_explainer import write_explained_html

        html_path = tmp_path / "report_2026-07-26_explained.html"

        # Make the template environment raise on render
        with patch(
            "processors.report_explainer._get_template_env",
            side_effect=RuntimeError("Simulated render failure"),
        ):
            with pytest.raises(RuntimeError, match="Simulated render failure"):
                write_explained_html(db, html_path)

        # The tmp file should NOT exist (write didn't happen)
        assert not html_path.exists()

    def test_atomic_write_cleanup(self, db, tmp_path):
        """The .tmp file should not remain after a successful write."""
        from processors.report_explainer import write_explained_html

        html_path = tmp_path / "report_2026-07-26_explained.html"
        tmp_file = html_path.with_suffix(html_path.suffix + ".tmp")

        with patch(
            "processors.report_explainer.render_all_prompts",
            return_value={"relevance": "", "summary": ""},
        ):
            write_explained_html(db, html_path)

        assert html_path.exists()
        assert not tmp_file.exists(), ".tmp file was not cleaned up"


# ======================================================================
# Template variable contract tests
# ======================================================================

class TestVariableContract:
    """Validate the full dict returned by _collect_dashboard_data."""

    @patch("processors.report_explainer.render_all_prompts",
           return_value={"relevance": "REL", "summary": "SUM"})
    def test_all_template_variables_present(self, mock_render, db_with_data):
        """Every variable used in the template must be present in the data dict."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")

        # These 11 variables are used in explained.html.j2 (verified by grep)
        required = {
            "date_str",          # {{ date_str }}
            "total_papers",      # {{ total_papers }}
            "pending_report",    # {{ pending_report }}
            "publishers_count",  # {{ publishers_count }}
            "phases_count",      # {{ phases_count }}
            "phase_status",      # {% for phase in phase_status %}
            "weekly",            # {% for day in weekly %}
            "relevance_prompt",  # {{ relevance_prompt | e }}
            "summary_prompt",    # {{ summary_prompt | e }}
            "generated_at",      # {{ generated_at }}
        }
        missing = required - set(data.keys())
        assert not missing, f"Template variables missing: {missing}"

    @patch("processors.report_explainer.render_all_prompts",
           return_value={"relevance": "REL", "summary": "SUM"})
    def test_phase_status_dict_keys(self, mock_render, db_with_data):
        """Each phase_status element must have the correct keys."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        required_keys = {"name", "success", "failed", "skipped", "pending"}
        for i, phase in enumerate(data["phase_status"]):
            missing = required_keys - set(phase.keys())
            assert not missing, (
                f"phase_status[{i}] ({phase.get('name', '?')}) "
                f"missing keys: {missing}"
            )

    @patch("processors.report_explainer.render_all_prompts",
           return_value={"relevance": "REL", "summary": "SUM"})
    def test_weekly_dict_keys(self, mock_render, db_with_data):
        """Each weekly element must have the correct keys."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        required_keys = {"date", "weekday", "reportable",
                         "total_failed", "other"}
        for i, day in enumerate(data["weekly"]):
            missing = required_keys - set(day.keys())
            assert not missing, (
                f"weekly[{i}] ({day.get('date', '?')}) "
                f"missing keys: {missing}"
            )

    @patch("processors.report_explainer.render_all_prompts",
           return_value={"relevance": "REL", "summary": "SUM"})
    def test_generated_at_format(self, mock_render, db_with_data):
        """generated_at must match YYYY-MM-DD HH:MM:SS."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        ts = data["generated_at"]
        assert len(ts) == 19, f"Unexpected timestamp length: {ts!r}"
        datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")  # raises on mismatch
