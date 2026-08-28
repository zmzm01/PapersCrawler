#!/usr/bin/env bash
# =============================================================================
# 每周运行包装脚本 - 报告生成 + 邮件推送 + GitHub Pages 部署
# 可通过 PAPERSCRAWLER_PYTHON 指定项目 Python；默认使用 PATH 中的 python。
# Phase G/H 不需要浏览器，无需 xvfb-run。
# =============================================================================
set -euo pipefail

# 项目 conda 环境 Python 路径（crontab 下 PATH 不完整，用全路径）
PYTHON="${PAPERSCRAWLER_PYTHON:-python}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# crontab 下 PATH 极简，补充 hugo(/usr/local/bin) 和 conda bin(ghp-import等)
PYTHON_BIN_DIR="$(dirname "${PYTHON}")"
export PATH="/usr/local/bin:${PYTHON_BIN_DIR}:${PATH:-}"

# 切换到项目根目录（确保 .env 和 PYTHONPATH 正确）
cd "$(dirname "$0")"

export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
export LOG_LEVEL

echo "[run_weekly] Phase G + H: report generation and email delivery"
"${PYTHON}" tools/run_pipeline.py --weekly

echo "[run_weekly] Deploying latest report to GitHub Pages"
"${PYTHON}" tools/convert_reports_to_hugo.py --all --hugo --deploy
