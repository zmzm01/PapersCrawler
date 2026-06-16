"""
Phase E2: MinerU PDF full-text parsing.
"""

import logging
import random
import time
from datetime import datetime
from pathlib import Path

from config import CFG, BROWSER_SESSION_DIR, MINERU_OUTPUT_DIR
from db.database import DatabaseClient, FetchStatus
from pipeline.base import SCRAPER_MAP
from processors.mineru_paper_parser import MinerUParser
from sources.publisher import BasePublisherScraper

logger = logging.getLogger(__name__)


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

    relevant_papers = db.get_relevant_papers()
    papers_with_pdf = [
        p for p in relevant_papers
        if p["mineru_parse_status"] == "pending"
        and (p["pdf_url"] or p["publisher"] == "optica")
    ]
    if not papers_with_pdf:
        logger.info("Phase E2: no PDFs pending")
        return

    logger.info(f"Phase E2: {len(papers_with_pdf)} PDFs pending")

    parser = MinerUParser(CFG.MINERU_TOKEN)

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

        # 从 SCRAPER_MAP 获取 scraper 类
        scraper_config = SCRAPER_MAP.get(publisher)
        scraper_class = scraper_config[0] if scraper_config else None

        # 如 publisher 启用了 skip_phase_c_if_crossref_abstract，则需使用
        # 具体 Scraper 类（有 parse_page() 能力）做延迟页面访问补齐 pdf_url。
        # 其他 publisher 使用 BasePublisherScraper（无 parse_page() 开销）。
        has_parse = (scraper_class
                     and getattr(scraper_class, 'skip_phase_c_if_crossref_abstract', False))
        if has_parse:
            downloader = scraper_class(dl_dir)
        else:
            downloader = BasePublisherScraper(dl_dir)

        # 从 SCRAPER_MAP 查代理配置，不复用 session
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

        # ── 延迟页面访问：补齐 Phase C 跳过导致的缺失 pdf_url ──
        # 仅对启用了 skip_phase_c_if_crossref_abstract 的 publisher 执行：
        # 浏览器已启动，用 parse_page() 提取 citation_pdf_url 后写回 DB。
        lazy_pending = [p for p in group if not p["pdf_url"]] if has_parse else []
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

                # Lazy fetch 后仍无 pdf_url（Optica 页面解析失败等）→ 跳过
                if not pdf_url:
                    logger.warning(f"Phase E2: no pdf_url for {doi}, skipping")
                    db.update_mineru_error(
                        doi, "No PDF URL available (lazy fetch failed or Phase C returned empty)",
                        FetchStatus.FAILED.value, timestamp,
                    )
                    failed_count += 1
                    continue

                try:
                    safe_doi = doi.replace("/", "_").replace("\\", "_").replace("..", "_")
                    mineru_output_dir = MINERU_OUTPUT_DIR / safe_doi
                    mineru_output_dir.mkdir(parents=True, exist_ok=True)
                    pdf_save_path = mineru_output_dir / "paper.pdf"

                    # Reuse existing PDF if already downloaded and valid
                    if pdf_save_path.exists() and pdf_save_path.stat().st_size > 0:
                        with open(pdf_save_path, "rb") as f:
                            header = f.read(5)
                        if header == b'%PDF-':
                            logger.info(f"PDF already exists, reusing: {pdf_save_path}")
                        else:
                            logger.warning(f"Existing PDF invalid (header: {header!r}), re-downloading")
                            pdf_save_path.unlink()
                    if not pdf_save_path.exists():
                        logger.info(f"Downloading PDF: {doi} ← {pdf_url}")
                        pdf_bytes = downloader.download_pdf(pdf_url, page_url=page_url)

                        # Validate PDF content before saving
                        if not pdf_bytes or pdf_bytes[:5] != b'%PDF-':
                            raise RuntimeError(
                                f"Downloaded content is not a valid PDF "
                                f"({len(pdf_bytes)} bytes, "
                                f"header: {pdf_bytes[:20]!r})"
                            )

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
                        logger.info(f"MinerU success: {doi} ({full_md_path.stat().st_size} bytes)")
                    else:
                        raise RuntimeError("MinerU output missing full.md")

                except Exception as e:
                    logger.warning(f"MinerU failed [{doi}]: {e}")
                    db.update_mineru_error(
                        doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                    )
                    failed_count += 1

                delay = random.uniform(3, 8)
                time.sleep(delay)

        finally:
            try:
                downloader.close()
            except Exception:
                pass

    logger.info(f"Phase E2 done: {success_count} success, {failed_count} failed")
