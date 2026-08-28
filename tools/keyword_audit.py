#!/usr/bin/env python
"""Validate and audit the structured relevance keyword catalog."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from keyword_catalog import (  # noqa: E402
    flatten_catalog_terms,
    iter_catalog_entries,
    match_catalog,
    validate_catalog,
)


def load_config(path: Path) -> dict[str, Any]:
    """Load a keyword YAML file and return an empty config on empty input."""
    with path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def audit_catalog(config: dict[str, Any], corpus_path: Path | None = None) -> dict[str, Any]:
    """Build a machine-readable keyword coverage report.

    Parameters
    ----------
    config : dict[str, Any]
        Loaded keyword configuration.
    corpus_path : Path, optional
        JSONL file containing ``title`` and ``abstract`` fields.  If present,
        observed catalog hits are counted for every record.

    Returns
    -------
    dict[str, Any]
        Validation errors, catalog mappings and optional corpus statistics.
    """
    entries = iter_catalog_entries(config)
    errors = validate_catalog(config)
    report: dict[str, Any] = {
        "valid": not errors,
        "errors": errors,
        "entry_count": len(entries),
        "term_count": len(flatten_catalog_terms(config)),
        "entries": entries,
    }
    if corpus_path is None:
        return report

    hit_counts: Counter[str] = Counter()
    term_counts: Counter[str] = Counter()
    records_with_hit: set[int] = set()
    record_count = 0
    with corpus_path.open("r", encoding="utf-8") as corpus_file:
        for line_number, line in enumerate(corpus_file, start=1):
            if not line.strip():
                continue
            try:
                paper = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at line {line_number}: {error}") from error
            text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
            record_count += 1
            for match in match_catalog(text, config):
                hit_counts[match["id"]] += 1
                records_with_hit.add(record_count)
                for term in match["terms"]:
                    term_counts[term] += 1
    report["corpus"] = {
        "record_count": record_count,
        "records_with_any_hit": len(records_with_hit),
        "entry_hit_counts": dict(hit_counts),
        "term_hit_counts": dict(term_counts),
    }
    return report


def _print_report(report: dict[str, Any]) -> None:
    """Print a concise human-readable audit report."""
    status = "PASS" if report["valid"] else "FAIL"
    print(
        f"关键词目录: {status} | {report['entry_count']} 个概念 | "
        f"{report['term_count']} 个术语"
    )
    for error in report["errors"]:
        print(f"ERROR: {error}")
    for entry in report["entries"]:
        mapping = ", ".join(entry["subdomains"]) or "<未映射>"
        print(f"- {entry['id']}: {', '.join(entry['terms'])} -> {mapping}")
    corpus = report.get("corpus")
    if corpus:
        print(
            f"语料命中: {corpus['records_with_any_hit']}/"
            f"{corpus['record_count']} 条记录"
        )
        for entry_id, count in sorted(corpus["entry_hit_counts"].items()):
            print(f"  {entry_id}: {count}")


def main() -> int:
    """Run the keyword catalog audit CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=PROJECT_ROOT / "configs" / "keywords.yaml",
        help="keyword YAML path (default: configs/keywords.yaml)",
    )
    parser.add_argument(
        "--corpus", type=Path,
        help="optional JSONL corpus with title/abstract fields",
    )
    parser.add_argument("--json", action="store_true", help="print JSON output")
    arguments = parser.parse_args()
    try:
        report = audit_catalog(load_config(arguments.config), arguments.corpus)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"keyword audit failed: {error}", file=sys.stderr)
        return 2
    if arguments.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
