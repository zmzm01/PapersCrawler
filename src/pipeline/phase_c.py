"""
Phase C: Publisher page scraping via cloakbrowser.
"""

import json
import logging
import random
import re
import time
from collections import defaultdict
from datetime import datetime

from config import CFG
from db.database import DatabaseClient, FetchStatus
from pipeline.base import SCRAPER_MAP, create_scraper
from sources.publisher import NonResearchPageError, AcceptedPaperError, PageParseError

logger = logging.getLogger(__name__)


def _extract_page_title(html):
    """从 HTML 中提取 <title> 内容。

    Parameters
    ----------
    html : str
        HTML 源码。

    Returns
    -------
    str
        页面标题（前 120 字符），提取失败返回空字符串。
    """
    try:
        mt = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if mt:
            return mt.group(1).strip()[:120]
    except Exception:
        pass
    return ""


def _has_bot_markers(html, page_title=""):
    """检查 HTML 中是否存在反爬挑战标记。

    覆盖以下反爬系统：
    - Cloudflare Challenge（challenge-platform、_cf_chl_opt、cf-browser-verification、
      cf-ray + 短 HTML、turnstile + challenge）
    - Radware Bot Manager（radware、bot manager）
    - Nature Client Challenge（client challenge 页面标题）
    - 通用 JS 禁用检测（javascript is disabled）

    Parameters
    ----------
    html : str
        页面 HTML 源码。
    page_title : str
        页面标题（可选），用于检测标题中的 bot 标记。

    Returns
    -------
    bool
        True 如果检测到 bot 拦截标记。
    """
    html_lower = html.lower()
    title_lower = page_title.lower()
    return (
        "challenge-platform" in html
        or "_cf_chl_opt" in html
        or "cf-browser-verification" in html
        or ("cf-ray" in html_lower and len(html) < 2000)
        or ("turnstile" in html_lower and "challenge" in html_lower)
        or "radware" in html_lower
        or "bot manager" in html_lower
        or "javascript is disabled" in html_lower
        or "radware" in title_lower
        or "bot manager" in title_lower
        or "captcha" in title_lower
        or "client challenge" in title_lower
    )


