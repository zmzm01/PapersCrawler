"""
测试: 出版商页面解析 (publisher.py)

覆盖范围:
  - 各出版社 HTML 解析逻辑
  - Paper 数据类
  - Cloudflare 防检测 JS 注入
  - 异常处理 (NonResearchPageError, PageParseError)

使用保存的 HTML 示例文件进行解析测试，不需要启动浏览器。
"""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sources.publisher import (
    Paper, BasePublisherScraper,
    NatureScraper, ScienceScraper, APSScraper,
    AIPScraper, IOPScraper, CambridgeScraper, OpticaScraper,
    NonResearchPageError, PageParseError,
)


def test_paper_dataclass():
    """验证 Paper 数据类默认值。"""
    paper = Paper()
    assert paper.doi is None
    assert paper.title is None
    assert paper.authors is None

    paper2 = Paper(doi="10.0000/test", title="Test")
    assert paper2.doi == "10.0000/test"


def test_base_scraper_requires_dir():
    """BasePublisherScraper 初始化时如果目录不存在应抛出 FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        BasePublisherScraper("/nonexistent/dir/for/test")


def test_scraper_parse_not_implemented():
    """基类的 parse_page 应抛出 NotImplementedError。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        scraper = BasePublisherScraper(tmpdir)
        with pytest.raises(NotImplementedError):
            scraper.parse_page()


# ---- HTML 解析测试 (离线) ----
# 这些测试构造最小的 HTML 片段来验证解析逻辑

def test_aps_scraper_meta_parsing():
    """验证 APS 解析器的 meta 标签提取。"""
    import tempfile
    html = """
    <html><head>
    <meta name="citation_title" content="Test Paper Title"/>
    <meta name="citation_date" content="2025-01-15"/>
    <meta name="citation_doi" content="10.1103/PhysRevLett.134.195001"/>
    <meta name="citation_journal_title" content="Physical Review Letters"/>
    <meta name="citation_author" content="Alice"/>
    <meta name="citation_author" content="Bob"/>
    <meta name="citation_pdf_url" content="https://example.com/pdf"/>
    <meta name="description" content="Short description"/>
    </head><body>
    <div id="abstract-section-content"><p>This is the abstract text.</p></div>
    </body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 保存 HTML 作为缓存文件
        html_path = os.path.join(tmpdir, "test.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = APSScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == "Test Paper Title"
        assert paper.date == "2025-01-15"
        assert paper.doi == "10.1103/PhysRevLett.134.195001"
        assert paper.journal == "Physical Review Letters"
        assert len(paper.authors) == 2
        assert "Alice" in paper.authors
        assert "Bob" in paper.authors
        assert paper.pdf_url == "https://example.com/pdf"
        assert "abstract" in paper.abstract.lower()


def test_cambridge_scraper_abstract_in_meta():
    """验证 Cambridge 解析器从 meta 标签提取摘要。"""
    import tempfile
    html = """
    <html><head>
    <meta name="citation_title" content="Cambridge Paper"/>
    <meta name="citation_doi" content="10.1017/hpl.2025.10090"/>
    <meta name="citation_abstract" content="This is the Cambridge abstract from meta tag."/>
    <meta name="citation_author" content="Author One"/>
    <meta name="citation_online_date" content="2025-03-01"/>
    <meta name="citation_journal_title" content="HPL"/>
    </head><body></body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "cambridge.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = CambridgeScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == "Cambridge Paper"
        assert paper.doi == "10.1017/hpl.2025.10090"
        assert "Cambridge abstract" in paper.abstract


def test_nature_scraper_no_dc_type_raises():
    """Nature 页面无 dc.type 应抛出 PageParseError。"""
    import tempfile
    html = "<html><head></head><body></body></html>"
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "nature.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = NatureScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        with pytest.raises(PageParseError):
            scraper.parse_page()


def test_nature_scraper_not_original_paper():
    """Nature 非 OriginalPaper 应抛出 NaturePageNotPaper。"""
    import tempfile
    html = '<html><head><meta name="dc.type" content="News"/></head><body></body></html>'
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "nature_news.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = NatureScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        with pytest.raises(NonResearchPageError):
            scraper.parse_page()


def test_science_scraper_type_check():
    """Science 页面 dc.Type 非 research-article 应报错。"""
    import tempfile
    html = '<html><head><meta name="dc.Type" content="editorial"/></head><body></body></html>'
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "science_editorial.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = ScienceScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        with pytest.raises(NonResearchPageError):
            scraper.parse_page()


