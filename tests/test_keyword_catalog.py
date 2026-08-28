"""Offline tests for structured keyword management and benchmark metrics."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from keyword_catalog import match_catalog, validate_catalog
from evaluate_relevance import score_predictions
from processors.paper_relevance import PaperRelevanceChecker


def _config():
    """Build a small valid catalog for unit tests."""
    return {
        "scope_definition": {"channel": {}, "diagnostics": {}},
        "keyword_catalog": [
            {"id": "channel", "terms": ["plasma channel", "等离子体通道"],
             "subdomains": ["channel"]},
            {"id": "diagnostics", "terms": ["闪烁体探测器"],
             "subdomains": ["diagnostics"]},
        ],
    }


def test_catalog_matches_aliases_and_chinese_terms():
    """Literal matching returns concept IDs and mapped subdomains."""
    matches = match_catalog(
        "A PLASMA CHANNEL was characterized with 闪烁体探测器.", _config()
    )
    assert [item["id"] for item in matches] == ["channel", "diagnostics"]
    assert matches[0]["subdomains"] == ["channel"]


def test_catalog_validation_catches_unknown_subdomain_and_duplicate_term():
    """Catalog validation prevents silent unmapped interest points."""
    config = _config()
    config["keyword_catalog"].append({
        "id": "bad", "terms": ["plasma channel"], "subdomains": ["missing"]
    })
    errors = validate_catalog(config)
    assert any("duplicate keyword term" in error for error in errors)
    assert any("unknown subdomain" in error for error in errors)


def test_checker_exposes_catalog_matches_without_deciding_relevance():
    """The relevance checker exposes audit evidence separately from labels."""
    checker = PaperRelevanceChecker(_config())
    matches = checker.keyword_catalog_matches("plasma channel", "")
    assert matches[0]["id"] == "channel"


def test_relevance_score_reports_binary_metrics_and_confusion_matrix():
    """Benchmark scoring distinguishes four-class and report-level errors."""
    gold = [
        {"id": "a", "gold_category": "A"},
        {"id": "b", "gold_category": "B"},
        {"id": "d", "gold_category": "D"},
    ]
    predictions = [
        {"id": "a", "predicted_category": "B"},
        {"id": "b", "predicted_category": "D"},
        {"id": "d", "predicted_category": "D"},
    ]
    result = score_predictions(gold, predictions)
    assert result["count"] == 3
    assert result["accuracy"] == 1 / 3
    assert result["relevant_ab_vs_cd"]["recall"] == 0.5
    assert result["confusion_matrix"]["B"]["D"] == 1