def phase_c_publisher(db, publishers):
    """Scrape publisher pages for abstracts and PDF links.

    Parameters
    ----------
    db : DatabaseClient
    publishers : list of dict
        Publisher configs from publishers.yaml.
        Used to check enabled/disabled status per publisher key.
    """
    logger.info("--- Phase C: Publisher page scraping ---")
    if CFG.SKIP_PHASE_C:
        logger.info("Phase C: CFG.SKIP_PHASE_C=True, skipping")
        return

    paper_tasks = db.get_pendings("publisher_page_fetched_status")
    if CFG.MAX_PAPERS_PER_PHASE:
        paper_tasks = paper_tasks[:CFG.MAX_PAPERS_PER_PHASE]
    if not paper_tasks:
        logger.info("Phase C: no pending papers")
        return

    logger.info(f"Phase C: {len(paper_tasks)} papers pending")

    # 构建已启用 publisher 集合：只要有任一期刊 enabled，该 publisher 就算启用
    enabled_publishers = {
        j["publisher"] for j in publishers
        if j.get("enabled", True)
    }

    paper_tasks_grouped = defaultdict(list)
    for paper_task in paper_tasks:
        key = paper_task["publisher"] or "unknown"
        paper_tasks_grouped[key].append(paper_task)

    for publisher, papers in paper_tasks_grouped.items():
        # 跳过已禁用的 publisher（不浪费浏览器启动时间）
        if publisher not in enabled_publishers:
            logger.info(f"Publisher {publisher} is disabled, skipping {len(papers)} papers")
            timestamp = str(datetime.now())
            for paper in papers:
                try:
                    db.update_error_message(
                        paper["doi"], "publisher_page_fetched_status",
                        FetchStatus.SKIPPED.value,
                        "publisher_page_fetched_error",
                        "Publisher disabled in publishers.yaml",
                        "publisher_page_fetched_date", timestamp,
                    )
                except Exception:
                    pass
            continue

        # ── CrossRef 摘要驱动跳过浏览器访问 ──
        # 对于已从 CrossRef 获取到有效摘要的 publisher（如 Optica OA 期刊），
        # 跳过浏览器访问以节省反爬额度并加速 Pipeline。
        # publisher 通过设置 Scraper 类属性 skip_phase_c_if_crossref_abstract=True
        # 来启用此优化。
        scraper_class = SCRAPER_MAP.get(publisher, (None,))[0]
        if (scraper_class
                and getattr(scraper_class, 'skip_phase_c_if_crossref_abstract', False)):
            skip_papers = []
            remain_papers = []
            for paper in papers:
                if (paper.get("cr_metadata_fetched_status") == "success"
                        and paper.get("abstract")):
                    skip_papers.append(paper)
                else:
                    remain_papers.append(paper)
            if skip_papers:
                timestamp = str(datetime.now())
                for paper in skip_papers:
                    db.update_process_status(
                        paper["doi"], "publisher_page_fetched_status",
                        FetchStatus.SKIPPED.value,
                        "publisher_page_fetched_date", timestamp,
                    )
                logger.info(
                    f"{publisher}: {len(skip_papers)}/{len(papers)} papers "
                    f"skipped (CrossRef has abstract)"
                )
            papers = remain_papers
            if not papers:
                logger.info(f"{publisher}: all papers skipped, no browser visit needed")
                continue

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
            is_first_in_group = True
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

                # First paper in publisher group: CF challenge needs long
                # initial verification, so skip 5s/15s attempts and go
                # straight to 45s + 2min cooldown.
                if is_first_in_group:
                    retry_attempts = [2]
                    logger.debug(f"First-in-group, extended timeout [{paperDOI}]")
                else:
                    retry_attempts = range(3)
                is_first_in_group = False

                paper_succeeded = False
                paper_skipped = False
                last_error = None

                # Pre-fetch non-research detection: check DB title before browser launch
                if CFG.PREFETCH_NON_RESEARCH:
                    paper_title = (paper["title"] or "").strip()
                    if paper_title:
                        title_lower = paper_title.lower()
                        for kw in CFG.NON_RESEARCH_KEYWORDS:
                            if title_lower.startswith(kw):
                                db.insert_skipped_doi(paperDOI, "NonResearchPreFetch", timestamp)
                                db.delete_paper(paperDOI)
                                logger.info(
                                    f"Non-research pre-fetch: {paperDOI}"
                                    f" | {paper_title[:80]}"
                                )
                                paper_skipped = True
                                break
                    if paper_skipped:
                        continue

                for attempt in retry_attempts:
                    try:
                        if attempt == 0:
                            timeout = 5000
                            cooloff = 0
                        elif attempt == 1:
                            timeout = 15000
                            cooloff = 0
                        else:
                            timeout = 45000
                            # First-in-group: no prior failure, skip cooldown
                            if len(retry_attempts) == 1:
                                logger.debug(f"Extended timeout 45s (first-in-group) [{paperDOI}]")
                            else:
                                cooloff = random.uniform(120, 180)
                                logger.debug(f"Cooling {cooloff:.0f}s before retry 3 [{paperDOI}]")
                                time.sleep(cooloff)
                        scraper.fetch_page(page_url, timeout=timeout)

                        # Always try parsing first — CF/bot markers in HTML
                        # (e.g. _cf_chl_opt from CDN scripts) do NOT necessarily
                        # mean the page is blocked.  Only treat as a bot block
                        # when parsing also returns empty results.
                        paperPage = scraper.parse_page()

                        if not paperPage.title and not paperPage.doi and not paperPage.abstract:
                            # Empty parse — check for bot detection patterns
                            page_title_snippet = _extract_page_title(scraper.html)

                            bot_blocked = _has_bot_markers(
                                scraper.html, page_title=page_title_snippet,
                            )

                            if bot_blocked:
                                logger.warning(
                                    f"Bot detection page (attempt "
                                    f"{'1/1' if len(retry_attempts) == 1 else f'{attempt+1}/{len(retry_attempts)}'})"
                                    f" [{paperDOI}]"
                                    + (f" | page title: {page_title_snippet}"
                                       if page_title_snippet else "")
                                )
                            else:
                                logger.warning(
                                    f"Empty parse result (attempt "
                                    f"{'1/1' if len(retry_attempts) == 1 else f'{attempt+1}/{len(retry_attempts)}'})"
                                    f" [{paperDOI}]"
                                )

                            if attempt < len(retry_attempts) - 1:
                                continue
                            raise PageParseError(
                                "Title, DOI and Abstract all empty"
                                + (" (bot block)" if bot_blocked else "")
                            )

                        if CFG.POSTFETCH_NON_RESEARCH:
                            title_lower = (paperPage.title or "").lower()
                            for kw in CFG.NON_RESEARCH_KEYWORDS:
                                if title_lower.startswith(kw):
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

                    except AcceptedPaperError:
                        consecutive_failures = 0
                        db.delete_paper(paperDOI)
                        logger.info(f"Accepted Paper deleted (will be re-discovered when formally published): {paperDOI}")
                        paper_skipped = True
                        break

                    except NonResearchPageError:
                        consecutive_failures = 0
                        db.insert_skipped_doi(paperDOI, "NonResearchPageError", timestamp)
                        db.delete_paper(paperDOI)
                        logger.info(f"Non-research page deleted (skipped_dois recorded): {paperDOI}")
                        paper_skipped = True
                        break

                    except Exception as e:
                        last_error = e
                        # If parse_page() raised an error and the HTML contains
                        # bot-detection markers, treat it as a bot block and
                        # retry with longer timeout instead of giving up early.
                        if scraper and hasattr(scraper, 'html') and scraper.html:
                            page_title_snippet = _extract_page_title(scraper.html)
                            is_bot = _has_bot_markers(
                                scraper.html, page_title=page_title_snippet,
                            )
                            if is_bot:
                                logger.warning(
                                    f"Bot block caused parse error (attempt "
                                    f"{'1/1' if len(retry_attempts) == 1 else f'{attempt+1}/{len(retry_attempts)}'})"
                                    f" [{paperDOI}]: {e}"
                                )
                                if attempt < len(retry_attempts) - 1:
                                    continue
                                # fall through to error handling below
                        if attempt == 0:
                            continue
                        break

                if not paper_succeeded and not paper_skipped:
                    error_msg = str(last_error) if last_error else "Unknown error"
                    error_type = type(last_error).__name__ if last_error else "N/A"
                    page_title_snippet = (
                        _extract_page_title(scraper.html)
                        if scraper and hasattr(scraper, 'html') and scraper.html
                        else ""
                    )
                    html_saved = ""
                    if scraper and hasattr(scraper, '_save_error_html'):
                        save_url = getattr(scraper, 'page_url', None) or page_url
                        if scraper._save_error_html(save_url, f"phaseC_fail_{paperDOI}"):
                            html_saved = f" | HTML saved to error dir"
                    if isinstance(last_error, PageParseError):
                        logger.warning(f"Phase C page parse error [{paperDOI}]: {error_msg} | type={error_type}{html_saved}")
                    else:
                        logger.warning(f"Phase C scrape failed after 3 attempts [{paperDOI}]: {error_msg} | type={error_type}{html_saved}")
                    if page_title_snippet:
                        logger.debug(f"Phase C page title [{paperDOI}]: {page_title_snippet}")
                    db.update_error_message(
                        paperDOI, "publisher_page_fetched_status",
                        FetchStatus.FAILED.value,
                        "publisher_page_fetched_error", error_msg[:500],
                        "publisher_page_fetched_date", timestamp,
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= CFG.PUBLISHER_MAX_CONSECUTIVE_FAILURES:
                        logger.warning(f"Publisher {publisher}: {consecutive_failures} consecutive failures, aborting")
                        break

                delay = random.uniform(CFG.PUBLISHER_PAGE_DELAY_MIN, CFG.PUBLISHER_PAGE_DELAY_MAX)
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
