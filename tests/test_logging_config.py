"""Tests for date-separated and bounded application logs."""

from datetime import date, timedelta
import logging

from logging_config import DailyLogHandler


def test_daily_log_handler_writes_date_specific_file(tmp_path):
    """Records are written to the current day's managed log file."""
    handler = DailyLogHandler(tmp_path, retention_days=14)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "hello", (), None
    )

    handler.emit(record)
    handler.close()

    log_path = tmp_path / f"PaperCrawler-{date.today().isoformat()}.log"
    assert log_path.read_text(encoding="utf-8") == "hello\n"


def test_daily_log_handler_prunes_old_managed_logs(tmp_path):
    """Only managed files older than retention are removed."""
    old_date = date.today() - timedelta(days=3)
    old_path = tmp_path / f"PaperCrawler-{old_date.isoformat()}.log"
    unrelated_path = tmp_path / "other.log"
    old_path.write_text("old", encoding="utf-8")
    unrelated_path.write_text("keep", encoding="utf-8")

    handler = DailyLogHandler(tmp_path, retention_days=2)
    handler.close()

    assert not old_path.exists()
    assert unrelated_path.exists()
