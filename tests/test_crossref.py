"""
Tests: CrossRef DOI metadata (crossref.py)

Coverage:
  - TextClean JATS XML stripping
  - PaperMetadata dataclass
  - parse_work() date/author logic
  - fetch_by_doi() with mocked HTTP responses

All network-dependent tests are replaced with mocked responses.
"""

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sources.crossref import CrossrefClient, PaperMetadata, NotFoundError


@pytest.fixture
def client():
    """Create a CrossrefClient with a dummy mailto (no real API call)."""
    return CrossrefClient(mailto="test@example.com")


# ---- TextClean ----

def test_text_clean_jats_xml():
    """JATS XML tags should be removed, leaving only plain text."""
    jats = '<jats:p>This is a <jats:italic>formula</jats:italic> description.</jats:p>'
    cleaned = CrossrefClient.TextClean(jats)
    assert "jats:p" not in cleaned
    assert "jats:italic" not in cleaned
    assert "formula" in cleaned


def test_text_clean_empty():
    """Empty text cleaning returns None."""
    assert CrossrefClient.TextClean("") is None
    assert CrossrefClient.TextClean(None) is None


# ---- PaperMetadata ----

def test_paper_metadata_dataclass():
    """PaperMetadata stores fields correctly."""
    meta = PaperMetadata(
        doi="10.1234/test",
        title="Test Paper",
        authors=[{"name": "Alice"}],
        journal="J. Test",
        published="2025-01-15",
    )
    assert meta.doi == "10.1234/test"
    assert meta.title == "Test Paper"
    assert meta.journal == "J. Test"


# ---- fetch_by_doi (mocked) ----

@patch('requests.Session.get')
def test_fetch_by_doi_success(mock_get, client):
    """Mock a successful CrossRef API response and verify parsing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ok",
        "message": {
            "DOI": "10.1364/OE.582177",
            "title": ["Test Paper Title for Testing"],
            "author": [
                {"given": "Alice", "family": "Smith", "ORCID": "https://orcid.org/0000-0001-2345-6789"},
                {"given": "Bob", "family": "Jones"},
            ],
            "published-print": {"date-parts": [[2025, 6, 15]]},
            "abstract": "<jats:p>This is a test abstract for unit testing.</jats:p>",
            "container-title": ["Test Journal"],
            "publisher": "Test Publisher",
            "URL": "https://doi.org/10.1364/OE.582177",
        }
    }
    mock_get.return_value = mock_resp

    meta = client.fetch_by_doi("10.1364/OE.582177")

    assert meta.doi == "10.1364/OE.582177"
    assert meta.title == "Test Paper Title for Testing"
    assert meta.published == "2025-06-15"
    assert meta.journal == "Test Journal"
    assert meta.publisher == "Test Publisher"
    assert len(meta.authors) == 2
    assert meta.authors[0]["name"] == "Alice Smith"
    assert meta.authors[1]["name"] == "Bob Jones"
    assert "test abstract" in meta.abstract


@patch('requests.Session.get')
def test_fetch_by_doi_not_found(mock_get, client):
    """404 response should raise NotFoundError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    with pytest.raises(NotFoundError):
        client.fetch_by_doi("10.9999/invalid-doi")


@patch('requests.Session.get')
def test_fetch_by_doi_no_abstract(mock_get, client):
    """Non-OA paper may have no abstract; other fields should still parse."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ok",
        "message": {
            "DOI": "10.1103/PhysRevLett.134.195001",
            "title": ["Non-OA Test Paper"],
            "author": [{"given": "Charlie", "family": "Brown"}],
            "published-online": {"date-parts": [[2025, 4, 1]]},
            "container-title": ["Physical Review Letters"],
            "publisher": "APS",
        }
    }
    mock_get.return_value = mock_resp

    meta = client.fetch_by_doi("10.1103/PhysRevLett.134.195001")

    assert meta.doi == "10.1103/PhysRevLett.134.195001"
    assert meta.title == "Non-OA Test Paper"
    assert meta.published == "2025-04-01"
    assert meta.journal == "Physical Review Letters"
    assert meta.abstract is None


# ---- parse_work ----

def test_parse_work_date_parts():
    """Verify date-parts parsing logic."""
    work = {
        "DOI": "10.0000/test",
        "published-online": {"date-parts": [[2025, 6, 15]]},
    }
    meta = CrossrefClient.parse_work(work)
    assert meta.published == "2025-06-15"


def test_parse_work_date_only_year():
    """Date with only year should parse as YYYY-00-00."""
    work = {
        "DOI": "10.0000/test",
        "published-print": {"date-parts": [[2025]]},
    }
    meta = CrossrefClient.parse_work(work)
    assert meta.published == "2025-00-00"


def test_parse_work_no_authors():
    """Response without author field should have authors=None."""
    work = {"DOI": "10.0000/test", "title": ["No Author Paper"]}
    meta = CrossrefClient.parse_work(work)
    assert meta.authors is None


def test_parse_work_empty_authors():
    """Empty author list should result in authors=None."""
    work = {"DOI": "10.0000/test", "author": []}
    meta = CrossrefClient.parse_work(work)
    assert meta.authors is None


def test_parse_work_no_date():
    """No date field should not crash."""
    work = {"DOI": "10.0000/test"}
    meta = CrossrefClient.parse_work(work)
    assert meta.published is None
