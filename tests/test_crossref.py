"""
测试: CrossRef DOI 元数据 (crossref.py)

覆盖范围:
  - DOI 查询 (真实 API 调用)
  - JATS XML 摘要清洗 (TextClean)
  - PaperMetadata 数据类
  - date-parts 日期解析逻辑

注意: 所有测试需要网络连接，自动跳过如果无网络。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sources.crossref import CrossrefClient, PaperMetadata, NotFoundError


@pytest.fixture
def client():
    """创建 CrossRef 客户端实例。"""
    from config import CROSSREF_MAILTO
    return CrossrefClient(mailto=CROSSREF_MAILTO)


def test_text_clean_jats_xml():
    """JATS XML 标签应被移除，只保留纯文本。"""
    jats = '<jats:p>This is a <jats:italic>formula</jats:italic> description.</jats:p>'
    cleaned = CrossrefClient.TextClean(jats)
    assert "jats:p" not in cleaned
    assert "jats:italic" not in cleaned
    assert "formula" in cleaned


def test_text_clean_empty():
    """空文本清洗返回 None。"""
    assert CrossrefClient.TextClean("") is None
    assert CrossrefClient.TextClean(None) is None


def test_paper_metadata_dataclass():
    """PaperMetadata 数据类正确存储字段。"""
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


@pytest.mark.skip(reason="需要网络连接和 CrossRef API 访问")
def test_fetch_by_doi_open_access(client):
    """查询一篇 OA 论文的元数据。"""
    doi = "10.1364/OE.582177"  # 已知的 OA 论文
    meta = client.fetch_by_doi(doi)

    assert meta is not None
    assert meta.doi is not None
    assert meta.title is not None
    assert len(meta.authors) > 0


@pytest.mark.skip(reason="需要网络连接和 CrossRef API 访问")
def test_fetch_by_doi_non_oa(client):
    """查询一篇非 OA 论文 (可能无摘要)。"""
    doi = "10.1103/mw7c-8qy4"  # 已知的非 OA 论文
    meta = client.fetch_by_doi(doi)

    assert meta is not None
    assert meta.doi is not None
    # 非 OA 论文可能无摘要，但不影响其他元数据


@pytest.mark.skip(reason="需要网络连接和 CrossRef API 访问")
def test_fetch_by_doi_invalid(client):
    """查询无效 DOI 应抛出 NotFoundError。"""
    with pytest.raises(NotFoundError):
        client.fetch_by_doi("10.9999/this-does-not-exist-99999999")


def test_parse_work_date_parts():
    """验证 date-parts 解析逻辑。"""
    from datetime import datetime

    work = {
        "DOI": "10.0000/test",
        "published-online": {"date-parts": [[2025, 6, 15]]},
    }
    meta = CrossrefClient.parse_work(work)
    assert meta.published == "2025-06-15"


def test_parse_work_date_only_year():
    """只有年份时的日期解析。"""
    work = {
        "DOI": "10.0000/test",
        "published-print": {"date-parts": [[2025]]},
    }
    meta = CrossrefClient.parse_work(work)
    assert meta.published == "2025-00-00"


def test_parse_work_no_date():
    """无日期字段时不应崩溃。"""
    work = {"DOI": "10.0000/test"}
    meta = CrossrefClient.parse_work(work)
    assert meta.published is None
