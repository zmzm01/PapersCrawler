#!/usr/bin/env python
"""Export a deterministic, stratified sample for relevance recall audits."""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "papers.db"


def _stratum(record: dict[str, Any], mode: str) -> tuple[str, ...]:
    """Return the configured sampling stratum for one paper."""
    publisher = str(record.get("publisher") or "unknown")
    year = str(record.get("paper_year") or "unknown")
    if mode == "publisher-year":
        return publisher, year
    if mode == "publisher":
        return (publisher,)
    if mode == "year":
        return (year,)
    return ("all",)


def stratified_sample(records: Iterable[dict[str, Any]], size: int,
                      seed: int, mode: str) -> list[dict[str, Any]]:
    """Select a deterministic proportional sample across configured strata.

    Parameters
    ----------
    records : iterable of dict
        Candidate paper records.
    size : int
        Maximum number of records to return.
    seed : int
        Seed used to shuffle strata and records.
    mode : str
        One of ``publisher-year``, ``publisher``, ``year`` or ``none``.

    Returns
    -------
    list[dict]
        Selected records. Each stratum receives its population-proportional
        quota using the largest-remainder method.
    """
    if size <= 0:
        return []
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_stratum(record, mode)].append(record)
    population_size = sum(len(group) for group in groups.values())
    sample_size = min(size, population_size)
    randomizer = random.Random(seed)
    for group in groups.values():
        randomizer.shuffle(group)

    quotas = {
        key: sample_size * len(group) / population_size
        for key, group in groups.items()
    }
    allocations = {key: int(quota) for key, quota in quotas.items()}
    remaining = sample_size - sum(allocations.values())
    remainder_keys = sorted(groups)
    randomizer.shuffle(remainder_keys)
    remainder_keys.sort(
        key=lambda key: quotas[key] - allocations[key], reverse=True,
    )
    for key in remainder_keys[:remaining]:
        allocations[key] += 1

    selected = []
    for key in sorted(groups):
        selected.extend(groups[key][:allocations[key]])
    randomizer.shuffle(selected)
    return selected


def load_candidates(db_path: Path, category: str, model: str,
                    include_reviewed: bool = False) -> list[dict[str, Any]]:
    """Load screen decisions eligible for an audit sample.

    Parameters
    ----------
    db_path : pathlib.Path
        PapersCrawler SQLite database.
    category : str
        Existing screen category to sample.
    model : str
        ``legacy``, ``all`` or an exact recorded model ID.
    include_reviewed : bool, optional
        Include papers already present in ``relevance_reviews``.

    Returns
    -------
    list[dict]
        Candidate paper dictionaries.
    """
    conditions = [
        "p.relevance_screen_status = 'success'",
        "p.relevance_screen_category = ?",
        "COALESCE(TRIM(p.abstract), '') != ''",
    ]
    parameters: list[Any] = [category]
    if model == "legacy":
        conditions.append("COALESCE(TRIM(p.relevance_screen_model), '') = ''")
    elif model != "all":
        conditions.append("p.relevance_screen_model = ?")
        parameters.append(model)
    if not include_reviewed:
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM relevance_reviews AS review "
            "WHERE LOWER(TRIM(review.doi)) = LOWER(TRIM(p.doi)))"
        )
    query = """
        SELECT p.doi, p.title, p.abstract, p.journal, p.publisher,
               p.created_date, p.relevance_screen_category,
               p.relevance_screen_confidence, p.relevance_screen_reason,
               p.relevance_screen_model,
               SUBSTR(COALESCE(p.paperdate_crossref, p.paperdate_page,
                               p.paperdate_rss, p.created_date, ''), 1, 4)
                   AS paper_year
        FROM papers AS p
        WHERE {conditions}
        ORDER BY LOWER(TRIM(p.doi))
    """.format(conditions=" AND ".join(conditions))
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(query, parameters)]
    finally:
        connection.close()


def audit_record(record: dict[str, Any], mode: str) -> dict[str, Any]:
    """Convert a database row to an annotation-ready JSON object."""
    stratum = _stratum(record, mode)
    return {
        "id": record["doi"],
        "doi": record["doi"],
        "title": record["title"] or "",
        "abstract": record["abstract"] or "",
        "journal": record["journal"] or "",
        "publisher": record["publisher"] or "",
        "paper_year": record["paper_year"] or "",
        "predicted_category": record["relevance_screen_category"],
        "predicted_confidence": record["relevance_screen_confidence"],
        "predicted_reason": record["relevance_screen_reason"],
        "predicted_model": record["relevance_screen_model"],
        "gold_category": None,
        "audit_notes": "",
        "selection_stratum": list(stratum),
    }


def write_jsonl(records: Iterable[dict[str, Any]], output: Path | None) -> None:
    """Write audit records to a file or standard output."""
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    content = "\n".join(lines) + ("\n" if lines else "")
    if output is None:
        sys.stdout.write(content)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def register_cohort(db_path: Path, cohort: str,
                    records: list[dict[str, Any]],
                    metadata: dict[str, Any] | None = None) -> int:
    """Register sampled records as a persistent WebUI audit cohort.

    Parameters
    ----------
    db_path : pathlib.Path
        PapersCrawler SQLite database.
    cohort : str
        Stable name shown in the WebUI.
    records : list of dict
        Annotation-ready audit records.
    metadata : dict, optional
        Sampling parameters and source-population size.

    Returns
    -------
    int
        Number of newly inserted cohort items.
    """
    src_path = PROJECT_ROOT / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from db.database import DatabaseClient

    with DatabaseClient(db_path) as database:
        database.init_db_papers()
        return database.register_relevance_audit_cohort(
            cohort, records, metadata=metadata,
        )


def main() -> int:
    """Run the relevance-audit sampling CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--category", choices=list("ABCD"), default="D")
    parser.add_argument(
        "--model", default="legacy",
        help="legacy (default), all, or an exact relevance_screen_model ID",
    )
    parser.add_argument(
        "--stratify", choices=["publisher-year", "publisher", "year", "none"],
        default="publisher-year",
    )
    parser.add_argument("--include-reviewed", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--register-cohort",
        help="persist the selected sample under this name for WebUI review",
    )
    arguments = parser.parse_args()
    if arguments.size <= 0:
        parser.error("--size must be positive")
    try:
        candidates = load_candidates(
            arguments.db, arguments.category, arguments.model,
            include_reviewed=arguments.include_reviewed,
        )
        selected = stratified_sample(
            candidates, arguments.size, arguments.seed, arguments.stratify,
        )
        audit_records = [
            audit_record(record, arguments.stratify) for record in selected
        ]
        if arguments.output or not arguments.register_cohort:
            write_jsonl(audit_records, arguments.output)
        inserted_count = 0
        if arguments.register_cohort:
            inserted_count = register_cohort(
                arguments.db, arguments.register_cohort, audit_records,
                metadata={
                    "population_size": len(candidates),
                    "category": arguments.category,
                    "model_filter": arguments.model,
                    "stratify_mode": arguments.stratify,
                    "seed": arguments.seed,
                },
            )
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"relevance audit sampling failed: {error}", file=sys.stderr)
        return 2
    if arguments.output:
        print(
            f"Exported {len(selected)} of {len(candidates)} candidates to "
            f"{arguments.output}",
        )
    if arguments.register_cohort:
        print(
            f"Registered {inserted_count} new items in WebUI cohort "
            f"{arguments.register_cohort!r}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
