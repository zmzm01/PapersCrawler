#!/usr/bin/env python
"""Summarise and inspect PapersCrawler warning and error logs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "data" / "logs"
LOG_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\] "
    r"(?P<logger>[^:]+): (?P<message>.*)$"
)
MANAGED_LOG_PATTERN = re.compile(
    r"^PaperCrawler-(?P<date>\d{4}-\d{2}-\d{2})\.log(?:\.\d+)?$"
)
LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


@dataclass
class LogEntry:
    """One parsed logging record, including any continuation lines."""

    timestamp: str
    level: str
    logger: str
    message: str
    source_file: str


def _iter_log_paths(log_dir: Path, start_date: date, end_date: date) -> list[Path]:
    """Return managed log files whose filename date falls in the range."""
    paths = []
    if not log_dir.exists():
        return paths
    for path in log_dir.iterdir():
        match = MANAGED_LOG_PATTERN.fullmatch(path.name)
        if not match or not path.is_file():
            continue
        try:
            log_date = date.fromisoformat(match.group("date"))
        except ValueError:
            continue
        if start_date <= log_date <= end_date:
            paths.append(path)
    return sorted(paths)


def _parse_log_file(path: Path) -> list[LogEntry]:
    """Parse one daily log, preserving multiline exception details."""
    entries: list[LogEntry] = []
    current: LogEntry | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LOG_LINE_PATTERN.match(raw_line)
        if match:
            if current is not None:
                entries.append(current)
            current = LogEntry(
                timestamp=match.group("timestamp"),
                level=match.group("level"),
                logger=match.group("logger"),
                message=match.group("message"),
                source_file=path.name,
            )
        elif current is not None:
            current.message += "\n" + raw_line
    if current is not None:
        entries.append(current)
    return entries


def read_log_entries(
    log_dir: Path,
    start_date: date,
    end_date: date,
    minimum_level: str = "WARNING",
    contains: str | None = None,
) -> list[LogEntry]:
    """Read and filter entries from the date-separated application logs.

    Parameters
    ----------
    log_dir : Path
        Directory containing ``PaperCrawler-YYYY-MM-DD.log`` files.
    start_date, end_date : date
        Inclusive date range to inspect.
    minimum_level : str, optional
        Minimum severity to include.
    contains : str, optional
        Case-insensitive substring required in logger or message.

    Returns
    -------
    list[LogEntry]
        Entries ordered from oldest to newest.
    """
    threshold = LEVEL_ORDER[minimum_level]
    entries = [
        entry
        for path in _iter_log_paths(log_dir, start_date, end_date)
        for entry in _parse_log_file(path)
        if LEVEL_ORDER.get(entry.level, 0) >= threshold
    ]
    if contains:
        needle = contains.casefold()
        entries = [
            entry
            for entry in entries
            if needle in entry.logger.casefold()
            or needle in entry.message.casefold()
        ]
    return sorted(entries, key=lambda entry: entry.timestamp)


def _message_key(message: str) -> str:
    """Normalise common variable fragments for useful frequency counts."""
    first_line = message.splitlines()[0]
    first_line = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", first_line)
    first_line = re.sub(r"https?://\S+", "<url>", first_line)
    return first_line.strip()


def _truncate(value: str, width: int) -> str:
    """Truncate a display value without introducing multiline output."""
    value = " ".join(value.splitlines()).strip()
    if len(value) <= width:
        return value
    return value[: max(1, width - 1)] + "…"


def _color(text: str, code: str, enabled: bool) -> str:
    """Apply a terminal color when color output is enabled."""
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def _print_text_report(
    entries: list[LogEntry],
    start_date: date,
    end_date: date,
    minimum_level: str,
    limit: int,
    summary_only: bool,
    use_color: bool,
) -> None:
    """Print a compact human-readable report."""
    range_label = (
        start_date.isoformat()
        if start_date == end_date
        else f"{start_date.isoformat()} 至 {end_date.isoformat()}"
    )
    counts = Counter(entry.level for entry in entries)
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for entry in entries:
        source_counts[entry.logger][entry.level] += 1
    message_counts = Counter(
        (entry.level, entry.logger, _message_key(entry.message))
        for entry in entries
    )

    print(f"日志统计 | {range_label} | {minimum_level} 及以上")
    print(f"总计: {len(entries)} 条")
    if counts:
        level_summary = "  ".join(
            f"{level} {counts[level]}"
            for level in ("CRITICAL", "ERROR", "WARNING")
            if counts[level]
        )
        print(
            "级别: "
            + _color(level_summary, "31" if counts.get("ERROR") else "33", use_color)
        )
    if not entries:
        print("没有匹配的日志。")
        return

    print("\n按来源:")
    print(f"{'来源':<32} {'WARNING':>8} {'ERROR':>7} {'合计':>7}")
    for logger_name, logger_counter in sorted(
        source_counts.items(), key=lambda item: sum(item[1].values()), reverse=True
    ):
        warning_count = logger_counter["WARNING"]
        error_count = logger_counter["ERROR"] + logger_counter["CRITICAL"]
        total = sum(logger_counter.values())
        print(
            f"{_truncate(logger_name, 32):<32} {warning_count:>8} "
            f"{error_count:>7} {total:>7}"
        )

    print("\n高频消息:")
    for (level, logger_name, message), count in message_counts.most_common(10):
        level_text = _color(
            f"{level:<8}",
            "31" if level in {"ERROR", "CRITICAL"} else "33",
            use_color,
        )
        print(
            f"{count:>4} × {level_text} {_truncate(logger_name, 24):<24} "
            f"{_truncate(message, 100)}"
        )

    if summary_only:
        return

    print(f"\n最近明细（最多 {limit} 条）:")
    for entry in reversed(entries[-limit:]):
        level_text = _color(
            f"[{entry.level}]",
            "31" if entry.level in {"ERROR", "CRITICAL"} else "33",
            use_color,
        )
        print(
            f"{entry.timestamp} {level_text} {entry.logger}: "
            f"{_truncate(entry.message, 160)}"
        )


def _json_report(
    entries: list[LogEntry], start_date: date, end_date: date, limit: int
) -> dict:
    """Build a machine-readable report payload."""
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    message_counts = Counter()
    for entry in entries:
        source_counts[entry.logger][entry.level] += 1
        message_counts[(entry.level, entry.logger, _message_key(entry.message))] += 1
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total": len(entries),
        "levels": dict(Counter(entry.level for entry in entries)),
        "sources": {
            logger_name: dict(level_counts)
            for logger_name, level_counts in sorted(source_counts.items())
        },
        "frequent_messages": [
            {"count": count, "level": level, "logger": logger_name, "message": message}
            for (level, logger_name, message), count in message_counts.most_common(10)
        ],
        "entries": [asdict(entry) for entry in entries[-limit:]],
    }


def _parse_date(value: str) -> date:
    """Parse an ISO date supplied on the command line."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"日期格式应为 YYYY-MM-DD: {value}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the log report tool."""
    parser = argparse.ArgumentParser(
        description=(
            "统计和查看 PapersCrawler 的 WARNING/ERROR 日志，"
            "默认查看今天。"
        )
    )
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date", type=_parse_date, help="查看指定日期（YYYY-MM-DD）"
    )
    date_group.add_argument(
        "--days",
        type=int,
        metavar="N",
        help="查看最近 N 个自然日（包含今天）",
    )
    parser.add_argument(
        "--level",
        choices=("WARNING", "ERROR", "CRITICAL"),
        default="WARNING",
        help="最低级别，默认 WARNING（包含 ERROR）",
    )
    parser.add_argument(
        "--contains", metavar="TEXT", help="只显示包含关键词的记录"
    )
    parser.add_argument(
        "--limit", type=int, default=30, help="最多显示多少条明细，默认 30"
    )
    parser.add_argument(
        "--summary-only", action="store_true", help="只显示统计，不显示明细"
    )
    parser.add_argument(
        "--json", action="store_true", help="输出 JSON，便于脚本继续处理"
    )
    parser.add_argument("--no-color", action="store_true", help="关闭终端颜色")
    parser.add_argument(
        "--log-dir", type=Path, default=DEFAULT_LOG_DIR, help=argparse.SUPPRESS
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """Run the log summary command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.days is not None and args.days < 1:
        parser.error("--days 必须大于 0")
    if args.limit < 1:
        parser.error("--limit 必须大于 0")

    end_date = date.today()
    if args.date is not None:
        start_date = end_date = args.date
    elif args.days is not None:
        start_date = end_date - timedelta(days=args.days - 1)
    else:
        start_date = end_date

    entries = read_log_entries(
        args.log_dir,
        start_date,
        end_date,
        minimum_level=args.level,
        contains=args.contains,
    )
    if args.json:
        print(
            json.dumps(
                _json_report(entries, start_date, end_date, args.limit),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_text_report(
            entries,
            start_date,
            end_date,
            args.level,
            args.limit,
            args.summary_only,
            use_color=sys.stdout.isatty() and not args.no_color,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
