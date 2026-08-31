"""
Phase E2: MinerU PDF full-text parsing.
"""

import logging
import random
import time
from datetime import datetime

from config import CFG, BROWSER_SESSION_DIR, MINERU_OUTPUT_DIR
from db.database import FetchStatus
from pipeline.base import SCRAPER_MAP
from processors.mineru_paper_parser import MinerUParser
from sources.publisher import BasePublisherScraper
from sources.fulltext import resolve_candidates

logger = logging.getLogger(__name__)


def _failure_kind(error):
    """Classify a download error for audit and future retry policy."""
    message = str(error).lower()
    if "accepted paper" in message or "not_yet_published" in message:
        return "not_yet_published"
    if "403" in message or "401" in message or "login" in message:
        return "auth_required"
    if "429" in message or "rate" in message:
        return "rate_limited"
    if "timeout" in message:
        return "timeout"
    if "invalid pdf" in message or "no pdf" in message:
        return "invalid_pdf"
    return "download_error"


def _is_accepted_url(url):
    """Return whether a Publisher URL denotes an unpublished accepted paper."""
    return "/accepted/" in str(url or "").lower()


def _is_valid_pdf_file(file_path):
    """Return whether ``file_path`` exists and starts with a PDF signature."""
    try:
        if not file_path.is_file() or file_path.stat().st_size <= 0:
            return False
        with file_path.open("rb") as stream:
            return stream.read(5) == b"%PDF-"
    except OSError:
        return False


