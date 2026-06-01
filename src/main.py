"""
main.py
=======
PapersCrawler 主入口 —— 8 阶段文献追踪流水线。

流水线架构:
  Phase A — RSS 抓取      : 从配置的期刊 RSS Feed 发现新论文，记录到数据库
  Phase B — CrossRef 补充 : 通过 DOI 从 CrossRef API 获取完整元数据
  Phase C — Publisher 抓取: 使用 Playwright 浏览器爬取期刊页面摘要
  Phase D — 语义相似度初筛: 基于 sentence-transformers 计算论文与领域的语义相似度
  Phase E — LLM 相关性    : 调用 DeepSeek API 对初筛通过的论文做相关性判断
  Phase E2 — MinerU 全文  : 对相关论文下载 PDF 并用 MinerU 解析全文
  Phase F — LLM 总结      : 对判定相关的论文（优先用 MinerU 全文）生成结构化总结
  Phase G — 报告生成      : 生成 Markdown + PDF 双格式报告
  Phase H — 邮件推送      : 通过 SMTP 将报告发送给团队成员

运行方式:
  # 桌面环境 (有显示器)
  python src/main.py

  # 无图形界面服务器
  xvfb-run -a python src/main.py

错误处理策略:
  - 每篇论文独立处理: 一篇失败不影响其他论文
  - 状态持久化到数据库: 中断后重启可从断点继续
  - RSS 使用本地缓存: 减少网络请求，避免 IP 封禁风险
"""

import json
import logging
import os
import random
import shutil
import sys
import time
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from config import (
    load_publishers, load_keywords, load_email_config,
    REQUEST_TIMEOUT, CROSSREF_MAILTO,
    LOG_FILE_PATH, DB_PATH, BROWSER_SESSION_DIR,
    RAW_RSS_DIR, RAW_PAGE_DIR, REPORT_DIR, CONFIG_DIR,
    LLM_API_CONFIG_DICT_RELE, LLM_API_CONFIG_DICT_SUMM, SUMMARIES_PROMPT,
    MINERU_TOKEN, MINERU_OUTPUT_DIR,
    SEMANTIC_MODEL_PATH, SEMANTIC_SIMILARITY_THRESHOLD,
                MAX_PAPERS_PER_PHASE,
    SKIP_PHASE_C, SKIP_PHASE_E, SKIP_PHASE_E2, SKIP_PHASE_F, SKIP_PHASE_H,
    SKIP_NATURE_NEWS,
    PUBLISHER_PAGE_DELAY_MIN, PUBLISHER_PAGE_DELAY_MAX,
    PUBLISHER_MAX_CONSECUTIVE_FAILURES,
    LLM_CONCURRENT_MAX,
)

from utils.db import DatabaseClient, FetchStatus
from sources.rss import RSSProcessor
from sources.crossref import CrossrefClient, NotFoundError
from sources.publisher import (
    NatureScraper, ScienceScraper, APSScraper,
    AIPScraper, IOPScraper, CambridgeScraper, OpticaScraper,
    NaturePageNotPaper, PageParseError,
)
from utils.paper_relevance import (
    PaperRelevanceChecker,
    SemanticFilter,
    LLMAPICallError,
    LLMResponseParseError,
)
from utils.llm_summarize_deepseek import (
    DeepSeekPaperSummarizer,
    LLMContextLengthExceed,
)
from utils.paper_report_generator import generate_report
from utils.email_sender import EmailSender
from utils.mineru_paper_parser import MinerUParser
from playwright.sync_api import sync_playwright


# ==================================================================
# Publisher Scraper 配置
#
# 每个出版商对应:
#   (Scraper 类, 浏览器 Session 缓存目录, 代理配置)
# 代理配置为 None 表示直连，为 dict 时使用指定代理（如 Optica 需要美国 IP）
# ==================================================================

SCRAPER_MAP = {
    "nature":    (NatureScraper,    BROWSER_SESSION_DIR / "nature",    None),
    "science":   (ScienceScraper,   BROWSER_SESSION_DIR / "science",   None),
    "aps":       (APSScraper,       BROWSER_SESSION_DIR / "aps",       None),
    "aip":       (AIPScraper,       BROWSER_SESSION_DIR / "aip",       None),
    "iop":       (IOPScraper,       BROWSER_SESSION_DIR / "iop",       None),
    "cambridge": (CambridgeScraper, BROWSER_SESSION_DIR / "cambridge", None),
    "optica":    (OpticaScraper,    BROWSER_SESSION_DIR / "optica",
                  {"server": "http://127.0.0.1:10808"}),
}


def _create_scraper(publisher):
    """
    根据 publisher 标识字符串创建并初始化对应的 Scraper 实例。

    工作流程：
    1. 从 SCRAPER_MAP 查找 (Scraper 类, 缓存目录, 代理) 三元组
    2. 如果缓存目录不存在则自动创建
    3. 实例化 Scraper 并调用 start_browser 启动 Chromium
    4. 返回初始化好的 scraper 对象（浏览器已启动，可直接使用）

    Args:
        publisher: publisher 标识字符串（如 "nature", "aps"）

    Returns:
        已初始化并启动浏览器的 Scraper 实例

    Raises:
        ValueError: publisher 不在 SCRAPER_MAP 中
    """
    config = SCRAPER_MAP.get(publisher)
    if not config:
        raise ValueError(f"No scraper config for publisher: {publisher}")
    scraper_class, user_data_dir, proxy = config
    os.makedirs(user_data_dir, exist_ok=True)
    scraper = scraper_class(user_data_dir)
    scraper.start_browser(proxy)
    return scraper


# ==================================================================
# 双通道日志设置：同时输出到文件和控制台
# DEBUG 级别记录所有细节，方便排查问题
# ==================================================================

file_handler = logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
console_handler = logging.StreamHandler()
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger(__name__)


# ==================================================================
# 主入口
# ==================================================================

