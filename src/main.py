import os
import logging

from config import load_publishers, REQUEST_TIMEOUT, CROSSREF_MAILTO, LOG_FILE_PATH, DB_PATH, BROWSER_SESSION_DIR, RAW_RSS_DIR
from utils.db import DatabaseClient, FetchStatus
from sources.rss import RSSProcessor
from sources.crossref import CrossrefClient
from sources.publisher import NatureScraper, ScienceScraper, APSScraper, AIPScraper, IOPScraper, CambridgeScraper, OpticaScraper


# publisher scraper 配置
scraper_map = {
    "nature": (NatureScraper, BROWSER_SESSION_DIR / "nature", None),
    "science": (ScienceScraper, BROWSER_SESSION_DIR / "science", None),
    "aps": (APSScraper, BROWSER_SESSION_DIR / "aps", None),
    "aip": (AIPScraper, BROWSER_SESSION_DIR / "aip", None),
    "iop": (IOPScraper, BROWSER_SESSION_DIR / "iop", None),
    "cambridge": (CambridgeScraper, BROWSER_SESSION_DIR / "cambridge", None),
    "optica": (OpticaScraper, BROWSER_SESSION_DIR / "cambridge", {"server": "http://127.0.0.1:10808"}),
}
def create_scraper(publisher):
    config = scraper_map[publisher]
    if not config:
        raise ValueError(f"No config for {publisher}")
    scraper_class, user_data_dir, proxy = config
    os.makedirs(user_data_dir, exist_ok=True)
    scraper = scraper_class(user_data_dir)
    scraper.start_browser(proxy)
    return scraper


# 日志设置
file_handler = logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
console_handler = logging.StreamHandler()
logging.basicConfig(
    level=logging.DEBUG,   # DEBUG 会输出所有细节
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[file_handler, console_handler]
)

# 加载 logger
logger = logging.getLogger(__name__)

# 加载数据源
publishers = load_publishers() 
logger.info("成功加载数据源，开始处理...")

# 加载数据库
dbClient = DatabaseClient(DB_PATH)
dbClient.init_db_papers()

# ==============================
# 开始 RSS 更新
# ==============================
logger.info("开始 RSS 处理...")

rsspro = RSSProcessor() # 初始化 RSS 抓取器

for journal in publishers:
    logger.info("RSS 抓取开始")
    journalid = journal["id"]
    publisher = journal["publisher"]
    rss_url = journal["rss"]
    journal_name = journal["name"]
    try:
        # 设置 rss 文件路径
        RAW_RSS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d")
        rss_file_save_path = RAW_RSS_DIR / f"{journalid}_{timestamp}.xml"

        if rss_file_save_path.exists():
            xml_text = rss_file_save_path.read_text()
        else:
            xml_text = rsspro.fetch_rss(rss_url)
            rsspro.save_raw_rss(xml_text, str(rss_file_save_path)) # 保存
        
        papers = rsspro.parse_rss(xml_text, journal) # 解析
        logger.debug(f"Found {len(papers)} papers in {journalid}.")

        # 写入基本信息到数据库
        for paper in papers:
            paperDOI = paper["doi"]
            
            logger.debug(f"正在处理文章 {paperDOI}")
            
            # 检查 paper DOI 是否已经存在，不存在则记录部分 RSS 获取的元数据
            if not dbClient.paper_doi_exists(paperDOI):
                logger.debug(f"Write paper {paperDOI} into database.")
                dbClient.insert_rss_basicinfo(paperDOI, paper["title"], paper["link"], journal_name, publisher, paper["updated"])
                dbClient.insert_paper_created_date(paperDOI, timestamp) # 插入创建时间
    
    except Exception as e:
        logger.error(f"{journal["id"]}: {e}")

logger.info(f"抓取 RSS 源完成")


# ==============================
# 开始 CrossRef 抓取
# ==============================
logger.info("开始 CrossRef 元数据抓取...")

# 加载 CrossrefClient
crClient = CrossrefClient(mailto=CROSSREF_MAILTO, timeout=REQUEST_TIMEOUT)

# 找到那些新增的需要获取元数据的文章
paper_tasks = dbClient.get_pendings(cr_metadata_fetched_status)

for paper_task in paper_tasks:
    paperDOI = paper_task["doi"]
    try:
        crossrefPaper = crClient.fetch_by_doi(paperDOI)
        logger.debug(f"{crossrefPaper.title} | {crossrefPaper.doi} | {crossrefPaper.url}")

        dbClient.update_crossref_metadata(paperDOI, crossrefPaper.title, crossrefPaper.authors, crossrefPaper.published)
        dbClient.update_process_status(paperDOI, 'cr_metadata_fetched_status', FetchStatus.SUCCESS.value, cr_metadata_fetched_date, str(datetime.now())) # 更新 CrossRef 元数据处理状态
    except NotFoundError as e:
        # 捕捉到 CrossRef NotFound 错误
        logger.error(f"CrossRef returns NO METADATA about {paperDOI}, perhaps the DOI has not been activated yet.")
        dbClient.update_error_message(paperDOI, 'cr_metadata_fetched_status', FetchStatus.FAILED.value, cr_metadata_fetched_error, str(e), cr_metadata_fetched_date, str(datetime.now())) # 更新 CrossRef 元数据处理状态

logger.info("CrossRef 元数据抓取完成")

# ==============================
# 开始 publisher page 抓取
# ==============================

logger.info("开始 publisher page 抓取...")

paper_tasks = dbClient.get_pendings(publisher_page_fetched_status)
paper_tasks_grouped = defaultdict(list) # 按照 publisher 分组
for paper_task in paper_tasks:
    key = paper_task["publisher"]
    paper_tasks_grouped[key].append(paper_task)

for publisher, papers in paper_tasks_grouped.items():
    scraper = create_scraper(publisher)
    for paper in papers:
        paperDOI = paper["doi"]
        page_url = paper["page_url"]
        try:
            scraper.fetch_page(page_url)
            paperPage = scraper.parse_page()
            # TODO: 更新页面抓取数据
        except NotFoundError as e:
            pass
            # TODO: 错误处理

logger.info("publisher page 抓取完成")