def phase_e2_mineru(db):
    """Download PDF and parse full text via MinerU API.

    Parameters
    ----------
    db : DatabaseClient
    """
    logger.info("--- Phase E2: MinerU PDF parsing ---")
    if CFG.SKIP_PHASE_E2:
        logger.info("Phase E2: SKIP_PHASE_E2=True, skipping")
        return

    if not CFG.MINERU_TOKEN:
        logger.info("Phase E2: MINERU_TOKEN not configured, skipping")
        return

    papers_with_pdf = db.get_relevance_screen_candidates(
        require_pdf_url=False,
    )
    if not papers_with_pdf:
        logger.info("Phase E2: no PDFs pending")
        return

    logger.info(f"Phase E2: {len(papers_with_pdf)} PDFs pending")

    parser = MinerUParser(CFG.MINERU_TOKEN)

    # Reserve quota before launching any browser. Existing valid local PDFs
    # do not consume quota; failed network attempts do.
    reserved = []
    for paper in papers_with_pdf:
        candidates = resolve_candidates(db, paper)
        paper = dict(paper)
        paper["_pdf_candidates"] = candidates
        if not paper.get("pdf_url") and candidates:
            paper["pdf_url"] = candidates[0]["url"]
        safe_doi = paper["doi"].replace("/", "_").replace("\\", "_").replace("..", "_")
        local_pdf = MINERU_OUTPUT_DIR / safe_doi / "paper.pdf"
        if _is_valid_pdf_file(local_pdf):
            reserved.append(dict(paper, _quota_reserved=False))
            continue
        # Papers without a URL may still obtain one through the delayed
        # publisher page resolver below.  Do not reserve quota yet.
        if not paper["pdf_url"]:
            if _is_accepted_url(paper.get("page_url")):
                db.update_mineru_error(
                    paper["doi"], "not_yet_published: Accepted Paper",
                    FetchStatus.SKIPPED.value, str(datetime.now()),
                )
                continue
            reserved.append(dict(paper, _quota_reserved=False))
            continue
        if db.claim_fulltext_download(
                paper["doi"], paper["publisher"],
                CFG.FULLTEXT_DOWNLOAD_DAILY_MAX,
                CFG.FULLTEXT_DOWNLOAD_PUBLISHER_MAX):
            reserved.append(dict(paper, _quota_reserved=True))
        else:
            logger.info("Phase E2 daily download quota exhausted: %s", paper["doi"])

    papers_with_pdf = reserved
    if not papers_with_pdf:
        logger.info("Phase E2: no papers admitted by download quota")
        return

    # Group papers by publisher for per-publisher scraper with proper proxy
    papers_by_publisher = {}
    for p in papers_with_pdf:
        publisher = p["publisher"] or "__unknown__"
        papers_by_publisher.setdefault(publisher, []).append(dict(p))

    success_count = 0
    failed_count = 0

    for publisher, group in papers_by_publisher.items():
        # 使用独立 session 目录，不碰 publisher 主缓存
        dl_dir = BROWSER_SESSION_DIR / "mineru_download" / publisher
        dl_dir.mkdir(parents=True, exist_ok=True)

        # 从 SCRAPER_MAP 获取 scraper 类
        scraper_config = SCRAPER_MAP.get(publisher)
        scraper_class = scraper_config[0] if scraper_config else None

        # 如 publisher 启用了 skip_phase_c_if_crossref_abstract，则需使用
        # 具体 Scraper 类（有 parse_page() 能力）做延迟页面访问补齐 pdf_url。
        # 其他 publisher 使用 BasePublisherScraper（无 parse_page() 开销）。
        has_parse = (
            scraper_class
            and bool(getattr(
                CFG, "PUBLISHER_SKIP_IF_CROSSREF_ABSTRACT", True,
            ))
            and getattr(
                scraper_class, "skip_phase_c_if_crossref_abstract", True,
            )
        )
        if has_parse:
            downloader = scraper_class(dl_dir)
        else:
            downloader = BasePublisherScraper(dl_dir)

        # 从 SCRAPER_MAP 查代理配置，不复用 session
        # Phase E2 is always on the campus route.  Publisher proxies are
        # reserved for Phase C abstract retrieval only.
        proxy = None

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
                if paper.get("_quota_reserved"):
                    db.finish_fulltext_download(paper["doi"], "failed", str(e)[:500])
                failed_count += 1
            try:
                downloader.close()
            except Exception:
                pass
            continue

        # ── 延迟页面访问：补齐 Phase C 跳过导致的缺失 pdf_url ──
        # 仅对启用了 skip_phase_c_if_crossref_abstract 的 publisher 执行：
        # 浏览器已启动，用 parse_page() 提取 citation_pdf_url 后写回 DB。
        lazy_pending = [
            p for p in group
            if not p["pdf_url"]
            and not _is_valid_pdf_file(
                MINERU_OUTPUT_DIR
                / p["doi"].replace("/", "_").replace("\\", "_")
                .replace("..", "_")
                / "paper.pdf"
            )
        ] if has_parse else []
        if lazy_pending:
            logger.info(
                f"{publisher}: lazy page fetch for {len(lazy_pending)} papers"
            )
            for paper in lazy_pending:
                doi = paper["doi"]
                page_url = paper["page_url"]
                if not page_url:
                    continue
                try:
                    downloader.fetch_page(page_url, timeout=30000)
                    parsed = downloader.parse_page()
                    if parsed and parsed.pdf_url:
                        db.update_publisher_pdf_url(doi, parsed.pdf_url)
                        paper["pdf_url"] = parsed.pdf_url
                        paper["_pdf_candidates"] = [{
                            "url": parsed.pdf_url,
                            "source": "publisher",
                            "priority": 100,
                        }]
                        logger.info(
                            f"Lazy fetch OK: {doi} → {parsed.pdf_url}"
                        )
                    else:
                        logger.warning(
                            f"Lazy fetch: no pdf_url for {doi}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Lazy fetch failed [{doi}]: {e}"
                    )
                downloader.page.wait_for_timeout(3000)

        try:
            for paper in group:
                doi = paper["doi"]
                pdf_url = paper["pdf_url"]
                page_url = paper["page_url"]
                timestamp = str(datetime.now())

                safe_doi = (
                    doi.replace("/", "_")
                    .replace("\\", "_")
                    .replace("..", "_")
                )
                mineru_output_dir = MINERU_OUTPUT_DIR / safe_doi
                mineru_output_dir.mkdir(parents=True, exist_ok=True)
                pdf_save_path = mineru_output_dir / "paper.pdf"
                local_pdf_is_valid = _is_valid_pdf_file(pdf_save_path)

                # A valid manually imported PDF is sufficient; only network
                # downloads require a URL.
                if not pdf_url and not local_pdf_is_valid:
                    logger.warning(f"Phase E2: no pdf_url for {doi}, skipping")
                    db.update_mineru_error(
                        doi, "No PDF URL available (lazy fetch failed or Phase C returned empty)",
                        FetchStatus.FAILED.value, timestamp,
                    )
                    failed_count += 1
                    if paper.get("_quota_reserved"):
                        db.finish_fulltext_download(doi, "failed", "No PDF URL")
                    continue

                if not local_pdf_is_valid and not paper.get("_quota_reserved"):
                    if not db.claim_fulltext_download(
                            doi, paper["publisher"],
                            CFG.FULLTEXT_DOWNLOAD_DAILY_MAX,
                            CFG.FULLTEXT_DOWNLOAD_PUBLISHER_MAX):
                        logger.info("Phase E2 daily download quota exhausted: %s", doi)
                        continue
                    paper["_quota_reserved"] = True

                try:
                    # Reuse existing PDF if already downloaded and valid
                    if local_pdf_is_valid:
                        logger.info(f"PDF already exists, reusing: {pdf_save_path}")
                    elif pdf_save_path.exists():
                        logger.warning(
                            "Existing PDF is invalid, re-downloading: %s",
                            pdf_save_path,
                        )
                        pdf_save_path.unlink()
                    if not pdf_save_path.exists():
                        download_errors = []
                        pdf_bytes = None
                        candidates = paper.get("_pdf_candidates") or [
                            {"url": pdf_url, "source": "publisher"}
                        ]
                        for candidate in candidates:
                            candidate_url = candidate.get("url")
                            if not candidate_url:
                                continue
                            try:
                                logger.info("Downloading PDF: %s ← %s", doi, candidate_url)
                                candidate_bytes = downloader.download_pdf(
                                    candidate_url, page_url=page_url,
                                )
                                if candidate_bytes and candidate_bytes[:5] == b"%PDF-":
                                    pdf_bytes = candidate_bytes
                                    paper["_selected_location"] = candidate
                                    break
                                download_errors.append(
                                    f"{candidate_url}: invalid PDF content"
                                )
                            except Exception as error:
                                download_errors.append(f"{candidate_url}: {error}")
                        if not pdf_bytes:
                            raise RuntimeError("; ".join(download_errors)[:500] or
                                               "No PDF candidate succeeded")

                        pdf_save_path.write_bytes(pdf_bytes)
                        logger.info(f"PDF saved ({len(pdf_bytes)} bytes): {pdf_save_path}")
                        del pdf_bytes  # 释放 PDF 原始字节，避免堆积在内存中

                    mineru_output_dir = parser.parse_pdf(
                        pdf_save_path, output_dir=mineru_output_dir,
                    )
                    full_md_path = mineru_output_dir / "full.md"

                    if full_md_path.exists():
                        rel_dir = str(mineru_output_dir.relative_to(MINERU_OUTPUT_DIR.parent))
                        db.update_mineru_result(
                            doi, "", rel_dir,
                            FetchStatus.SUCCESS.value, timestamp,
                        )
                        success_count += 1
                        if paper.get("_quota_reserved"):
                            diagnostics = dict(
                                getattr(downloader, "last_download_diagnostics", {})
                            )
                            diagnostics.update({
                                "location_source": (paper.get(
                                    "_selected_location", {}
                                ).get("source", "publisher")),
                                "failure_kind": None,
                            })
                            db.finish_fulltext_download(
                                doi, "success", details=diagnostics,
                            )
                        logger.info(f"MinerU success: {doi} ({full_md_path.stat().st_size} bytes)")
                    else:
                        raise RuntimeError("MinerU output missing full.md")

                except Exception as e:
                    logger.warning(f"MinerU failed [{doi}]: {e}")
                    failure_kind = _failure_kind(e)
                    terminal_status = (
                        FetchStatus.SKIPPED.value
                        if failure_kind == "not_yet_published"
                        else FetchStatus.FAILED.value
                    )
                    db.update_mineru_error(
                        doi, str(e)[:500], terminal_status, timestamp,
                    )
                    if terminal_status == FetchStatus.FAILED.value:
                        failed_count += 1
                    if paper.get("_quota_reserved"):
                        diagnostics = dict(
                            getattr(downloader, "last_download_diagnostics", {})
                        )
                        diagnostics.update({
                            "location_source": (paper.get(
                                "_selected_location", {}
                            ).get("source", "publisher")),
                            "failure_kind": failure_kind,
                        })
                        db.finish_fulltext_download(
                            doi,
                            "skipped" if failure_kind == "not_yet_published"
                            else "failed",
                            str(e)[:500], diagnostics,
                        )

                delay = random.uniform(
                    CFG.FULLTEXT_DOWNLOAD_DELAY_MIN,
                    CFG.FULLTEXT_DOWNLOAD_DELAY_MAX,
                )
                time.sleep(delay)

        finally:
            try:
                downloader.close()
            except Exception:
                pass

    logger.info(f"Phase E2 done: {success_count} success, {failed_count} failed")