def main():
    """
    PapersCrawler 主流水线：按顺序执行 8 个阶段。

    流程：
    1. 加载配置（期刊列表、关键词表）
    2. 初始化数据库（建表 & 连接）
    3. 依次执行 Phase A → Phase H
    4. 每个阶段独立处理，单篇失败不影响整体
    """
    # ---- 加载配置 ----
    publishers = load_publishers()
    keywords = load_keywords()
    logger.info(f"加载 {len(publishers)} 个期刊数据源")
    logger.info(f"关键词 {len(keywords['keywords'])} 个, 领域描述 {len(keywords['domain_description'])} 字符")

    # ---- 创建报告输出目录 ----
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 初始化数据库 ----
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    logger.info(f"数据库已就绪: {DB_PATH}")

    # ---- 流水线执行 ----
    phase_a_rss(db, publishers)
    phase_b_crossref(db)
    phase_c_publisher(db)
    phase_d_semantic_filter(db, keywords)
    phase_e_llm_relevance(db)
    phase_e2_mineru(db)
    phase_f_llm_summary(db)
    phase_g_report(db, REPORT_DIR)
    phase_h_email(REPORT_DIR)

    logger.info("所有阶段执行完毕")


# ==================================================================
# Phase A: RSS Feed 抓取
#
# 职责: 从各期刊 RSS Feed 获取最新论文列表，写入数据库
# 策略: 优先使用本地缓存的 RSS 文件（同一天不重复请求），
#       减少对外请求次数，降低 IP 封禁和 Rate Limit 风险
# ==================================================================

def phase_a_rss(db, publishers):
    """
    遍历所有启用的出版商 RSS Feed，抓取新论文的基本信息并写入数据库。

    工作流程：
    1. 遍历 publishers 列表，跳过 enabled=False 的期刊
    2. 检查本地是否有当天缓存的 RSS XML 文件，有则直接读取，无则 HTTP 请求
    3. 使用 RSSProcessor 解析 XML，提取 DOI、标题、链接、日期
    4. 对每篇论文检查 DOI 是否已存在（去重），不存在则插入数据库
    5. 记录创建日期

    Args:
        db:         DatabaseClient 实例
        publishers: 期刊配置列表 (来自 publishers.yaml)
    """
    logger.info("--- Phase A: RSS Feed 抓取 ---")
    rsspro = RSSProcessor()
    timestamp = datetime.now().strftime("%Y%m%d")

    for journal in publishers:
        # ---- 跳过已禁用的期刊数据源 ----
        if not journal.get("enabled", True):
            logger.info(f"跳过已禁用的期刊: {journal.get('name', journal.get('id', 'unknown'))}")
            continue

        journalid = journal["id"]
        publisher = journal["publisher"]
        rss_url = journal["rss"]
        journal_name = journal["name"]

        try:
            # ---- 本地缓存优先：同一天不重复请求 RSS Feed ----
            RAW_RSS_DIR.mkdir(parents=True, exist_ok=True)
            rss_file_save_path = RAW_RSS_DIR / f"{journalid}_{timestamp}.xml"

            if rss_file_save_path.exists():
                # 从本地缓存读取（减少网络请求）
                xml_text = rss_file_save_path.read_text()
                logger.debug(f"使用缓存的 RSS: {rss_file_save_path}")
            else:
                # 缓存不存在，发起 HTTP 请求
                xml_text = rsspro.fetch_rss(rss_url)
                rsspro.save_raw_rss(xml_text, str(rss_file_save_path))
                logger.debug(f"RSS 已缓存: {rss_file_save_path}")

            # ---- 解析 RSS XML，提取论文列表 ----
            papers = rsspro.parse_rss(xml_text, journal)
            logger.info(f"{journalid}: 发现 {len(papers)} 篇论文")

            # ---- 逐篇插入数据库（含去重检查） ----
            for paper in papers:
                paperDOI = paper.doi

                if not paperDOI:
                    # 无 DOI 的论文无法在后续阶段处理，跳过
                    logger.debug(f"跳过无 DOI 论文: {paper.title}")
                    continue

                # 去重：DOI 已存在的论文不再重复插入
                if db.paper_doi_exists(paperDOI):
                    logger.debug(f"DOI 已存在，跳过: {paperDOI}")
                    continue

                # 过滤 Nature 新闻 (d41586 DOI 前缀，非研究文章)
                if SKIP_NATURE_NEWS and "/d41586-" in paperDOI:
                    logger.debug(f"跳过 Nature 新闻: {paperDOI}")
                    continue

                logger.debug(f"写入新论文: {paperDOI}")
                # 写入 RSS 阶段的基本信息（DOI, 标题, 链接, 期刊名, 出版商, 日期）
                db.insert_rss_basicinfo(
                    paperDOI, paper.title, paper.url,
                    journal_name, publisher, paper.date
                )
                # 记录创建日期
                db.insert_paper_created_date(paperDOI, timestamp)

        except Exception as e:
            # 单期刊失败不中断整体流程
            logger.error(f"RSS 抓取失败 [{journalid}]: {e}")

    logger.info("Phase A 完成")


# ==================================================================
# Phase B: CrossRef 元数据补充
#
# 职责: 通过 DOI 查询 CrossRef API，补充标题、作者、摘要、
#       出版日期等完整元数据
# ==================================================================

