"""
Tests: Explained HTML report generator (report_explainer.py)

Coverage:
  - _collect_dashboard_data() — structure, counts
  - write_explained_html() — happy path with real DB + template
  - Template variable contract — keys used by explained.html.j2
  - Edge cases: empty DB

History:
  - 2026-07-25: Removed TestFormatWeekday, phase_status, weekly tests
    (per user feedback — chart sections removed; the data collectors and
    their tests are no longer needed).
"""

from __future__ import annotations

from datetime import datetime
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
# _collect_dashboard_data tests
# ======================================================================

class TestCollectDashboardData:
    """Structure correctness (stats counters removed 2026-07-25)."""

    def test_structure_with_data(self, db_with_data):
        """Returned dict must contain only the post-stats-removal keys."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        # 2026-07-25 (2nd pass): stats grid removed, only prompts + meta remain.
        expected_keys = {
            "date_str", "relevance_prompt", "summary_prompt", "generated_at",
        }
        assert set(data.keys()) == expected_keys, (
            f"Extra keys: {set(data.keys()) - expected_keys}; "
            f"Missing keys: {expected_keys - set(data.keys())}"
        )


# ======================================================================
# write_explained_html tests
# ======================================================================


def test_extract_date_from_compact_report_filename():
    """Phase G 的 YYYYMMDD 文件名应被转换为 ISO 日期。"""
    from processors.report_explainer import _extract_date_from_path

    assert _extract_date_from_path(
        Path("report_20260816_explained.html")
    ) == "2026-08-16"

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
        assert len(content) > 512, (
            f"HTML too small: {len(content)} bytes"
        )

        # Core content present
        assert "报告解释" in content
        assert "RELEVANCE_PROMPT_MARKER" in content
        assert "SUMMARY_PROMPT_MARKER" in content
        assert "2026-07-26" in content

        # 2026-07-25: chart sections removed → these markers must NOT appear
        # 注意：CSS 中含 Menlo/Monaco/monospace，'Mon' 子串会假阳性，改为检查更具体的标记
        assert "CrossRef" not in content, "phase chart 'CrossRef' leaked"
        assert "Publisher" not in content, "phase chart 'Publisher' leaked"
        assert "MinerU" not in content, "phase chart 'MinerU' leaked"
        # 周历图例/标题（中文标记，比英文 weekday 子串更精确）
        assert "近 7 天采集" not in content, "weekly chart title leaked"
        assert "可报告" not in content, "weekly chart legend '可报告' leaked"
        assert "处理失败" not in content, "weekly chart legend '处理失败' leaked"
        # 阶段图例
        assert "阶段状态" not in content, "phase chart title leaked"
        assert "待处理" not in content, "phase chart legend '待处理' leaked"
        # 2026-07-25 (2nd pass): stats grid removed → 这些 stat-card 标记不应出现
        assert "总论文" not in content, "stat-card '总论文' leaked"
        assert "待报告" not in content, "stat-card '待报告' leaked"
        assert "出版社" not in content, "stat-card '出版社' leaked"

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
    """Validate the dict returned by _collect_dashboard_data."""

    @patch("processors.report_explainer.render_all_prompts",
           return_value={"relevance": "REL", "summary": "SUM"})
    def test_all_template_variables_present(self, mock_render, db_with_data):
        """Every variable used in the template must be present in the data dict."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")

        # 2026-07-25 (2nd pass): 4 variables after stats grid removal
        required = {
            "date_str",          # {{ date_str }}
            "relevance_prompt",  # {{ relevance_prompt | e }}
            "summary_prompt",    # {{ summary_prompt | e }}
            "generated_at",      # {{ generated_at }}
        }
        missing = required - set(data.keys())
        assert not missing, f"Template variables missing: {missing}"

    @patch("processors.report_explainer.render_all_prompts",
           return_value={"relevance": "REL", "summary": "SUM"})
    def test_generated_at_format(self, mock_render, db_with_data):
        """generated_at must match YYYY-MM-DD HH:MM:SS."""
        from processors.report_explainer import _collect_dashboard_data

        data = _collect_dashboard_data(db_with_data, "2026-07-26")
        ts = data["generated_at"]
        assert len(ts) == 19, f"Unexpected timestamp length: {ts!r}"
        datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")  # raises on mismatch
