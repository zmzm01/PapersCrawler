"""
Pipeline orchestrator.

Provides run_pipeline() for full execution and run_phases() for selective runs.
"""

import json

from config import (
    load_publishers, load_keywords,
    DB_PATH, REPORT_DIR, DATA_DIR,
    SKIP_PHASE_A, SKIP_PHASE_B, SKIP_PHASE_C, SKIP_PHASE_D,
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
        "A": SKIP_PHASE_A, "B": SKIP_PHASE_B, "C": SKIP_PHASE_C,
        "D": SKIP_PHASE_D, "E": SKIP_PHASE_E, "E2": SKIP_PHASE_E2,
        "F": SKIP_PHASE_F, "G": SKIP_PHASE_G, "H": SKIP_PHASE_H,
    }
    return {k: overrides.get(k, defaults[k]) for k in defaults}
from db.database import DatabaseClient
from pipeline.base import logger

from pipeline.phase_a import phase_a_rss
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
        If True, ignore SKIP_PHASE_* config and run requested phases.
        Used by Web UI where buttons control execution explicitly.
    """
    publishers = load_publishers()
    keywords = load_keywords()
    logger.info(f"Loaded {len(publishers)} publishers")
    logger.info(f"Keywords: {len(keywords['keywords'])} items, "
                f"domain: {len(keywords['domain_description'])} chars")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    logger.info(f"Database ready: {DB_PATH}")

    overrides = _load_skip_overrides()
    effective_skip = _get_effective_skip(overrides)
    phase_map = {
        "A": (phase_a_rss, [db, publishers], not effective_skip["A"]),
        "B": (phase_b_crossref, [db], not effective_skip["B"]),
        "C": (phase_c_publisher, [db], not effective_skip["C"]),
        "D": (phase_d_semantic_filter, [db, keywords], not effective_skip["D"]),
        "E": (phase_e_llm_relevance, [db], not effective_skip["E"]),
        "E2": (phase_e2_mineru, [db], not effective_skip["E2"]),
        "F": (phase_f_llm_summary, [db], not effective_skip["F"]),
        "G": (phase_g_report, [db, REPORT_DIR], not effective_skip["G"]),
        "H": (phase_h_email, [REPORT_DIR], not effective_skip["H"]),
    }

    if phase_list is None:
        if force:
            phase_list = list(phase_map.keys())
        else:
            phase_list = [k for k, (_, _, enabled) in phase_map.items() if enabled]

    for key in phase_list:
        func, args, enabled = phase_map[key]
        if not force and not enabled:
            logger.info(f"Phase {key}: SKIP_PHASE_{key}=True, skipping")
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


if __name__ == "__main__":
    import sys
    phases = sys.argv[1:] if len(sys.argv) > 1 else None
    run_phases(phases)