def phase_b_crossref(db):
    """
    对 RSS 阶段发现的新论文，通过 CrossRef API 补全元数据。

    工作流程：
    1. 查询 cr_metadata_fetched_status = 'pending' 的论文
    2. 对每篇论文用 DOI 调用 CrossRef API
    3. 将返回的元数据（标题、作者 JSON、出版日期）写入数据库
    4. 标记处理状态（success / failed）

    错误处理：
    - NotFoundError: DOI 不存在，标记为 failed（不重试）
    - 其他异常: 标记为 failed，记录错误信息

    Args:
        db: DatabaseClient 实例
    """
    logger.info("--- Phase B: CrossRef 元数据补充 ---")
    crClient = CrossrefClient(mailto=CROSSREF_MAILTO, timeout=REQUEST_TIMEOUT)

    # 获取所有待补充 CrossRef 元数据的论文
    paper_tasks = db.get_pendings("cr_metadata_fetched_status")
    if MAX_PAPERS_PER_PHASE:
        paper_tasks = paper_tasks[:MAX_PAPERS_PER_PHASE]
    if not paper_tasks:
        logger.info("Phase B: 无待处理论文")
        return

    logger.info(f"Phase B: {len(paper_tasks)} 篇论文待补充 CrossRef 元数据")

    for paper_task in paper_tasks:
        paperDOI = paper_task["doi"]
        timestamp = str(datetime.now())

        try:
            # ---- 查询 CrossRef API ----
            crossrefPaper = crClient.fetch_by_doi(paperDOI)
            logger.debug(f"CrossRef 命中: {crossrefPaper.title} | {paperDOI}")

            # ---- 更新元数据 ----
            authors_json = json.dumps(crossrefPaper.authors, ensure_ascii=False) if crossrefPaper.authors else "[]"

            if not crossrefPaper.authors:
                # CrossRef 返回了数据但缺少作者信息
                logger.warning(f"CrossRef 作者数据缺失: {paperDOI}")
                db.update_crossref_metadata(
                    paperDOI, crossrefPaper.title,
                    authors_json, crossrefPaper.published,
                    crossrefPaper.abstract or ""
                )
                db.update_error_message(
                    paperDOI, "cr_metadata_fetched_status",
                    FetchStatus.FAILED.value,
                    "cr_metadata_fetched_error", "CrossRef author data missing",
                    "cr_metadata_fetched_date", timestamp
                )
            else:
                db.update_crossref_metadata(
                    paperDOI, crossrefPaper.title,
                    authors_json, crossrefPaper.published,
                    crossrefPaper.abstract or ""
                )
                # 标记为成功
                db.update_process_status(
                    paperDOI, "cr_metadata_fetched_status",
                    FetchStatus.SUCCESS.value,
                    "cr_metadata_fetched_date", timestamp
                )

        except NotFoundError as e:
            # DOI 不存在于 CrossRef，可能是新论文尚未注册
            logger.warning(f"CrossRef 无记录: {paperDOI}")
            db.update_error_message(
                paperDOI, "cr_metadata_fetched_status",
                FetchStatus.FAILED.value,
                "cr_metadata_fetched_error", str(e),
                "cr_metadata_fetched_date", timestamp
            )

        except Exception as e:
            # 其他网络或解析错误
            logger.error(f"CrossRef 失败 [{paperDOI}]: {e}")
            db.update_error_message(
                paperDOI, "cr_metadata_fetched_status",
                FetchStatus.FAILED.value,
                "cr_metadata_fetched_error", str(e),
                "cr_metadata_fetched_date", timestamp
            )

    logger.info("Phase B 完成")


# ==================================================================
# Phase C: Publisher 页面抓取
#
# 职责: 使用 Playwright 浏览器访问期刊页面，提取摘要和 PDF 链接
# 策略: 按 publisher 分组，同一出版商复用同一个浏览器实例
# ==================================================================

