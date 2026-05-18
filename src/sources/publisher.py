import re
import json
from pathlib import Path

from parsel import Selector
from playwright.sync_api import sync_playwright

from dataclasses import dataclass, field
from typing import List


# 定义 dataclass
@dataclass
class Paper:
    doi: str | None = None
    title: str | None = None
    date: str | None = None
    journal: str | None = None
    abstract: str | None = None
    authors: List[str] | None = None
    pdf_url: str | None = None
    url: str | None = None  # canonical url


class BasePublisherScraper:
    def __init__(self, user_data_dir):
        """
        Initialization

        Args:
            user_data_dir: dir to store session cache.
        Raise:
            FileNotFoundError: if user_data_dir does not exist.
        ---
        """
        user_data_dir = Path(user_data_dir)
        if not user_data_dir.is_dir():
            raise FileNotFoundError(f"dir {user_data_dir} does not exist.")

        self.user_data_dir = user_data_dir
        self.context = None
        self.page = None

    def start_browser(self, proxy=None):
        """
        Start the browser (Scraper will REUSER the browser and page for each publisher)
        Scraper default start chromium browser.
        ---
        """
        self.pw = sync_playwright().start()
        self.context = self.pw.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            proxy=proxy,
        )
        self.page = self.context.new_page()
        # 注入防检测 JS
        self.page.evaluate("""
        () => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        }
        """)

        # self.page.goto("https://bot.sannysoft.com/", timeout=120000)

    def fetch_page(self, url=None, html_path=None, timeout=5000):
        """
        获取页面 html ，统一等待 5s 过 CF Challenge

        Args:
            url: 如果提供 url 则通过浏览器抓取页面
            html_path: 如果已经抓取过页面，则通过保存的 html 页面直接解析
            timeout: 页面等待时间（ms）
        Raise:
            PageParseError: 如果提供了 html_path 但文件不存在
        ---
        """
        if url:
            self.page.goto(url, wait_until="domcontentloaded", timeout=120000)
            # TODO: 这里等待机制可以优化
            self.page.wait_for_timeout(timeout)  # 给 CF Challenge 5s 的时间
            self.html = self.page.content()
        elif html_path:
            html_path = Path(html_path)
            if not html_path.exists():
                raise PageParseError(f"HTML file {html_path} does not exist.")
            with open(html_path, "r", encoding="utf-8") as f:
                self.html = f.read()

    def parse_page(self):
        raise NotImplementedError("parse_page method is defined by each child class.")

    def save_page(self, path):
        """
        Save page.content(), for debugging or something else.

        Args:
            path: str
        ---
        """
        html = self.page.content()
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    def close(self):
        self.context.close()
        self.pw.stop()


# 定义错误类
class PageParseError(Exception):
    pass


class NaturePageNotPaper(Exception):
    """表示找到的 Nature page 不是正常的 paper"""

    pass


# APS 解析器
class APSScraper(BasePublisherScraper):
    def parse_page(self):
        """
        专为 APS paper 设计的 page 解析器

        Returns:
            Paper: 自定义的 Paper dataclass
        ---
        """
        sel = Selector(text=self.html)

        # metadata
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        date = sel.css('meta[name="citation_date"]::attr(content)').get() or ""
        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        pdf_url = (
            sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""
        )  # 这里的 pdf_url 会面临重定向且需要 access 才能真正下载

        description = (
            sel.css('meta[name="description"]::attr(content)').get() or ""
        )  # 应该是 APS 提供的简短描述

        # 仅获取摘要判断相关性
        paragraphs = sel.css("#abstract-section-content p::text").getall()
        paragraphs = [
            p.strip() for p in paragraphs if p.strip()
        ]  # 此处是担心 abstract 有多段，但是物理期刊一般不可能吧？
        abstract = " ".join(paragraphs)

        # 通过 MathJAX 渲染的数学公式非常恶心，无法直接拿到源码，因此放弃直接从 HTML 页面抓全文

        return Paper(
            doi=doi,
            date=date,
            journal=journal,
            title=title,
            abstract=abstract,
            authors=authors,
            pdf_url=pdf_url,
        )


