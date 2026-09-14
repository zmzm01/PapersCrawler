#!/usr/bin/env python3
"""Copy Phase G public report sidecars to a static-site export root."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import warnings
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALID_ID = re.compile(r"^[a-z0-9-]+$")


def export_public_methodology(output_path: Path) -> dict[str, object]:
    """Export the current public-safe paper summarization methodology.

    Parameters
    ----------
    output_path : pathlib.Path
        Destination JSON path consumed by the static report site.

    Returns
    -------
    dict[str, object]
        Public methodology payload written to ``output_path``.
    """
    from processors.prompt_explainer import (
        render_summary_input_template,
        render_summary_prompt,
    )

    summary_prompt = render_summary_prompt().strip()
    fingerprint = (
        hashlib.sha256(summary_prompt.encode("utf-8")).hexdigest()
        if summary_prompt
        else ""
    )
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z"),
        "promptFingerprint": fingerprint,
        "summaryPrompt": summary_prompt,
        "summaryInputTemplate": render_summary_input_template(),
    }
    write_json(output_path, payload)
    return payload


def write_json(path: Path, value: object) -> None:
    """Atomically write a UTF-8 JSON document.

    Parameters
    ----------
    path : Path
        Destination path.
    value : object
        JSON-serializable value to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def enrich_from_database(payload: dict, database_path: Path) -> dict:
    """Restore presentation fields for historical sidecars without parsing Markdown."""
    if not database_path.exists():
        return payload
    try:
        conn = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        warnings.warn(
            f"Cannot read {database_path}; exporting sidecar without historical enrichment: {exc}",
            stacklevel=2,
        )
        return payload
    conn.row_factory = sqlite3.Row
    try:
        for paper in payload.get("content", {}).get("papers", []):
            if not isinstance(paper, dict) or not paper.get("doi"):
                continue
            row = conn.execute(
                "SELECT abstract, pdf_url, llm_relevance_basis FROM papers WHERE LOWER(doi) = LOWER(?)",
                (paper["doi"],),
            ).fetchone()
            if row is None:
                continue
            paper["abstract"] = paper.get("abstract") or row["abstract"] or ""
            paper["pdfUrl"] = paper.get("pdfUrl") or row["pdf_url"] or ""
            paper["relevanceBasis"] = paper.get("relevanceBasis") or row["llm_relevance_basis"] or ""
        return payload
    except sqlite3.Error as exc:
        warnings.warn(
            f"Cannot enrich public report from {database_path}: {exc}",
            stacklevel=2,
        )
        return payload
    finally:
        conn.close()


def export_reports(
    output_root: Path,
    source_dir: Path | Iterable[Path],
    database_path: Path,
    markdown_root: Path | None = None,
) -> int:
    """Synchronize generated public sidecars into a static-site export root.

    Parameters
    ----------
    output_root : Path
        Static-site generated-data root.
    source_dir : Path or iterable of Path
        One or more directories containing public report sidecars. Multiple
        directories allow automatic and explicitly published preview reports
        to be synchronized without deleting either set.
    database_path : Path
        SQLite database used for optional historical enrichment.
    markdown_root : Path, optional
        Static directory for downloadable public Markdown reports.

    Returns
    -------
    int
        Number of exported reports.
    """
    destination = output_root / "papers"
    source_dirs = [source_dir] if isinstance(source_dir, Path) else list(source_dir)
    sidecars = []
    for directory in source_dirs:
        sidecars.extend(directory.glob("*.public.json"))

    reports = []
    exported_ids = set()
    exported_markdown = set()
    if markdown_root is not None:
        markdown_root.mkdir(parents=True, exist_ok=True)
    for source in sorted(sidecars, key=lambda path: str(path), reverse=True):
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("source") != "papers" or not isinstance(payload.get("id"), str) or not VALID_ID.fullmatch(payload["id"]):
            raise ValueError(f"Invalid public report sidecar: {source}")
        payload = enrich_from_database(payload, database_path)
        markdown_source = source.with_name(
            source.name.removesuffix(".public.json") + ".md"
        )
        if markdown_root is not None and markdown_source.is_file():
            markdown_name = f"{payload['id']}.md"
            markdown_target = markdown_root / markdown_name
            temporary_target = markdown_target.with_suffix(".md.tmp")
            shutil.copyfile(markdown_source, temporary_target)
            temporary_target.replace(markdown_target)
            payload["downloadUrl"] = f"/downloads/{markdown_name}"
            exported_markdown.add(markdown_name)
        else:
            payload.pop("downloadUrl", None)
        target = destination / f"{payload['id']}.json"
        write_json(target, payload)
        exported_ids.add(payload["id"])
        reports.append({key: payload[key] for key in ("id", "source", "title", "publishedAt", "summary", "tags")})
    if destination.exists():
        for stale_path in destination.glob("papers-*.json"):
            if stale_path.stem not in exported_ids:
                stale_path.unlink()
    if markdown_root is not None:
        for stale_path in markdown_root.glob("papers-*.md"):
            if stale_path.name not in exported_markdown:
                stale_path.unlink()
    write_json(destination / "index.json", reports)
    return len(reports)


def main() -> None:
    """Parse CLI arguments and synchronize public reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="Public export root")
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        dest="sources",
        default=None,
        help="Directory containing *.public.json sidecars (repeatable)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "papers.db",
        help="Optional database used to enrich historical sidecars",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        help="Optional static directory for downloadable Markdown reports",
    )
    args = parser.parse_args()
    sources = args.sources or [PROJECT_ROOT / "data" / "reports" / "auto"]
    count = export_reports(
        args.out,
        sources,
        args.database,
        markdown_root=args.markdown_out,
    )
    print(f"Exported {count} PapersCrawler public report(s).")


if __name__ == "__main__":
    main()
