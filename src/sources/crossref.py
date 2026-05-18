"""
crossref.py
负责根据 DOI 通过 CrossRef REST API 获取文章元数据
https://api.crossref.org/swagger-ui/index.html
"""

import time
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup


# 自定义异常：表示资源不存在（404）
class NotFoundError(requests.RequestException):
    """Raised when the requested resource returns 404."""
    pass

# =========================================================
# Data Models
# =========================================================


@dataclass
class PaperMetadata:
    doi: str
    title: str | None = None
    authors: list[dict] | None = None
    journal: str | None = None
    publisher: str | None = None
    published: int | None = None
    abstract: str | None = None
    url: str | None = None
    raw: dict[str, Any] | None = None


# =========================================================
# Crossref Client
# =========================================================


class CrossrefClient:
    """
    Crossref DOI metadata fetcher
    """

    BASE_URL = "https://api.crossref.org"

    def __init__(self, mailto: str, timeout: int = 30, max_retries: int = 3):
        """
        Initialization

        Args:
            mailto: Your contact email (Crossref strongly recommends this)
            timeout: Request timeout seconds.
            max_retries: Retry count.
        ---
        """

        self.mailto = mailto
        self.timeout = timeout
        self.max_retries = max_retries

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    f"PaperCrawler " f"(mailto:{mailto}) " f"Python requests"
                ),
                "Accept": "application/json",
            }
        )

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def fetch_by_doi(self, doi: str) -> PaperMetadata | None:
        """
        Fetch metadata from Crossref using DOI.

        Args:
            doi: the doi of paper. Must be a standard DOI (not http(s) link).
        Returns:
            PaperMetadata: self-defined PaperMetadata dataclass
        Raise:
            NotFoundError: CrossRef cannot find metadata, perhaps the DOI is FAKE.
        ---
        """

        # 构造请求 url
        url = f"{self.BASE_URL}/works/{doi}"

        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout)

                # 遇到 404 立即抛出自定义异常
                if response.status_code == 404:
                    raise NotFoundError(f"DOI {doi} not found (404)")
                
                # 其他 4xx/5xx 会触发 raise_for_status
                response.raise_for_status()
                data = response.json()

                # 调试用
                # import json
                # with open("crossref_respon.json", "w", encoding="utf-8") as f:
                #     json.dump(data, f, ensure_ascii=False, indent=2)

                return self.parse_work(data["message"])

            except requests.RequestException as e:
                # 如果是 NotFoundError，不要重试，直接向上抛出
                if isinstance(e, NotFoundError):
                    raise e
                # 其他请求异常（超时、连接错误、5xx等）进行重试
                if attempt == self.max_retries - 1:
                    raise e

                time.sleep(2**attempt)

        return None

    # ---------------------------------------------------------
    # Clean the abstract
    # ---------------------------------------------------------
    @staticmethod
    def TextClean(abstract: str | None) -> str | None:
        """
        Clean the text due to CrossRef's title/abstract always contains some JATS XML fragment.

        Args:
            abstract
        Returns:
            cleaned text
        ---
        """

        if not abstract:
            return None

        soup = BeautifulSoup(abstract, "lxml")
        text = soup.get_text(" ")
        text = " ".join(text.split())

        return text

    # ---------------------------------------------------------
    # Metadata parsing
    # ---------------------------------------------------------
    @staticmethod
    def parse_work(work: dict[str, Any]) -> PaperMetadata:
        """
        Convert Crossref raw response into normalized metadata schema.

        Args:
            work: the "message" part CrossRef return.
        Returns:
            PaperMetadata class
        ---
        """
        # title
        title = None
        if work.get("title"):
            title = CrossrefClient.TextClean(work["title"][0])

        # journal
        journal = None
        if work.get("container-title"):
            journal = work["container-title"][0]

        # published
        published_date = None
        published = (
            work.get("published-online")
            or work.get("published-print")
            or work.get("created")
        )  # CrossRef 提供多个日期，注意选择

        if published:
            date_parts = published.get("date-parts", [])
            if date_parts and len(date_parts[0]) > 0:
                parts = date_parts[0]
                year = parts[0]
                month = parts[1] if len(parts) > 1 and parts[1] else 0
                day = parts[2] if len(parts) > 2 and parts[2] else 0
                published_date = f"{year:04d}-{month:02d}-{day:02d}"

        # authors
        authors = []
        for author in work.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            full_name = (f"{given} {family}").strip()
            authors.append({"name": full_name, "orcid": author.get("ORCID")})

        # abstract
        abstract = CrossrefClient.TextClean(work.get("abstract"))

        # build PaperMetadata
        return PaperMetadata(
            doi=work.get("DOI"),
            title=title,
            authors=authors,
            abstract=abstract,
            journal=journal,
            publisher=work.get("publisher"),
            published=published_date,
            url=work.get("URL"),
            raw=work,
        )


if __name__ == "__main__":
    # 测试
    doi_OA = "10.1364/OE.582177"
    doi_NOA = "10.1103/mw7c-8qy4"

    client = CrossrefClient(mailto="czmczm01@qq.com")

    paper = client.fetch_by_doi(doi_OA)
    print("=" * 30)
    print("Open Access paper TEST")
    print(paper.title)
    print(paper.doi)
    print(paper.url)
    print(paper.authors)
    print(paper.published)
    print(paper.publisher)
    print(paper.journal)
    print(paper.abstract)

    print("=" * 30)
    print("Non Open Access paper TEST")
    paper = client.fetch_by_doi(doi_NOA)
    print(paper.title)
    print(paper.doi)
    print(paper.url)
    print(paper.authors)
    print(paper.published)
    print(paper.publisher)
    print(paper.journal)
    print(paper.abstract)
