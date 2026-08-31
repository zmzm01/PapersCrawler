"""Offline coverage tests for pipeline orchestration and integration edges.

These tests deliberately replace network, browser and LLM clients with small
deterministic fakes.  The production code is consequently exercised through
the same success, retry, skip and failure decisions used in a real run without
spending external API quotas.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from pipeline import (
    base,
    phase_a,
    phase_b,
    phase_c,
    phase_e,
    phase_e2,
    phase_e3,
    phase_f,
    phase_g,
    phase_h,
)
from processors.paper_relevance import LLMAPICallError
from sources.crossref import NotFoundError
from sources.publisher import AcceptedPaperError, NonResearchPageError, Paper


def test_base_scraper_factory_and_journal_overrides(tmp_path, monkeypatch):
    """Factory and journal settings honor defaults, overrides and errors."""
    calls = []

    class FakeScraper:
        def __init__(self, user_data_dir):
            self.user_data_dir = user_data_dir

        def start_browser(self, proxy):
            calls.append((self.user_data_dir, proxy))

    monkeypatch.setitem(
        base.SCRAPER_MAP, "fake", (FakeScraper, tmp_path / "fake", {"server": "normal"})
    )
    scraper = base.create_scraper("fake", proxy_override={"server": "fallback"})
    assert isinstance(scraper, FakeScraper)
    assert calls == [(tmp_path / "fake", {"server": "fallback"})]
    with pytest.raises(ValueError):
        base.create_scraper("missing")

    override_path = tmp_path / "overrides.json"
    monkeypatch.setattr(base, "JOURNAL_OVERRIDES_PATH", override_path)
    assert base.load_journal_overrides() == {"journals": {}}
    override_path.write_text("not-json", encoding="utf-8")
    assert base.load_journal_overrides() == {"journals": {}}
    override_path.write_text(
        json.dumps({"journals": {"j": {"enabled": False}}}), encoding="utf-8"
    )
    assert base.load_journal_overrides()["journals"]["j"]["enabled"] is False

    journal = {"id": "j", "enabled": True, "rss_enabled": False}
    assert base.journal_effective(
        journal, {"journals": {"j": {"rss_enabled": True}}}, "rss_enabled"
    )
    assert not base.journal_effective(
        journal, {"journals": {"j": {"enabled": False}}}, "cr_enabled"
    )
    assert base.journal_effective(journal, {}, "rss_enabled") is False
    assert base.journal_effective({"id": "j"}, {}, "cr_enabled") is True
    assert base.journal_effective({"id": "j"}, {}, "enabled") is True


def test_phase_a_rss_success_skip_and_failure(monkeypatch, tmp_path):
    """RSS phase handles filters, inserts and per-journal failures."""
    paper_type = SimpleNamespace
    rss_papers = [
        paper_type(doi="", title="no doi", url="", date=""),
        paper_type(doi="10/existing", title="existing", url="", date=""),
        paper_type(doi="10/skipped", title="skipped", url="", date=""),
        paper_type(doi="10/d41586-news", title="news", url="", date=""),
        paper_type(doi="10/new", title="new", url="u", date="2026"),
    ]

    class FakeRSS:
        def fetch_rss(self, url):
            if url == "bad":
                raise RuntimeError("network")
            return "xml"

        def save_raw_rss(self, text, path):
            Path(path).write_text(text, encoding="utf-8")

        def parse_rss(self, text, journal):
            return rss_papers

    class FakeDB:
        def __init__(self):
            self.inserted = []

        def paper_doi_exists(self, doi):
            return doi == "10/existing"

        def is_doi_skipped(self, doi):
            return doi == "10/skipped"

        def insert_rss_basicinfo(self, *args):
            self.inserted.append(args)

        def insert_paper_created_date(self, *args):
            self.inserted.append(args)

    monkeypatch.setattr(phase_a, "RSSProcessor", FakeRSS)
    monkeypatch.setattr(phase_a, "RAW_RSS_DIR", tmp_path / "raw")
    monkeypatch.setattr(phase_a.CFG, "SKIP_PHASE_A_RSS", False)
    monkeypatch.setattr(phase_a.CFG, "SKIP_NATURE_NEWS", True)
    publishers = [
        {"id": "ok", "publisher": "nature", "rss": "ok", "name": "Nature"},
        {"id": "bad", "publisher": "aps", "rss": "bad", "name": "APS"},
        {
            "id": "off",
            "publisher": "aps",
            "rss": "off",
            "name": "Off",
            "rss_enabled": False,
        },
    ]
    database = FakeDB()
    phase_a.phase_a_rss(database, publishers, use_overrides=False)
    assert any(row[0] == "10/new" for row in database.inserted)
    assert (tmp_path / "raw" / "ok.xml").read_text(encoding="utf-8") == "xml"

    monkeypatch.setattr(phase_a.CFG, "SKIP_PHASE_A_RSS", True)
    assert phase_a.phase_a_rss(database, publishers) is None


def test_phase_a_crossref_deduplicates_and_records_success(monkeypatch, tmp_path):
    """CrossRef phase covers duplicate ISSNs and all paper filters."""

    class FakeClient:
        def __init__(self, **kwargs):
            self.calls = []

        def fetch_by_journal(self, issn, start, end):
            self.calls.append(issn)
            if issn == "bad":
                raise RuntimeError("temporary")
            return [
                SimpleNamespace(doi=None, title="missing", url=None, published=""),
                SimpleNamespace(
                    doi="10/d41586-news", title="news", url="", published=""
                ),
                SimpleNamespace(doi="10/skipped", title="skip", url="", published=""),
                SimpleNamespace(
                    doi="10/existing", title="existing", url="", published=""
                ),
                SimpleNamespace(doi="10/new", title="new", url="u", published="2026"),
            ]

    class FakeDB:
        def __init__(self):
            self.actions = []

        def is_doi_skipped(self, doi):
            return doi == "10/skipped"

        def paper_doi_exists(self, doi):
            return doi == "10/existing"

        def append_discovery_source(self, *args):
            self.actions.append(("append", args))

        def insert_paper_basicinfo(self, **kwargs):
            self.actions.append(("insert", kwargs))

        def insert_paper_created_date(self, *args):
            self.actions.append(("date", args))

    saved = []
    monkeypatch.setattr(phase_a, "CrossrefClient", FakeClient)
    monkeypatch.setattr(phase_a, "_save_last_run_date", saved.append)
    monkeypatch.setattr(phase_a, "_compute_lookback_days", lambda: 2)
    monkeypatch.setattr(phase_a.CFG, "SKIP_PHASE_A_CR", False)
    monkeypatch.setattr(phase_a.CFG, "SKIP_NATURE_NEWS", True)
    publishers = [
        {"id": "one", "publisher": "aps", "name": "J", "issn": "good"},
        {"id": "duplicate", "publisher": "aps", "name": "J2", "issn": "good"},
        {"id": "none", "publisher": "aps", "name": "J3"},
        {"id": "bad", "publisher": "aps", "name": "J4", "issn": "bad"},
        {
            "id": "off",
            "publisher": "aps",
            "name": "J5",
            "issn": "off",
            "cr_enabled": False,
        },
    ]
    database = FakeDB()
    phase_a.phase_a_crossref(database, publishers)
    assert saved
    assert [action[0] for action in database.actions] == ["append", "insert", "date"]
    assert phase_a.phase_a_crossref(database, publishers) is None
    monkeypatch.setattr(phase_a.CFG, "SKIP_PHASE_A_CR", True)
    assert phase_a.phase_a_crossref(database, publishers) is None


def test_phase_e_screen_success_and_error_paths(monkeypatch):
    """Phase E stores normalized results and isolates every worker failure."""
    rows = [
        {
            "doi": "10/pending",
            "title": "pending",
            "abstract": "",
            "publisher_page_fetched_status": "pending",
        },
        {
            "doi": "10/skip",
            "title": "skip",
            "abstract": "",
            "publisher_page_fetched_status": "success",
        },
        {
            "doi": "10/good",
            "title": "good",
            "abstract": "abstract",
            "publisher_page_fetched_status": "success",
        },
        {
            "doi": "10/d",
            "title": "d",
            "abstract": "abstract",
            "publisher_page_fetched_status": "success",
        },
        {
            "doi": "10/missing",
            "title": "missing",
            "abstract": "abstract",
            "publisher_page_fetched_status": "success",
        },
        {
            "doi": "10/json",
            "title": "json",
            "abstract": "abstract",
            "publisher_page_fetched_status": "success",
        },
        {
            "doi": "10/generic",
            "title": "generic",
            "abstract": "abstract",
            "publisher_page_fetched_status": "success",
        },
    ]

    class FakeDB:
        def __init__(self):
            self.actions = []

        def get_pendings(self, status):
            return rows

        def update_process_status(self, *args):
            self.actions.append(("skip", args))

        def update_llm_relevance(self, *args, **kwargs):
            self.actions.append(("relevance", args, kwargs))

        def update_relevance_screen(self, *args):
            self.actions.append(("screen", args))

        def update_relevance_screen_error(self, *args):
            self.actions.append(("error", args))

    class FakeChecker:
        def __init__(self, config):
            pass

        def build_default_prompt(self, title, abstract, doi=None):
            return doi

        def call_deepseek_api(self, prompt, config, breaker):
            if prompt == "10/good":
                return json.dumps(
                    {
                        "PredictedCategory": "B",
                        "MatchedSubfields": ["known", "Unknown!"],
                        "Confidence": "HIGH",
                        "Notes": "ok",
                    }
                )
            if prompt == "10/d":
                return json.dumps(
                    {
                        "PredictedCategory": "D",
                        "MatchedSubfields": [],
                        "Confidence": "medium",
                        "Notes": "reject",
                    }
                )
            if prompt == "10/missing":
                return json.dumps({"Notes": "bad shape"})
            if prompt == "10/json":
                return "not json"
            raise RuntimeError("generic")

    monkeypatch.setattr(phase_e, "PaperRelevanceChecker", FakeChecker)
    monkeypatch.setattr(
        phase_e, "load_keywords", lambda: {"scope_definition": {"known": {}}}
    )
    monkeypatch.setattr(phase_e.CFG, "SKIP_PHASE_E", False)
    monkeypatch.setattr(phase_e.CFG, "MAX_PAPERS_PER_PHASE", 0)
    monkeypatch.setattr(phase_e.CFG, "LLM_CONCURRENT_MAX", 5)
    monkeypatch.setattr(phase_e.CFG, "LLM_CIRCUIT_BREAKER_THRESHOLD", 10)
    monkeypatch.setattr(phase_e.CFG, "LLM_API_CONFIG_DICT_RELE", {})
    database = FakeDB()
    phase_e.phase_e_llm_relevance(database)
    kinds = {action[0] for action in database.actions}
    assert {"skip", "relevance", "screen", "error"} <= kinds


def test_phase_b_all_error_classes(monkeypatch):
    """Phase B records missing authors, not-found, HTTP and generic errors."""
    papers = [{"doi": f"10/p{i}"} for i in range(5)]

    class FakeClient:
        def __init__(self, **kwargs):
            self.index = 0

        def fetch_by_doi(self, doi):
            self.index += 1
            if self.index == 1:
                return SimpleNamespace(authors=[], title="", published="", abstract="")
            if self.index == 2:
                raise NotFoundError("not found")
            if self.index == 3:
                response = requests.Response()
                response.status_code = 429
                error = requests.HTTPError("rate limited", response=response)
                raise error
            if self.index == 4:
                response = requests.Response()
                response.status_code = 500
                raise requests.HTTPError("server error", response=response)
            raise RuntimeError("unexpected")

    class FakeDB:
        def __init__(self):
            self.errors = []
            self.partial_updates = []

        def get_pendings(self, status):
            return papers

        def update_error_message(self, *args):
            self.errors.append(args)

        def update_crossref_metadata(self, *args):
            self.partial_updates.append(args)

        def update_process_status(self, *args):
            raise AssertionError("all fake responses are error paths")

    monkeypatch.setattr(phase_b, "CrossrefClient", FakeClient)
    monkeypatch.setattr(phase_b.CFG, "SKIP_PHASE_B", False)
    monkeypatch.setattr(phase_b.CFG, "MAX_PAPERS_PER_PHASE", 0)
    database = FakeDB()
    phase_b.phase_b_crossref(database)
    assert len(database.errors) == 5
    assert len(database.partial_updates) == 1
    monkeypatch.setattr(phase_b.CFG, "SKIP_PHASE_B", True)
    assert phase_b.phase_b_crossref(database) is None


def test_phase_c_helpers_and_skip(monkeypatch):
    """Phase C's early skip path and parser helpers remain deterministic."""
    assert phase_c._extract_page_title(None) == ""
    assert phase_c._has_bot_markers("<html>cf-ray</html>")
    monkeypatch.setattr(phase_c.CFG, "SKIP_PHASE_C", True)
    assert phase_c.phase_c_publisher(SimpleNamespace(), []) is None


