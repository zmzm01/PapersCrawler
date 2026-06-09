#!/usr/bin/env python
"""
每周调度入口：报告生成 → 邮件推送。

等价于依次执行 Phase G / H。
尊重 settings.yaml 中的 SKIP_PHASE_* 配置（CLI 模式，force=False）。
Phase H 将 auto/ 目录下的今日报告作为附件发送；无新增论文时发送无更新通知。

典型 cron 配置:

    # 每周一 9:00
    0 9 * * 1 cd /path/to/PapersCrawler && python tools/schedule_weekly.py
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import LOG_FILE_PATH, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
console_handler = logging.StreamHandler()
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[file_handler, console_handler],
)

from pipeline.runner import run_weekly

if __name__ == "__main__":
    run_weekly()
