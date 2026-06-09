#!/usr/bin/env python
"""
每日调度入口：发现 → LLM 总结。

等价于依次执行 Phase A-RSS / A-CR / B / C / D / E / E2 / F。
尊重 settings.yaml 中的 SKIP_PHASE_* 配置（CLI 模式，force=False）。

典型 cron 配置:

    # 每天 2:00
    0 2 * * * cd /path/to/PapersCrawler && python tools/schedule_daily.py

无图形界面服务器需配合 xvfb-run（Phase C 需要虚拟显示器）:

    0 2 * * * cd /path/to/PapersCrawler && xvfb-run -a python tools/schedule_daily.py
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import LOG_FILE_PATH, DATA_DIR, DB_PATH

DATA_DIR.mkdir(parents=True, exist_ok=True)

file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
console_handler = logging.StreamHandler()
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[file_handler, console_handler],
)

from db.database import DatabaseClient
from pipeline.runner import run_daily

if __name__ == "__main__":
    # 自动重置所有失败 Publisher 抓取的论文，使其得到重试机会
    logger = logging.getLogger(__name__)
    reset_db = DatabaseClient(DB_PATH)
    reset_db.init_db_papers()
    count = reset_db.batch_reset_status(
        [("publisher_page_fetched_status", "pending")],
        "publisher_page_fetched_status = 'failed'",
    )
    if count:
        logger.info(f"Auto-reset {count} failed publisher pages for retry")
    run_daily()