def phase_c_publisher(db):
    """
    对每篇论文，使用对应出版商的 Playwright Scraper 抓取页面元数据。

    工作流程：
    1. 查询 publisher_page_fetched_status = 'pending' 的论文
    2. 按 publisher 字段分组（同一出版商复用浏览器实例）
    3. 对每组：创建 scraper → 遍历论文 → 抓取页面 → 解析元数据 → 更新数据库
    4. 处理完毕后关闭浏览器（finally 保证资源释放）

    边界情况：
    - NaturePageNotPaper: Nature/Science 中非论文页面（News, Podcast 等），跳过
    - PageParseError: 页面结构变化导致解析失败，标记失败
    - 其他异常: 记录错误并继续处理下一篇论文

    Args:
        db: DatabaseClient 实例
    """
    logger.info("--- Phase C: Publisher 页面抓取 ---")
    if SKIP_PHASE_C:
        logger.info("Phase C: SKIP_PHASE_C=True, skipping")
        return

    paper_tasks = db.get_pendings("publisher_page_fetched_status")
    if MAX_PAPERS_PER_PHASE:
        paper_tasks = paper_tasks[:MAX_PAPERS_PER_PHASE]
    if not paper_tasks:
        logger.info("Phase C: 无待处理论文")
        return

    logger.info(f"Phase C: {len(paper_tasks)} 篇论文待抓取页面")

    # ---- 按 publisher 分组 ----
    paper_tasks_grouped = defaultdict(list)
    for paper_task in paper_tasks:
        key = paper_task["publisher"] or "unknown"
        paper_tasks_grouped[key].append(paper_task)

    # ---- 逐分组处理 ----
    for publisher, papers in paper_tasks_grouped.items():
        logger.info(f"开始处理 publisher: {publisher} ({len(papers)} 篇)")

        scraper = None
        try:
            # 创建并启动 scraper（复用于该出版商的所有论文）
            scraper = _create_scraper(publisher)
        except (ValueError, Exception) as e:
            logger.error(f"无法创建 scraper for {publisher}: {e}")
            # 标记该组所有论文为失败
            timestamp = str(datetime.now())
            for paper in papers:
                try:
                    db.update_error_message(
                        paper["doi"], "publisher_page_fetched_status",
                        FetchStatus.FAILED.value,
                        "publisher_page_fetched_error", str(e),
                        "publisher_page_fetched_date", timestamp
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
                    logger.warning(f"无页面 URL，跳过: {paperDOI}")
                    db.update_process_status(
                        paperDOI, "publisher_page_fetched_status",
                        FetchStatus.FAILED.value,
                        "publisher_page_fetched_date", timestamp
                    )
                    continue

                try:
                    # ---- 步骤 1: 浏览器访问页面 ----
                    scraper.fetch_page(page_url)

                    # ---- 步骤 2: 解析页面提取元数据 ----
                    paperPage = scraper.parse_page()

                    # ---- Cloudflare 拦截检测 ----
                    _cf_blocked = (
                        "challenge-platform" in scraper.html
                        or "_cf_chl_opt" in scraper.html
                        or "cf-browser-verification" in scraper.html
                    )
                    if _cf_blocked or (not paperPage.title and not paperPage.doi and not paperPage.abstract):
                        logger.warning(
                            f"Publisher 页面数据不完整（可能被 Cloudflare 拦截）: {paperDOI}"
                        )
                        db.update_error_message(
                            paperDOI, "publisher_page_fetched_status",
                            FetchStatus.FAILED.value,
                            "publisher_page_fetched_error",
                            "Title, DOI and Abstract all empty (possible Cloudflare block)",
                            "publisher_page_fetched_date", timestamp
                        )
                        consecutive_failures += 1
                        if consecutive_failures >= PUBLISHER_MAX_CONSECUTIVE_FAILURES:
                            logger.warning(
                                f"Publisher {publisher} 连续 {consecutive_failures} 篇抓取失败，中止该 publisher，剩余论文保留待处理状态"
                            )
                            break
                    else:
                        # ---- 步骤 3: 写入数据库 ----
                        consecutive_failures = 0
                        authors_json = json.dumps(
                            paperPage.authors, ensure_ascii=False
                        ) if paperPage.authors else "[]"
                        pdf_url = paperPage.pdf_url or ""
                        abstract = paperPage.abstract or ""
                        paperdate_page = paperPage.date or ""

                        db.update_publisher_page(
                            paperDOI, abstract, authors_json, pdf_url,
                            paperdate_page, FetchStatus.SUCCESS.value, timestamp
                        )
                        logger.debug(f"Publisher 页面抓取成功: {paperDOI}")

                except NaturePageNotPaper:
                    # Nature/Science 中非论文页面（如 News），静默跳过
                    consecutive_failures = 0
                    logger.info(f"非论文页面，跳过: {paperDOI}")
                    db.update_process_status(
                        paperDOI, "publisher_page_fetched_status",
                        FetchStatus.SKIPPED.value,
                        "publisher_page_fetched_date", timestamp
                    )

                except PageParseError as e:
                    logger.warning(f"页面解析失败 [{paperDOI}]: {e}")
                    db.update_error_message(
                        paperDOI, "publisher_page_fetched_status",
                        FetchStatus.FAILED.value,
                        "publisher_page_fetched_error", str(e),
                        "publisher_page_fetched_date", timestamp
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= PUBLISHER_MAX_CONSECUTIVE_FAILURES:
                        logger.warning(
                            f"Publisher {publisher} 连续 {consecutive_failures} 篇抓取失败，中止该 publisher，剩余论文保留待处理状态"
                        )
                        break

                except Exception as e:
                    logger.error(f"Publisher 抓取异常 [{paperDOI}]: {e}")
                    db.update_error_message(
                        paperDOI, "publisher_page_fetched_status",
                        FetchStatus.FAILED.value,
                        "publisher_page_fetched_error", str(e),
                        "publisher_page_fetched_date", timestamp
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= PUBLISHER_MAX_CONSECUTIVE_FAILURES:
                        logger.warning(
                            f"Publisher {publisher} 连续 {consecutive_failures} 篇抓取失败，中止该 publisher，剩余论文保留待处理状态"
                        )
                        break

                # 页面间随机延迟，避免连续请求触发速率限制
                delay = random.uniform(PUBLISHER_PAGE_DELAY_MIN, PUBLISHER_PAGE_DELAY_MAX)
                logger.debug(f"随机延迟 {delay:.1f}s 后处理下一篇...")
                time.sleep(delay)

        finally:
            # 确保浏览器资源被释放
            if scraper:
                try:
                    scraper.close()
                except Exception:
                    pass

        # 出版社间冷却，避免快速切换触发检测
        logger.info(f"出版社 {publisher} 处理完毕，冷却 15s...")
        time.sleep(15)

    logger.info("Phase C 完成")


# ==================================================================
# Phase D: 语义相似度初筛
#
# 职责: 使用 sentence-transformers 计算论文标题+摘要与研究领域的语义相似度
# 策略: score >= SEMANTIC_SIMILARITY_THRESHOLD → 进入 Phase E (LLM 精细判断)
#       score <  threshold → 直接标记为不相关，跳过 LLM (省 API 费用)
# 依赖: pip install sentence-transformers
# ==================================================================

def phase_d_semantic_filter(db, domain_config):
    """
    基于语义相似度对论文进行初筛。

    工作流程：
    1. 加载领域描述文本（空则跳过整个阶段，所有论文进 Phase E）
    2. 初始化 SemanticFilter（加载 sentence-transformers 模型，仅一次）
    3. 对每篇 pending 论文计算 title+abstract 与领域描述的余弦相似度
    4. score >= 阈值 → 保留 llm_relevance 为 pending，等待 Phase E
    5. score <  阈值 → 标记 llm_relevance 为 skipped（省去 LLM 调用）

    语义相似度优势：
    - 不依赖精确字符匹配，同义词/近义词也能获得合理分数
    - 段落级别的领域描述比关键词列表语义信息更丰富
    - cosine 分数可以精细排序，阈值可调

    Args:
        db:            DatabaseClient 实例
        domain_config: {"keywords": list[str], "domain_description": str}
    """
    logger.info("--- Phase D: 语义相似度初筛 ---")

    keywords = domain_config.get("keywords", [])
    domain_description = domain_config.get("domain_description", "")

    if not domain_description:
        logger.info("Phase D: 无领域描述，跳过（所有论文将进入 Phase E）")
        return

    logger.info(f"领域描述: {domain_description[:100]}...")
    logger.info(f"关键词数量: {len(keywords)}")

    # 初始化语义过滤器 (模型加载一次，复用给所有论文)
    try:
        sf = SemanticFilter(SEMANTIC_MODEL_PATH, domain_description)
    except ImportError as e:
        logger.error(f"Phase D: {e}")
        logger.error("请安装 sentence-transformers: pip install sentence-transformers")
        return
    except Exception as e:
        logger.error(f"Phase D: 语义过滤器初始化失败: {e}")
        return

    papers = db.get_pendings("semantic_filter_status")
    if MAX_PAPERS_PER_PHASE:
        papers = papers[:MAX_PAPERS_PER_PHASE]
    if not papers:
        logger.info("Phase D: 无待处理论文")
        return

    logger.info(f"Phase D: {len(papers)} 篇论文待初筛")

    threshold = SEMANTIC_SIMILARITY_THRESHOLD
    passed = 0
    skipped = 0

    for paper in papers:
        doi = paper["doi"]
        title = paper["title"] or ""
        abstract = paper["abstract"] or ""
        timestamp = str(datetime.now())

        try:
            # ---- 计算语义相似度 ----
            score = sf.compute_similarity(title, abstract)

            # ---- 存储得分 ----
            db.update_semantic_filter(doi, score, FetchStatus.SUCCESS.value, timestamp)

            if score >= threshold:
                # 相似度达标 → 保留 llm_relevance 为 pending，等待 Phase E 细筛
                passed += 1
                logger.debug(f"{doi}: score={score:.3f} → 通过初筛")
            else:
                # 相似度不足 → 直接标记不相关，省去 LLM 调用
                db.update_process_status(
                    doi, "llm_relevance_status",
                    FetchStatus.SKIPPED.value,
                    "llm_relevance_date", timestamp
                )
                skipped += 1
                logger.debug(f"{doi}: score={score:.3f} → 跳过 (阈值={threshold})")

        except Exception as e:
            logger.error(f"Phase D: 语义相似度计算失败 [{doi}]: {e}")
            db.update_error_message(
                doi, "semantic_filter_status",
                FetchStatus.FAILED.value,
                "semantic_filter_error", str(e),
                "semantic_filter_date", timestamp
            )

    logger.info(f"Phase D 完成: {passed} 篇通过, {skipped} 篇跳过")


# ==================================================================
# Phase E: LLM 相关性判断
#
# 职责: 调用 DeepSeek API 对初筛通过的论文做精细相关性判断
# 输出: JSON { relevant, confidence, reason }
# ==================================================================

def phase_e_llm_relevance(db):
    """
    调用 DeepSeek LLM 对初筛通过的论文进行相关性判断。

    工作流程：
    1. 查询 llm_relevance_status = 'pending' 的论文
    2. 加载关键词和领域描述，构造提示词
    3. 通过 ThreadPoolExecutor 并发调用 LLM API
    4. 主线程统一解析 JSON 并写入数据库

    Args:
        db: DatabaseClient 实例
    """
    logger.info("--- Phase E: LLM 相关性判断 ---")
    if SKIP_PHASE_E:
        logger.info("Phase E: SKIP_PHASE_E=True, skipping")
        return

    domain_config = load_keywords()
    keywords = domain_config.get("keywords", [])
    domain_description = domain_config.get("domain_description", "")
    if not keywords and not domain_description:
        logger.info("Phase E: 无关键词与领域描述配置，跳过 LLM 相关性判断")
        return

    paper_tasks = db.get_pendings("llm_relevance_status")
    if MAX_PAPERS_PER_PHASE:
        paper_tasks = paper_tasks[:MAX_PAPERS_PER_PHASE]
    if not paper_tasks:
        logger.info("Phase E: 无待判断论文")
        return

    logger.info(f"Phase E: {len(paper_tasks)} 篇论文待判断相关性")

    checker = PaperRelevanceChecker(keywords, domain_description)

    # 预构建所有 prompt（主线程中，无网络 I/O）
    tasks = []
    skipped_no_abstract = 0
    for paper in paper_tasks:
        doi = paper["doi"]
        abstract = (paper["abstract"] or "").strip()
        if not abstract:
            logger.info(f"无摘要，跳过 LLM 判断: {doi}")
            db.update_process_status(
                doi, "llm_relevance_status",
                FetchStatus.SKIPPED.value,
                "llm_relevance_date", str(datetime.now())
            )
            skipped_no_abstract += 1
            continue
        prompt = checker.build_default_prompt(
            paper["title"] or "", abstract
        )
        tasks.append((paper, prompt))

    if skipped_no_abstract:
        logger.info(f"Phase E: {skipped_no_abstract} 篇因无摘要跳过")

    if not tasks:
        logger.info("Phase E: 无有效待判断论文（均无摘要）")
        return

    # 并发调用 LLM API
    max_workers = min(len(tasks), LLM_CONCURRENT_MAX)
    logger.info(f"Phase E: 使用 {max_workers} 个并发请求")
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(checker.call_deepseek_api, prompt, LLM_API_CONFIG_DICT_RELE): (paper, prompt)
            for paper, prompt in tasks
        }
        for future in as_completed(futures):
            paper, _ = futures[future]
            doi = paper["doi"]
            timestamp = str(datetime.now())
            try:
                result_str = future.result()
                result = json.loads(result_str)
                relevant = 1 if result.get("relevant", False) else 0
                confidence = result.get("confidence", "low")
                reason = result.get("reason", "")

                db.update_llm_relevance(
                    doi, relevant, confidence, reason,
                    FetchStatus.SUCCESS.value, timestamp
                )
                success_count += 1
                logger.debug(f"LLM 相关性判断: {doi} → relevant={bool(relevant)}, "
                             f"confidence={confidence}")

            except (LLMAPICallError, LLMResponseParseError) as e:
                logger.warning(f"LLM 相关性 API 错误 [{doi}]: {e}")
                db.update_llm_relevance_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp
                )

            except json.JSONDecodeError as e:
                logger.warning(f"LLM 返回非 JSON [{doi}]: {e}")
                db.update_llm_relevance_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp
                )

            except Exception as e:
                logger.error(f"LLM 相关性异常 [{doi}]: {e}")
                db.update_llm_relevance_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp
                )

    logger.info(f"Phase E 完成: {success_count} 篇判断成功")