def test_phase_c_processes_success_skips_and_retries(monkeypatch):
    """Publisher phase exercises normal parsing, skips and final failure."""
    papers = [
        {"doi": "10/no-url", "page_url": "", "title": "no url", "publisher": "fake"},
        {
            "doi": "10/prefetch",
            "page_url": "prefetch",
            "title": "News: not research",
            "publisher": "fake",
        },
        {
            "doi": "10/accepted",
            "page_url": "accepted",
            "title": "accepted",
            "publisher": "fake",
        },
        {"doi": "10/non", "page_url": "non", "title": "non", "publisher": "fake"},
        {
            "doi": "10/success",
            "page_url": "success",
            "title": "success",
            "publisher": "fake",
        },
        {"doi": "10/empty", "page_url": "empty", "title": "empty", "publisher": "fake"},
        {"doi": "10/error", "page_url": "error", "title": "error", "publisher": "fake"},
    ]

    class FakeScraper:
        def __init__(self):
            self.html = ""
            self.page_url = ""
            self.current = ""

        def prewarm(self):
            raise RuntimeError("prewarm is optional")

        def fetch_page(self, url, timeout):
            self.current = url
            self.page_url = url
            if url == "error":
                self.html = "<title>captcha</title> cf-ray"
                raise RuntimeError("browser error")

        def parse_page(self):
            if self.current == "accepted":
                raise AcceptedPaperError("accepted")
            if self.current == "non":
                raise NonResearchPageError("non-research")
            if self.current == "empty":
                return Paper()
            return Paper(
                doi="10/success",
                title="A real paper",
                abstract="abstract",
                authors=["Alice"],
                pdf_url="https://example.test/a.pdf",
                date="2026",
            )

        def _save_error_html(self, url, name):
            return True

        def close(self):
            return None

    class FakeDB:
        def __init__(self):
            self.actions = []

        def get_papers_by_status(self, status, value):
            return []

        def get_pending_publisher_papers(self, publisher, skip_crossref_abstract=False):
            return papers

        def get_papers_by_status_and_publisher(self, *args):
            return papers

        def update_error_message(self, *args):
            self.actions.append(("error", args))

        def update_process_status(self, *args):
            self.actions.append(("status", args))

        def update_publisher_page(self, *args):
            self.actions.append(("success", args))

        def insert_skipped_doi(self, *args):
            self.actions.append(("skip", args))

        def delete_paper(self, *args):
            self.actions.append(("delete", args))

    monkeypatch.setattr(
        phase_c, "create_scraper", lambda *args, **kwargs: FakeScraper()
    )
    monkeypatch.setattr(phase_c, "SCRAPER_MAP", {"fake": (FakeScraper, None, None)})
    monkeypatch.setattr(phase_c.random, "uniform", lambda *args: 0)
    monkeypatch.setattr(phase_c.time, "sleep", lambda *args: None)
    monkeypatch.setattr(phase_c.CFG, "SKIP_PHASE_C", False)
    monkeypatch.setattr(phase_c.CFG, "MAX_PAPERS_PER_PHASE", 0)
    monkeypatch.setattr(phase_c.CFG, "PREFETCH_NON_RESEARCH", True)
    monkeypatch.setattr(phase_c.CFG, "POSTFETCH_NON_RESEARCH", False)
    monkeypatch.setattr(phase_c.CFG, "NON_RESEARCH_KEYWORDS", ["news:"])
    monkeypatch.setattr(phase_c.CFG, "PUBLISHER_FALLBACK_PROXY_URL", "")
    monkeypatch.setattr(phase_c.CFG, "PUBLISHER_MAX_CONSECUTIVE_FAILURES", 99)
    monkeypatch.setattr(phase_c.CFG, "PUBLISHER_PAGE_DELAY_MIN", 0)
    monkeypatch.setattr(phase_c.CFG, "PUBLISHER_PAGE_DELAY_MAX", 0)
    database = FakeDB()
    phase_c.phase_c_publisher(database, [{"publisher": "fake", "enabled": True}])
    kinds = {action[0] for action in database.actions}
    assert {"skip", "delete", "success", "error"} <= kinds


