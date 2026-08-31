"""OpenAlex singleton metadata client.

OpenAlex is used as a bounded fallback after Crossref.  The client only
performs DOI singleton lookups and never downloads files from OpenAlex.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote

import requests


@dataclass
class OpenAlexMetadata:
    """Normalized metadata returned by an OpenAlex Work lookup."""

    doi: str
    openalex_id: str | None = None
    title: str | None = None
    authors: list[dict] | None = None
    journal: str | None = None
    published: str | None = None
    abstract: str | None = None
    locations: list[dict] | None = None
    raw: dict[str, Any] | None = None


class OpenAlexNotFoundError(requests.RequestException):
    """Raised when OpenAlex has no Work for a DOI."""


class OpenAlexClient:
    """Query OpenAlex Works by DOI with conservative rate limiting.

    Parameters
    ----------
    api_key : str, optional
        Optional OpenAlex API key.
    timeout : float
        Request timeout in seconds.
    max_retries : int
        Number of attempts for transient failures.
    requests_per_second : float
        Global client rate limit.  Singleton lookups are cheap, but keeping
        this deliberately below the service limit prevents bursts.
    backoff_max_seconds : float
        Maximum exponential backoff delay.
    session : requests.Session, optional
        Injectable session for tests and callers with a custom route.
    """

    BASE_URL = "https://api.openalex.org/works/https://doi.org/"

    def __init__(self, api_key="", timeout=30, max_retries=3,
                 requests_per_second=8, backoff_max_seconds=30,
                 session=None):
        self.api_key = (api_key or "").strip()
        self.timeout = float(timeout)
        self.max_retries = max(1, int(max_retries))
        self.requests_per_second = max(0.1, float(requests_per_second))
        self.backoff_max_seconds = max(0.0, float(backoff_max_seconds))
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent", "PapersCrawler OpenAlex client"
        )
        self._rate_lock = threading.Lock()
        self._last_request_at = 0.0

    def close(self):
        """Close the underlying HTTP session."""
        if self.session is not None:
            self.session.close()
            self.session = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _wait_rate_limit(self):
        interval = 1.0 / self.requests_per_second
        with self._rate_lock:
            delay = interval - (time.monotonic() - self._last_request_at)
            if delay > 0:
                time.sleep(delay)
            self._last_request_at = time.monotonic()

    def fetch_by_doi(self, doi: str) -> OpenAlexMetadata:
        """Fetch and normalize one OpenAlex Work identified by DOI.

        Raises
        ------
        OpenAlexNotFoundError
            When OpenAlex returns HTTP 404.
        requests.RequestException
            After transient failures are exhausted.
        """
        clean_doi = (doi or "").strip()
        if not clean_doi:
            raise ValueError("DOI must not be empty")
        url = f"{self.BASE_URL}{quote(clean_doi, safe='/') }"
        params = {"api_key": self.api_key} if self.api_key else None
        for attempt in range(self.max_retries):
            try:
                self._wait_rate_limit()
                response = self.session.get(
                    url, params=params, timeout=self.timeout
                )
                if response.status_code == 404:
                    raise OpenAlexNotFoundError(f"DOI {doi} not found")
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return self.parse_work(response.json(), clean_doi)
            except OpenAlexNotFoundError:
                raise
            except requests.RequestException:
                if attempt >= self.max_retries - 1:
                    raise
                retry_after = 0.0
                response = locals().get("response")
                if response is not None:
                    try:
                        retry_after = float(response.headers.get("Retry-After", 0))
                    except (TypeError, ValueError):
                        retry_after = 0.0
                delay = min(
                    self.backoff_max_seconds,
                    max(retry_after, 2 ** attempt),
                )
                time.sleep(delay + random.uniform(0, min(0.25, delay / 4)))
        raise RuntimeError("unreachable")

    def fetch_many(self, dois, max_concurrency=4, return_errors=False):
        """Fetch several DOI singleton records with bounded concurrency.

        Parameters
        ----------
        dois : iterable of str
            DOI values to query.
        max_concurrency : int
            Maximum number of in-flight requests.
        return_errors : bool
            When true, also return a DOI-to-exception mapping. This lets the
            pipeline persist 404 separately from transient failures.

        Returns
        -------
        dict or tuple of dict
            DOI to metadata mapping. Failed lookups are omitted. If
            ``return_errors`` is true, returns ``(results, errors)``.
        """
        normalized = [str(doi).strip() for doi in dois if str(doi).strip()]
        results = {}
        errors = {}
        with ThreadPoolExecutor(max_workers=max(1, int(max_concurrency))) as pool:
            futures = {
                pool.submit(self.fetch_by_doi, doi): doi for doi in normalized
            }
            for future in as_completed(futures):
                doi = futures[future]
                try:
                    results[doi] = future.result()
                except Exception as error:
                    errors[doi] = error
        if return_errors:
            return results, errors
        return results

    @staticmethod
    def _rebuild_abstract(index):
        """Rebuild plain text from OpenAlex's inverted abstract index."""
        if not isinstance(index, dict):
            return None
        tokens = []
        for word, positions in index.items():
            if not isinstance(positions, list):
                continue
            tokens.extend((position, str(word)) for position in positions)
        if not tokens:
            return None
        tokens.sort(key=lambda pair: pair[0])
        return " ".join(word for _, word in tokens).strip() or None

    @classmethod
    def parse_work(cls, work: dict[str, Any], doi: str | None = None):
        """Convert an OpenAlex Work response into normalized metadata."""
        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        locations = []
        raw_locations = list(work.get("locations") or [])
        best_location = work.get("best_oa_location")
        if isinstance(best_location, dict):
            raw_locations.insert(0, best_location)
        for location in raw_locations:
            if not isinstance(location, dict):
                continue
            pdf_url = location.get("pdf_url")
            landing_url = location.get("landing_page_url")
            if not pdf_url and not landing_url:
                continue
            locations.append({
                "url": pdf_url or landing_url,
                "pdf_url": pdf_url,
                "landing_page_url": landing_url,
                "source": "openalex",
                "version": location.get("version"),
                "is_oa": bool(location.get("is_oa")),
                "license": location.get("license"),
            })
        authors = []
        for authorship in work.get("authorships") or []:
            author = authorship.get("author") or {}
            name = author.get("display_name")
            if name:
                authors.append({
                    "name": name,
                    "orcid": author.get("orcid"),
                })
        if not authors:
            authors = None
        publication_date = work.get("publication_date")
        return OpenAlexMetadata(
            doi=doi or work.get("doi") or "",
            openalex_id=work.get("id"),
            title=work.get("title") or None,
            authors=authors,
            journal=source.get("display_name") or None,
            published=publication_date or None,
            abstract=cls._rebuild_abstract(work.get("abstract_inverted_index")),
            locations=locations,
            raw=work,
        )
