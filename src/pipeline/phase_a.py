"""
Phase A: RSS Feed fetching.
"""

from datetime import datetime

from config import (
    SKIP_PHASE_A, RAW_RSS_DIR, SKIP_NATURE_NEWS,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import logger
from sources.rss import RSSProcessor


def phase_a_rss(db, publishers):
    """Fetch new papers from configured RSS feeds and store in database.

    Parameters
    ----------
    db : DatabaseClient
    publishers : list of dict
        Publisher configs from publishers.yaml.
    """
    if SKIP_PHASE_A:
        logger.info("Phase A: SKIP_PHASE_A=True, skipping")
        return
    logger.info("--- Phase A: RSS Feed fetch ---")
    rsspro = RSSProcessor()
    timestamp = datetime.now().strftime("%Y%m%d")

    for journal in publishers:
        if not journal.get("enabled", True):
            logger.info(f"Skipping disabled journal: "
                        f"{journal.get('name', journal.get('id', 'unknown'))}")
            continue

        journalid = journal["id"]
        publisher = journal["publisher"]
        rss_url = journal["rss"]
        journal_name = journal["name"]

        try:
            RAW_RSS_DIR.mkdir(parents=True, exist_ok=True)
            rss_file_save_path = RAW_RSS_DIR / f"{journalid}.xml"

            xml_text = rsspro.fetch_rss(rss_url)
            rsspro.save_raw_rss(xml_text, str(rss_file_save_path))

            papers = rsspro.parse_rss(xml_text, journal)
            if not papers:
                logger.warning(f"Empty RSS result [{journalid}]")
            logger.info(f"{journalid}: found {len(papers)} papers")

            for paper in papers:
                paperDOI = paper.doi
                if not paperDOI:
                    logger.debug(f"Skipping paper without DOI: {paper.title}")
                    continue
                if db.paper_doi_exists(paperDOI):
                    logger.debug(f"DOI already exists: {paperDOI}")
                    continue
                if SKIP_NATURE_NEWS and "/d41586-" in paperDOI:
                    logger.debug(f"Skipping Nature news: {paperDOI}")
                    continue
                db.insert_rss_basicinfo(
                    paperDOI, paper.title, paper.url,
                    journal_name, publisher, paper.date,
                )
                db.insert_paper_created_date(paperDOI, timestamp)

        except Exception as e:
            logger.error(f"RSS fetch failed [{journalid}]: {e}")

    logger.info("Phase A done")
