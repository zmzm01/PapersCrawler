"""
PapersCrawler CLI entry point.

Usage:
    python src/main.py

Runs the full pipeline (Phases A through H).
For selective phase execution, use pipeline/runner.run_phases().
"""

import os

from config import DATA_DIR
from logging_config import configure_logging, resolve_log_dir

configure_logging(
    os.getenv("LOG_LEVEL", "DEBUG"),
    resolve_log_dir(DATA_DIR / "logs"),
)

from pipeline.runner import run_pipeline
from config import _check_mineru_token

# 在 logging.basicConfig 配置完成后再检测 token，避免 warning 偷装默认 handler
_check_mineru_token()

if __name__ == "__main__":
    run_pipeline()
