#!/usr/bin/env bash
# =============================================================================
# 每日运行包装脚本 — conda + xvfb-run
#
# 用法:
#   ./tools/run_daily.sh                    # 默认 conda 环境 base
#   CONDA_ENV=paperscrawler ./tools/run_daily.sh  # 指定 conda 环境
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

CONDA_ENV="${CONDA_ENV:-base}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

echo "[run_daily] Activating conda env: ${CONDA_ENV}"
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

export LOG_LEVEL
exec xvfb-run -a python "${PROJECT_ROOT}/tools/schedule_daily.py"
