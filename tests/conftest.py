"""
pytest configuration.
Ensures src/ is on sys.path for all test imports.
"""
import os
import sys
import tempfile


# Entry-point tests spawn subprocesses and some test modules configure logging
# during collection.  Set the override before collection so no test can attach
# a handler to the repository's production log directory.
_TEST_LOG_ROOT = tempfile.TemporaryDirectory(prefix="paperscrawler-pytest-")
os.environ["PAPERSCRAWLER_LOG_DIR"] = _TEST_LOG_ROOT.name

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
