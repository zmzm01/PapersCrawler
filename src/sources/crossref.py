"""
crossref.py - CrossRef API 元数据补全模块
============================================
本模块负责通过 DOI 向 CrossRef REST API 查询论文的完整元数据。
它是整个爬虫管线的核心下游组件：RSS 模块先抓取到论文的初步信息（DOI、标题等），
然后 CrossRef 模块据此补全摘要、作者列表、期刊名、出版商、出版日期等详细字段。

核心功能：
1. CrossrefClient 封装了 HTTP 请求、重试逻辑、响应解析
2. PaperMetadata 数据类定义了统一的标准元数据结构
3. TextClean 静态方法清洗 CrossRef 返回的 JATS XML 片段，提取纯文本

CrossRef API 文档：https://api.crossref.org/swagger-ui/index.html

注意事项：
- CrossRef 强烈建议在请求头中提供联系邮箱（mailto），以便在出现问题时联系开发者
- 返回的标题和摘要常包含 JATS XML 标记，需要用 BeautifulSoup 清洗
- 对于 404 响应直接抛出 NotFoundError，不进行重试（DOI 不存在重试无意义）
"""
import time
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup


# =========================================================
# 自定义异常
# =========================================================

class NotFoundError(requests.RequestException):
    """
    资源未找到异常（HTTP 404）。

    当 CrossRef 无法根据给定 DOI 找到对应论文时抛出。
    继承自 requests.RequestException，可以在上层统一捕获处理。
    """
    pass

# =========================================================
# Data Models（数据模型）
# =========================================================


@dataclass
class PaperMetadata:
    """
    论文元数据标准模型

    用于规范地从 CrossRef 响应中提取和存储论文信息。
    所有可选字段在数据缺失时默认值为 None。

    Attributes:
        doi (str): 论文 DOI 标识符
        title (str | None): 论文标题（已清洗纯文本）
        authors (list[dict] | None): 作者列表，每个作者字典格式为 {"name": str, "orcid": str | None}
        journal (str | None): 发表期刊名称
        publisher (str | None): 出版商名称
        published (str | None): 出版日期，格式为 YYYY-MM-DD
        abstract (str | None): 摘要纯文本（已清洗 JATS XML 标记）
        url (str | None): 论文在线访问链接
        raw (dict | None): CrossRef 返回的原始 message 字典，供后续自定义解析使用
    """
    doi: str
    title: str | None = None
    authors: list[dict] | None = None
    journal: str | None = None
    publisher: str | None = None
    published: str | None = None
    abstract: str | None = None
    url: str | None = None
    raw: dict[str, Any] | None = None


# =========================================================
# Crossref Client（CrossRef API 客户端）
# =========================================================


