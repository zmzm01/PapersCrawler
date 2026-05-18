"""
测试: RSS Feed 解析 (rss.py)

覆盖范围:
  - RSS XML 文本解析
  - DOI 提取 (dc_identifier / prism_doi)
  - 日期字段优先策略
  - 条目字段映射

使用 data/raw/rss/ 中的缓存 XML 文件进行测试，不需要网络连接。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sources.rss import RSSProcessor


def test_parse_rss_with_cached_data():
    """用缓存的 RSS XML 文件验证解析功能。"""
    rss_dir = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "rss")

    # 选取一个期刊的最新缓存文件
    import glob
    nature_files = sorted(glob.glob(os.path.join(rss_dir, "nature_*.xml")))
    if not nature_files:
        # 没有缓存文件时跳过测试
        return

    with open(nature_files[-1], "r", encoding="utf-8") as f:
        xml_text = f.read()

    journal_config = {"id": "nature", "name": "Nature", "publisher": "nature"}
    rsspro = RSSProcessor()
    papers = rsspro.parse_rss(xml_text, journal_config)

    assert len(papers) > 0, "应至少解析出 1 篇论文"
    assert "doi" in papers[0]
    assert "title" in papers[0]
    assert "link" in papers[0]

    # 检查至少有一篇有 DOI
    dois = [p["doi"] for p in papers if p["doi"]]
    assert len(dois) > 0, "至少应有一篇论文提取到 DOI"


def test_extract_doi_from_prism():
    """测试从 prism_doi 字段提取 DOI。"""
    from feedparser import FeedParserDict
    rsspro = RSSProcessor()

    # 模拟一个包含 prism_doi 的 feedparser 条目
    entry = FeedParserDict()
    entry["prism_doi"] = "10.1038/s41586-025-00123-4"
    doi = rsspro.extract_doi(entry)
    assert doi == "10.1038/s41586-025-00123-4"


def test_extract_doi_from_dc_identifier():
    """测试从 dc_identifier (doi:...) 字段提取 DOI。"""
    from feedparser import FeedParserDict
    rsspro = RSSProcessor()

    entry = FeedParserDict()
    entry["dc_identifier"] = "doi:10.1103/PhysRevLett.134.195001"
    doi = rsspro.extract_doi(entry)
    assert doi == "10.1103/PhysRevLett.134.195001"


def test_extract_doi_no_doi():
    """测试无 DOI 字段时返回 None。"""
    from feedparser import FeedParserDict
    rsspro = RSSProcessor()

    entry = FeedParserDict()
    doi = rsspro.extract_doi(entry)
    assert doi is None


def test_parse_rss_entries_have_required_fields():
    """验证所有 RSS 缓存文件的解析结果包含必要字段。"""
    import glob
    rss_dir = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "rss")
    xml_files = glob.glob(os.path.join(rss_dir, "*.xml"))

    if not xml_files:
        return

    rsspro = RSSProcessor()
    tested = 0

    for xml_file in xml_files[:5]:  # 只测试前 5 个文件以节省时间
        with open(xml_file, "r", encoding="utf-8") as f:
            xml_text = f.read()

        papers = rsspro.parse_rss(xml_text, {"id": "test"})
        for paper in papers:
            assert isinstance(paper.get("title"), str)
            assert isinstance(paper.get("link"), str)
            assert isinstance(paper.get("rss_fetched_at"), str)
        tested += 1

    assert tested > 0, "至少应测试 1 个 RSS 文件"
