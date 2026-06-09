"""
PapersCrawler CLI entry point.

Usage:
    python src/main.py

Runs the full pipeline (Phases A through H).
For selective phase execution, use pipeline/runner.run_phases().
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from config import LOG_FILE_PATH, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
console_handler = logging.StreamHandler()
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[file_handler, console_handler],
)

from pipeline.runner import run_pipeline

if __name__ == "__main__":
    run_pipeline()