def test_phase_c_fallback_proxy_recovers(monkeypatch):
    """A configured fallback proxy can recover after normal attempts fail."""
    calls = []

    class FakeScraper:
        skip_phase_c_if_crossref_abstract = False

        def __init__(self, fallback=False):
            self.fallback = fallback
            self.html = "<title>captcha</title> cf-ray"
            self.page_url = "fallback"

        def prewarm(self):
            return None

        def fetch_page(self, url, timeout):
            if not self.fallback:
                raise RuntimeError("blocked")

        def parse_page(self):
            if not self.fallback:
                raise RuntimeError("blocked")
            return Paper(doi="10/fallback", title="ok", abstract="a")

        def close(self):
            return None

    def fake_create(_publisher, proxy_override=None):
        calls.append(proxy_override)
        return FakeScraper(fallback=proxy_override is not None)

    class FakeDB:
        def __init__(self):
            self.actions = []

        def get_papers_by_status(self, *args):
            return []

        def get_pending_publisher_papers(self, *args, **kwargs):
            return [
                {
                    "doi": "10/fallback",
                    "page_url": "u",
                    "title": "t",
                    "publisher": "fake",
                }
            ]

        def update_publisher_page(self, *args):
            self.actions.append(args)

        def update_error_message(self, *args):
            self.actions.append(args)

        def close(self):
            return None

    monkeypatch.setattr(phase_c, "create_scraper", fake_create)
    monkeypatch.setattr(phase_c, "SCRAPER_MAP", {"fake": (FakeScraper, None, None)})
    monkeypatch.setattr(phase_c.CFG, "SKIP_PHASE_C", False)
    monkeypatch.setattr(phase_c.CFG, "MAX_PAPERS_PER_PHASE", 0)
    monkeypatch.setattr(phase_c.CFG, "PREFETCH_NON_RESEARCH", False)
    monkeypatch.setattr(phase_c.CFG, "POSTFETCH_NON_RESEARCH", False)
    monkeypatch.setattr(phase_c.CFG, "PUBLISHER_FALLBACK_PROXY_URL", "http://proxy")
    monkeypatch.setattr(phase_c.CFG, "PUBLISHER_MAX_CONSECUTIVE_FAILURES", 3)
    monkeypatch.setattr(phase_c.random, "uniform", lambda *args: 0)
    monkeypatch.setattr(phase_c.time, "sleep", lambda *args: None)
    database = FakeDB()
    phase_c.phase_c_publisher(database, [{"publisher": "fake", "enabled": True}])
    assert calls == [None, {"server": "http://proxy"}, None]
    assert database.actions


