#!/usr/bin/env python3
"""Copy Phase G public report sidecars to a MySite-compatible export root."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALID_ID = re.compile(r"^[a-z0-9-]+$")


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
        warnings.warn(f"Cannot read {database_path}; exporting sidecar without historical enrichment: {exc}")
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
        warnings.warn(f"Cannot enrich public report from {database_path}: {exc}")
        return payload
    finally:
        conn.close()


def export_reports(output_root: Path, source_dir: Path, database_path: Path) -> int:
    """Synchronize generated public sidecars into a static-site export root.

    Parameters
    ----------
    output_root : Path
        Static-site generated-data root.
    source_dir : Path
        Directory containing public report sidecars.
    database_path : Path
        SQLite database used for optional historical enrichment.

    Returns
    -------
    int
        Number of exported reports.
    """
    destination = output_root / "papers"
    reports = []
    exported_ids = set()
    for source in sorted(source_dir.glob("report_*.public.json"), reverse=True):
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("source") != "papers" or not isinstance(payload.get("id"), str) or not VALID_ID.fullmatch(payload["id"]):
            raise ValueError(f"Invalid public report sidecar: {source}")
        target = destination / f"{payload['id']}.json"
        payload = enrich_from_database(payload, database_path)
        write_json(target, payload)
        exported_ids.add(payload["id"])
        reports.append({key: payload[key] for key in ("id", "source", "title", "publishedAt", "summary", "tags")})
    if destination.exists():
        for stale_path in destination.glob("papers-*.json"):
            if stale_path.stem not in exported_ids:
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
        default=PROJECT_ROOT / "data" / "reports" / "auto",
        help="Directory containing report_*.public.json sidecars",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "papers.db",
        help="Optional database used to enrich historical sidecars",
    )
    args = parser.parse_args()
    count = export_reports(args.out, args.source, args.database)
    print(f"Exported {count} PapersCrawler public report(s).")


if __name__ == "__main__":
    main()
