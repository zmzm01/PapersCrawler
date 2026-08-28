"""Regression test for HIGH #3 (2026-07-24 Pipeline Review).

When CrossRef returns no authors, Phase B must mark the paper as FAILED,
not SUCCESS. Design contract: tasks.md 2026-05-23, design.md Phase B section.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from db.database import FetchStatus  # noqa: E402


def _make_paper(authors=None):
    """Build a minimal crossref paper-like object."""
    p = MagicMock()
    p.authors = authors
    p.title = "Test Title"
    p.published = "2026-01-01"
    p.abstract = "Test abstract"
    return p


@patch("pipeline.phase_b.CrossrefClient")
@patch("pipeline.phase_b.DatabaseClient")
def test_phase_b_marks_failed_when_authors_missing(mock_db_cls, mock_cr_cls):
    """Missing authors → FAILED status, not SUCCESS."""
    from pipeline.phase_b import phase_b_crossref

    mock_db = MagicMock()
    mock_db.get_pendings.return_value = [{"doi": "10.1234/test"}]
    mock_db_cls.return_value = mock_db

    mock_cr = MagicMock()
    mock_cr.fetch_by_doi.return_value = _make_paper(authors=None)
    mock_cr_cls.return_value = mock_cr

    phase_b_crossref(mock_db)

    # Must mark as FAILED
    mock_db.update_error_message.assert_called_once()
    call_args = mock_db.update_error_message.call_args
    assert call_args[0][1] == "cr_metadata_fetched_status"
    assert call_args[0][2] == FetchStatus.FAILED.value
    assert "no authors" in call_args[0][4].lower()

    # Must NOT mark as SUCCESS
    success_calls = [
        c for c in mock_db.update_process_status.call_args_list
        if len(c[0]) > 2 and c[0][2] == FetchStatus.SUCCESS.value
    ]
    assert success_calls == [], f"Unexpected SUCCESS calls: {success_calls}"

    # Must NOT write partial metadata
    mock_db.update_crossref_metadata.assert_not_called()


@patch("pipeline.phase_b.CrossrefClient")
@patch("pipeline.phase_b.DatabaseClient")
def test_phase_b_marks_success_when_authors_present(mock_db_cls, mock_cr_cls):
    """Authors present → SUCCESS status (regression guard)."""
    from pipeline.phase_b import phase_b_crossref

    mock_db = MagicMock()
    mock_db.get_pendings.return_value = [{"doi": "10.1234/test"}]
    mock_db_cls.return_value = mock_db

    mock_cr = MagicMock()
    mock_cr.fetch_by_doi.return_value = _make_paper(authors=[{"name": "Smith, J."}])
    mock_cr_cls.return_value = mock_cr

    phase_b_crossref(mock_db)

    mock_db.update_crossref_metadata.assert_called_once()
    mock_db.update_process_status.assert_called_once()
    call_args = mock_db.update_process_status.call_args
    assert call_args[0][2] == FetchStatus.SUCCESS.value
