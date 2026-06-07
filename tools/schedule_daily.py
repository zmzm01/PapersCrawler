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
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import LOG_FILE_PATH, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
console_handler = logging.StreamHandler()
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[file_handler, console_handler],
)

from pipeline.runner import run_daily

if __name__ == "__main__":
    run_daily()
