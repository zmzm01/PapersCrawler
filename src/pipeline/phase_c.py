"""
Phase C: Publisher page scraping via cloakbrowser.
"""

import json
import random
import time
from collections import defaultdict
from datetime import datetime

from config import (
    SKIP_PHASE_C, MAX_PAPERS_PER_PHASE,
    PUBLISHER_PAGE_DELAY_MIN, PUBLISHER_PAGE_DELAY_MAX,
    PUBLISHER_MAX_CONSECUTIVE_FAILURES,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import logger, create_scraper
from sources.publisher import NonResearchPageError, PageParseError

# Keywords to detect non-research articles (Erratum, etc.)
_NON_RESEARCH_KEYWORDS = ["erratum", "comment on", "response to", "publisher's note"]


def phase_c_publisher(db):
    """Scrape publisher pages for abstracts and PDF links.

    Parameters
    ----------
    db : DatabaseClient
    """
    logger.info("--- Phase C: Publisher page scraping ---")
    if SKIP_PHASE_C:
        logger.info("Phase C: SKIP_PHASE_C=True, skipping")
        return

    paper_tasks = db.get_pendings("publisher_page_fetched_status")
    if MAX_PAPERS_PER_PHASE:
        paper_tasks = paper_tasks[:MAX_PAPERS_PER_PHASE]
    if not paper_tasks:
        logger.info("Phase C: no pending papers")
        return

    logger.info(f"Phase C: {len(paper_tasks)} papers pending")

    paper_tasks_grouped = defaultdict(list)
    for paper_task in paper_tasks:
        key = paper_task["publisher"] or "unknown"
        paper_tasks_grouped[key].append(paper_task)

    for publisher, papers in paper_tasks_grouped.items():
        logger.info(f"Processing publisher: {publisher} ({len(papers)} papers)")

        scraper = None
        try:
            scraper = create_scraper(publisher)
        except (ValueError, Exception) as e:
            logger.error(f"Cannot create scraper for {publisher}: {e}")
            timestamp = str(datetime.now())
            for paper in papers:
                try:
                    db.update_error_message(
                        paper["doi"], "publisher_page_fetched_status",
                        FetchStatus.FAILED.value,
                        "publisher_page_fetched_error", str(e),
                        "publisher_page_fetched_date", timestamp,
                    )
                except Exception:
                    pass
            continue

        try:
            consecutive_failures = 0
            for paper in papers:
                paperDOI = paper["doi"]
                page_url = paper["page_url"]
                timestamp = str(datetime.now())

                if not page_url:
                    logger.warning(f"No page URL, skipping: {paperDOI}")
                    db.update_process_status(
                        paperDOI, "publisher_page_fetched_status",
                        FetchStatus.FAILED.value,
                        "publisher_page_fetched_date", timestamp,
                    )
                    continue

                paper_succeeded = False
                paper_skipped = False
                last_error = None

                for attempt in range(3):
                    try:
                        if attempt == 0:
                            timeout = 5000
                            cooloff = 0
                        elif attempt == 1:
                            timeout = 15000
                            cooloff = 0
                        else:
                            timeout = 45000
                            cooloff = random.uniform(120, 180)
                            logger.debug(f"Cooling {cooloff:.0f}s before retry 3 [{paperDOI}]")
                            time.sleep(cooloff)
                        scraper.fetch_page(page_url, timeout=timeout)
                        paperPage = scraper.parse_page()

                        cf_blocked = (
                            "challenge-platform" in scraper.html
                            or "_cf_chl_opt" in scraper.html
                            or "cf-browser-verification" in scraper.html
                        )
                        if cf_blocked:
                            logger.warning(f"Cloudflare detected (attempt {attempt+1}/3) [{paperDOI}]")
                            if attempt < 2:
                                continue
                            raise PageParseError(
                                "Title, DOI and Abstract all empty (possible CF block)"
                            )
                        if not paperPage.title and not paperPage.doi and not paperPage.abstract:
                            if attempt < 2:
                                continue
                            raise PageParseError("Title, DOI and Abstract all empty")

                        title_lower = (paperPage.title or "").lower()
                        abstract_text = (paperPage.abstract or "").strip()
                        if not abstract_text and any(
                            kw in title_lower for kw in _NON_RESEARCH_KEYWORDS
                        ):
                            raise NonResearchPageError(
                                f"Non-research page (keyword: {paperPage.title})"
                            )

                        consecutive_failures = 0
                        authors_json = (
                            json.dumps(paperPage.authors, ensure_ascii=False)
                            if paperPage.authors else "[]"
                        )
                        db.update_publisher_page(
                            paperDOI, paperPage.abstract or "",
                            authors_json, paperPage.pdf_url or "",
                            paperPage.date or "",
                            FetchStatus.SUCCESS.value, timestamp,
                        )
                        paper_succeeded = True
                        logger.info(f"Publisher page OK: {paperDOI}")
                        break

                    except NonResearchPageError:
                        consecutive_failures = 0
                        logger.info(f"Non-research page, skipped: {paperDOI}")
                        db.update_error_message(
                            paperDOI, "publisher_page_fetched_status",
                            FetchStatus.SKIPPED.value,
                            "publisher_page_fetched_error",
                            "NonResearchPageError: not a research article",
                            "publisher_page_fetched_date", timestamp,
                        )
                        db.update_process_status(
                            paperDOI, "semantic_filter_status",
                            FetchStatus.SKIPPED.value,
                            "semantic_filter_date", timestamp,
                        )
                        db.update_process_status(
                            paperDOI, "llm_relevance_status",
                            FetchStatus.SKIPPED.value,
                            "llm_relevance_date", timestamp,
                        )
                        paper_skipped = True
                        logger.info(f"Non-research page, downstream phases cascaded: {paperDOI}")
                        break

                    except Exception as e:
                        last_error = e
                        if attempt == 0:
                            continue
                        break

                if not paper_succeeded and not paper_skipped:
                    error_msg = str(last_error) if last_error else "Unknown error"
                    if isinstance(last_error, PageParseError):
                        logger.warning(f"Phase C page parse error [{paperDOI}]: {error_msg}")
                    else:
                        logger.warning(f"Phase C scrape failed after 3 attempts [{paperDOI}]: {error_msg}")
                    db.update_error_message(
                        paperDOI, "publisher_page_fetched_status",
                        FetchStatus.FAILED.value,
                        "publisher_page_fetched_error", error_msg[:500],
                        "publisher_page_fetched_date", timestamp,
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= PUBLISHER_MAX_CONSECUTIVE_FAILURES:
                        logger.warning(f"Publisher {publisher}: {consecutive_failures} consecutive failures, aborting")
                        break

                delay = random.uniform(PUBLISHER_PAGE_DELAY_MIN, PUBLISHER_PAGE_DELAY_MAX)
                logger.debug(f"Delay {delay:.1f}s...")
                time.sleep(delay)

        finally:
            if scraper:
                try:
                    scraper.close()
                except Exception:
                    pass

        logger.info(f"Publisher {publisher} done, cooling 15s...")
        time.sleep(15)

    logger.info("Phase C done")
