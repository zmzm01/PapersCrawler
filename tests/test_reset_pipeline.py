"""Offline tests for precise relevance-state reset selection."""

import sqlite3

from tools import reset_pipeline


RELEVANCE_COLUMNS = (
    "llm_relevance_status, llm_relevance_error, llm_relevance_date, "
    "llm_relevance_category, llm_relevance_subfields, llm_relevance_result, "
    "llm_relevance_confidence, llm_relevance_reason, llm_relevance_basis, "
    "relevance_screen_status, relevance_screen_error, relevance_screen_date, "
    "relevance_screen_category, relevance_screen_subfields, "
    "relevance_screen_confidence, relevance_screen_reason"
)


def _make_reset_db(tmp_path):
    """Create the minimal papers table used by the reset command."""
    database_path = tmp_path / "papers.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE papers (doi TEXT, publisher TEXT, "
        "llm_relevance_status TEXT, llm_relevance_error TEXT, "
        "llm_relevance_date TEXT, llm_relevance_category TEXT, "
        "llm_relevance_subfields TEXT, llm_relevance_result INTEGER, "
        "llm_relevance_confidence TEXT, llm_relevance_reason TEXT, "
        "llm_relevance_basis TEXT, relevance_screen_status TEXT, "
        "relevance_screen_error TEXT, relevance_screen_date TEXT, "
        "relevance_screen_category TEXT, relevance_screen_subfields TEXT, "
        "relevance_screen_confidence TEXT, relevance_screen_reason TEXT)"
    )
    values = [
        (
            "10.1234/ABC", "aps", "success", "old error", "today", "A",
            "old", 1, "high", "old reason", "fulltext", "success", None,
            "today", "A", "old", "high", "old screen reason",
        ),
        (
            "10.5678/other", "aps", "success", None, "today", "B",
            "old", 1, "high", "old reason", "fulltext", "success", None,
            "today", "B", "old", "high", "old screen reason",
        ),
    ]
    placeholders = ",".join("?" for _ in values[0])
    connection.executemany(f"INSERT INTO papers VALUES ({placeholders})", values)
    connection.commit()
    connection.close()
    return database_path


def _rows(database_path):
    connection = sqlite3.connect(database_path)
    rows = connection.execute(
        "SELECT doi, llm_relevance_status, llm_relevance_category, "
        "relevance_screen_status, relevance_screen_category FROM papers "
        "ORDER BY doi"
    ).fetchall()
    connection.close()
    return rows


def test_reset_relevance_exact_dois_is_case_insensitive_and_scoped(tmp_path, monkeypatch):
    """Only the requested DOI is reset, regardless of its current status."""
    database_path = _make_reset_db(tmp_path)
    monkeypatch.setattr(reset_pipeline, "DB_PATH", database_path)
    monkeypatch.setattr(reset_pipeline, "_confirm", lambda count, label: True)

    reset_pipeline.cmd_reset_relevance(dois=" 10.1234/abc ")

    connection = sqlite3.connect(database_path)
    selected = connection.execute(
        "SELECT " + RELEVANCE_COLUMNS + " FROM papers WHERE doi = '10.1234/ABC'"
    ).fetchone()
    untouched = connection.execute(
        "SELECT " + RELEVANCE_COLUMNS + " FROM papers WHERE doi = '10.5678/other'"
    ).fetchone()
    connection.close()
    assert all(value is None or value == "pending" for value in selected)
    assert untouched[0] == "success"
    assert untouched[3] == "B"
    assert _rows(database_path)[1][1:] == ("success", "B", "success", "B")


def test_reset_relevance_dois_and_categories_are_mutually_exclusive(tmp_path, monkeypatch, capsys):
    """A selector conflict must not mutate the database."""
    database_path = _make_reset_db(tmp_path)
    monkeypatch.setattr(reset_pipeline, "DB_PATH", database_path)

    reset_pipeline.cmd_reset_relevance(dois="10.1234/ABC", categories="A")

    assert "互斥" in capsys.readouterr().out
    assert all(row[1] == "success" for row in _rows(database_path))


def test_reset_relevance_empty_dois_is_rejected_without_fallback_reset(tmp_path, monkeypatch, capsys):
    """An empty --dois value must not accidentally use the default reset scope."""
    database_path = _make_reset_db(tmp_path)
    monkeypatch.setattr(reset_pipeline, "DB_PATH", database_path)

    reset_pipeline.cmd_reset_relevance(dois=" , ")

    assert "至少一个非空 DOI" in capsys.readouterr().out
    assert all(row[1] == "success" for row in _rows(database_path))
