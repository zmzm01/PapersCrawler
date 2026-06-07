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

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.runner import run_weekly

if __name__ == "__main__":
    run_weekly()