class NatureScraper(BasePublisherScraper):
    def parse_page(self):
        """
        专为 Nature paper 设计的 page 解析器
        仅处理标准的文章（dc.type 为 OriginalPaper），不处理 News/Podcast/...

        Returns:
            Paper: 自定义的 Paper dataclass
        ---
        """
        sel = Selector(text=self.html)

        # 找元数据 dc.type 判断是不是正常文章
        dctype = sel.css('meta[name="dc.type"]::attr(content)').get() or ""
        if not dctype == "OriginalPaper":
            raise NaturePageNotPaper("This Nature page is not OriginalPaper.")
        elif dctype == "":
            raise PageParseError(
                "Get no dc.type in Nature page, maybe the page structure has been modified."
            )

        # 找 pdf url
        # nature 中给出类似 /articles/s41567-026-03184-9.pdf 的格式
        pdf_url_part = sel.css('a[data-test="download-pdf"]::attr(href)').get() or ""
        if pdf_url_part:
            # 如果找到则拼接
            pdf_url = "https://www.nature.com" + pdf_url_part
        else:
            pdf_url = None

        # Nature 可以找 JSON-LD
        json_ld_text = sel.css('script[type="application/ld+json"]::text').get()
        data = json.loads(json_ld_text).get("mainEntity")
        if json_ld_text:
            title = data.get("headline", "")
            abstract = data.get("description", "")
            keywords = data.get("keywords", [])  # Nature 还提供了关键词
            authors = [a["name"] for a in data.get("author", [])]

        # 通过正文而非 JSON-LD 抓取的 Abstract, 后者好像会混入一些奇怪的话
        paragraphs = sel.css("#Abs1-content *::text").getall()
        paragraphs = [
            p.strip() for p in paragraphs if p.strip()
        ]  # 此处是担心 abstract 有多段，但是物理期刊一般不可能吧？
        abstract_article = " ".join(paragraphs)
        if abstract_article:
            abstract = abstract_article

        # Nature 的正文就直接包含了 MathJAX 的原始公式，可以直接从 Page 中提取全文
        # Nature 的 Page 写得是相当清晰的

        return Paper(title=title, abstract=abstract, authors=authors, pdf_url=pdf_url)


class ScienceScraper(BasePublisherScraper):
    def parse_page(self):
        """
        专为 Science paper 设计的 page 解析器
        会在最开始检查 dc.Type ，非 research-article 的页面跳过

        Returns:
            Paper: 自定义的 Paper dataclass
        ---
        """
        sel = Selector(text=self.html)

        # 找元数据 dc.type 判断是不是正常文章
        dctype = sel.css('meta[name="dc.Type"]::attr(content)').get() or ""
        if not dctype == "research-article":
            raise NaturePageNotPaper("This Science page is not research-article.")
        elif dctype == "":
            raise PageParseError(
                "Get no dc.type in Nature page, maybe the page structure has been modified."
            )

        # metadata
        title = sel.css('meta[name="dc.Title"]::attr(content)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="dc.Creator"]::attr(content)').getall()
        date = sel.css('meta[name="dc.Date"]::attr(content)').get() or ""
        doi = (
            sel.css('meta[name="dc.Identifier"][scheme="doi"]::attr(content)').get()
            or ""
        )

        pdf_url_part = sel.css('a[href*="download=true"]::attr(href)').get()
        if pdf_url_part:
            pdf_url = "https://www.science.org" + pdf_url_part
        else:
            pdf_url = None

        # 仅获取摘要判断相关性
        abstract = (
            sel.xpath('string(//section[@id="abstract"]//div[@role="paragraph"])').get()
            or ""
        )
        abstract = (
            re.sub(r"\s+", " ", abstract).strip() if abstract else ""
        )  # 清理不可见字符

        # Science 正文好像还挺好抓

        return Paper(
            doi=doi,
            date=date,
            journal=journal,
            title=title,
            abstract=abstract,
            authors=authors,
            pdf_url=pdf_url,
        )