class CrossrefClient:
    """
    CrossRef DOI 元数据查询客户端
    ==============================
    封装了向 CrossRef REST API 发起请求、处理响应、解析数据的完整逻辑。

    使用方式：
        client = CrossrefClient(mailto="your@email.com")
        paper = client.fetch_by_doi("10.1234/example")
    """

    # CrossRef 的 REST API 基础地址
    BASE_URL = "https://api.crossref.org"

    def __init__(self, mailto: str, timeout: int = 30, max_retries: int = 3):
        """
        初始化 CrossRef 客户端。

        Args:
            mailto (str): 联系邮箱地址，CrossRef 强烈建议提供，以便在 API 使用异常时联系开发者
            timeout (int): 单次请求的超时秒数，默认 30
            max_retries (int): 请求失败（超时、5xx）的最大重试次数，默认 3。404 不重试
        """
        self.mailto = mailto
        self.timeout = timeout
        self.max_retries = max_retries

        # 创建持久化 Session，复用 TCP 连接
        self.session = requests.Session()

        # 设置默认请求头
        self.session.headers.update(
            {
                # CrossRef 推荐以 "应用名 (mailto:邮箱) 技术栈" 格式设置 User-Agent
                "User-Agent": (
                    f"PaperCrawler " f"(mailto:{mailto}) " f"Python requests"
                ),
                # 明确声明接受 JSON，CrossRef 默认返回 JSON 格式
                "Accept": "application/json",
            }
        )

    # ---------------------------------------------------------
    # Public API（公开方法）
    # ---------------------------------------------------------

    def fetch_by_doi(self, doi: str) -> PaperMetadata | None:
        """
        通过 DOI 从 CrossRef 获取论文的完整元数据。

        请求流程：
        1. 构造 GET /works/{doi} 请求 URL
        2. 发送请求，解析 JSON 响应
        3. 遇到 404（DOI 不存在）直接抛 NotFoundError
        4. 遇到其他网络错误进行指数退避重试
        5. 将 CrossRef 的 message 字典解析为标准 PaperMetadata

        Args:
            doi (str): 待查询的论文 DOI，必须是纯 DOI 字符串（如 "10.1234/example"），
                       不能是 http(s) 链接形式

        Returns:
            PaperMetadata: 论文元数据对象

        Raises:
            NotFoundError: DOI 不存在（404），可能为虚假 DOI 或 DOI 尚未在 CrossRef 注册
            requests.RequestException: 其他网络异常，且在 max_retries 次重试后仍然失败
        """
        # 构造请求 URL：/works/{doi} 是 CrossRef 的单个作品查询端点
        url = f"{self.BASE_URL}/works/{doi}"

        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout)

                # 404 意味着该 DOI 在 CrossRef 数据库中不存在
                # 重试没有意义，直接抛出自定义异常让上层处理（如标记为无效 DOI）
                if response.status_code == 404:
                    raise NotFoundError(f"DOI {doi} not found (404)")

                # 其他 4xx/5xx 状态码统一转为异常，触发重试逻辑
                response.raise_for_status()
                data = response.json()

                # 调试用代码：将完整响应保存到文件便于排查解析问题
                # import json
                # with open("crossref_respon.json", "w", encoding="utf-8") as f:
                #     json.dump(data, f, ensure_ascii=False, indent=2)

                # CrossRef 的 JSON 响应结构为 {"status": "ok", "message": {...}}
                # message 字段包含论文的全部元数据
                return self.parse_work(data["message"])

            except requests.RequestException as e:
                # NotFoundError 需要立即向上传播，不进行重试
                if isinstance(e, NotFoundError):
                    raise e

                # 其他请求异常（超时、连接重置、DNS 错误、5xx 服务器错误等）
                # 如果已经是最后一次尝试，直接向上抛出
                if attempt == self.max_retries - 1:
                    raise e

                # 指数退避等待：2^0=1s, 2^1=2s, 2^2=4s, ...
                # 避免在对方服务器过载时雪上加霜
                time.sleep(2 ** attempt)

        # 理论上不会执行到这里（因为最后一次尝试会抛出异常），但作为安全兜底
        return None

    # ---------------------------------------------------------
    # 期刊级查询
    # ---------------------------------------------------------

    def fetch_by_journal(self, issn: str, from_date: str, to_date: str,
                         max_results: int | None = None) -> list[PaperMetadata]:
        """
        按 ISSN + 日期范围查询期刊论文列表。

        使用 CrossRef /journals/{issn}/works 端点，支持:
        - 日期范围过滤 (from-pub-date / until-pub-date)
        - 文章类型过滤 (type=journal-article，排除 editorial/correction 等)
        - offset 翻页（上限约 10000 条，超出需 cursor 模式，暂不实现）

        Args:
            issn:        期刊 ISSN，如 "1476-4687"
            from_date:   起始日期，含该日，"YYYY-MM-DD"
            to_date:     截止日期，含该日，"YYYY-MM-DD"
            max_results: 返回条数上限，None 表示全部

        Returns:
            list[PaperMetadata]: 日期范围内的论文列表。每篇包含 doi/title/date/
                                 journal/publisher/authors/url 等字段。

        Raises:
            requests.RequestException: 网络错误（超时、HTTP 非 2xx 等）
        """
        papers: list[PaperMetadata] = []
        offset = 0
        rows = 100

        url = f"{self.BASE_URL}/journals/{issn}/works"

        while True:
            params = {
                "filter": (
                    f"from-pub-date:{from_date},"
                    f"until-pub-date:{to_date},"
                    f"type:journal-article"
                ),
                "rows": rows,
                "offset": offset,
            }

            try:
                response = self.session.get(url, params=params,
                                            timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                raise e

            items = data.get("message", {}).get("items", [])
            for item in items:
                try:
                    paper = self.parse_work(item)
                    if paper.doi:
                        papers.append(paper)
                except Exception:
                    continue

            total = data.get("message", {}).get("total-results", 0)
            offset += rows

            if max_results is not None and len(papers) >= max_results:
                papers = papers[:max_results]
                break
            if offset >= total or not items:
                break
            if offset > 10000:
                break

            time.sleep(0.2)

        return papers

    # ---------------------------------------------------------
    # 文本清洗工具
    # ---------------------------------------------------------
    @staticmethod
    def TextClean(abstract: str | None) -> str | None:
        """
        清洗 CrossRef 返回的 JATS XML 格式文本，提取纯文本内容。

        背景：CrossRef 的标题和摘要字段经常包含 JATS XML 标记（如 <jats:title>、
        <jats:bold>、<i> 等标签），直接使用可读性差。本方法使用 BeautifulSoup
        去除所有 XML/HTML 标签，合并多余空白字符，返回干净的纯文本。

        Args:
            abstract (str | None): 待清洗的原始文本（可能包含 XML 标签）

        Returns:
            str | None: 清洗后的纯文本；如果输入为空则返回 None
        """
        if not abstract:
            return None

        # 使用 lxml 解析器处理 JATS XML 片段
        soup = BeautifulSoup(abstract, "lxml")
        # get_text(" ") 用空格连接各文本节点，避免单词粘连
        text = soup.get_text(" ")
        # 将连续的空白字符（空格、换行、制表符）压缩为单个空格
        text = " ".join(text.split())

        return text

    # ---------------------------------------------------------
    # 元数据解析
    # ---------------------------------------------------------
    @staticmethod
    def parse_work(work: dict[str, Any]) -> PaperMetadata:
        """
        将 CrossRef 原始响应中的 message 字典解析为 PaperMetadata 标准对象。

        解析过程中会对以下字段做特别处理：
        - title: 取第一个标题元素并用 TextClean 清洗 JATS 标记
        - authors: 拼接 given + family 为全名，同时保留 ORCID
        - abstract: 用 TextClean 清洗 JATS 标记
        - published: 从 published-online → published-print → created 中按优先级选取，
                     格式化为 YYYY-MM-DD

        Args:
            work (dict[str, Any]): CrossRef API 返回的 message 字典，
                                   即 response["message"] 的内容

        Returns:
            PaperMetadata: 结构化的论文元数据对象
        """
        # ---- 标题 ----
        # CrossRef 的 title 字段是一个列表，这里取第一个元素
        # 标题常包含 JATS XML 标签（如 <jats:title>），需要用 TextClean 清洗
        title = None
        if work.get("title"):
            title = CrossrefClient.TextClean(work["title"][0])

        # ---- 期刊名 ----
        # container-title 是被收录的期刊/会议名称
        journal = None
        if work.get("container-title"):
            journal = work["container-title"][0]

        # ---- 出版日期 ----
        # CrossRef 提供多个日期字段，按优先级选取：
        # 1. published-online: 在线发表日期（最贴近实际上线时间）
        # 2. published-print: 印刷出版日期
        # 3. created: 记录创建日期（兜底）
        # 这是因为一篇论文可能有多个出版阶段，online 日期通常最新
        published_date = None
        published = (
            work.get("published-online")
            or work.get("published-print")
            or work.get("created")
        )

        if published:
            # date-parts 结构为 [[year, month, day], ...]
            # 取第一个日期部分（通常只有一个）
            date_parts = published.get("date-parts", [])
            if date_parts and len(date_parts[0]) > 0:
                parts = date_parts[0]
                # 年份一定有，月份和日期可能为 0 或缺失
                year = parts[0]
                month = parts[1] if len(parts) > 1 and parts[1] else 0
                day = parts[2] if len(parts) > 2 and parts[2] else 0
                # 格式化为 YYYY-MM-DD，月份日期不足补零
                published_date = f"{year:04d}-{month:02d}-{day:02d}"

        # ---- 作者列表 ----
        # 每个作者包含 given（名）、family（姓）、ORCID（可选）
        authors = []
        for author in work.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            # 拼接为全名，如 "John Smith"
            full_name = (f"{given} {family}").strip()
            authors.append({"name": full_name, "orcid": author.get("ORCID")})
        if not authors:
            authors = None

        # ---- 摘要 ----
        # 摘要常包含大量 JATS XML 标记，必须清洗
        abstract = CrossrefClient.TextClean(work.get("abstract"))

        # ---- 构建结果对象 ----
        return PaperMetadata(
            doi=work.get("DOI"),
            title=title,
            authors=authors,
            abstract=abstract,
            journal=journal,
            publisher=work.get("publisher"),
            published=published_date,
            url=work.get("URL"),
            raw=work,  # 保留原始数据，便于后续自定义字段解析
        )


if __name__ == "__main__":
    # 测试代码：验证对 OA（开源）和 NOA（非开源）论文的解析能力
    doi_OA = "10.1364/OE.582177"    # 开放获取论文
    doi_NOA = "10.1103/mw7c-8qy4"   # 非开放获取论文（可能没有完整元数据）

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