def test_phase_e2_validation_and_early_exits(monkeypatch, tmp_path):
    """PDF signature validation and all admission early exits are covered."""
    valid = tmp_path / "valid.pdf"
    valid.write_bytes(b"%PDF-1.7 test")
    empty = tmp_path / "empty.pdf"
    empty.touch()
    invalid = tmp_path / "invalid.pdf"
    invalid.write_text("html", encoding="utf-8")
    assert phase_e2._is_valid_pdf_file(valid)
    assert not phase_e2._is_valid_pdf_file(empty)
    assert not phase_e2._is_valid_pdf_file(invalid)
    assert not phase_e2._is_valid_pdf_file(tmp_path / "missing.pdf")

    class EmptyDB:
        def get_relevance_screen_candidates(self, **kwargs):
            return []

    monkeypatch.setattr(phase_e2.CFG, "SKIP_PHASE_E2", True)
    assert phase_e2.phase_e2_mineru(EmptyDB()) is None
    monkeypatch.setattr(phase_e2.CFG, "SKIP_PHASE_E2", False)
    monkeypatch.setattr(phase_e2.CFG, "MINERU_TOKEN", "")
    assert phase_e2.phase_e2_mineru(EmptyDB()) is None
    monkeypatch.setattr(phase_e2.CFG, "MINERU_TOKEN", "token")
    assert phase_e2.phase_e2_mineru(EmptyDB()) is None


