"""
Phase C: Publisher page scraping via cloakbrowser.
"""

import json
import logging
import random
import re
import time
from datetime import datetime, timedelta

from config import CFG
from db.database import FetchStatus
from pipeline.base import SCRAPER_MAP, create_scraper
from sources.publisher import NonResearchPageError, AcceptedPaperError, PageParseError

logger = logging.getLogger(__name__)


def _limit_phase_papers(papers, processed_count, phase_limit):
    """Return the papers still allowed by the phase-wide limit.

    Parameters
    ----------
    papers : list
        Pending papers for the current publisher.
    processed_count : int
        Number of papers already selected by this Phase C invocation.
    phase_limit : int
        Maximum number for the whole phase; ``0`` means unlimited.

    Returns
    -------
    list
        A bounded view of ``papers``.
    """
    if not phase_limit:
        return papers
    remaining = max(phase_limit - processed_count, 0)
    return papers[:remaining]


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
        "challenge-platform" in html_lower
        or "_cf_chl_opt" in html_lower
        or "cf-browser-verification" in html_lower
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


def _record_publisher_failure(
        db, doi, error, status_date, failure_kind=None, retry_after=None):
    """Persist a Publisher failure with retry metadata when supported.

    The fallback keeps lightweight test doubles and third-party callers that
    implement only the historical ``update_error_message`` API compatible.

    Parameters
    ----------
    db : DatabaseClient
        Database client or compatible test double.
    doi : str
        DOI of the failed paper.
    error : str
        Human-readable failure message.
    status_date : str
        Failure timestamp.
    failure_kind : str, optional
        Stable failure class, such as ``"bot_block"``.
    retry_after : str, optional
        Earliest automatic retry timestamp.

    Returns
    -------
    int or None
        Consecutive Bot-block count when the database supports it.
    """
    recorder = getattr(db, "record_publisher_page_failure", None)
    if callable(recorder):
        return recorder(
            doi, error, status_date,
            failure_kind=failure_kind,
            retry_after=retry_after,
        )
    db.update_error_message(
        doi, "publisher_page_fetched_status", FetchStatus.FAILED.value,
        "publisher_page_fetched_error", str(error)[:500],
        "publisher_page_fetched_date", status_date,
    )
    return None


