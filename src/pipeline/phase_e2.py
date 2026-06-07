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
from pipeline.base import logger, SCRAPER_MAP
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

    # Group papers by publisher for per-publisher scraper with proper proxy
    papers_by_publisher = {}
    for p in papers_with_pdf:
        publisher = p["publisher"] or "__unknown__"
        papers_by_publisher.setdefault(publisher, []).append(p)

    success_count = 0
    failed_count = 0

    for publisher, group in papers_by_publisher.items():
        # 使用独立 session 目录，不碰 publisher 主缓存
        dl_dir = BROWSER_SESSION_DIR / "mineru_download" / publisher
        dl_dir.mkdir(parents=True, exist_ok=True)
        downloader = BasePublisherScraper(dl_dir)

        # 从 SCRAPER_MAP 查代理配置，不复用 session
        scraper_config = SCRAPER_MAP.get(publisher)
        proxy = scraper_config[2] if scraper_config else None

        logger.info(f"Phase E2: launching browser for '{publisher}' ({len(group)} papers)")
        try:
            downloader.start_browser(proxy)
            logger.info(f"Phase E2: browser ready for '{publisher}'")
        except Exception as e:
            logger.error(f"Phase E2: browser launch failed for '{publisher}': {e}")
            for paper in group:
                db.update_mineru_error(
                    paper["doi"], f"Browser launch failed: {e}"[:500],
                    FetchStatus.FAILED.value, str(datetime.now()),
                )
                failed_count += 1
            try:
                downloader.close()
            except Exception:
                pass
            continue

        try:
            for paper in group:
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
                    del pdf_bytes  # 释放 PDF 原始字节，避免堆积在内存中

                    safe_doi = doi.replace("/", "_").replace("\\", "_").replace("..", "_")
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
            try:
                downloader.close()
            except Exception:
                pass

    logger.info(f"Phase E2 done: {success_count} success, {failed_count} failed")
