"""Tests for legacy weekly report reconstruction planning."""

from datetime import datetime

from tools.rebuild_historical_reports import (
    _archive_report,
    _historical_report_paths,
    _remove_report_artifacts,
)


def test_historical_report_paths_selects_only_dated_reports_before_cutover(tmp_path):
    """Legacy reconstruction ignores explainers and reports from the new era."""
    for filename in (
        "report_20260809.md",
        "report_20260816.md",
        "report_20260823.md",
        "report_20260816_explained.html",
        "report_notes.md",
    ):
        (tmp_path / filename).touch()

    reports = _historical_report_paths(tmp_path, datetime(2026, 8, 23))

    assert [path.name for path in reports] == [
        "report_20260809.md", "report_20260816.md"
    ]


def test_archive_report_moves_all_public_report_artifacts(tmp_path):
    """Archiving keeps legacy report companions together outside auto output."""
    report_path = tmp_path / "report_20260816.md"
    report_path.write_text("# report", encoding="utf-8")
    report_path.with_suffix(".public.json").write_text("{}", encoding="utf-8")
    explainer_path = tmp_path / "report_20260816_explained.html"
    explainer_path.write_text("<!doctype html>", encoding="utf-8")
    archive_dir = tmp_path / "legacy"

    archived_path = _archive_report(report_path, archive_dir)

    assert archived_path == archive_dir / "report_20260816.md"
    assert sorted(path.name for path in archive_dir.iterdir()) == [
        "report_20260816.md",
        "report_20260816.public.json",
        "report_20260816_explained.html",
    ]
    assert not report_path.exists()
    assert not explainer_path.exists()


def test_remove_report_artifacts_removes_empty_report_companions(tmp_path):
    """An empty historical report cannot leave a public page or sidecar behind."""
    report_path = tmp_path / "report_20260809.md"
    report_path.write_text("# empty", encoding="utf-8")
    report_path.with_suffix(".public.json").write_text("{}", encoding="utf-8")
    report_path.with_name("report_20260809_explained.html").write_text(
        "<!doctype html>", encoding="utf-8"
    )

    _remove_report_artifacts(report_path)

    assert list(tmp_path.iterdir()) == []