def test_phase_e2_download_parse_success_and_failures(monkeypatch, tmp_path):
    """E2 handles local PDFs, quota admission, invalid downloads and parser errors."""
    output_root = tmp_path / "mineru"
    session_root = tmp_path / "sessions"
    local_dir = output_root / "10_local"
    local_dir.mkdir(parents=True)
    (local_dir / "paper.pdf").write_bytes(b"%PDF-1.7 local")
    rows = [
        {
            "doi": "10/local",
            "publisher": "aps",
            "pdf_url": "",
            "page_url": "",
            "_quota_reserved": False,
        },
        {
            "doi": "10/no-url",
            "publisher": "aps",
            "pdf_url": "",
            "page_url": "",
            "_quota_reserved": False,
        },
        {
            "doi": "10/quota",
            "publisher": "aps",
            "pdf_url": "https://quota",
            "page_url": "u",
            "_quota_reserved": False,
        },
        {
            "doi": "10/good",
            "publisher": "aps",
            "pdf_url": "https://good",
            "page_url": "u",
            "_quota_reserved": False,
        },
        {
            "doi": "10/bad",
            "publisher": "aps",
            "pdf_url": "https://bad",
            "page_url": "u",
            "_quota_reserved": False,
        },
        {
            "doi": "10/parser",
            "publisher": "aps",
            "pdf_url": "https://parser",
            "page_url": "u",
            "_quota_reserved": False,
        },
    ]

    class FakeDB:
        def __init__(self):
            self.actions = []

        def get_relevance_screen_candidates(self, **kwargs):
            return rows

        def update_mineru_error(self, *args):
            self.actions.append(("error", args))

        def claim_fulltext_download(self, doi, *args):
            return doi != "10/quota"

        def finish_fulltext_download(self, *args):
            self.actions.append(("quota", args))

        def update_mineru_result(self, *args):
            self.actions.append(("success", args))

    class FakeDownloader:
        page = SimpleNamespace(wait_for_timeout=lambda self, _delay: None)

        def __init__(self, _directory):
            self.page = SimpleNamespace(wait_for_timeout=lambda _delay: None)

        def start_browser(self, proxy):
            return None

        def download_pdf(self, url, page_url=None):
            if url == "https://bad":
                return b"not-pdf"
            return b"%PDF-1.7 downloaded"

        def close(self):
            return None

    class FakeParser:
        def __init__(self, token):
            pass

        def parse_pdf(self, pdf_path, output_dir):
            if pdf_path.parent.name == "10_parser":
                raise RuntimeError("parse failed")
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "full.md").write_text("full", encoding="utf-8")
            return output_dir

    monkeypatch.setattr(phase_e2, "MINERU_OUTPUT_DIR", output_root)
    monkeypatch.setattr(phase_e2, "BROWSER_SESSION_DIR", session_root)
    monkeypatch.setattr(phase_e2, "BasePublisherScraper", FakeDownloader)
    monkeypatch.setattr(phase_e2, "MinerUParser", FakeParser)
    monkeypatch.setattr(
        phase_e2, "SCRAPER_MAP", {"aps": (FakeDownloader, session_root, None)}
    )
    monkeypatch.setattr(phase_e2.CFG, "SKIP_PHASE_E2", False)
    monkeypatch.setattr(phase_e2.CFG, "MINERU_TOKEN", "token")
    monkeypatch.setattr(phase_e2.CFG, "FULLTEXT_DOWNLOAD_DAILY_MAX", 10)
    monkeypatch.setattr(phase_e2.CFG, "FULLTEXT_DOWNLOAD_PUBLISHER_MAX", 10)
    monkeypatch.setattr(phase_e2.CFG, "FULLTEXT_DOWNLOAD_DELAY_MIN", 0)
    monkeypatch.setattr(phase_e2.CFG, "FULLTEXT_DOWNLOAD_DELAY_MAX", 0)
    monkeypatch.setattr(phase_e2.random, "uniform", lambda *args: 0)
    monkeypatch.setattr(phase_e2.time, "sleep", lambda *args: None)
    database = FakeDB()
    phase_e2.phase_e2_mineru(database)
    kinds = {action[0] for action in database.actions}
    assert "success" in kinds
    assert "error" in kinds