# ==================================================================
# Phase E2: MinerU PDF 全文解析
#
# 职责: 对 LLM 判定为相关的论文，下载 PDF 并通过 MinerU API 解析全文
# 输出: Markdown 格式全文存入 mineru_fulltext 列，供 Phase F 使用
#
# 设计考量:
# - MinerU 调用较慢且消耗 Token，仅处理有 PDF 链接的相关论文
# - 单篇失败不中断处理，记录错误后继续下一篇
# - 临时 PDF 和 MinerU 输出目录均在处理完毕后清理
# ==================================================================

def phase_e2_mineru(db):
    """
    对 LLM 判定为相关的论文，下载 PDF 并调用 MinerU API 解析全文。

    工作流程：
    1. 检查 MINERU_TOKEN 是否已配置，未配置则跳过
    2. 查询 llm_relevance_result = 1 且 pdf_url 非空、mineru_parse_status = 'pending' 的论文
    3. 逐篇下载 PDF → 保存为临时文件 → 调用 MinerUParser.parse_pdf
    4. 读取 full.md 内容写入数据库
    5. 清理临时文件（PDF 和 MinerU 输出目录）

    MinerU 输出结构:
      {output_dir}/
        ├── full.md           # Markdown 全文（Phase F 的输入源）
        ├── images/           # 文中提取的图片
        └── layout.json 等   # 版面识别结果

    Args:
        db: DatabaseClient 实例
    """
    logger.info("--- Phase E2: MinerU PDF 全文解析 ---")
    if SKIP_PHASE_E2:
        logger.info("Phase E2: SKIP_PHASE_E2=True, skipping")
        return

    # ---- Token 检查：未配置则静默跳过 ----
    if not MINERU_TOKEN:
        logger.info("Phase E2: MINERU_TOKEN 未配置，跳过 PDF 全文解析")
        return

    # ---- 筛选待处理论文：相关 + 有 PDF + 未解析 ----
    relevant_papers = db.get_relevant_papers()
    papers_with_pdf = [
        p for p in relevant_papers
        if p["pdf_url"] and p["mineru_parse_status"] == "pending"
    ]

    if not papers_with_pdf:
        logger.info("Phase E2: 无待解析的 PDF")
        return

    logger.info(f"Phase E2: {len(papers_with_pdf)} 篇论文待 MinerU 解析")

    # ---- 初始化 MinerU 解析器 ----
    parser = MinerUParser(MINERU_TOKEN)

    success_count = 0
    failed_count = 0
    pw = None
    pdf_context = None

    try:
        # ---- 初始化 Playwright 浏览器用于 PDF 下载 ----
        # 复用 Phase C 的反检测策略，出版商 PDF 链接通常需要 session cookie / Cloudflare 认证
        pw = sync_playwright().start()
        pdf_context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_SESSION_DIR / "mineru_download"),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1920, "height": 1080},
        )
        pdf_page = pdf_context.new_page()
        # 注入反检测 JS（与 Phase C Publisher Scraper 一致）
        pdf_page.evaluate("""
        () => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
        }
        """)

        for paper in papers_with_pdf:
            doi = paper["doi"]
            pdf_url = paper["pdf_url"]
            timestamp = str(datetime.now())
            pdf_path = None

            try:
                # ---- 步骤 1: 通过 Playwright 下载 PDF 到临时文件 ----
                # 出版商 PDF 链接通常先返回 HTML 预览页，再由 JS viewer 异步加载真实 PDF。
                # page.goto() 的 response 只代表导航请求（HTML），需监听所有网络响应捕获 PDF。
                logger.info(f"下载 PDF: {doi} ← {pdf_url}")
                pdf_body = None

                def _capture_pdf(response):
                    nonlocal pdf_body
                    ct = (response.headers.get("content-type") or "").lower()
                    if "application/pdf" in ct or "application/octet-stream" in ct:
                        try:
                            pdf_body = response.body()
                        except Exception:
                            pass  # 响应体已被浏览器消费（PDF viewer 内嵌场景）

                pdf_page.on("response", _capture_pdf)
                try:
                    pdf_page.goto(pdf_url, wait_until="networkidle", timeout=60000)
                finally:
                    pdf_page.remove_listener("response", _capture_pdf)

                if pdf_body is None or pdf_body[:5] != b'%PDF-':
                    # 兜底：通过页面内 fetch 重新获取（浏览器 session/cookie 可用）
                    logger.debug(f"响应监听未捕获 PDF，尝试 fetch 兜底: {doi}")
                    raw = pdf_page.evaluate(f"""
                        async () => {{
                            const resp = await fetch('{pdf_url}');
                            const buf = await resp.arrayBuffer();
                            return Array.from(new Uint8Array(buf));
                        }}
                    """)
                    pdf_body = bytes(raw) if raw else None

                if pdf_body is None or pdf_body[:5] != b'%PDF-':
                    raise RuntimeError(
                        "页面未返回有效 PDF（可能被重定向到预览页或需登录）"
                    )

                with tempfile.NamedTemporaryFile(
                    suffix=".pdf", delete=False
                ) as tmp:
                    tmp.write(pdf_body)
                    pdf_path = tmp.name

                # ---- 步骤 2: MinerU 解析 PDF，结果持久化到 data/mineru_output/ ----
                logger.debug(f"MinerU 解析中: {doi}")
                safe_doi = doi.replace("/", "_").replace("\\", "_")
                mineru_output_dir = parser.parse_pdf(
                    pdf_path, output_dir=MINERU_OUTPUT_DIR / safe_doi
                )
                full_md_path = mineru_output_dir / "full.md"

                # ---- 步骤 3: 读取全文 Markdown 并写入数据库 ----
                if full_md_path.exists():
                    fulltext = full_md_path.read_text(encoding="utf-8")
                    # 相对路径（相对于 data/），用于定位 PDF 和 MinerU 输出
                    rel_dir = str(mineru_output_dir.relative_to(MINERU_OUTPUT_DIR.parent))
                    db.update_mineru_result(
                        doi, fulltext, rel_dir,
                        FetchStatus.SUCCESS.value, timestamp
                    )
                    success_count += 1
                    logger.info(f"MinerU 成功: {doi} ({len(fulltext)} 字符)")
                else:
                    raise RuntimeError("MinerU 输出缺少 full.md")

                # ---- 步骤 4: 将 PDF 保存到 MinerU 输出目录 ----
                pdf_dest = mineru_output_dir / "paper.pdf"
                shutil.move(pdf_path, str(pdf_dest))
                logger.debug(f"PDF 已保存: {pdf_dest}")
                pdf_path = None

            except Exception as e:
                logger.warning(f"MinerU 失败 [{doi}]: {e}")
                db.update_mineru_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp
                )
                failed_count += 1
                # 清理残留的临时 PDF
                try:
                    if pdf_path:
                        Path(pdf_path).unlink(missing_ok=True)
                except Exception:
                    pass

            # PDF 下载间随机延迟，避免触发速率限制
            delay = random.uniform(3, 8)
            logger.debug(f"PDF 下载延迟 {delay:.1f}s...")
            time.sleep(delay)

    finally:
        # 释放 Playwright 资源
        try:
            if pdf_context:
                pdf_context.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass

    logger.info(
        f"Phase E2 完成: {success_count} 成功, {failed_count} 失败"
    )


