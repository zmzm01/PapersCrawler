"""Tests for configurable browser backend lifecycle and auditing."""

import sys
from types import ModuleType, SimpleNamespace

import pytest

from browser_backend import launch_browser_backend
from db.database import DatabaseClient
from pipeline.base import record_browser_event


class FakeContext:
    """Minimal Playwright context used by backend lifecycle tests."""

    def __init__(self):
        self.closed = False

    def close(self):
        """Record context closure."""
        self.closed = True


def test_camoufox_session_keeps_manager_and_closes_it(monkeypatch, tmp_path):
    """Camoufox's context manager must remain alive until session close."""
    context = FakeContext()
    manager = SimpleNamespace(exited=False)

    class FakeCamoufox:
        def __init__(self, **kwargs):
            manager.kwargs = kwargs

        def __enter__(self):
            return context

        def __exit__(self, *_args):
            manager.exited = True

    package = ModuleType("camoufox")
    sync_api = ModuleType("camoufox.sync_api")
    sync_api.Camoufox = FakeCamoufox
    monkeypatch.setitem(sys.modules, "camoufox", package)
    monkeypatch.setitem(sys.modules, "camoufox.sync_api", sync_api)

    session = launch_browser_backend(
        "camoufox", tmp_path, proxy={"server": "http://proxy"},
    )
    assert manager.kwargs["persistent_context"] is True
    assert manager.kwargs["humanize"] is True
    session.close()
    assert context.closed is True
    assert manager.exited is True


def test_unknown_browser_backend_is_rejected(tmp_path):
    """Configuration mistakes must fail before importing a browser package."""
    with pytest.raises(ValueError, match="Unsupported browser backend"):
        launch_browser_backend("unknown", tmp_path)


def test_browser_backend_audit_summary(tmp_path):
    """Browser attempts are persisted and aggregated by backend."""
    with DatabaseClient(tmp_path / "papers.db") as database:
        database.init_db_papers()
        database.record_browser_backend_event(
            "C", "aps", "10/test", "page_fetch", "camoufox", "failed",
            failure_kind="timeout", error="timed out", duration_ms=100,
        )
        database.record_browser_backend_event(
            "C", "aps", "10/test", "page_fetch", "cloakbrowser", "success",
            duration_ms=200, is_fallback=True,
        )
        rows = database.get_browser_backend_summary()

    assert len(rows) == 2
    cloak = next(row for row in rows if row["backend"] == "cloakbrowser")
    assert cloak["successes"] == 1
    assert cloak["fallback_attempts"] == 1


def test_browser_audit_failure_does_not_interrupt_pipeline(caplog):
    """Telemetry persistence failures must remain outside business flow."""

    class FailingDatabase:
        """Database double whose optional telemetry sink is unavailable."""

        def record_browser_backend_event(self, *_args, **_kwargs):
            """Simulate a transient SQLite write failure."""
            raise RuntimeError("database is locked")

    record_browser_event(
        FailingDatabase(), "C", "aps", None, "launch", "camoufox", "success",
    )

    assert "Could not record browser backend event" in caplog.text
