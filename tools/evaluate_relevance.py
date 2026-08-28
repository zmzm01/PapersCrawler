#!/usr/bin/env python
"""Score relevance predictions against a small, human-labelled benchmark."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read non-empty JSONL records and report the line of malformed input."""
    records = []
    with path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at line {line_number}: {error}") from error
            if not isinstance(record, dict):
                raise ValueError(f"JSONL line {line_number} is not an object")
            records.append(record)
    return records


def _category(value: Any) -> str:
    """Normalise a category value to A/B/C/D or an empty string."""
    value = str(value or "").strip().upper()
    return value if value in {"A", "B", "C", "D"} else ""


def score_predictions(gold_records: Iterable[dict[str, Any]],
                      prediction_records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Calculate exact and useful binary relevance metrics.

    Parameters
    ----------
    gold_records : iterable of dict
        Records with ``id`` and ``gold_category``.
    prediction_records : iterable of dict
        Records with ``id`` and ``predicted_category``.

    Returns
    -------
    dict[str, Any]
        Confusion matrix, four-class accuracy and A/B-vs-C/D precision,
        recall and F1.
    """
    gold = {str(record.get("id", "")): _category(record.get("gold_category"))
            for record in gold_records}
    predicted = {
        str(record.get("id", "")): _category(record.get("predicted_category"))
        for record in prediction_records
    }
    ids = [record_id for record_id, category in gold.items()
           if record_id and category and record_id in predicted and predicted[record_id]]
    matrix = {actual: {guess: 0 for guess in "ABCD"} for actual in "ABCD"}
    for record_id in ids:
        matrix[gold[record_id]][predicted[record_id]] += 1
    exact = sum(matrix[category][category] for category in "ABCD")
    relevant_gold = sum(gold[record_id] in {"A", "B"} for record_id in ids)
    relevant_predicted = sum(predicted[record_id] in {"A", "B"} for record_id in ids)
    true_positive = sum(
        gold[record_id] in {"A", "B"} and predicted[record_id] in {"A", "B"}
        for record_id in ids
    )
    false_positive = relevant_predicted - true_positive
    false_negative = relevant_gold - true_positive
    precision = true_positive / relevant_predicted if relevant_predicted else 0.0
    recall = true_positive / relevant_gold if relevant_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "count": len(ids),
        "missing_predictions": sorted(set(gold) - set(predicted)),
        "accuracy": exact / len(ids) if ids else 0.0,
        "confusion_matrix": matrix,
        "relevant_ab_vs_cd": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        },
    }


def load_db_review_pairs(db_path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Load latest human review decisions and final LLM categories from SQLite."""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """WITH latest_review AS (
                   SELECT review.*
                   FROM relevance_reviews AS review
                   JOIN (
                       SELECT doi, MAX(id) AS id
                       FROM relevance_reviews GROUP BY doi
                   ) AS newest ON newest.id = review.id
               )
               SELECT paper.doi AS id,
                      paper.llm_relevance_category AS predicted_category,
                      latest_review.decision AS gold_category
               FROM papers AS paper
               JOIN latest_review ON latest_review.doi = paper.doi
               WHERE latest_review.decision IN ('A', 'B', 'C', 'D')
                 AND paper.llm_relevance_category IN ('A', 'B', 'C', 'D')"""
        ).fetchall()
    finally:
        connection.close()
    gold = [{"id": row["id"], "gold_category": row["gold_category"]} for row in rows]
    predicted = [{"id": row["id"], "predicted_category": row["predicted_category"]} for row in rows]
    return gold, predicted


def _print_score(score: dict[str, Any]) -> None:
    """Print benchmark metrics for terminal use."""
    binary = score["relevant_ab_vs_cd"]
    print(f"样本数: {score['count']}")
    print(f"四分类准确率: {score['accuracy']:.3f}")
    print(
        "A/B vs C/D: "
        f"precision={binary['precision']:.3f}, "
        f"recall={binary['recall']:.3f}, f1={binary['f1']:.3f}"
    )
    print("混淆矩阵（行=人工，列=预测）:")
    print("      A  B  C  D")
    for category in "ABCD":
        values = "  ".join(str(score["confusion_matrix"][category][guess]) for guess in "ABCD")
        print(f"  {category}   {values}")
    if score["missing_predictions"]:
        print("缺少预测:", ", ".join(score["missing_predictions"]))


def main() -> int:
    """Run the relevance benchmark CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, help="gold JSONL file")
    parser.add_argument("--predictions", type=Path, help="prediction JSONL file")
    parser.add_argument(
        "--db", type=Path,
        default=PROJECT_ROOT / "data" / "papers.db",
        help="use latest WebUI reviews and final LLM results from this DB",
    )
    parser.add_argument("--json", action="store_true", help="print JSON output")
    arguments = parser.parse_args()
    try:
        if arguments.gold:
            if not arguments.predictions:
                parser.error("--gold requires --predictions")
            gold = read_jsonl(arguments.gold)
            predictions = read_jsonl(arguments.predictions)
        else:
            gold, predictions = load_db_review_pairs(arguments.db)
        score = score_predictions(gold, predictions)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"relevance evaluation failed: {error}", file=sys.stderr)
        return 2
    if arguments.json:
        print(json.dumps(score, ensure_ascii=False, indent=2))
    else:
        _print_score(score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
