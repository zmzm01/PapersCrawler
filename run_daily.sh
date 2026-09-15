#!/usr/bin/env bash
# =============================================================================
# 每日运行包装脚本 - Python + 可选 xvfb-run
# 可通过 PAPERSCRAWLER_PYTHON 指定项目 Python；默认使用项目 .venv。
# =============================================================================
set -euo pipefail

# crontab 下 PATH 不完整，默认使用仓库内独立虚拟环境。
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PAPERSCRAWLER_PYTHON:-${PROJECT_ROOT}/.venv/bin/python}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# 切换到项目根目录（确保 .env 和 PYTHONPATH 正确）
cd "${PROJECT_ROOT}"

export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
export LOG_LEVEL

if command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a "${PYTHON}" tools/run_pipeline.py --daily
else
  "${PYTHON}" tools/run_pipeline.py --daily
fi