def _row_value(row, column, default=None):
    """Read a mapping-like database row while tolerating legacy test doubles."""
    if hasattr(row, "keys") and column not in row.keys():
        return default
    try:
        return row[column]
    except (KeyError, IndexError):
        return default


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

    logger.info("Phase C: checking pending papers per publisher")

    # 构建已启用/禁用 publisher 集合
    all_publisher_keys = {j["publisher"] for j in publishers}
    enabled_publishers = {
        j["publisher"] for j in publishers if j.get("enabled", True)
    }

    processed_count = 0
    phase_limit = CFG.MAX_PAPERS_PER_PHASE

    for publisher_key in sorted(all_publisher_keys):
        # ── 禁用 publisher：标记已有论文为 skipped，不启动浏览器 ──
        if publisher_key not in enabled_publishers:
            disabled_papers = db.get_papers_by_status(
                "publisher_page_fetched_status", "pending",
            )
            disabled_for_pub = [
                p for p in disabled_papers
                if p["publisher"] == publisher_key
            ]
            if not disabled_for_pub:
                continue
            timestamp = str(datetime.now())
            for paper in disabled_for_pub:
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
            logger.info(
                f"Publisher {publisher_key} is disabled, "
                f"skipped {len(disabled_for_pub)} papers"
            )
            continue

        # ── 检查该 publisher 是否有论文待抓取 ──
        scraper_class = SCRAPER_MAP.get(publisher_key, (None,))[0]
        should_skip_cr = (
            bool(getattr(
                CFG, "PUBLISHER_SKIP_IF_CROSSREF_ABSTRACT", True,
            ))
            and scraper_class is not None
            and getattr(
                scraper_class, "skip_phase_c_if_crossref_abstract", True,
            )
        )

        papers = db.get_pending_publisher_papers(
            publisher_key, skip_crossref_abstract=should_skip_cr,
        )

        if should_skip_cr:
            # 记录因已有 CrossRef 摘要而被过滤的论文数
            status_query = getattr(
                db, "get_papers_by_status_and_publisher", None,
            )
            if callable(status_query):
                all_for_pub = status_query(
                    "publisher_page_fetched_status", "pending", publisher_key,
                )
                if getattr(CFG, "PUBLISHER_FORCE_BOT_RETRY", False):
                    # 显式强制重试只恢复 Bot 阻断论文，不让所有已有
                    # CrossRef 摘要的论文同时失去页面短路优化。
                    pending_dois = {paper["doi"] for paper in papers}
                    bot_papers = [
                        paper for paper in all_for_pub
                        if paper["doi"] not in pending_dois
                        and (
                            _row_value(
                                paper, "publisher_page_failure_kind",
                            ) == "bot_block"
                            or "bot block" in (
                                _row_value(
                                    paper,
                                    "publisher_page_fetched_error",
                                    "",
                                ) or ""
                            ).lower()
                        )
                    ]
                    papers.extend(bot_papers)
                filtered = len(all_for_pub) - len(papers)
                if filtered:
                    logger.info(
                        f"{publisher_key}: {filtered}/{len(all_for_pub)} papers "
                        f"skipped (CrossRef has abstract)"
                    )

        papers = _limit_phase_papers(papers, processed_count, phase_limit)

        if not papers:
            continue

        processed_count += len(papers)
        logger.info(f"Processing publisher: {publisher_key} ({len(papers)} papers)")

        scraper = None
        try:
            scraper = create_scraper(publisher_key)
        except (ValueError, Exception) as e:
            logger.error(f"Cannot create scraper for {publisher_key}: {e}")
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

        # 预热导航：建立 Cookie 同意等会话状态（仅配置了 prewarm_url 的
        # 出版社执行，如 AIP 的 Osano consent），避免组内第一篇论文因
        # 冷启动拿到"同意壳"空页面而解析失败。失败仅告警，不阻断。
        try:
            scraper.prewarm()
        except Exception:
            logger.warning("Prewarm raised for %s, continuing anyway", publisher_key)

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
                    normal_retry_attempts = [2]
                    logger.debug(f"First-in-group, extended timeout [{paperDOI}]")
                else:
                    normal_retry_attempts = list(range(3))
                is_first_in_group = False

                fallback_proxy_url = getattr(
                    CFG, "PUBLISHER_FALLBACK_PROXY_URL", "",
                ).strip()
                retry_plan = [
                    (attempt, False) for attempt in normal_retry_attempts
                ]
                if fallback_proxy_url:
                    retry_plan.append((None, True))

                paper_succeeded = False
                paper_skipped = False
                last_error = None
                last_scraper = scraper
                fallback_attempted = False
                bot_block_detected = False

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

                for attempt, is_fallback in retry_plan:
                    attempt_scraper = scraper
                    fallback_scraper = None
                    try:
                        if is_fallback:
                            fallback_attempted = True
                            logger.info(
                                "Phase C fallback retry with configured proxy "
                                "[%s]",
                                paperDOI,
                            )
                            if scraper:
                                try:
                                    scraper.close()
                                except Exception:
                                    pass
                                scraper = None
                            fallback_scraper = create_scraper(
                                publisher_key,
                                proxy_override={"server": fallback_proxy_url},
                            )
                            attempt_scraper = fallback_scraper
                            last_scraper = attempt_scraper
                            try:
                                attempt_scraper.prewarm()
                            except Exception:
                                logger.warning(
                                    "Fallback prewarm raised for %s, "
                                    "continuing anyway",
                                    publisher_key,
                                )
                            timeout = 45000
                        else:
                            last_scraper = attempt_scraper
                            if attempt == 0:
                                timeout = 5000
                                cooloff = 0
                            elif attempt == 1:
                                timeout = 15000
                                cooloff = 0
                            else:
                                timeout = 45000
                                # First-in-group: no prior failure, skip cooldown
                                if len(normal_retry_attempts) == 1:
                                    logger.debug(
                                        f"Extended timeout 45s (first-in-group) "
                                        f"[{paperDOI}]"
                                    )
                                else:
                                    cooloff = random.uniform(120, 180)
                                    logger.debug(
                                        f"Cooling {cooloff:.0f}s before retry 3 "
                                        f"[{paperDOI}]"
                                    )
                                    time.sleep(cooloff)
                        attempt_scraper.fetch_page(page_url, timeout=timeout)

                        # Always try parsing first — CF/bot markers in HTML
                        # (e.g. _cf_chl_opt from CDN scripts) do NOT necessarily
                        # mean the page is blocked.  Only treat as a bot block
                        # when parsing also returns empty results.
                        paperPage = attempt_scraper.parse_page()

                        if not paperPage.title and not paperPage.doi and not paperPage.abstract:
                            # Empty parse — check for bot detection patterns
                            page_title_snippet = _extract_page_title(
                                attempt_scraper.html,
                            )

                            bot_blocked = _has_bot_markers(
                                attempt_scraper.html,
                                page_title=page_title_snippet,
                            )
                            bot_block_detected = bot_block_detected or bot_blocked

                            if is_fallback:
                                attempt_label = "fallback"
                            elif len(normal_retry_attempts) == 1:
                                attempt_label = "1/1"
                            else:
                                attempt_label = f"{attempt + 1}/{len(normal_retry_attempts)}"
                            if bot_blocked:
                                logger.warning(
                                    f"Bot detection page (attempt {attempt_label})"
                                    f" [{paperDOI}]"
                                    + (f" | page title: {page_title_snippet}"
                                       if page_title_snippet else "")
                                )
                            else:
                                logger.warning(
                                    f"Empty parse result (attempt {attempt_label})"
                                    f" [{paperDOI}]"
                                )

                            if not is_fallback and attempt < len(normal_retry_attempts) - 1:
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
                        if is_fallback:
                            logger.info(
                                f"Publisher page OK via fallback proxy: {paperDOI}"
                            )
                        else:
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
                        if (
                            attempt_scraper
                            and hasattr(attempt_scraper, "html")
                            and attempt_scraper.html
                        ):
                            page_title_snippet = _extract_page_title(
                                attempt_scraper.html,
                            )
                            is_bot = _has_bot_markers(
                                attempt_scraper.html,
                                page_title=page_title_snippet,
                            )
                            if is_bot:
                                bot_block_detected = True
                                if is_fallback:
                                    attempt_label = "fallback"
                                elif len(normal_retry_attempts) == 1:
                                    attempt_label = "1/1"
                                else:
                                    attempt_label = f"{attempt + 1}/{len(normal_retry_attempts)}"
                                logger.warning(
                                    f"Bot block caused parse error (attempt {attempt_label})"
                                    f" [{paperDOI}]: {e}"
                                )
                                if not is_fallback and attempt < len(normal_retry_attempts) - 1:
                                    continue
                                # fall through to error handling below
                        if not is_fallback and attempt == 0:
                            continue
                        if not is_fallback and fallback_proxy_url:
                            continue
                        break
                    finally:
                        if fallback_scraper:
                            try:
                                fallback_scraper.close()
                            except Exception:
                                pass
                        if is_fallback:
                            try:
                                scraper = create_scraper(publisher_key)
                                scraper.prewarm()
                            except Exception as exc:
                                scraper = None
                                logger.warning(
                                    "Could not restore normal scraper for %s: %s",
                                    publisher_key,
                                    exc,
                                )

                if not paper_succeeded and not paper_skipped:
                    error_msg = str(last_error) if last_error else "Unknown error"
                    error_type = type(last_error).__name__ if last_error else "N/A"
                    page_title_snippet = ""
                    if (
                        last_scraper
                        and hasattr(last_scraper, "html")
                        and last_scraper.html
                    ):
                        page_title_snippet = _extract_page_title(
                            last_scraper.html,
                        )
                    html_saved = ""
                    if last_scraper and hasattr(last_scraper, '_save_error_html'):
                        save_url = getattr(last_scraper, 'page_url', None) or page_url
                        if last_scraper._save_error_html(save_url, f"phaseC_fail_{paperDOI}"):
                            html_saved = " | HTML saved to error dir"
                    retry_summary = (
                        " after normal retries and fallback proxy"
                        if fallback_attempted else ""
                    )
                    if isinstance(last_error, PageParseError):
                        logger.warning(
                            f"Phase C page parse error{retry_summary} "
                            f"[{paperDOI}]: {error_msg} | type={error_type}"
                            f"{html_saved}"
                        )
                    else:
                        failure_summary = (
                            "normal retries and fallback proxy"
                            if fallback_attempted else "3 attempts"
                        )
                        logger.warning(
                            f"Phase C scrape failed after {failure_summary} "
                            f"[{paperDOI}]: {error_msg} | type={error_type}{html_saved}"
                        )
                    if page_title_snippet:
                        logger.debug(f"Phase C page title [{paperDOI}]: {page_title_snippet}")
                    failure_kind = "bot_block" if bot_block_detected else None
                    retry_after = None
                    if failure_kind == "bot_block":
                        cooldown_hours = max(
                            1,
                            int(getattr(
                                CFG,
                                "PUBLISHER_BOT_RETRY_COOLDOWN_HOURS",
                                72,
                            )),
                        )
                        retry_after = str(
                            datetime.now()
                            + timedelta(hours=cooldown_hours)
                        )
                    retry_count = _record_publisher_failure(
                        db,
                        paperDOI,
                        error_msg,
                        timestamp,
                        failure_kind=failure_kind,
                        retry_after=retry_after,
                    )
                    if failure_kind == "bot_block":
                        max_retries = max(
                            1,
                            int(getattr(
                                CFG, "PUBLISHER_BOT_MAX_RETRIES", 3,
                            )),
                        )
                        if (
                            retry_count is not None
                            and retry_count >= max_retries
                        ):
                            logger.warning(
                                "Publisher Bot block quarantined [%s] "
                                "after %d failure(s); use "
                                "--retry-bot-blocks to force a retry",
                                paperDOI,
                                retry_count,
                            )
                        else:
                            logger.info(
                                "Publisher Bot block cooldown [%s] until %s",
                                paperDOI,
                                retry_after,
                            )
                    consecutive_failures += 1
                    if consecutive_failures >= CFG.PUBLISHER_MAX_CONSECUTIVE_FAILURES:
                        logger.warning(f"Publisher {publisher_key}: {consecutive_failures} consecutive failures, aborting")
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

        logger.info(f"Publisher {publisher_key} done, cooling 15s...")
        time.sleep(15)

    logger.info("Phase C done")
