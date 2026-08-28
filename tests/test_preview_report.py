"""Tests for the non-mutating report preview paper selection."""

from datetime import datetime
import os
import tempfile

import pytest

from db.database import DatabaseClient, FetchStatus
from tools.preview_report import _fetch_papers


@pytest.fixture
def db():
    """Create a temporary database containing no production data."""
    file_descriptor, database_path = tempfile.mkstemp(suffix=".db")
    os.close(file_descriptor)
    database = DatabaseClient(database_path)
    database.init_db_papers()
    yield database
    database.close()
    os.unlink(database_path)


def _insert_reportable_paper(database, doi, created_date):
    """Insert one reportable paper with the requested discovery date."""
    database.insert_rss_basicinfo(
        doi, doi, "https://example.com", "Journal", "Publisher", "2026"
    )
    database.insert_paper_created_date(doi, created_date)
    database.update_llm_relevance(
        doi,
        "A",
        "[]",
        "high",
        "relevant",
        FetchStatus.SUCCESS.value,
        created_date,
        basis="fulltext",
    )
    database.update_llm_summary(
        doi,
        '{"one_sentence":"summary"}',
        FetchStatus.SUCCESS.value,
        created_date,
    )


def test_fetch_papers_before_date_excludes_cutoff_and_newer(db):
    """The before-date filter is strict and uses created_date."""
    _insert_reportable_paper(db, "10.0000/old", "20260816")
    _insert_reportable_paper(db, "10.0000/cutoff", "2026-08-17")
    _insert_reportable_paper(db, "10.0000/new", "20260818")

    papers = _fetch_papers(
        db,
        "all",
        datetime(2026, 8, 21),
        before_date="2026-08-17",
    )

    assert [paper["doi"] for paper in papers] == ["10.0000/old"]


def test_fetch_papers_before_date_can_combine_with_week_scope(db):
    """Date bounds can be combined with an existing scope."""
    _insert_reportable_paper(db, "10.0000/inside", "20260815")
    _insert_reportable_paper(db, "10.0000/outside", "2026-08-08")

    papers = _fetch_papers(
        db,
        "week",
        datetime(2026, 8, 21),
        before_date="2026-08-17",
    )

    assert [paper["doi"] for paper in papers] == ["10.0000/inside"]