# ==================================================================
# Phase F: LLM 论文内容总结
#
# 职责: 对判定为相关的论文，调用 DeepSeek API 生成结构化总结
# 输入: MinerU 全文（无全文则跳过）
# 输出: JSON (含 一句话/动机/方法/结果/要点 五个维度)
# ==================================================================

def phase_f_llm_summary(db):
    """
    对 LLM 判定为相关的论文生成结构化总结。

    总结结构 (JSON):
      - one_sentence:             一句话核心结论
      - motivation_and_goal:      研究动机与目标
      - key_setup_and_method:     关键方法与参数
      - main_results_and_physics: 主要结果与物理解释 (Markdown)
      - take_home_message:        要点与局限

     输入: MinerU 全文（无全文则跳过）
     并发: ThreadPoolExecutor 并行调用 LLM API

     Args:
         db: DatabaseClient 实例
    """
    logger.info("--- Phase F: LLM 总结 ---")
    if SKIP_PHASE_F:
        logger.info("Phase F: SKIP_PHASE_F=True, skipping")
        return
    papers = db.get_pendings("llm_summary_status")
    if MAX_PAPERS_PER_PHASE:
        papers = papers[:MAX_PAPERS_PER_PHASE]
    if not papers:
        logger.info("Phase F: 无待总结论文")
        return

    # ---- 仅总结 LLM 判定为相关的论文 ----
    relevant_papers = [
        p for p in papers
        if p["llm_relevance_result"]
    ]

    domain_config = load_keywords()
    if not domain_config.get("keywords") and not domain_config.get("domain_description"):
        relevant_papers = papers

    if not relevant_papers:
        logger.info("Phase F: 无相关论文需要总结")
        return

    # ---- 筛选有 MinerU 全文的论文 & 预构建输入 ----
    summarizer = DeepSeekPaperSummarizer(llm_api_config=LLM_API_CONFIG_DICT_SUMM)
    tasks = []
    for paper in relevant_papers:
        doi = paper["doi"]
        mineru_text = paper["mineru_fulltext"] or ""
        if not mineru_text.strip():
            logger.info(f"无 MinerU 全文，跳过总结: {doi}")
            db.update_llm_summary_error(
                doi, "No MinerU fulltext available",
                FetchStatus.SKIPPED.value, str(datetime.now())
            )
            continue
        article_text = f"标题: {paper['title'] or ''}\n\n全文:\n{mineru_text}"
        logger.debug(f"使用 MinerU 全文 for {doi}: {len(mineru_text)} 字符")
        tasks.append((paper, article_text))

    if not tasks:
        logger.info("Phase F: 无可用全文，跳过")
        return

    logger.info(f"Phase F: {len(tasks)} 篇论文待总结")

    max_workers = min(len(tasks), LLM_CONCURRENT_MAX)
    logger.info(f"Phase F: 使用 {max_workers} 个并发请求")
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(summarizer.call_deepseek_api, article_text, SUMMARIES_PROMPT): paper
            for paper, article_text in tasks
        }
        for future in as_completed(futures):
            paper = futures[future]
            doi = paper["doi"]
            timestamp = str(datetime.now())
            try:
                result_str = future.result()
                json.loads(result_str)
                db.update_llm_summary(
                    doi, result_str, FetchStatus.SUCCESS.value, timestamp
                )
                success_count += 1

            except (LLMAPICallError, LLMResponseParseError) as e:
                logger.warning(f"LLM 总结 API 错误 [{doi}]: {e}")
                db.update_llm_summary_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp
                )

            except LLMContextLengthExceed as e:
                logger.warning(f"LLM 总结上下文过长 [{doi}]: {e}")
                db.update_llm_summary_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp
                )

            except json.JSONDecodeError as e:
                logger.warning(f"LLM 返回非 JSON [{doi}]: {e}")
                db.update_llm_summary_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp
                )

            except Exception as e:
                logger.error(f"LLM 总结意外错误 [{doi}]: {e}")
                db.update_llm_summary_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp
                )

    logger.info(f"Phase F 完成: {success_count} 篇论文已总结")


