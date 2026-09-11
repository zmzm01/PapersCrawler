"""Tests for deterministic relevance-audit sampling."""

import sqlite3

from tools.sample_relevance_audit import load_candidates, stratified_sample


def _create_database(path):
    """Create a minimal papers and reviews database for sampling tests."""
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE papers (
            doi TEXT, title TEXT, abstract TEXT, journal TEXT, publisher TEXT,
            created_date TEXT, paperdate_crossref TEXT, paperdate_page TEXT,
            paperdate_rss TEXT, relevance_screen_status TEXT,
            relevance_screen_category TEXT, relevance_screen_confidence TEXT,
            relevance_screen_reason TEXT, relevance_screen_model TEXT
        );
        CREATE TABLE relevance_reviews (id INTEGER PRIMARY KEY, doi TEXT);
    """)
    rows = [
        ("10/a", "A", "abstract", "J", "aps", "2025-01-01", "2025", "D", None),
        ("10/b", "B", "abstract", "J", "aps", "2026-01-01", "2026", "D", None),
        ("10/c", "C", "abstract", "J", "iop", "2025-01-01", "2025", "D", None),
        ("10/d", "D", "abstract", "J", "iop", "2026-01-01", "2026", "D", "new/model"),
    ]
    connection.executemany("""
        INSERT INTO papers (
            doi, title, abstract, journal, publisher, created_date,
            paperdate_crossref, relevance_screen_status,
            relevance_screen_category, relevance_screen_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'success', ?, ?)
    """, rows)
    connection.execute("INSERT INTO relevance_reviews (doi) VALUES ('10/c')")
    connection.commit()
    connection.close()


def test_load_candidates_defaults_to_unreviewed_legacy_d(tmp_path):
    """Default candidate selection excludes new-model and reviewed rows."""
    database_path = tmp_path / "papers.db"
    _create_database(database_path)

    rows = load_candidates(database_path, "D", "legacy")

    assert [row["doi"] for row in rows] == ["10/a", "10/b"]


def test_stratified_sample_is_deterministic_and_proportional():
    """Sampling is repeatable and follows source-population proportions."""
    records = [
        {
            "doi": f"a{record_number}",
            "publisher": "a",
            "paper_year": "2025",
        }
        for record_number in range(90)
    ] + [
        {
            "doi": f"b{record_number}",
            "publisher": "b",
            "paper_year": "2026",
        }
        for record_number in range(10)
    ]

    first = stratified_sample(records, 20, 7, "publisher-year")
    second = stratified_sample(records, 20, 7, "publisher-year")

    assert first == second
    assert sum(record["publisher"] == "a" for record in first) == 18
    assert sum(record["publisher"] == "b" for record in first) == 2
