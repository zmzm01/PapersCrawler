"""Defensive tests for runner phase registry consistency.

Regression guard for CRITICAL #1 (2026-07-24 Pipeline Review): DAILY_PHASES
must stay a subset of phase_map.keys() — removing a phase from the registry
without updating the schedule constants causes KeyError on the next cron run.

Note: phase_map is defined inside run_phases() and is not directly importable.
We replicate its keys as PHASE_MAP_KEYS here; if phase_map is ever promoted
to module level, switch this to a direct import.
"""
import sys
from pathlib import Path

# Ensure src/ is importable when running pytest from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pipeline.runner import DAILY_PHASES, WEEKLY_PHASES  # noqa: E402

# Phase keys registered inside run_phases() — kept in sync manually.
PHASE_MAP_KEYS = {"A-RSS", "A-CR", "B", "C", "E", "E2", "F", "G", "H"}


def test_daily_phases_subset_of_phase_map():
    """DAILY_PHASES must only reference phases registered in phase_map."""
    assert set(DAILY_PHASES).issubset(PHASE_MAP_KEYS), (
        f"DAILY_PHASES references unregistered phases: "
        f"{set(DAILY_PHASES) - PHASE_MAP_KEYS}"
    )


def test_weekly_phases_subset_of_phase_map():
    """WEEKLY_PHASES must only reference phases registered in phase_map."""
    assert set(WEEKLY_PHASES).issubset(PHASE_MAP_KEYS), (
        f"WEEKLY_PHASES references unregistered phases: "
        f"{set(WEEKLY_PHASES) - PHASE_MAP_KEYS}"
    )
