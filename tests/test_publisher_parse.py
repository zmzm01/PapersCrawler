"""
测试: 出版商页面解析 (publisher.py)

覆盖范围:
  - 各出版社 HTML 解析逻辑
  - Paper 数据类
  - 异常处理 (NonResearchPageError, PageParseError)
  - Science 多段摘要拼接、Nature JSON-LD 边界、IOP docstring、
    Cambridge 伪摘要正则等回归项

使用保存的 HTML 示例文件进行解析测试，不需要启动浏览器。
"""

import os
import sys
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


def test_cambridge_scraper_abstract_url_rejected():
    """验证 Cambridge citation_abstract 为 URL/图片链接时被拒绝置空。

    复现 20260713 报告缺陷：部分 Cambridge 文章的 citation_abstract 标签内容
    是首页 PDF 图片链接（如 //static.cambridge.org/content/id/.../firstPage-pdf-xxx.jpg），
    而非摘要文本。应被 _validate_cambridge_abstract 识别并置空。
    """
    import tempfile
    html = """
    <html><head>
    <meta name="citation_title" content="Cambridge Paper"/>
    <meta name="citation_doi" content="10.1017/hpl.2026.10180"/>
    <meta name="citation_abstract" content="//static.cambridge.org/content/id/urn:cambridge.org:id:article:hpl202610180/firstPage-pdf-001.jpg"/>
    <meta name="citation_author" content="Author One"/>
    <meta name="citation_online_date" content="2026-07-01"/>
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
        # URL 形式的伪摘要应被置空，而非原样保留
        assert paper.abstract == ""
        assert "static.cambridge.org" not in paper.abstract


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


def test_iop_scraper_decodes_encoded_carriage_returns():
    """Regression test for the ae81e4-style literal ``&#xD;`` abstract text."""
    import tempfile
    html = """
    <html><head>
    <meta name="citation_title" content="IOP Paper"/>
    <meta name="citation_doi" content="10.1088/1361-6587/ae81e4"/>
    </head><body>
    <div class="article-abstract"><div class="article-text">
      first&#xD;second &amp; third&#xD;particlein-&#xD;cell
    </div></div>
    </body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "iop_encoded.html")
        with open(html_path, "w") as file:
            file.write(html)
        scraper = IOPScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()
        assert paper.abstract == "first second & third particlein-cell"


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


# ---------------------------------------------------------------------------
# 回归测试（2026-07-31 review 修复项）
# ---------------------------------------------------------------------------

def test_science_scraper_multiple_abstract_paragraphs():
    """Science 多段摘要应全部拼接（回归 #1）。

    此前用 XPath string() 作用于节点集，只取第一个 div[role="paragraph"]，
    导致多段摘要丢失；改用 //text() 后应保留所有段落。
    """
    import tempfile
    html = """
    <html><head>
    <meta name="dc.Type" content="research-article"/>
    <meta name="dc.Title" content="Multi-paragraph Science Paper"/>
    <meta name="dc.Identifier" scheme="doi" content="10.1126/science.adx0001"/>
    </head><body>
    <section id="abstract">
    <div role="paragraph"><p>First paragraph of the abstract.</p></div>
    <div role="paragraph"><p>Second paragraph of the abstract.</p></div>
    </section>
    </body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "science_multi.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = ScienceScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert "First paragraph" in paper.abstract
        assert "Second paragraph" in paper.abstract