class CambridgeScraper(BasePublisherScraper):
    def parse_page(self):
        """
        专为 Cambridge paper 设计的 page 解析器

        Returns:
            Paper: 自定义的 Paper dataclass
        ---
        """
        sel = Selector(text=self.html)

        # metadata
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        canonical_url = sel.css('link[rel="canonical"]::attr(href)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        date = sel.css('meta[name="citation_online_date"]::attr(content)').get() or ""

        keywords_str = sel.css('meta[name="citation_keywords"]::attr(content)').get()
        if keywords_str:
            # 最后一个 if item.strip() 用于过滤末尾可能出现的一个单独 ; 导致的空字符串
            keywords_str = [
                item.strip() for item in keywords_str.split(";") if item.strip()
            ]

        pdf_url = sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""

        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""

        # 仅获取摘要判断相关性
        # 非常好的 Cambridge 将 abstract 写在 metadata 里！
        abstract = sel.css('meta[name="citation_abstract"]::attr(content)').get() or ""

        return Paper(
            doi=doi,
            url=canonical_url,
            date=date,
            journal=journal,
            title=title,
            abstract=abstract,
            authors=authors,
            pdf_url=pdf_url,
        )


class AIPScraper(BasePublisherScraper):
    def parse_page(self):
        """
        专为 AIP paper 设计的 page 解析器

        Returns:
            Paper: 自定义的 Paper dataclass
        ---
        """
        sel = Selector(text=self.html)

        # metadata
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        canonical_url = sel.css('link[rel="canonical"]::attr(href)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        date = sel.css('meta[name="publish_date"]::attr(content)').get() or ""

        pdf_url = sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""

        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""

        # 仅获取摘要判断相关性
        abstract = (
            sel.xpath(
                'string(//section[@class="abstract"][@aria-label="Main abstract"])'
            ).get()
            or ""
        )
        abstract = (
            re.sub(r"\s+", " ", abstract).strip() if abstract else ""
        )  # 清理不可见字符

        return Paper(
            doi=doi,
            url=canonical_url,
            date=date,
            journal=journal,
            title=title,
            abstract=abstract,
            authors=authors,
            pdf_url=pdf_url,
        )


class IOPScraper(BasePublisherScraper):
    def parse_page(self):
        """
        专为 IOP paper 设计的 page 解析器

        Returns:
            Paper: 自定义的 Paper dataclass
        ---
        """
        sel = Selector(text=self.html)

        # metadata
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        canonical_url = sel.css('link[rel="canonical"]::attr(href)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        date = sel.css('meta[name="citation_online_date"]::attr(content)').get() or ""

        pdf_url = sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""

        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""

        # 仅获取摘要判断相关性
        abstract = (
            sel.xpath(
                'string(//div[@class="article-abstract"]//div[contains(@class, "article-text")])'
            ).get()
            or ""
        )
        abstract = (
            re.sub(r"\s+", " ", abstract).strip() if abstract else ""
        )  # 清理不可见字符

        return Paper(
            doi=doi,
            url=canonical_url,
            date=date,
            journal=journal,
            title=title,
            abstract=abstract,
            authors=authors,
            pdf_url=pdf_url,
        )


class OpticaScraper(BasePublisherScraper):
    def parse_page(self):
        """
        专为 Optica paper 设计的 page 解析器

        Returns:
            Paper: 自定义的 Paper dataclass
        ---
        """
        sel = Selector(text=self.html)

        # metadata
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        date = sel.css('meta[name="citation_online_date"]::attr(content)').get() or ""

        pdf_url = sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""

        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""

        # 仅获取摘要判断相关性
        abstract = abstract = (
            sel.xpath(
                'string(//div[@id="articleBody"]/h2[@id="Abstract"]/following-sibling::div[1])'
            ).get()
            or ""
        )
        abstract = (
            re.sub(r"\s+", " ", abstract).strip() if abstract else ""
        )  # 清理不可见字符

        return Paper(
            doi=doi,
            date=date,
            journal=journal,
            title=title,
            abstract=abstract,
            authors=authors,
            pdf_url=pdf_url,
        )


if __name__ == "__main__":
    from pprint import pprint

    # Nature 测试
    # url = "https://www.nature.com/articles/s41567-026-03184-9" # OriginalPaper
    # url = "https://www.nature.com/articles/d41586-026-01575-9" # podcast
    # url = "https://www.nature.com/articles/d41586-026-01504-w" # highlight
    # url = "https://www.nature.com/articles/d41586-026-01558-w" # news
    # nScraper = NatureScraper("/home/user/Code/PapersCrawler/TEST/publisher_test/chrome_cache/nature")
    # nScraper.start_browser()
    # nScraper.fetch_page(url)
    # paper = nScraper.parse_page()
    # pprint(paper)
    # html_path = Path("/home/user/Code/PapersCrawler/TEST/publisher_test/html_example/nature_news.html")
    # nScraper.save_page(html_path)
    # nScraper.close()

    # Science 测试
    # url = "https://www.science.org/doi/abs/10.1126/science.adx9954?af=R"
    # sScraper = ScienceScraper("/home/user/Code/PapersCrawler/TEST/publisher_test/chrome_cache/science")
    # sScraper.start_browser()
    # sScraper.fetch_page(url)
    # paper = sScraper.parse_page()
    # pprint(paper)
    # html_path = Path("/home/user/Code/PapersCrawler/TEST/publisher_test/html_example/science.html")
    # sScraper.save_page(html_path)
    # sScraper.close()

    # APS 测试
    # url = "https://journals.aps.org/prl/abstract/10.1103/yq7c-8bsv"
    # apsScraper = APSScraper("/home/user/Code/PapersCrawler/TEST/publisher_test/chrome_cache/aps")
    # apsScraper.start_browser()
    # apsScraper.fetch_page(url)
    # paper = apsScraper.parse_page()
    # pprint(paper)
    # html_path = Path("/home/user/Code/PapersCrawler/TEST/publisher_test/html_example/aps.html")
    # apsScraper.save_page(html_path)
    # apsScraper.close()

    # Cambridge 测试
    # url = "https://dx.doi.org/10.1017/hpl.2025.10090?rft_dat=source%3Ddrss"
    # cScraper = CambridgeScraper("/home/user/Code/PapersCrawler/TEST/publisher_test/chrome_cache/cambridge")
    # cScraper.start_browser()
    # cScraper.fetch_page(url)
    # paper = cScraper.parse_page()
    # pprint(paper)
    # html_path = Path("/home/user/Code/PapersCrawler/TEST/publisher_test/html_example/cambridge.html")
    # cScraper.save_page(html_path)
    # cScraper.close()

    # AIP 测试
    # url = "https://pubs.aip.org/aip/apl/article/128/19/194001/3391238/A-cavity-mediated-reconfigurable-coupling-scheme"
    # aipScraper = AIPScraper("/home/user/Code/PapersCrawler/TEST/publisher_test/chrome_cache/AIP")
    # aipScraper.start_browser()
    # aipScraper.fetch_page(url)
    # paper = aipScraper.parse_page()
    # pprint(paper)
    # html_path = Path("/home/user/Code/PapersCrawler/TEST/publisher_test/html_example/aip.html")
    # aipScraper.save_page(html_path)
    # aipScraper.close()

    # IOP 测试
    # url = "https://iopscience.iop.org/article/10.1088/1361-6587/ae5adb"
    # iopScraper = IOPScraper("/home/user/Code/PapersCrawler/TEST/publisher_test/chrome_cache/IOP")
    # iopScraper.start_browser()
    # iopScraper.fetch_page(url)
    # paper = iopScraper.parse_page()
    # pprint(paper)
    # html_path = Path("/home/user/Code/PapersCrawler/TEST/publisher_test/html_example/iop.html")
    # iopScraper.save_page(html_path)
    # iopScraper.close()

    # Optica 测试
    # url = "https://opg.optica.org/abstract.cfm?URI=optica-13-5-951"
    # url = "https://opg.optica.org/optica/fulltext.cfm?uri=optica-13-5-867"
    # optScraper = OpticaScraper("/home/user/Code/PapersCrawler/TEST/publisher_test/chrome_cache/Optica")
    # optScraper.start_browser(proxy={"server": "http://127.0.0.1:10808"}) # Optica 可能需要美国代理才不触发检测
    # optScraper.fetch_page(url, 5000)
    # paper = optScraper.parse_page()
    # pprint(paper)
    # html_path = Path("/home/user/Code/PapersCrawler/TEST/publisher_test/html_example/optica.html")
    # optScraper.save_page(html_path)
    # optScraper.close()
