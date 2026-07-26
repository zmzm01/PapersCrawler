"""
report_explainer.py
===================
Explained HTML report generator.

Produces an HTML page (``report_<date>_explained.html``) that accompanies
the daily Markdown report, showing:

- Dashboard summary: total papers, pending reports, publisher count
- Phase status breakdown for all 5 pipeline stages
- 7-day collection history with reportable / failed / other counts
- Full Phase E (relevance) and Phase F (summary) prompt snapshots

Dependencies
------------
- ``_get_template_env()`` from ``paper_report_generator`` (reuses Jinja2 Environment)
- ``render_all_prompts()`` from ``prompt_explainer``
- ``DatabaseClient`` from ``db.database``
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from processors.paper_report_generator import _get_template_env
from processors.prompt_explainer import render_all_prompts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase status column mapping — order must match the template's expectation:
#   ["CrossRef", "Publisher", "Relevance", "MinerU", "Summary"]
# ---------------------------------------------------------------------------
_PHASE_CONFIGS: List[Dict[str, str]] = [
    {"name": "CrossRef",  "status_col": "cr_metadata_fetched_status"},
    {"name": "Publisher", "status_col": "publisher_page_fetched_status"},
    {"name": "Relevance", "status_col": "llm_relevance_status"},
    {"name": "MinerU",    "status_col": "mineru_parse_status"},
    {"name": "Summary",   "status_col": "llm_summary_status"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_weekday(d: date) -> str:
    """Return a 3-letter English weekday abbreviation.

    Parameters
    ----------
    d : date
        Any ``datetime.date`` instance.

    Returns
    -------
    str
        ``"Mon"``, ``"Tue"``, ``"Wed"``, ``"Thu"``, ``"Fri"``, ``"Sat"``,
        or ``"Sun"``.
    """
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return weekdays[d.weekday()]


# ---------------------------------------------------------------------------
# Dashboard data collector
# ---------------------------------------------------------------------------

def _collect_dashboard_data(db, date_str: str) -> Dict[str, Any]:
    """Collect all variables required by the ``explained.html.j2`` template.

    Queries the database for:

    - **total_papers** — all papers in the database.
    - **pending_report** — papers with successful summary + A/B relevance but not yet reported.
    - **publishers_count** — distinct non-empty ``publisher`` values.
    - **phase_status** — success/failed/skipped/pending counts per stage.
    - **weekly** — 7-day daily aggregates ending on ``date_str``.
    - **relevance_prompt** / **summary_prompt** — rendered via
      :func:`~processors.prompt_explainer.render_all_prompts`.
    - **generated_at** — current wall-clock timestamp.

    Parameters
    ----------
    db : DatabaseClient
        Open database client (must have an active ``conn``).
    date_str : str
        Report date in ``YYYY-MM-DD`` format.

    Returns
    -------
    dict
        Flat dictionary ready to pass to ``template.render(**data)``.
        See the module docstring for all keys.
    """
    conn = db.conn

    # ---- Total papers ----
    total_papers: int = conn.execute(
        "SELECT COUNT(*) FROM papers"
    ).fetchone()[0]

    # ---- Pending report: summary success + A/B relevance + not yet reported ----
    pending_report: int = conn.execute(
        "SELECT COUNT(*) FROM papers "
        "WHERE llm_summary_status = 'success' "
        "  AND report_date IS NULL "
        "  AND llm_relevance_status = 'success' "
        "  AND llm_relevance_category IN ('A', 'B')"
    ).fetchone()[0]

    # ---- Distinct publishers ----
    publishers_count: int = conn.execute(
        "SELECT COUNT(DISTINCT publisher) FROM papers "
        "WHERE publisher IS NOT NULL AND publisher != ''"
    ).fetchone()[0]

    # ---- Per-phase status counts ----
    phase_status: List[Dict[str, Any]] = []
    for cfg in _PHASE_CONFIGS:
        rows = conn.execute(
            f"SELECT COALESCE({cfg['status_col']}, 'pending') AS status, "
            f"       COUNT(*) AS cnt "
            f"FROM papers GROUP BY status"
        ).fetchall()
        counts: Dict[str, int] = {"success": 0, "failed": 0,
                                  "skipped": 0, "pending": 0}
        for r in rows:
            s = r["status"]
            if s in counts:
                counts[s] = r["cnt"]
        phase_status.append({
            "name": cfg["name"],
            "success": counts["success"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
            "pending": counts["pending"],
        })

    # ---- 7-day weekly stats (ending on the report date) ----
    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        report_date = date.today()
        logger.warning("Invalid date_str %r, falling back to today", date_str)

    weekly: List[Dict[str, Any]] = []
    for offset in range(6, -1, -1):
        day = report_date - timedelta(days=offset)
        day_str = day.strftime("%Y%m%d")

        # Single query with mutually exclusive categories:
        #   reportable  → A/B relevance + summary success (takes priority)
        #   total_failed → any phase failed, but NOT reportable
        #   other       → remainder (always non-negative)
        row = conn.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN llm_relevance_category IN ('A', 'B')
                                   AND llm_relevance_status = 'success'
                                   AND llm_summary_status = 'success'
                                 THEN 1 ELSE 0 END), 0) AS reportable,
                COALESCE(SUM(CASE WHEN llm_relevance_category IS NULL
                                   OR llm_relevance_category NOT IN ('A', 'B')
                                   OR llm_relevance_status IS NULL
                                   OR llm_relevance_status != 'success'
                                   OR llm_summary_status IS NULL
                                   OR llm_summary_status != 'success'
                                 THEN
                                     CASE WHEN cr_metadata_fetched_status = 'failed'
                                           OR publisher_page_fetched_status = 'failed'
                                           OR llm_relevance_status = 'failed'
                                           OR mineru_parse_status = 'failed'
                                           OR llm_summary_status = 'failed'
                                          THEN 1 ELSE 0 END
                                 ELSE 0 END), 0) AS total_failed
            FROM papers
            WHERE created_date = ?
        """, (day_str,)).fetchone()

        day_total = row["total"]
        reportable = row["reportable"]
        total_failed = row["total_failed"]
        other = day_total - reportable - total_failed

        weekly.append({
            "date": day_str,
            "weekday": _format_weekday(day),
            "reportable": reportable,
            "total_failed": total_failed,
            "other": other,
        })

    # ---- Prompts ----
    prompts = render_all_prompts()

    return {
        "date_str": date_str,
        "total_papers": total_papers,
        "pending_report": pending_report,
        "publishers_count": publishers_count,
        "phases_count": 5,
        "phase_status": phase_status,
        "weekly": weekly,
        "relevance_prompt": prompts.get("relevance", ""),
        "summary_prompt": prompts.get("summary", ""),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_explained_html(db, html_path: Path) -> None:
    """Render the explained HTML report and write to ``html_path``.

    This is the single entry-point called by ``phase_g.py``.

    The caller (``phase_g_report``) wraps this call in a
    ``try/except``, so **this function does not catch exceptions** —
    any failure propagates up to the caller's warning handler.

    Parameters
    ----------
    db : DatabaseClient
        Open database client.
    html_path : Path
        Destination path for the generated HTML file.  Parent directories
        must exist (the caller creates them).

    Raises
    ------
    Exception
        Propagates any Jinja2 rendering or I/O error to the caller.
    """
    # Extract the report date from the output filename.
    # Expected filename pattern: report_YYYY-MM-DD_explained.html
    date_str = _extract_date_from_path(html_path)

    data = _collect_dashboard_data(db, date_str)

    env = _get_template_env()
    template = env.get_template("html/explained.html.j2")
    html = template.render(**data)

    # Atomic write: .tmp → rename (same pattern as phase_g.py)
    tmp_path = html_path.with_suffix(html_path.suffix + ".tmp")
    tmp_path.write_text(html, encoding="utf-8")
    tmp_path.replace(html_path)

    logger.debug("Explained HTML written: %s (%.1f KB)",
                 html_path.name, len(html) / 1024)


def _extract_date_from_path(path: Path) -> str:
    """Extract ``YYYY-MM-DD`` from a report filename.

    Parameters
    ----------
    path : Path
        Path like ``.../report_2026-07-26_explained.html``.

    Returns
    -------
    str
        Date string ``"2026-07-26"``.  Falls back to today on parse failure.
    """
    stem = path.stem  # e.g. "report_2026-07-26_explained"
    # Strip leading "report_" and trailing "_explained"
    # Expected: "report_2026-07-26_explained" → "2026-07-26"
    try:
        parts = stem.split("_", 1)  # ["report", "2026-07-26_explained"]
        if len(parts) >= 2:
            inner = parts[1]  # "2026-07-26_explained"
            # The date is the first 10 chars of the remainder
            candidate = inner[:10]
            # Validate
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate
    except (ValueError, IndexError):
        pass
    logger.warning("Could not extract date from %s, using today", path.name)
    return date.today().strftime("%Y-%m-%d")
