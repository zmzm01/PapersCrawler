"""
Phase A: RSS Feed fetching and CrossRef journal querying.
"""

import json
from datetime import datetime, timedelta, date

import logging

from config import (
    CFG, RAW_RSS_DIR, LAST_RUN_PATH, STATE_DIR,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import load_journal_overrides, journal_effective
from sources.rss import RSSProcessor
from sources.crossref import CrossrefClient

logger = logging.getLogger(__name__)


# ==================================================================
# Phase A-CR 智能回溯：故障补漏机制
# ==================================================================

def _load_last_run_date() -> str | None:
    """读取 Phase A-CR 上次成功运行的日期（YYYY-MM-DD）。

    首次运行（文件不存在）返回 None — 此时回溯窗口退化为 1 天。
    文件格式异常时记录警告并返回 None（保守行为）。
    """
    if not LAST_RUN_PATH.exists():
        return None
    try:
        with open(LAST_RUN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("last_successful_run")
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read {LAST_RUN_PATH.name}: {e}, "
                       f"falling back to default lookback")
        return None


def _save_last_run_date(run_date: str) -> None:
    """写入 Phase A-CR 成功运行的日期到 last_run.json。

    原子写入：先写 .tmp 再 rename，避免崩溃中途导致文件损坏。
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = LAST_RUN_PATH.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"last_successful_run": run_date}, f, indent=2)
        tmp_path.replace(LAST_RUN_PATH)
    except OSError as e:
        logger.warning(f"Failed to write {LAST_RUN_PATH.name}: {e}")


def _compute_lookback_days() -> int:
    """计算 Phase A-CR 本次实际回溯天数。

    决策逻辑：
      1. 无 last_run.json（首次运行）→ CROSSREF_LOOKBACK_DAYS（默认 1）
      2. last_run 距今 ≤ CROSSREF_LOOKBACK_DAYS → CROSSREF_LOOKBACK_DAYS
         （日常情况：每次都回溯 1 天）
      3. last_run 距今 > CROSSREF_LOOKBACK_DAYS → 按缺口回溯
         （故障补漏：自动覆盖遗漏日期）
      4. 实际值封顶 CROSSREF_LOOKBACK_DAYS_MAX（默认 7）
         （避免一次性拉太多导致 API 超限）
    """
    last_run = _load_last_run_date()
    if last_run is None:
        logger.info("No last_run record, using default lookback")
        return CFG.CROSSREF_LOOKBACK_DAYS

    try:
        last_date = date.fromisoformat(last_run)
    except ValueError:
        logger.warning(f"Invalid last_run date format: {last_run}, "
                       f"falling back to default lookback")
        return CFG.CROSSREF_LOOKBACK_DAYS

    days_since = (date.today() - last_date).days
    actual_lookback = max(CFG.CROSSREF_LOOKBACK_DAYS, days_since)
    actual_lookback = min(actual_lookback, CFG.CROSSREF_LOOKBACK_DAYS_MAX)

    if actual_lookback > CFG.CROSSREF_LOOKBACK_DAYS:
        logger.info(f"Last run was {days_since} day(s) ago, "
                    f"extending lookback to {actual_lookback} day(s) "
                    f"(capped at {CFG.CROSSREF_LOOKBACK_DAYS_MAX})")
    else:
        logger.debug(f"Lookback: {actual_lookback} day(s)")
    return actual_lookback


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
    lookback_days = _compute_lookback_days()
    from_date = (date.today() - timedelta(days=lookback_days)).isoformat()
    logger.info(f"Query window: {from_date} ~ {to_date} (lookback={lookback_days}d)")

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

    # 智能回溯：记录本次成功日期，供下次决策
    _save_last_run_date(to_date)
    logger.info("Phase A-CR done")