def test_phase_e3_evidence_normalisation_and_errors(monkeypatch, tmp_path):
    """Long evidence selection and E3 success/error persistence are covered."""
    long_text = "# Intro\n" + ("laser diagnostics conclusion " * 3000)
    evidence = phase_e3.build_relevance_evidence(
        long_text, max_chars=1000, evidence_terms=["plasma"]
    )
    assert len(evidence) == 1000
    assert "Intro" in evidence
    assert phase_e3._normalise_result(
        {
            "PredictedCategory": "x",
            "Confidence": "X",
            "MatchedSubfields": ["unknown"],
            "Notes": 3,
        },
        {"scope_definition": {"known": {}}},
    ) == ("D", "[]", "low", "3")

    fulltext_path = tmp_path / "x" / "full.md"
    fulltext_path.parent.mkdir()
    fulltext_path.write_text("laser full text", encoding="utf-8")
    rows = [
        {
            "doi": "10/success",
            "title": "A",
            "abstract": "a",
            "mineru_fulltext": "",
            "mineru_output_dir": "x",
            "llm_relevance_basis": None,
        },
        {
            "doi": "10/inline",
            "title": "B",
            "abstract": "b",
            "mineru_fulltext": "inline",
            "mineru_output_dir": "",
            "llm_relevance_basis": None,
        },
        {
            "doi": "10/done",
            "title": "C",
            "abstract": "c",
            "mineru_fulltext": "done",
            "mineru_output_dir": "",
            "llm_relevance_basis": "fulltext",
        },
        {
            "doi": "10/empty",
            "title": "D",
            "abstract": "d",
            "mineru_fulltext": "",
            "mineru_output_dir": "missing",
            "llm_relevance_basis": None,
        },
    ]

    class FakeDB:
        def __init__(self):
            self.updated = []

        def get_relevance_screen_candidates(self, **kwargs):
            return rows

        def update_llm_relevance(self, *args, **kwargs):
            self.updated.append(("ok", args, kwargs))

        def update_llm_relevance_error(self, *args):
            self.updated.append(("error", args))

    class FakeChecker:
        def __init__(self, config):
            self.config = config

        def build_fulltext_prompt(self, *args, **kwargs):
            return "prompt"

        def call_deepseek_api(self, prompt, config, breaker):
            if "" == prompt:
                raise AssertionError
            if not hasattr(self, "calls"):
                self.calls = 0
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "PredictedCategory": "A",
                        "MatchedSubfields": [],
                        "Confidence": "high",
                        "Notes": "ok",
                    }
                )
            raise LLMAPICallError("llm failed")

    monkeypatch.setattr(phase_e3, "DATA_DIR", tmp_path)
    monkeypatch.setattr(phase_e3, "load_keywords", lambda: {"scope_definition": {}})
    monkeypatch.setattr(phase_e3, "PaperRelevanceChecker", FakeChecker)
    monkeypatch.setattr(phase_e3.CFG, "SKIP_PHASE_E3", False)
    monkeypatch.setattr(phase_e3.CFG, "LLM_CONCURRENT_MAX", 2)
    monkeypatch.setattr(phase_e3.CFG, "FULLTEXT_RELEVANCE_MAX_CHARS", 1000)
    database = FakeDB()
    phase_e3.phase_e3_fulltext_relevance(database)
    assert {item[0] for item in database.updated} == {"ok", "error"}


