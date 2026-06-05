"""
Phase A: RSS Feed fetching and CrossRef journal querying.
"""

import json
from datetime import datetime, timedelta, date
from pathlib import Path

from config import (
    SKIP_PHASE_A_RSS, SKIP_PHASE_A_CR,
    RAW_RSS_DIR, SKIP_NATURE_NEWS, CROSSREF_LOOKBACK_DAYS,
    CROSSREF_MAILTO, DATA_DIR,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import logger
from sources.rss import RSSProcessor
from sources.crossref import CrossrefClient

JOURNAL_OVERRIDES_PATH = DATA_DIR / "journal_overrides.json"


def _load_journal_overrides():
    """Load per-journal enable/disable overrides from data/journal_overrides.json.

    Returns a dict keyed by journal id, with fields: enabled, rss_enabled, cr_enabled.
    Missing keys fall back to publishers.yaml defaults.
    """
    if not JOURNAL_OVERRIDES_PATH.exists():
        return {}
    try:
        return json.loads(JOURNAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return {}


def _journal_effective(journal, overrides, field):
    """Resolve effective setting for a journal field.

    Priority: journal_overrides.json > publishers.yaml.
    ``field`` is one of 'enabled', 'rss_enabled', 'cr_enabled'.
    For 'rss_enabled'/'cr_enabled', falls back to 'enabled' if not specified.
    """
    jid = journal["id"]
    ov = overrides.get("journals", {}).get(jid, {})
    if field in ov:
        return ov[field]
    if field in ("rss_enabled", "cr_enabled") and "enabled" in ov:
        return ov["enabled"]
    return journal.get(field, True)


def phase_a_rss(db, publishers):
    """Fetch new papers from configured RSS feeds and store in database.

    Parameters
    ----------
    db : DatabaseClient
    publishers : list of dict
        Publisher configs from publishers.yaml.
    """
    if SKIP_PHASE_A_RSS:
        logger.info("Phase A-RSS: SKIP_PHASE_A_RSS=True, skipping")
        return
    logger.info("--- Phase A-RSS: RSS Feed fetch ---")
    rsspro = RSSProcessor()
    timestamp = datetime.now().strftime("%Y%m%d")
    overrides = _load_journal_overrides()

    for journal in publishers:
        if not _journal_effective(journal, overrides, "rss_enabled"):
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

    logger.info("Phase A-RSS done")


def phase_a_crossref(db, publishers):
    """Fetch papers from CrossRef by journal ISSN + date range.

    Daily incremental mode: queries from (today - CROSSREF_LOOKBACK_DAYS) to today.
    New DOIs are inserted with discovery_source='crossref'.
    Existing DOIs get discovery_source appended with ',crossref'.

    Parameters
    ----------
    db : DatabaseClient
    publishers : list of dict
        Publisher configs from publishers.yaml.
    """
    if SKIP_PHASE_A_CR:
        logger.info("Phase A-CR: SKIP_PHASE_A_CR=True, skipping")
        return
    logger.info("--- Phase A-CR: CrossRef journal query ---")

    timestamp = datetime.now().strftime("%Y%m%d")
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=CROSSREF_LOOKBACK_DAYS)).isoformat()
    logger.info(f"Query window: {from_date} ~ {to_date}")

    client = CrossrefClient(mailto=CROSSREF_MAILTO)
    overrides = _load_journal_overrides()

    for journal in publishers:
        if not _journal_effective(journal, overrides, "cr_enabled"):
            continue

        issn = journal.get("issn")
        if not issn:
            logger.debug(f"No ISSN configured for [{journal['id']}], skipping")
            continue

        journal_name = journal["name"]
        publisher = journal["publisher"]

        try:
            papers = client.fetch_by_journal(issn, from_date, to_date)
            logger.info(f"{journal['id']}: found {len(papers)} papers via CrossRef")

            for paper in papers:
                if not paper.doi:
                    continue
                if SKIP_NATURE_NEWS and "/d41586-" in (paper.doi or ""):
                    logger.debug(f"Skipping Nature news from CrossRef: {paper.doi}")
                    continue
                if db.paper_doi_exists(paper.doi):
                    db.append_discovery_source(paper.doi, "crossref")
                else:
                    db.insert_paper_basicinfo(
                        doi=paper.doi,
                        title=paper.title or "",
                        link=paper.url or "",
                        journal=journal_name,
                        publisher=publisher,
                        date=paper.published,
                        source="crossref",
                    )
                    db.insert_paper_created_date(paper.doi, timestamp)

        except Exception as e:
            logger.error(f"CrossRef journal query failed [{journal['id']}]: {e}")

    logger.info("Phase A-CR done")
