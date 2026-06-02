"""
PapersCrawler CLI entry point.

Usage:
    python src/main.py

Runs the full pipeline (Phases A through H).
For selective phase execution, use pipeline/runner.run_phases().
"""

from pipeline.runner import run_pipeline

if __name__ == "__main__":
    run_pipeline()
