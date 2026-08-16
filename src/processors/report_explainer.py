"""
report_explainer.py
===================
Explained HTML report generator.

Produces an HTML page (``report_<date>_explained.html``) that accompanies
the daily Markdown report, showing:

- Full Phase E (relevance) and Phase F (summary) prompt snapshots

History
-------
- 2026-07-25 (1st pass): Removed phase status chart and 7-day collection chart
  (per user feedback — no one reads them). Kept stats grid + prompt
  snapshots as the only "explain why this report looks this way" content.
- 2026-07-25 (2nd pass): Removed stats grid (total/pending/publishers) per
  same user feedback. Page now contains only the prompt snapshots, which is
  what readers actually want when cross-checking the report's judgements.

Dependencies
------------
- ``_get_template_env()`` from ``paper_report_generator`` (reuses Jinja2 Environment)
- ``render_all_prompts()`` from ``prompt_explainer``
- ``DatabaseClient`` from ``db.database``
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict

from processors.paper_report_generator import _get_template_env
from processors.prompt_explainer import render_all_prompts

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dashboard data collector
# ---------------------------------------------------------------------------

def _collect_dashboard_data(db, date_str: str) -> Dict[str, Any]:
    """Collect all variables required by the ``explained.html.j2`` template.

    Queries the database for:

    - **relevance_prompt** / **summary_prompt** — rendered via
      :func:`~processors.prompt_explainer.render_all_prompts`.
    - **generated_at** — current wall-clock timestamp.

    2026-07-25: removed all stats counters (total_papers / pending_report /
    publishers_count) per user feedback — the stats grid was not useful for
    readers. The function no longer takes meaningful use of ``db``, but the
    parameter is kept for API stability and future extensibility.

    Parameters
    ----------
    db : DatabaseClient
        Open database client (kept for API stability; no longer queried).
    date_str : str
        Report date in ``YYYY-MM-DD`` format.

    Returns
    -------
    dict
        Flat dictionary ready to pass to ``template.render(**data)``.
    """
    # ---- Prompts ----
    prompts = render_all_prompts()

    return {
        "date_str": date_str,
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
    """Extract a report date from a compact or ISO-format filename.

    Parameters
    ----------
    path : Path
        Path like ``.../report_20260726_explained.html`` or
        ``.../report_2026-07-26_explained.html``.

    Returns
    -------
    str
        Date string ``"2026-07-26"``.  Falls back to today on parse failure.
    """
    match = re.match(
        r"^report_(?P<date>\d{8}|\d{4}-\d{2}-\d{2})_explained$",
        path.stem,
    )
    if match:
        raw_date = match.group("date")
        date_format = "%Y%m%d" if len(raw_date) == 8 else "%Y-%m-%d"
        try:
            return datetime.strptime(raw_date, date_format).strftime("%Y-%m-%d")
        except ValueError:
            pass
    logger.warning("Could not extract date from %s, using today", path.name)
    return date.today().strftime("%Y-%m-%d")