def test_phase_f_summary_paths_and_formula_helper(monkeypatch, tmp_path):
    """Phase F covers summary validation, formula fixing and failures."""
    summary = {
        "one_sentence": "laser result",
        "motivation_and_goal": "goal",
        "key_setup_and_method": "method",
        "main_results_and_physics": "result",
        "limitations": [],
        "take_home_message": "take",
    }
    monkeypatch.setattr(
        phase_f,
        "FormulaFixer",
        lambda **kwargs: SimpleNamespace(fix_text=lambda text, **_: text + "!"),
    )
    fixed_json, fixed_count = phase_f._fix_summary_with_formula_fixer(
        summary, "10/x", {}, False, None
    )
    assert fixed_count >= 1
    assert "laser result!" in fixed_json

    fulltext = tmp_path / "full.md"
    fulltext.write_text("full text", encoding="utf-8")
    rows = [
        {
            "doi": "10/ok",
            "title": "ok",
            "llm_relevance_category": "A",
            "mineru_output_dir": "out",
        },
        {
            "doi": "10/skip",
            "title": "skip",
            "llm_relevance_category": "C",
            "mineru_output_dir": "out",
        },
        {
            "doi": "10/no-text",
            "title": "none",
            "llm_relevance_category": "B",
            "mineru_output_dir": "missing",
        },
    ]

    class FakeDB:
        def __init__(self):
            self.actions = []

        def get_pending_summary_papers(self, limit=None):
            return rows

        def update_llm_summary(self, *args):
            self.actions.append(("success", args))

        def update_llm_summary_error(self, *args):
            self.actions.append(("error", args))

    class FakeSummarizer:
        def __init__(self, **kwargs):
            pass

        def call_deepseek_api(self, article_text, prompt, breaker):
            return json.dumps(summary)

    monkeypatch.setattr(phase_f, "DATA_DIR", tmp_path)
    monkeypatch.setattr(phase_f, "DeepSeekPaperSummarizer", FakeSummarizer)
    monkeypatch.setattr(
        phase_f,
        "_fix_summary_with_formula_fixer",
        lambda *args: (json.dumps(summary), 0),
    )
    monkeypatch.setattr(
        phase_f, "load_keywords", lambda: {"scope_definition": {"laser": {}}}
    )
    monkeypatch.setattr(phase_f.CFG, "SKIP_PHASE_F", False)
    monkeypatch.setattr(phase_f.CFG, "SKIP_FORMULA_FIX", False)
    monkeypatch.setattr(phase_f.CFG, "FORCE_FORMULA_FIX", False)
    monkeypatch.setattr(phase_f.CFG, "LLM_CONCURRENT_MAX", 1)
    monkeypatch.setattr(phase_f.CFG, "FORMULA_FIX_CONCURRENT_MAX", 1)
    monkeypatch.setattr(phase_f.CFG, "LLM_CIRCUIT_BREAKER_THRESHOLD", 3)
    monkeypatch.setattr(phase_f.CFG, "LLM_API_CONFIG_DICT_SUMM", {})
    monkeypatch.setattr(phase_f.CFG, "LLM_API_CONFIG_DICT_FORMULA", {})
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "full.md").write_text("full", encoding="utf-8")
    database = FakeDB()
    phase_f.phase_f_llm_summary(database)
    assert any(action[0] == "success" for action in database.actions)
    assert any(action[0] == "error" for action in database.actions)


def test_phase_g_and_h_early_and_delivery_paths(monkeypatch, tmp_path):
    """Report generation and email delivery use isolated fake integrations."""

    class EmptyDB:
        def get_papers_for_report(self):
            return []

    monkeypatch.setattr(phase_g.CFG, "SKIP_PHASE_G", True)
    assert phase_g.phase_g_report(EmptyDB(), tmp_path / "a", tmp_path / "u") is None
    monkeypatch.setattr(phase_g.CFG, "SKIP_PHASE_G", False)
    assert phase_g.phase_g_report(EmptyDB(), tmp_path / "a", tmp_path / "u") is None

    template_dir = tmp_path / "email"
    template_dir.mkdir()
    monkeypatch.setattr(phase_h, "EMAIL_TEMPLATE_DIR", template_dir)
    assert (
        phase_h._render_email_template("missing", report_title="fallback") == "fallback"
    )
    (template_dir / "bad.html").write_text("{missing}", encoding="utf-8")
    assert phase_h._render_email_template("bad", report_title="fallback") == "fallback"
    (template_dir / "ok.html").write_text("Hello {name}", encoding="utf-8")
    assert phase_h._render_email_template("ok", name="world") == "Hello world"

    class NoopDB:
        def get_publisher_page_stats(self, days):
            return {}

    monkeypatch.setattr(phase_h.CFG, "SKIP_PHASE_H", True)
    assert phase_h.phase_h_email(NoopDB(), tmp_path) is None
    monkeypatch.setattr(phase_h.CFG, "SKIP_PHASE_H", False)
    monkeypatch.setattr(phase_h, "load_email_config", dict)
    assert phase_h.phase_h_email(NoopDB(), tmp_path) is None


