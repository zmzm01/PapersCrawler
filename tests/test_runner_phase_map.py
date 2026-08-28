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
from unittest.mock import Mock

# Ensure src/ is importable when running pytest from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pipeline.runner import DAILY_PHASES, WEEKLY_PHASES  # noqa: E402
import pipeline.runner as runner  # noqa: E402

# Phase keys registered inside run_phases() — kept in sync manually.
PHASE_MAP_KEYS = {"A-RSS", "A-CR", "B", "C", "E", "E2", "E3", "F", "G", "H"}


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


def test_force_runs_configured_skipped_phases_and_restores_flags(tmp_path, monkeypatch):
    """Forced runs execute every phase, including phases skipped by config."""
    database = Mock()
    database.get_run_metrics.return_value = {
        "error_samples": [{"stage": "E", "message": "one paper failed"}],
    }
    monkeypatch.setattr(runner, "load_publishers", lambda: [])
    monkeypatch.setattr(
        runner, "load_keywords", lambda: {"scope_definition": {}}
    )
    monkeypatch.setattr(runner, "DatabaseClient", lambda _path: database)
    for directory_name in ("REPORT_DIR", "AUTO_REPORT_DIR", "USER_REPORT_DIR"):
        monkeypatch.setattr(runner, directory_name, tmp_path / directory_name)

    phase_mocks = {}
    for phase_name in PHASE_MAP_KEYS:
        attribute = {
            "A-RSS": "phase_a_rss",
            "A-CR": "phase_a_crossref",
            "B": "phase_b_crossref",
            "C": "phase_c_publisher",
            "E": "phase_e_llm_relevance",
            "E2": "phase_e2_mineru",
            "E3": "phase_e3_fulltext_relevance",
            "F": "phase_f_llm_summary",
            "G": "phase_g_report",
            "H": "phase_h_email",
        }[phase_name]
        phase_mocks[phase_name] = Mock()
        monkeypatch.setattr(runner, attribute, phase_mocks[phase_name])

    for skip_attribute in runner._PHASE_KEY_MAP.values():
        monkeypatch.setattr(runner.CFG, skip_attribute, False)
    monkeypatch.setattr(runner.CFG, "SKIP_PHASE_H", True)

    def assert_h_is_temporarily_enabled(*_args):
        """The phase sees the forced runtime override, not the config flag."""
        assert runner.CFG.SKIP_PHASE_H is False

    phase_mocks["H"].side_effect = assert_h_is_temporarily_enabled

    result = runner.run_phases(force=True)

    expected_order = [
        "A-RSS", "A-CR", "B", "C", "E", "E2", "E3", "F", "G", "H",
    ]
    assert [phase.name for phase in result.phase_results] == expected_order
    assert all(mock.called for mock in phase_mocks.values())
    assert result.status == "partial"
    assert runner.CFG.SKIP_PHASE_H is True