def test_science_scraper_no_dc_type_with_og_type():
    """Science 页面无 dc.Type 但有 og:type → NonResearchPageError.

    Careers/Working Life 类文章没有 dc.Type meta，但有 og:type。
    说明页面正常加载但非研究文章。"""
    import tempfile
    html = """
    <html><head>
    <meta property="og:type" content="article"/>
    <meta property="og:title" content="I may not look like a professor"/>
    <meta name="dc.Title" content="I may not look like a professor"/>
    <meta name="dc.Identifier" scheme="doi" content="10.1126/science.aej3528"/>
    </head><body></body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "science_careers.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = ScienceScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        with pytest.raises(NonResearchPageError) as exc_info:
            scraper.parse_page()
        assert "og:type" in str(exc_info.value)


def test_science_scraper_no_dc_type_no_og_type():
    """Science 页面既无 dc.Type 也无 og:type → PageParseError.

    两样都没有说明页面结构可能已变化。"""
    import tempfile
    html = """
    <html><head>
    <title>Some page</title>
    </head><body></body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "science_no_meta.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = ScienceScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        with pytest.raises(PageParseError):
            scraper.parse_page()


def test_aps_scraper_cf_cdn_scripts_not_blocked():
    """APS 页面含 CF CDN 脚本但内容正常 → 解析成功（非误判为 bot）。

    这是 Bug 1 的回归测试：APS/AIP 页面可能包含 Cloudflare CDN
 脚本文件（含 challenge-platform、_cf_chl_opt 等标记），
    但只要页面有正常标题/DOI/摘要，就不应被误判为 bot 拦截。"""
    import tempfile
    html = """
    <html><head>
    <script src="/cdn-cgi/challenge-platform/scripts/jsd.js"></script>
    <meta name="citation_title" content="Valid APS Paper"/>
    <meta name="citation_date" content="2025-06-01"/>
    <meta name="citation_doi" content="10.1103/PhysRevLett.134.205001"/>
    <meta name="citation_journal_title" content="Physical Review Letters"/>
    <meta name="citation_author" content="Alice"/>
    <meta name="citation_pdf_url" content="https://example.com/paper.pdf"/>
    </head><body>
    <div id="abstract-section-content"><p>This paper studies laser-plasma interaction.</p></div>
    </body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "aps_cf_cdn.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = APSScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == "Valid APS Paper"
        assert paper.doi == "10.1103/PhysRevLett.134.205001"
        assert "laser-plasma" in (paper.abstract or "")


def test_aip_scraper_parse():
    """验证 AIP 解析器正确提取元数据。"""
    import tempfile
    html = """
    <html><head>
    <meta name="citation_title" content="AIP Paper"/>
    <meta name="citation_doi" content="10.1063/5.0000123"/>
    <meta name="citation_journal_title" content="Applied Physics Letters"/>
    <meta name="citation_author" content="First Author"/>
    <meta name="publish_date" content="2025-04-01"/>
    </head><body>
    <section class="abstract" aria-label="Main abstract">AIP abstract text here.</section>
    </body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "aip.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = AIPScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == "AIP Paper"
        assert paper.doi == "10.1063/5.0000123"
        assert "AIP abstract" in paper.abstract


def test_iop_scraper_parse():
    """验证 IOP 解析器正确提取元数据。"""
    import tempfile
    html = """
    <html><head>
    <meta name="citation_title" content="IOP Paper"/>
    <meta name="citation_doi" content="10.1088/1361-6587/ae5adb"/>
    <meta name="citation_online_date" content="2025-02-15"/>
    </head><body>
    <div class="article-abstract"><div class="article-text">IOP abstract content.</div></div>
    </body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "iop.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = IOPScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == "IOP Paper"
        assert "IOP abstract" in paper.abstract


def test_optica_scraper_parse():
    """验证 Optica 解析器正确提取元数据。"""
    import tempfile
    html = """
    <html><head>
    <meta name="citation_title" content="Optica Paper"/>
    <meta name="citation_doi" content="10.1364/OPTICA.12345"/>
    <meta name="citation_online_date" content="2025-05-01"/>
    </head><body>
    <div id="articleBody">
    <h2 id="Abstract">Abstract</h2>
    <div>Optica abstract content goes here.</div>
    </div>
    </body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "optica.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = OpticaScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == "Optica Paper"
        assert "Optica abstract" in paper.abstract