def test_phase_g_auto_and_selected_report_paths(monkeypatch, tmp_path):
    """Both automatic and selected report outputs write canonical artifacts."""
    paper = {"doi": "10/report"}

    class Cursor:
        def fetchall(self):
            return [paper]

    class DB:
        conn = SimpleNamespace(execute=lambda self, *args: Cursor())

        def get_papers_for_report(self):
            return [paper]

        def mark_papers_reported(self, dois, timestamp):
            self.marked = (dois, timestamp)

    monkeypatch.setattr(phase_g.CFG, "SKIP_PHASE_G", False)
    monkeypatch.setattr(phase_g.CFG, "GENERATE_EXPLAINED_HTML", True)
    monkeypatch.setattr(phase_g, "DB_PATH", tmp_path / "db.sqlite")
    monkeypatch.setattr(phase_g, "PUBLIC_EXPORT_DIR", tmp_path / "public")
    monkeypatch.setattr(phase_g, "load_keywords", lambda: {"scope_definition": {}})
    monkeypatch.setattr(
        phase_g,
        "build_report_papers",
        lambda rows: [{"doi": "10/report", "title": "Paper"}],
    )
    monkeypatch.setattr(phase_g, "build_report_presentation", lambda scope, rows: {})
    monkeypatch.setattr(
        phase_g,
        "write_public_report",
        lambda path, *args, **kwargs: path.write_text("{}", encoding="utf-8"),
    )
    monkeypatch.setattr(phase_g, "generate_report", lambda *args, **kwargs: "# report")
    import processors.report_explainer as explainer_module

    monkeypatch.setattr(
        explainer_module,
        "write_explained_html",
        lambda db, path: path.write_text("html", encoding="utf-8"),
    )
    import tools.export_public_reports as export_module

    monkeypatch.setattr(export_module, "export_reports", lambda *args: 1)
    database = DB()
    phase_g.phase_g_report(database, tmp_path / "auto", tmp_path / "user")
    assert list((tmp_path / "auto").glob("*.md"))
    assert database.marked[0] == ["10/report"]
    phase_g.phase_g_report(
        database, tmp_path / "auto", tmp_path / "user", doi_list=["10/report"]
    )
    assert list((tmp_path / "user").glob("*.md"))


def test_phase_h_sends_report_and_no_update(monkeypatch, tmp_path):
    """Email phase renders metadata and covers both message variants."""
    sent = []

    class FakeSender:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def send(self, *args, **kwargs):
            sent.append((args, kwargs))

    class DB:
        def get_publisher_page_stats(self, days):
            return {
                "aps": {"failed": 3, "success": 1},
                "disabled": {"failed": 0, "success": 2},
            }

    config = {
        "username": "user@example.com",
        "password": "secret",
        "smtp_host": "smtp",
        "smtp_port": 25,
        "from_addr": "user@example.com",
    }
    monkeypatch.setattr(phase_h.CFG, "SKIP_PHASE_H", False)
    monkeypatch.setattr(phase_h.CFG, "EMAIL_TEMPLATE_NAME", "default")
    monkeypatch.setattr(phase_h.CFG, "PUBLISHER_MAX_CONSECUTIVE_FAILURES", 3)
    monkeypatch.setattr(phase_h, "load_email_config", lambda: config)
    monkeypatch.setattr(phase_h, "load_email_recipients", lambda: ["to@example.com"])
    monkeypatch.setattr(
        phase_h,
        "load_publishers",
        lambda: [
            {"id": "a", "name": "J", "publisher": "aps"},
            {"id": "b", "name": "J", "publisher": "aps"},
            {"id": "off", "enabled": False, "publisher": "disabled"},
        ],
    )
    monkeypatch.setattr(
        phase_h,
        "load_keywords",
        lambda: {
            "scope_definition": {"s": {"topics": ["laser — topic"]}},
            "keyword_catalog": [{"terms": ["<plasma>"]}],
        },
    )
    monkeypatch.setattr(phase_h, "build_scope_block", lambda *args, **kwargs: "<scope>")
    monkeypatch.setattr(phase_h, "EmailSender", FakeSender)
    report = tmp_path / "report.md"
    report.write_text("## Paper\n**DOI** 10/x\n", encoding="utf-8")
    phase_h.phase_h_email(DB(), tmp_path, report_path=report)
    assert sent and sent[-1][1]["attachments"] == [str(report)]
    sent.clear()
    phase_h.phase_h_email(DB(), tmp_path, report_path=None)
    assert sent and "No Updates" in sent[-1][0][0]
