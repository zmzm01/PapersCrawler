#!/usr/bin/env bash
# =============================================================================
# 每日运行包装脚本 - Python + 可选 xvfb-run
# 可通过 PAPERSCRAWLER_PYTHON 指定项目 Python；默认使用 PATH 中的 python。
# =============================================================================
set -euo pipefail

# 项目 conda 环境 Python 路径（crontab 下 PATH 不完整，用全路径）
PYTHON="${PAPERSCRAWLER_PYTHON:-python}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# 切换到项目根目录（确保 .env 和 PYTHONPATH 正确）
cd "$(dirname "$0")"

export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
export LOG_LEVEL

if command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a "${PYTHON}" tools/run_pipeline.py --daily
else
  "${PYTHON}" tools/run_pipeline.py --daily
fi