# ==================================================================
# Phase G: 报告生成
#
# 职责: 将所有已生成总结的论文整合为 Markdown 报告，并转换为 PDF
# 输出: data/reports/report_<timestamp>.md 和 .pdf
# ==================================================================

def phase_g_report(db, report_dir):
    """
    生成 Markdown 文献报告，仅包含尚未报告过的新论文。

    工作流程：
    1. 从数据库获取 llm_summary_status = 'success' 且 report_status = 'pending' 的论文
    2. 解析 JSON 格式的总结数据和作者列表
    3. 调用 paper_report_generator 生成 Markdown 报告
    4. 保存报告后标记论文 report_status = 'reported'

    Args:
        db:         DatabaseClient 实例
        report_dir: 报告输出目录路径
    """
    logger.info("--- Phase G: 报告生成 ---")
    papers = db.get_papers_for_report()
    if not papers:
        logger.info("Phase G: 无新增已总结论文，跳过报告生成")
        return

    logger.info(f"Phase G: {len(papers)} 篇新论文将生成报告")

    # ---- 构建报告数据列表 ----
    paper_list = []
    reported_dois = []
    for p in papers:
        # 解析 LLM 总结 JSON
        summary = {}
        try:
            summary = json.loads(p["llm_summary_result"] or "{}")
        except json.JSONDecodeError:
            pass  # 解析失败则使用空字典

        # 解析作者列表
        authors = []
        try:
            authors = json.loads(p["authors_json"] or "[]")
        except json.JSONDecodeError:
            pass  # 解析失败则使用空列表

        # CrossRef / Publisher 的作者格式为 [{"name": "...", "orcid": "..."}]
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            authors = [a.get("name", "") for a in authors if a.get("name")]

        paper_dict = {
            "title": p["title"] or "",
            "authors": authors,
            # 日期优先级: CrossRef > Publisher > RSS
            "date": (
                p["paperdate_crossref"]
                or p["paperdate_page"]
                or p["paperdate_rss"]
                or ""
            ),
            "doi": p["doi"] or "",
            "page_url": p["page_url"] or "",
            "pdf_url": p["pdf_url"] or "",
            "abstract": p["abstract"] or "",
            "one_sentence": summary.get("one_sentence", ""),
            "motivation_and_goal": summary.get("motivation_and_goal", ""),
            "key_setup_and_method": summary.get("key_setup_and_method", ""),
            "main_results_and_physics": summary.get(
                "main_results_and_physics", ""
            ),
            "take_home_message": summary.get("take_home_message", ""),
        }
        paper_list.append(paper_dict)
        reported_dois.append(p["doi"])

    # ---- 生成 Markdown 报告 ----
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    md_report = generate_report(paper_list, format="markdown", toc=True)
    md_path = report_dir / f"report_{timestamp_str}.md"
    md_path.write_text(md_report, encoding="utf-8")
    logger.info(f"Markdown 报告已保存: {md_path}")

    # ---- 标记论文为已报告 ----
    report_timestamp = str(datetime.now())
    db.mark_papers_reported(reported_dois, report_timestamp)
    logger.info(f"已标记 {len(reported_dois)} 篇论文为 reported")

    logger.info(f"Phase G 完成: {len(paper_list)} 篇论文汇入报告")
    logger.info(f"如需 PDF 版本，请运行: python tools/convert_md_to_pdf.py {md_path}")


