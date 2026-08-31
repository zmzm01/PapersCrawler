"""Shared logging configuration for CLI and WebUI entry points."""

from __future__ import annotations

import logging
import os
import re
from datetime import date, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOG_DATE_PATTERN = re.compile(
    r"^PaperCrawler-(?P<date>\d{4}-\d{2}-\d{2})\.log(?:\.\d+)?$"
)


def resolve_log_dir(default_dir: Path) -> Path:
    """Resolve the application log directory, honoring an environment override.

    Parameters
    ----------
    default_dir : Path
        Directory used when ``PAPERSCRAWLER_LOG_DIR`` is not set.

    Returns
    -------
    Path
        The configured log directory. Relative override paths are interpreted
        relative to the current working directory.
    """
    configured_dir = os.getenv("PAPERSCRAWLER_LOG_DIR", "").strip()
    if not configured_dir:
        return Path(default_dir)
    return Path(configured_dir).expanduser()


class DailyLogHandler(logging.Handler):
    """Write logs to a date-specific file with bounded per-day rotation.

    Parameters
    ----------
    log_dir : Path
        Directory receiving daily log files.
    max_bytes : int
        Maximum size of one daily file before creating a numbered backup.
    backup_count : int
        Number of size-based backups kept for each day.
    retention_days : int
        Number of calendar days to retain before pruning old log files.
    """

    def __init__(
        self,
        log_dir: Path,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 1,
        retention_days: int = 14,
    ) -> None:
        super().__init__()
        self.log_dir = Path(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.retention_days = retention_days
        self._active_date = date.today()
        self._file_handler = None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._open_file_handler()
        self._prune_old_logs()

    def _path_for(self, log_date: date) -> Path:
        """Return the log path for one calendar date."""
        return self.log_dir / f"PaperCrawler-{log_date.isoformat()}.log"

    def _open_file_handler(self) -> None:
        """Open the rotating handler for the active date."""
        if self._file_handler is not None:
            self._file_handler.close()
        self._file_handler = RotatingFileHandler(
            self._path_for(self._active_date),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        if self.formatter is not None:
            self._file_handler.setFormatter(self.formatter)

    def _prune_old_logs(self) -> None:
        """Remove only managed log files older than the retention window."""
        cutoff = date.today() - timedelta(days=self.retention_days - 1)
        for path in self.log_dir.glob("PaperCrawler-*.log*"):
            match = _LOG_DATE_PATTERN.fullmatch(path.name)
            if not match:
                continue
            try:
                log_date = date.fromisoformat(match.group("date"))
            except ValueError:
                continue
            if log_date < cutoff:
                try:
                    path.unlink()
                except OSError:
                    logging.getLogger(__name__).warning(
                        "Could not prune old log file: %s", path
                    )

    def setFormatter(self, formatter: logging.Formatter | None) -> None:
        """Apply a formatter to both the wrapper and active file handler."""
        super().setFormatter(formatter)
        if self._file_handler is not None:
            self._file_handler.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """Write a record, switching files when the calendar date changes."""
        try:
            current_date = date.today()
            if current_date != self._active_date:
                self._active_date = current_date
                self._open_file_handler()
                self._prune_old_logs()
            self._file_handler.emit(record)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the active file and release handler resources."""
        if self._file_handler is not None:
            self._file_handler.close()
            self._file_handler = None
        super().close()


def configure_logging(
    log_level: str,
    log_dir: Path,
    default_level: int = logging.DEBUG,
) -> None:
    """Configure console logging and bounded date-separated file logging.

    Parameters
    ----------
    log_level : str
        Logging level name such as ``DEBUG`` or ``INFO``.
    log_dir : Path
        Directory for daily log files.
    default_level : int, optional
        Fallback level when ``log_level`` is not a known logging level.
    """
    root_logger = logging.getLogger()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if root_logger.handlers:
        root_logger.setLevel(getattr(logging, log_level.upper(), default_level))
        if not any(isinstance(handler, DailyLogHandler) for handler in root_logger.handlers):
            file_handler = DailyLogHandler(log_dir)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        return

    file_handler = DailyLogHandler(log_dir)
    console_handler = logging.StreamHandler()
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), default_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[file_handler, console_handler],
    )
