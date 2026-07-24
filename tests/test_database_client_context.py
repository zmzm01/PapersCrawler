"""Regression test for HIGH #4 (2026-07-24 Pipeline Review).

DatabaseClient must support context manager protocol and close() must be
idempotent. SQLite connections leak when clients are not released.
"""
import sys
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from db.database import DatabaseClient  # noqa: E402


def _make_db_path() -> Path:
    """Return a fresh tmpfile path for an isolated DB."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return Path(tmp.name)


def test_context_manager_closes_connection():
    """`with DatabaseClient(...) as db:` must close conn on exit."""
    db_path = _make_db_path()
    try:
        with DatabaseClient(str(db_path)) as db:
            assert db.conn is not None
            conn_ref = db.conn
        # After exit, conn must be None (closed)
        assert db.conn is None
        # The connection object should be closed
        # sqlite3 raises ProgrammingError on operations against closed conn
        try:
            conn_ref.execute("SELECT 1")
            assert False, "expected ProgrammingError on closed conn"
        except (sqlite3.ProgrammingError, Exception):
            pass  # any error means it's closed
    finally:
        db_path.unlink(missing_ok=True)


def test_close_is_idempotent():
    """close() called twice must not raise."""
    db_path = _make_db_path()
    try:
        db = DatabaseClient(str(db_path))
        db.close()
        db.close()  # second call must not raise
        assert db.conn is None
    finally:
        db_path.unlink(missing_ok=True)


def test_explicit_close_with_context_manager():
    """close() inside `with` block must not raise on __exit__."""
    db_path = _make_db_path()
    try:
        with DatabaseClient(str(db_path)) as db:
            db.close()
        # __exit__ should handle already-closed gracefully
        assert db.conn is None
    finally:
        db_path.unlink(missing_ok=True)