# ==================================================================
# Phase H: 邮件推送
#
# 职责: 将最新生成的报告文件通过 SMTP 发送给配置的收件人
# 策略: 仅在 email.yaml 已配置真实凭证时才执行，否则静默跳过
# ==================================================================

def phase_h_email(report_dir):
    """
    收集最新生成的 Markdown 报告并通过 SMTP 发送给团队成员。

    工作流程：
    1. 读取 configs/email.yaml 获取 SMTP 配置和收件人列表
    2. 找到最新生成的 .md 报告文件作为附件
    3. 构建邮件 (主题 + 正文 + .md 附件)
    4. 发送邮件

    跳过条件:
      - email.yaml 不存在
      - username/password 含占位符 "your_"
      - to_addrs 为空列表
      - 没有找到报告文件

    Args:
        report_dir: 报告输出目录路径
    """
    logger.info("--- Phase H: 邮件推送 ---")
    if SKIP_PHASE_H:
        logger.info("Phase H: SKIP_PHASE_H=True, skipping")
        return
    try:
        email_cfg = load_email_config()
    except Exception as e:
        logger.warning(f"邮件配置文件解析失败: {e}")
        return
    if not email_cfg:
        logger.info("Phase H: 无邮件配置，跳过")
        return

    # ---- 凭证检查：跳过未填写真实值的模板 ----
    username = email_cfg.get("username", "")
    password = email_cfg.get("password", "")
    if not username or not password or "your_" in username or "your_" in password:
        logger.info("Phase H: 邮件凭证未配置，跳过")
        return

    to_addrs = email_cfg.get("to_addrs", [])
    if not to_addrs:
        logger.info("Phase H: 无收件人，跳过")
        return

    # ---- 收集附件：最新 Markdown 报告 ----
    report_dir = Path(report_dir)
    md_files = sorted(report_dir.glob("report_*.md"), reverse=True)

    attachments = []
    if md_files:
        attachments.append(str(md_files[0]))

    if not attachments:
        logger.info("Phase H: 未找到报告文件，跳过")
        return

    # ---- 发送邮件 ----
    sender = EmailSender(
        smtp_host=email_cfg["smtp_host"],
        smtp_port=email_cfg["smtp_port"],
        username=username,
        password=password,
        from_addr=email_cfg["from_addr"],
        to_addrs=to_addrs,
        use_tls=email_cfg.get("use_tls", True),
    )

    subject = f"PaperCrawler 文献报告 - {datetime.now().strftime('%Y-%m-%d')}"

    body = (
        f"您好，\n\n"
        f"以下是近期的文献追踪报告，包含 {len(attachments)} 个附件。\n\n"
        f"祝好！\nPapersCrawler 自动发送"
    )

    try:
        sender.send(subject, body, body_type="plain", attachments=attachments)
        logger.info(f"邮件已发送至 {len(to_addrs)} 位收件人")
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")

    logger.info("Phase H 完成")


# ==================================================================
# 入口
# ==================================================================

if __name__ == "__main__":
    main()
