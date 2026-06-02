"""
Phase E2: MinerU PDF full-text parsing.
"""

import random
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

from config import (
    SKIP_PHASE_E2, MINERU_TOKEN, BROWSER_SESSION_DIR, MINERU_OUTPUT_DIR,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import logger
from processors.mineru_paper_parser import MinerUParser
from sources.publisher import BasePublisherScraper


def phase_e2_mineru(db):
    """Download PDF and parse full text via MinerU API.

    Parameters
    ----------
    db : DatabaseClient
    """
    logger.info("--- Phase E2: MinerU PDF parsing ---")
    if SKIP_PHASE_E2:
        logger.info("Phase E2: SKIP_PHASE_E2=True, skipping")
        return

    if not MINERU_TOKEN:
        logger.info("Phase E2: MINERU_TOKEN not configured, skipping")
        return

    relevant_papers = db.get_relevant_papers()
    papers_with_pdf = [
        p for p in relevant_papers
        if p["pdf_url"] and p["mineru_parse_status"] == "pending"
    ]
    if not papers_with_pdf:
        logger.info("Phase E2: no PDFs pending")
        return

    logger.info(f"Phase E2: {len(papers_with_pdf)} PDFs pending")

    parser = MinerUParser(MINERU_TOKEN)

    dl_dir = BROWSER_SESSION_DIR / "mineru_download"
    dl_dir.mkdir(parents=True, exist_ok=True)
    downloader = BasePublisherScraper(dl_dir)
    downloader.start_browser()

    success_count = 0
    failed_count = 0

    try:
        for paper in papers_with_pdf:
            doi = paper["doi"]
            pdf_url = paper["pdf_url"]
            page_url = paper["page_url"]
            timestamp = str(datetime.now())
            pdf_path = None

            try:
                logger.info(f"Downloading PDF: {doi} ← {pdf_url}")
                pdf_bytes = downloader.download_pdf(pdf_url, page_url=page_url)

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    pdf_path = tmp.name

                safe_doi = doi.replace("/", "_").replace("\\", "_")
                mineru_output_dir = parser.parse_pdf(
                    pdf_path, output_dir=MINERU_OUTPUT_DIR / safe_doi,
                )
                full_md_path = mineru_output_dir / "full.md"

                if full_md_path.exists():
                    fulltext = full_md_path.read_text(encoding="utf-8")
                    rel_dir = str(mineru_output_dir.relative_to(MINERU_OUTPUT_DIR.parent))
                    db.update_mineru_result(
                        doi, fulltext, rel_dir,
                        FetchStatus.SUCCESS.value, timestamp,
                    )
                    success_count += 1
                    logger.info(f"MinerU success: {doi} ({len(fulltext)} chars)")
                else:
                    raise RuntimeError("MinerU output missing full.md")

                shutil.move(pdf_path, str(mineru_output_dir / "paper.pdf"))
                pdf_path = None

            except Exception as e:
                logger.warning(f"MinerU failed [{doi}]: {e}")
                db.update_mineru_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                )
                failed_count += 1
                try:
                    if pdf_path:
                        Path(pdf_path).unlink(missing_ok=True)
                except Exception:
                    pass

            delay = random.uniform(3, 8)
            time.sleep(delay)

    finally:
        downloader.close()

    logger.info(f"Phase E2 done: {success_count} success, {failed_count} failed")
