"""
Phase G: Report generation.
"""

import json
from datetime import datetime
from pathlib import Path

from config import SKIP_PHASE_G
from db.database import DatabaseClient
from pipeline.base import logger
from processors.paper_report_generator import generate_report


def phase_g_report(db, report_dir):
    """Generate Markdown report from summarized papers.

    Parameters
    ----------
    db : DatabaseClient
    report_dir : Path
        Output directory for reports.
    """
    if SKIP_PHASE_G:
        logger.info("Phase G: SKIP_PHASE_G=True, skipping")
        return
    logger.info("--- Phase G: Report generation ---")

    papers = db.get_papers_for_report()
    if not papers:
        logger.info("Phase G: no new summarized papers")
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

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    md_report = generate_report(paper_list, format="markdown", toc=True)
    md_path = report_dir / f"report_{timestamp_str}.md"
    md_path.write_text(md_report, encoding="utf-8")
    logger.info(f"Report saved: {md_path}")

    report_timestamp = str(datetime.now())
    db.mark_papers_reported(reported_dois, report_timestamp)
    logger.info(f"Marked {len(reported_dois)} papers as reported")

    logger.info(f"Phase G done: {len(paper_list)} papers in report")
    logger.info(f"For PDF: python tools/convert_md_to_pdf.py {md_path}")
