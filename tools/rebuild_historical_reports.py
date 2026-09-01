#!/usr/bin/env python3
"""Rebuild legacy weekly reports into the current public-report schema.

The tool discovers dated Markdown reports in ``data/reports/auto`` before a
given cutover date.  It treats each report date as the inclusive end of a
``created_date`` window; the next report starts on the day after the previous
report date.  It rewrites the Markdown and creates a same-stem ``.public.json``
sidecar without updating any paper's ``report_date``.

Examples
--------
Rebuild every weekly report before the first report made by the new mechanism::

    python tools/rebuild_historical_reports.py --before 2026-08-23

Inspect the inferred date windows without writing files::

    python tools/rebuild_historical_reports.py --before 2026-08-23 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import AUTO_REPORT_DIR, DB_PATH, PUBLIC_EXPORT_DIR, load_keywords
from db.database import DatabaseClient
from processors.paper_report_generator import generate_report
from processors.public_report import report_id, write_public_report
from processors.report_presentation import build_report_presentation
from processors.report_snapshot import build_report_papers
from tools.preview_report import _atomic_write, _fetch_papers

logger = logging.getLogger(__name__)
_REPORT_NAME = re.compile(r"report_(\d{8})\.md$")


def _parse_date(value: str, argument: str) -> datetime:
    """Parse a CLI ISO date or raise a friendly argparse error."""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{argument} 格式错误，期望 YYYY-MM-DD: {value}"
        ) from exc


def _historical_report_paths(report_dir: Path, cutover_date: datetime) -> list[Path]:
    """Return dated automatic reports strictly before ``cutover_date``."""
    report_paths = []
    for report_path in report_dir.glob("report_*.md"):
        match = _REPORT_NAME.fullmatch(report_path.name)
        if match is None:
            continue
        report_date = datetime.strptime(match.group(1), "%Y%m%d")
        if report_date < cutover_date:
            report_paths.append(report_path)
    return sorted(report_paths)


def _report_date(report_path: Path) -> datetime:
    """Extract the report date from a validated automatic report path."""
    match = _REPORT_NAME.fullmatch(report_path.name)
    if match is None:
        raise ValueError(f"Invalid dated report filename: {report_path.name}")
    return datetime.strptime(match.group(1), "%Y%m%d")


def _write_rebuilt_report(
    database: DatabaseClient,
    report_path: Path,
    start_date: datetime | None,
    end_date: datetime,
) -> int:
    """Write one report and its current-schema public sidecar.

    Returns
    -------
    int
        Number of papers in the reconstructed ``created_date`` window.
    """
    paper_rows = _fetch_papers(
        database,
        "all",
        end_date,
        from_date=start_date.strftime("%Y-%m-%d") if start_date else None,
        through_date=end_date.strftime("%Y-%m-%d"),
    )
    paper_list = build_report_papers(paper_rows)
    if not paper_list:
        return 0

    scope_definition = load_keywords().get("scope_definition")
    presentation = build_report_presentation(scope_definition, paper_list)
    date_value = end_date.strftime("%Y%m%d")
    scope = {
        "kind": "created_date_range",
        "fromCreatedDate": start_date.strftime("%Y-%m-%d") if start_date else None,
        "throughCreatedDate": end_date.strftime("%Y-%m-%d"),
    }
    write_public_report(
        report_path.with_suffix(".public.json"),
        paper_list,
        date_value,
        scope_definition=scope_definition,
        presentation=presentation,
        report_identifier=report_id(date_value),
        scope=scope,
    )
    markdown = generate_report(
        paper_list,
        format="markdown",
        toc=True,
        scope_definition=scope_definition,
        presentation=presentation,
    )
    _atomic_write(report_path, markdown)
    return len(paper_list)


def _archive_report(report_path: Path, archive_dir: Path) -> Path:
    """Move one rebuilt report and its companion artifacts into an archive.

    Parameters
    ----------
    report_path : pathlib.Path
        Rebuilt Markdown report in the automatic report directory.
    archive_dir : pathlib.Path
        Destination directory for legacy public reports.

    Returns
    -------
    pathlib.Path
        Archived Markdown report path.
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / report_path.name
    companion_paths = [
        report_path,
        report_path.with_suffix(".public.json"),
        report_path.with_name(f"{report_path.stem}_explained.html"),
    ]
    for source_path in companion_paths:
        if source_path.exists():
            shutil.move(str(source_path), archive_dir / source_path.name)
    return destination


def _remove_report_artifacts(report_path: Path) -> None:
    """Remove an empty report and every public artifact associated with it."""
    artifact_paths = [
        report_path,
        report_path.with_suffix(".public.json"),
        report_path.with_name(f"{report_path.stem}_explained.html"),
    ]
    for artifact_path in artifact_paths:
        if artifact_path.exists():
            artifact_path.unlink()


def main() -> None:
    """Rebuild all legacy weekly reports before a new export cutover date."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--before",
        required=True,
        type=lambda value: _parse_date(value, "--before"),
        help="新机制首份报告日期；仅重建严格早于此日期的报告",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=AUTO_REPORT_DIR,
        help="历史自动报告目录（默认 data/reports/auto）",
    )
    parser.add_argument(
        "--export-root",
        type=Path,
        default=PUBLIC_EXPORT_DIR,
        help="公开站点导出根目录",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="只重建 Markdown 与 sidecar，不同步公开站点目录",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        help="重建后将旧 Markdown、sidecar 和解释页移入此目录",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示将要重建的 created_date 窗口，不写入文件",
    )
    args = parser.parse_args()

    report_paths = _historical_report_paths(args.report_dir, args.before)
    if not report_paths:
        print(f"No dated reports before {args.before:%Y-%m-%d} in {args.report_dir}")
        return

    previous_date = None
    if args.dry_run:
        for report_path in report_paths:
            current_date = _report_date(report_path)
            start_text = (
                (previous_date + timedelta(days=1)).strftime("%Y-%m-%d")
                if previous_date else "earliest"
            )
            archive_note = f" -> {args.archive_dir}" if args.archive_dir else ""
            print(
                f"{report_path.name}: created_date {start_text} .. "
                f"{current_date:%Y-%m-%d}{archive_note}"
            )
            previous_date = current_date
        return

    with DatabaseClient(DB_PATH) as database:
        for report_path in report_paths:
            current_date = _report_date(report_path)
            start_date = previous_date + timedelta(days=1) if previous_date else None
            paper_count = _write_rebuilt_report(
                database, report_path, start_date, current_date
            )
            start_text = start_date.strftime("%Y-%m-%d") if start_date else "earliest"
            if paper_count == 0:
                _remove_report_artifacts(report_path)
                print(
                    f"Skipped empty {report_path.name} "
                    f"(created_date {start_text} .. {current_date:%Y-%m-%d})"
                )
                previous_date = current_date
                continue
            print(
                f"Rebuilt {report_path.name}: {paper_count} papers "
                f"(created_date {start_text} .. {current_date:%Y-%m-%d})"
            )
            if args.archive_dir:
                archived_path = _archive_report(report_path, args.archive_dir)
                print(f"Archived {archived_path.name} -> {args.archive_dir}")
            previous_date = current_date

    if not args.no_export:
        from tools.export_public_reports import export_reports

        sources = [args.report_dir]
        if args.archive_dir:
            sources.append(args.archive_dir)
        count = export_reports(args.export_root, sources, DB_PATH)
        print(f"Public JSON export updated: {count} reports -> {args.export_root}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
