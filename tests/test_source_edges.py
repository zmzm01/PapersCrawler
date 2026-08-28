"""Coverage for RSS/CrossRef retry and malformed-source handling."""

import pytest
import requests

from sources import crossref, rss


def test_rss_lifecycle_and_fetch_retries(tmp_path, monkeypatch):
    """RSS session lifecycle, retry and date fallbacks are covered."""
    processor = rss.RSSProcessor()
    assert processor.session.trust_env is False
    processor.close()
    processor.close()
    with rss.RSSProcessor() as context:
        assert context.session is not None

    processor = rss.RSSProcessor()
    responses = [
        requests.ConnectionError("offline"),
        type("Response", (), {"raise_for_status": lambda self: None, "text": "xml"})(),
    ]

    def get(*args, **kwargs):
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(processor.session, "get", get)
    monkeypatch.setattr(
        rss.time if hasattr(rss, "time") else __import__("time"),
        "sleep",
        lambda _delay: None,
    )
    assert processor.fetch_rss("url") == "xml"
    save_path = tmp_path / "feed.xml"
    processor.save_raw_rss("xml", str(save_path))
    assert save_path.read_text(encoding="utf-8") == "xml"
    responses.append(requests.ConnectionError("offline again"))
    with pytest.raises(requests.RequestException):
        processor.fetch_rss("url", max_retries=1)

    papers = processor.parse_rss(
        """<rss><channel>
        <item><title>Title &amp; detail</title><link>https://paper</link>
        <dc:identifier>doi:10.1000/a</dc:identifier><updated>2026-08-24</updated></item>
        <item><title>No DOI</title><link>https://other</link></item>
        </channel></rss>""",
        {},
    )
    assert papers[0].doi == "10.1000/a"
    assert papers[1].doi is None


def test_crossref_retry_journal_and_parse_fallbacks(monkeypatch):
    """CrossRef retries HTTP failures and parses sparse records safely."""
    client = crossref.CrossrefClient("test@example.com", max_retries=2)
    response_ok = type(
        "Response",
        (),
        {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"message": {"DOI": "10/x", "title": ["Title"]}},
        },
    )()
    responses = [requests.ConnectionError("offline"), response_ok]
    monkeypatch.setattr(
        client.session,
        "get",
        lambda *args, **kwargs: (
            (_ for _ in ()).throw(responses.pop(0))
            if isinstance(responses[0], BaseException)
            else responses.pop(0)
        ),
    )
    monkeypatch.setattr(crossref.time, "sleep", lambda _delay: None)
    assert client.fetch_by_doi("10/x").doi == "10/x"

    response_404 = type(
        "Response", (), {"status_code": 404, "raise_for_status": lambda self: None}
    )()
    client.session.get = lambda *args, **kwargs: response_404
    with pytest.raises(crossref.NotFoundError):
        client.fetch_by_doi("missing")

    work = {
        "DOI": "10/sparse",
        "title": [],
        "container-title": [],
        "created": {"date-parts": [[2026]]},
        "author": [],
        "abstract": "",
        "publisher": "P",
        "URL": "u",
    }
    sparse = crossref.CrossrefClient.parse_work(work)
    assert sparse.published == "2026-00-00"
    assert sparse.authors is None
    assert crossref.CrossrefClient.TextClean("") is None

    journal_response = type(
        "Response",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {
                "message": {
                    "items": [{"DOI": "10/j", "title": ["J"]}, {"bad": object()}],
                    "total-results": 2,
                }
            },
        },
    )()
    client.session.get = lambda *args, **kwargs: journal_response
    papers = client.fetch_by_journal("1234", "2026-01-01", "2026-01-02", max_results=1)
    assert len(papers) == 1
    client.close()
    client.close()
