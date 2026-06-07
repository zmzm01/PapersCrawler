"""
Pipeline orchestrator.

Provides run_pipeline() for full execution and run_phases() for selective runs.
"""

import json

from config import (
    load_publishers, load_keywords,
    DB_PATH, REPORT_DIR, AUTO_REPORT_DIR, USER_REPORT_DIR, DATA_DIR,
    SKIP_PHASE_A_RSS, SKIP_PHASE_A_CR,
    SKIP_PHASE_B, SKIP_PHASE_C, SKIP_PHASE_D,
    SKIP_PHASE_E, SKIP_PHASE_E2, SKIP_PHASE_F, SKIP_PHASE_G, SKIP_PHASE_H,
)


def _load_skip_overrides():
    """Load SKIP_PHASE overrides from data/skip_overrides.json."""
    path = DATA_DIR / "skip_overrides.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return {}


def _get_effective_skip(overrides):
    """Build effective skip dict: overrides take precedence over defaults."""
    defaults = {
        "A_RSS": SKIP_PHASE_A_RSS, "A_CR": SKIP_PHASE_A_CR,
        "B": SKIP_PHASE_B, "C": SKIP_PHASE_C,
        "D": SKIP_PHASE_D, "E": SKIP_PHASE_E, "E2": SKIP_PHASE_E2,
        "F": SKIP_PHASE_F, "G": SKIP_PHASE_G, "H": SKIP_PHASE_H,

    }
    return {k: overrides.get(k, defaults[k]) for k in defaults}


from db.database import DatabaseClient
from pipeline.base import logger

from pipeline.phase_a import phase_a_rss, phase_a_crossref
from pipeline.phase_b import phase_b_crossref
from pipeline.phase_c import phase_c_publisher
from pipeline.phase_d import phase_d_semantic_filter
from pipeline.phase_e import phase_e_llm_relevance
from pipeline.phase_e2 import phase_e2_mineru
from pipeline.phase_f import phase_f_llm_summary
from pipeline.phase_g import phase_g_report
from pipeline.phase_h import phase_h_email


def run_phases(phase_list=None, force=False):
    """Run selected phases of the pipeline.

    Parameters
    ----------
    phase_list : list of str, optional
        Phase names to run (e.g. ["A", "C", "F"]).
        If None, runs all non-skipped phases.
    force : bool, optional
        If True, load SKIP overrides from data/skip_overrides.json.
        Used by Web UI: overrides are set via Config page SKIP toggles.
        CLI (force=False) always uses config.py defaults only.
    """
    publishers = load_publishers()
    keywords = load_keywords()
    logger.info(f"Loaded {len(publishers)} publishers")
    logger.info(f"Scope definition: {len(keywords.get('scope_definition', {}))} sub-domains, "
                f"embedding: {len(keywords.get('sub_domains_embedding', {}))} items")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    AUTO_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    USER_REPORT_DIR.mkdir(parents=True, exist_ok=True)

    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    logger.info(f"Database ready: {DB_PATH}")

    overrides = _load_skip_overrides() if force else {}
    effective_skip = _get_effective_skip(overrides)
    phase_map = {
        "A-RSS": (phase_a_rss, [db, publishers, force], not effective_skip["A_RSS"]),
        "A-CR": (phase_a_crossref, [db, publishers, force], not effective_skip["A_CR"]),
        "B": (phase_b_crossref, [db], not effective_skip["B"]),
        "C": (phase_c_publisher, [db, publishers], not effective_skip["C"]),
        "D": (phase_d_semantic_filter, [db, keywords], not effective_skip["D"]),
        "E": (phase_e_llm_relevance, [db], not effective_skip["E"]),
        "E2": (phase_e2_mineru, [db], not effective_skip["E2"]),
        "F": (phase_f_llm_summary, [db], not effective_skip["F"]),
        "G": (phase_g_report, [db, AUTO_REPORT_DIR, USER_REPORT_DIR], not effective_skip["G"]),
        "H": (phase_h_email, [db, AUTO_REPORT_DIR], not effective_skip["H"]),
    }

    if phase_list is None:
        if force:
            phase_list = list(phase_map.keys())
        else:
            phase_list = [k for k, (_, _, enabled) in phase_map.items() if enabled]

    for key in phase_list:
        func, args, enabled = phase_map[key]
        if not enabled:
            logger.info(f"Phase {key}: skipped by config/override")
            continue
        func(*args)

    logger.info("Pipeline finished")

 
def run_pipeline(force=False):
    """Run the full pipeline (equivalent to old main()).

    Parameters
    ----------
    force : bool, optional
        If True, run ALL phases regardless of SKIP_PHASE_* config.
    """
    run_phases(force=force)


# ── 便捷方法：每日/每周调度 ─────────────────────────────────────────

DAILY_PHASES = ["A-RSS", "A-CR", "B", "C", "D", "E", "E2", "F"]
WEEKLY_PHASES = ["G", "H"]


def run_daily():
    """每日运行：发现 → LLM 总结。

    等价于依次执行 Phase A-RSS / A-CR / B / C / D / E / E2 / F。
    尊重 settings.yaml 中的 SKIP_PHASE_* 配置（CLI 模式，force=False）。

    典型 cron 用法:

        # 每天 2:00
        0 2 * * * cd /path/to/PapersCrawler && python tools/schedule_daily.py
    """
    run_phases(phase_list=DAILY_PHASES)


def run_weekly():
    """每周运行：报告生成 → 邮件推送。

    等价于依次执行 Phase G / H。
    尊重 settings.yaml 中的 SKIP_PHASE_* 配置（CLI 模式，force=False）。

    典型 cron 用法:

        # 每周一 9:00
        0 9 * * 1 cd /path/to/PapersCrawler && python tools/schedule_weekly.py
    """
    run_phases(phase_list=WEEKLY_PHASES)


if __name__ == "__main__":
    import sys
    phases = sys.argv[1:] if len(sys.argv) > 1 else None
    run_phases(phases)