def test_nature_jsonld_author_single_dict_and_null_date():
    """Nature JSON-LD: author 为单个 dict 且 datePublished 为 null 时不崩溃（回归 #2）。"""
    import tempfile
    html = """
    <html><head>
    <meta name="dc.type" content="OriginalPaper"/>
    <script type="application/ld+json">
    {"mainEntity": {"headline": "JSON-LD Title", "author": {"name": "Single Author"}, "datePublished": null}}
    </script>
    </head><body></body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "nature_jsonld_single.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = NatureScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == "JSON-LD Title"
        assert paper.authors == ["Single Author"]


def test_nature_jsonld_mainentity_list():
    """Nature JSON-LD: mainEntity 为列表时取首个且不崩溃（回归 #2）。"""
    import tempfile
    html = """
    <html><head>
    <meta name="dc.type" content="OriginalPaper"/>
    <script type="application/ld+json">
    {"mainEntity": [{"headline": "First Entity", "author": [{"name": "A"}], "datePublished": "2026-05-19T00:00:00Z"}, {"headline": "Second Entity"}], "@graph": []}
    </script>
    </head><body></body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "nature_jsonld_list.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = NatureScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == "First Entity"
        assert paper.authors == ["A"]


def test_nature_jsonld_root_list():
    """Nature JSON-LD: 根节点为列表时不崩溃（回归 #2）。"""
    import tempfile
    html = """
    <html><head>
    <meta name="dc.type" content="OriginalPaper"/>
    <script type="application/ld+json">
    [{"mainEntity": {"headline": "Entity in Root List"}}]
    </script>
    </head><body></body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "nature_jsonld_root.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = NatureScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == ""


def test_nature_jsonld_invalid_json():
    """Nature JSON-LD: 非法 JSON 时不崩溃（回归 #2）。"""
    import tempfile
    html = """
    <html><head>
    <meta name="dc.type" content="OriginalPaper"/>
    <script type="application/ld+json">
    { not valid json
    </script>
    </head><body></body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "nature_jsonld_bad.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = NatureScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert paper.title == ""


def test_iop_scraper_docstring_present():
    """IOP 类 docstring 应存在（回归 #3）。

    此前 http_fallback_* 类属性写在 docstring 之前，导致 __doc__ 为 None。
    """
    from sources.publisher import IOPScraper as _IOP
    assert _IOP.__doc__ is not None
    assert "IOP" in _IOP.__doc__


def test_cambridge_abstract_ending_with_pdf_kept():
    """Cambridge 摘要正文以 .pdf 结尾时应保留（回归 #4）。

    此前扩展名正则未锚定开头，合法摘要会被误判为伪摘要置空。
    """
    import tempfile
    html = """
    <html><head>
    <meta name="citation_title" content="Cambridge Paper"/>
    <meta name="citation_doi" content="10.1017/hpl.2026.10181"/>
    <meta name="citation_abstract" content="We analyze the setup, full details are in supplementary file S1.pdf"/>
    <meta name="citation_author" content="Author One"/>
    <meta name="citation_online_date" content="2026-07-01"/>
    <meta name="citation_journal_title" content="HPL"/>
    </head><body></body></html>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "cambridge_pdf_end.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = CambridgeScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        paper = scraper.parse_page()

        assert "supplementary file S1.pdf" in paper.abstract


def test_cambridge_abstract_pure_url_still_rejected():
    """Cambridge 整段为图片 URL 的伪摘要仍应被置空（回归 #4 保持原有行为）。"""
    assert CambridgeScraper._ABSTRACT_URL_PATTERN.search(
        "//static.cambridge.org/content/id/x/firstPage-pdf-001.jpg"
    )
    assert not CambridgeScraper._ABSTRACT_URL_PATTERN.search(
        "We study the plasma wakefield in detail."
    )


def test_fetch_page_both_none_raises():
    """fetch_page url 与 html_path 均为 None 时应抛出 ValueError（回归 #7）。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        scraper = BasePublisherScraper(tmpdir)
        with pytest.raises(ValueError, match="不能同时为空"):
            scraper.fetch_page()


def test_save_page_offline_uses_self_html():
    """离线模式下 save_page 应读取 self.html，而不是 self.page.content()（回归 #8）。"""
    import tempfile
    html = "<html><head><title>Offline</title></head><body>Hello</body></html>"
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "src.html")
        with open(html_path, "w") as f:
            f.write(html)

        scraper = BasePublisherScraper(tmpdir)
        scraper.fetch_page(html_path=html_path)
        assert scraper.page is None  # 离线模式未启动浏览器

        out_path = os.path.join(tmpdir, "out.html")
        scraper.save_page(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            assert f.read() == html
