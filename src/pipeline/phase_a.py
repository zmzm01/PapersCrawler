"""
Phase A: RSS Feed fetching and CrossRef journal querying.
"""

from datetime import datetime, timedelta, date

import logging

from config import (
    CFG, RAW_RSS_DIR,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import load_journal_overrides, journal_effective
from sources.rss import RSSProcessor
from sources.crossref import CrossrefClient

logger = logging.getLogger(__name__)


def phase_a_rss(db, publishers, use_overrides=False):
    """Fetch new papers from configured RSS feeds and store in database.

    Parameters
    ----------
    db : DatabaseClient
    publishers : list of dict
        Publisher configs from publishers.yaml.
    use_overrides : bool
        是否从 journal_overrides.json 加载覆写。
        CLI (force=False) 时 False，只读 publishers.yaml。
        WebUI (force=True) 时 True，叠加 journal_overrides.json。
    """
    if CFG.SKIP_PHASE_A_RSS:
        logger.info("Phase A-RSS: CFG.SKIP_PHASE_A_RSS=True, skipping")
        return
    logger.info("--- Phase A-RSS: RSS Feed fetch ---")
    rsspro = RSSProcessor()
    timestamp = datetime.now().strftime("%Y%m%d")
    overrides = load_journal_overrides() if use_overrides else {}

    for journal in publishers:
        if not journal_effective(journal, overrides, "rss_enabled"):
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
                if db.is_doi_skipped(paperDOI):
                    logger.debug(f"DOI in skip list: {paperDOI}")
                    continue
                if CFG.SKIP_NATURE_NEWS and "/d41586-" in paperDOI:
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


def phase_a_crossref(db, publishers, use_overrides=False):
    """Fetch papers from CrossRef by journal ISSN + date range.

    Daily incremental mode: queries from (today - CFG.CROSSREF_LOOKBACK_DAYS) to today.
    New DOIs are inserted with discovery_source='crossref'.
    Existing DOIs get discovery_source appended with ',crossref'.

    Parameters
    ----------
    db : DatabaseClient
    publishers : list of dict
        Publisher configs from publishers.yaml.
    use_overrides : bool
        是否从 journal_overrides.json 加载覆写。
        CLI (force=False) 时 False，只读 publishers.yaml。
        WebUI (force=True) 时 True，叠加 journal_overrides.json。
    """
    if CFG.SKIP_PHASE_A_CR:
        logger.info("Phase A-CR: CFG.SKIP_PHASE_A_CR=True, skipping")
        return
    logger.info("--- Phase A-CR: CrossRef journal query ---")

    timestamp = datetime.now().strftime("%Y%m%d")
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=CFG.CROSSREF_LOOKBACK_DAYS)).isoformat()
    logger.info(f"Query window: {from_date} ~ {to_date}")

    client = CrossrefClient(mailto=CFG.CROSSREF_MAILTO)
    overrides = load_journal_overrides() if use_overrides else {}
    seen_issns = set()    # 去重：相同 ISSN 只请求一次

    for journal in publishers:
        if not journal_effective(journal, overrides, "cr_enabled"):
            continue

        issn = journal.get("issn")
        if not issn:
            logger.debug(f"No ISSN configured for [{journal['id']}], skipping")
            continue
        if issn in seen_issns:
            logger.debug(f"ISSN {issn} already queried, skipping [{journal['id']}]")
            continue
        seen_issns.add(issn)

        journal_name = journal["name"]
        publisher = journal["publisher"]

        try:
            papers = client.fetch_by_journal(issn, from_date, to_date)
            logger.info(f"{journal['id']}: found {len(papers)} papers via CrossRef")

            for paper in papers:
                if not paper.doi:
                    continue
                if CFG.SKIP_NATURE_NEWS and "/d41586-" in (paper.doi or ""):
                    logger.debug(f"Skipping Nature news from CrossRef: {paper.doi}")
                    continue
                if db.is_doi_skipped(paper.doi):
                    logger.debug(f"DOI in skip list: {paper.doi}")
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
