"""
Phase G: Report generation.

Two modes:
  - Auto (doi_list=None): pipeline daily run, writes to auto_dir, marks papers reported
  - User (doi_list provided): Web UI custom selection, writes to user_dir, no mark
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from config import CFG, load_keywords
from db.database import DatabaseClient
from processors.paper_report_generator import generate_report

logger = logging.getLogger(__name__)


def phase_g_report(db, auto_dir, user_dir, doi_list=None):
    """Generate Markdown report from summarized papers.

    Parameters
    ----------
    db : DatabaseClient
    auto_dir : Path
        Output directory for auto-generated daily reports.
    user_dir : Path
        Output directory for user-selected custom reports.
    doi_list : list of str, optional
        If provided, user-selected mode (write to user_dir, no mark).
        If None, auto mode (write to auto_dir, mark papers reported).
    """
    is_auto = doi_list is None
    if CFG.SKIP_PHASE_G and is_auto:
        logger.info("Phase G: SKIP_PHASE_G=True, skipping")
        return
    logger.info("--- Phase G: Report generation ---")

    if is_auto:
        papers = db.get_papers_for_report()
    else:
        placeholders = ",".join("?" for _ in doi_list)
        cur = db.conn.execute(
            f"SELECT * FROM papers WHERE llm_summary_status = 'success' AND doi IN ({placeholders})",
            doi_list,
        )
        papers = cur.fetchall()

    if not papers:
        if is_auto:
            logger.info("Phase G: no new summarized papers")
        else:
            logger.info("Phase G: no papers found for selected DOIs")
        return

    logger.info(f"Phase G: {len(papers)} papers for report")

    paper_list = []
    reported_dois = []
    for p in papers:
        summary = {}
        try:
            summary = json.loads(p["llm_summary_result"] or "{}")
        except json.JSONDecodeError:
            pass

        authors = []
        try:
            authors = json.loads(p["authors_json"] or "[]")
        except json.JSONDecodeError:
            pass

        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            authors = [a.get("name", "") for a in authors if a.get("name")]

        subfields = []
        try:
            subfields = json.loads(p["llm_relevance_subfields"] or "[]")
        except json.JSONDecodeError:
            pass

        paper_dict = {
            "title": p["title"] or "",
            "authors": authors,
            "date": (
                p["paperdate_crossref"]
                or p["paperdate_page"]
                or p["paperdate_rss"]
                or ""
            ),
            "doi": p["doi"] or "",
            "journal": p["journal"] or "",
            "publisher": p["publisher"] or "",
            "matched_subdomains": subfields,
            "page_url": p["page_url"] or "",
            "pdf_url": p["pdf_url"] or "",
            "abstract": p["abstract"] or "",
            "one_sentence": summary.get("one_sentence", ""),
            "motivation_and_goal": summary.get("motivation_and_goal", ""),
            "key_setup_and_method": summary.get("key_setup_and_method", ""),
            "main_results_and_physics": summary.get("main_results_and_physics", ""),
            "take_home_message": summary.get("take_home_message", ""),
        }
        paper_list.append(paper_dict)
        reported_dois.append(p["doi"])

    # 按期刊 + 日期排序
    paper_list.sort(key=lambda p: (p.get("journal", "") or "", p.get("date", "") or ""))

    if is_auto:
        out_dir = Path(auto_dir)
        date_str = datetime.now().strftime("%Y%m%d")
        md_path = out_dir / f"report_{date_str}.md"
        report_timestamp = str(datetime.now())
        db.mark_papers_reported(reported_dois, report_timestamp)
        logger.info(f"Marked {len(reported_dois)} papers as reported")
    else:
        out_dir = Path(user_dir)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_path = out_dir / f"report_{timestamp_str}.md"

    out_dir.mkdir(parents=True, exist_ok=True)

    # 加载子领域定义用于分组报告；无 scope_definition 时回退平铺模式
    scope_definition = load_keywords().get("scope_definition")
    md_report = generate_report(
        paper_list, format="markdown", toc=True,
        scope_definition=scope_definition,
    )
    md_path.write_text(md_report, encoding="utf-8")
    logger.info(f"Report saved: {md_path}")

    logger.info(f"Phase G done: {len(paper_list)} papers in report")
