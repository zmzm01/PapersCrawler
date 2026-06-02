"""
Tests: Pipeline phase modules.

Verifies that each phase module can be imported and its function signature
is correct. Actual phase logic testing is done via integration tests.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest


def test_all_phase_modules_importable():
    """Each pipeline phase module should import without errors."""
    from pipeline import phase_a, phase_b, phase_c, phase_d
    from pipeline import phase_e, phase_e2, phase_f, phase_g, phase_h
    assert phase_a is not None
    assert phase_b is not None
    assert phase_c is not None
    assert phase_d is not None
    assert phase_e is not None
    assert phase_e2 is not None
    assert phase_f is not None
    assert phase_g is not None
    assert phase_h is not None


def test_runner_importable():
    """Runner module should import without errors."""
    from pipeline.runner import run_pipeline, run_phases
    assert callable(run_pipeline)
    assert callable(run_phases)


def test_phase_a_signature():
    """phase_a_rss should accept (db, publishers)."""
    from pipeline.phase_a import phase_a_rss
    import inspect
    sig = inspect.signature(phase_a_rss)
    param_names = list(sig.parameters.keys())
    assert "db" in param_names
    assert "publishers" in param_names


def test_phase_g_signature():
    """phase_g_report should accept (db, report_dir)."""
    from pipeline.phase_g import phase_g_report
    import inspect
    sig = inspect.signature(phase_g_report)
    param_names = list(sig.parameters.keys())
    assert "db" in param_names
    assert "report_dir" in param_names


def test_phase_h_signature():
    """phase_h_email should accept (report_dir)."""
    from pipeline.phase_h import phase_h_email
    import inspect
    sig = inspect.signature(phase_h_email)
    param_names = list(sig.parameters.keys())
    assert "report_dir" in param_names
