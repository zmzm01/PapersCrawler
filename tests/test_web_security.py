"""Security tests for read-only Web UI file handling."""

from pathlib import Path

from web.app import _is_report_path_in_directory


def test_report_path_allows_file_inside_report_directory(tmp_path):
    """A normal report file should be accepted."""
    report_dir = tmp_path / "auto"
    report_path = report_dir / "report_20260810.md"
    assert _is_report_path_in_directory(report_path, report_dir)


def test_report_path_rejects_parent_traversal(tmp_path):
    """A path escaping the report directory should be rejected."""
    report_dir = tmp_path / "auto"
    escaped_path = report_dir / ".." / "secret.md"
    assert not _is_report_path_in_directory(escaped_path, report_dir)


def test_report_path_rejects_same_prefix_sibling(tmp_path):
    """A sibling such as ``auto-backup`` must not pass a prefix check."""
    report_dir = tmp_path / "auto"
    sibling_path = tmp_path / "auto-backup" / "secret.md"
    assert not _is_report_path_in_directory(sibling_path, report_dir)
