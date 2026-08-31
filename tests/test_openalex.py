"""Unit tests for OpenAlex fallback and full-text candidate handling."""

import json
from pathlib import Path
from types import SimpleNamespace

import requests

from db.database import DatabaseClient
from sources.fulltext import resolve_candidates
from sources.openalex import OpenAlexClient, OpenAlexNotFoundError


class _Response:
    """Small requests response double."""

    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.headers = {}
        self.url = "https://api.openalex.org/works/test"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._payload


def test_openalex_rebuilds_abstract_and_locations():
    """OpenAlex inverted index and external OA locations are normalized."""
    work = {
        "id": "https://openalex.org/W1",
        "title": "A title",
        "publication_date": "2026-01-02",
        "abstract_inverted_index": {"first": [1], "abstract": [0]},
        "authorships": [{"author": {"display_name": "A", "orcid": "o"}}],
        "locations": [{
            "pdf_url": "https://repository.test/a.pdf",
            "landing_page_url": "https://repository.test/a",
            "version": "acceptedVersion",
            "is_oa": True,
        }],
    }
    metadata = OpenAlexClient.parse_work(work, "10.1000/x")
    assert metadata.abstract == "abstract first"
    assert metadata.authors == [{"name": "A", "orcid": "o"}]
    assert metadata.locations[0]["pdf_url"].endswith("a.pdf")


def test_openalex_client_404_is_not_retried():
    """A missing DOI is terminal and does not trigger retry sleeps."""
    class Session:
        headers = {}

        def get(self, *args, **kwargs):
            return _Response({}, 404)

        def close(self):
            pass

    client = OpenAlexClient(session=Session(), max_retries=3, requests_per_second=1000)
    try:
        try:
            client.fetch_by_doi("10.1000/missing")
        except OpenAlexNotFoundError:
            pass
        else:
            raise AssertionError("expected OpenAlexNotFoundError")
    finally:
        client.close()


def test_openalex_metadata_merge_and_external_location(tmp_path):
    """OpenAlex only fills empty Crossref fields and filters hosted content."""
    db = DatabaseClient(str(Path(tmp_path) / "papers.db"))
    db.init_db_papers()
    db.insert_rss_basicinfo("10.1000/x", "Crossref title", "https://page",
                            "J", "aps", "2026")
    metadata = SimpleNamespace(
        title="OpenAlex title", authors=[{"name": "A"}], journal="JA",
        published="2026-02-01", abstract="OpenAlex abstract",
        openalex_id="W1", locations=[
            {"url": "https://content.openalex.org/x", "source": "openalex"},
            {"url": "https://repository.test/x.pdf", "source": "openalex",
             "is_oa": True},
        ],
    )
    db.update_openalex_metadata("10.1000/x", metadata, "now")
    paper = db.get_all_papers()[0]
    assert paper["title"] == "Crossref title"
    assert paper["abstract"] == "OpenAlex abstract"
    assert json.loads(paper["metadata_provenance_json"])["abstract"] == "openalex"
    assert [item["url"] for item in db.get_fulltext_locations("10.1000/x")] == [
        "https://repository.test/x.pdf"
    ]
    assert resolve_candidates(db, paper)[0]["source"] == "openalex"


def test_fulltext_candidates_prefer_crossref_then_openalex(tmp_path):
    """Entitled Crossref URLs precede OA and legacy Publisher fallbacks."""
    db = DatabaseClient(str(Path(tmp_path) / "papers.db"))
    db.init_db_papers()
    db.insert_rss_basicinfo(
        "10.1000/order", "Title", "https://publisher.test/article",
        "J", "aps", "2026",
    )
    db.add_fulltext_locations(
        "10.1000/order",
        [{"url": "https://oa.test/paper.pdf", "source": "openalex"}],
    )
    db.add_fulltext_locations(
        "10.1000/order",
        [{"url": "https://crossref.test/paper.pdf", "source": "crossref"}],
    )
    paper = dict(db.get_all_papers()[0])
    paper["pdf_url"] = "https://publisher.test/paper.pdf"

    assert [item["source"] for item in resolve_candidates(db, paper)] == [
        "crossref", "openalex", "publisher",
    ]
