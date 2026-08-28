"""Tests for the human-readable log report tool."""

from datetime import date

from tools.log_report import _json_report, read_log_entries


def _write_log(log_dir, log_date, content):
    path = log_dir / f"PaperCrawler-{log_date}.log"
    path.write_text(content, encoding="utf-8")
    return path


def test_read_log_entries_filters_level_and_keyword(tmp_path):
    log_date = "2026-08-22"
    _write_log(
        tmp_path,
        log_date,
        "\n".join(
            [
                "2026-08-22 10:00:00 [INFO] pipeline.phase_a: fetched 3 papers",
                "2026-08-22 10:01:00 [WARNING] pipeline.phase_c: bot detection page",
                "2026-08-22 10:02:00 [ERROR] pipeline.phase_c: request failed",
            ]
        ),
    )

    entries = read_log_entries(
        tmp_path,
        date(2026, 8, 22),
        date(2026, 8, 22),
        contains="BOT",
    )

    assert len(entries) == 1
    assert entries[0].level == "WARNING"
    assert entries[0].logger == "pipeline.phase_c"


def test_read_log_entries_preserves_multiline_details_and_rotated_files(tmp_path):
    log_date = "2026-08-22"
    _write_log(
        tmp_path,
        log_date,
        "2026-08-22 10:00:00 [ERROR] pipeline.phase_f: failed\nTraceback line\n",
    )
    (tmp_path / f"PaperCrawler-{log_date}.log.1").write_text(
        "2026-08-22 09:00:00 [WARNING] pipeline.phase_c: old warning\n",
        encoding="utf-8",
    )

    entries = read_log_entries(tmp_path, date(2026, 8, 22), date(2026, 8, 22))

    assert len(entries) == 2
    assert entries[0].source_file.endswith(".log.1")
    assert "Traceback line" in entries[1].message


def test_json_report_contains_counts_and_limited_entries(tmp_path):
    _write_log(
        tmp_path,
        "2026-08-22",
        "2026-08-22 10:00:00 [WARNING] module: repeated warning 1\n"
        "2026-08-22 10:01:00 [WARNING] module: repeated warning 2\n",
    )
    entries = read_log_entries(tmp_path, date(2026, 8, 22), date(2026, 8, 22))

    report = _json_report(entries, date(2026, 8, 22), date(2026, 8, 22), limit=1)

    assert report["total"] == 2
    assert report["levels"] == {"WARNING": 2}
    assert len(report["entries"]) == 1
