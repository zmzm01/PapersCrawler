"""
rss.py - RSS 数据源处理模块
================================
本模块负责从期刊的 RSS Feed 中获取最新的论文列表信息。
它是整个爬虫管线的上游入口之一：通过定期抓取各期刊配置的 RSS 地址，
解析出每篇新上线论文的 DOI、标题等信息，供下游的 Crossref 模块进一步
补充元数据（摘要、作者、出版日期等）。

核心功能：
1. RSS RSSProcessor 类封装了 HTTP 请求、Feed 解析、DOI 提取等逻辑
2. 所有需要使用的文件路径均通过方法参数传入，无全局依赖
3. 使用可复用的 requests.Session 管理连接，提升性能
"""
import requests
import feedparser
from pathlib import Path
from datetime import datetime
from dateutil import parser

from src.common import Paper


class RSSProcessor:
    """
    RSS 文章初筛处理器
    ===================
    职责：从 RSS Feed URL 获取原始 XML，解析提取论文的基本信息（DOI、标题、链接、日期），
    为后续创建 Paper 对象提供初始数据。

    设计要点：
    - 使用 requests.Session 复用 HTTP 连接，减少握手开销
    - 在构造函数中统一设置请求头，避免每次请求重复设置
    - 所有文件 I/O 路径通过方法参数传入，无全局状态依赖
    """

    def __init__(self):
        """初始化 RSS 处理器，创建持久化的 HTTP Session 并预设请求头。"""
        # 创建复用的 Session，并预设所有请求都需要的请求头
        # Session 会自动管理连接池和 Cookie，避免频繁 TCP 握手
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/136.0 Safari/537.36"
            ),
            # Accept 头指定优先接受 RSS/XML 类型，部分期刊服务器会据此判断是否返回 Feed
            "Accept": (
                "application/rss+xml,"
                "application/xml,"
                "text/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        })

    def fetch_rss(self, url: str) -> str:
        """
        通过复用 Session 获取指定 RSS Feed 的原始文本内容。

        Args:
            url (str): RSS Feed 的请求 URL

        Returns:
            str: 服务端返回的 RSS XML 文本（未经解析的原始字符串）

        Raises:
            requests.RequestException: 当 HTTP 请求失败或超时时抛出
        """
        # 不加请求头 Cambridge/AIP 等出版商会拦截请求，返回 403
        # 请求头已在 __init__ 中统一设置，无需每次传入
        response = self.session.get(url, timeout=30)
        # 将非 2xx 状态码转为异常，方便上层统一处理
        response.raise_for_status()
        return response.text

    def save_raw_rss(self, xml_text: str, save_path: str):
        """
        将 RSS Feed 的原始 XML 文本保存到本地文件，便于后续排查问题或离线重放。

        Args:
            xml_text (str): RSS Feed 的原始文本内容
            save_path (str): 本地保存路径（含文件名）
        """
        Path(save_path).write_text(xml_text, encoding="utf-8")

    def parse_rss(self, xml_text: str, journal_config: dict) -> list:
        """
        解析 RSS Feed XML 文本，提取其中每条论文条目的关键信息。

        解析流程：
        1. 使用 feedparser 将 XML 解析为字典结构
        2. 遍历每个 entry（每条 entry 对应一篇论文）
        3. 从 entry 中提取 DOI、标题、链接、日期
        4. 记录抓取时间，返回结构化的字典列表

        Args:
            xml_text (str): RSS Feed 的原始 XML 文本
            journal_config (dict): 与 RSS Feed 对应的期刊配置字典（从数据源 YAML 文件中解析得到），
                                   可用于后续扩展（如按期刊设置不同的 DOI 提取策略）

        Returns:
            list[dict]: 论文基本信息字典列表，每个字典格式为：
                {
                    "doi": str | None,       # 论文 DOI（可能为空）
                    "title": str,            # 论文标题
                    "link": str,             # 论文页面链接
                    "updated": str | None,   # 论文发布日期（YYYY-MM-DD 格式）
                    "rss_fetched_at": str,   # 本次 RSS 抓取的 ISO 时间戳
                }
        """
        feed = feedparser.parse(xml_text)
        papers = []
        for entry in feed.entries:
            doi = self.extract_doi(entry)

            # 不同的出版社使用不同的日期字段名，按优先级依次尝试
            # published: 部分期刊用这个通用字段
            # prism_publicationdate: PRISM 标准字段（常见于 Nature、Science 等）
            # updated: RSS 规范中的最后更新时间
            dt = entry.get("published") or entry.get("prism_publicationdate") or entry.get("updated")
            if dt:
                # dateutil.parser 能自动识别多种日期格式（ISO、美式、欧式等）
                dt = parser.parse(dt)
                # 统一转换为 YYYY-MM-DD 格式，便于后续数据库存储和比较
                dt = dt.strftime('%Y-%m-%d')

            paper = Paper(
                doi=doi,
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                date=dt,
            )
            papers.append(paper)
        return papers

    def extract_doi(self, entry) -> str | None:
        """
        从单条 RSS entry 中提取论文的 DOI 标识符。

        背景：不同出版社在 RSS Feed 中存放 DOI 的字段位置不同，需要逐一尝试：
        1. dc_identifier 字段 → 值为 "doi:10.xxx/yyy" 格式，需要解析冒号后面的部分
        2. prism_doi 字段 → 直接存储纯 DOI 字符串
        3. 都没有 → 返回 None

        Args:
            entry: feedparser 解析后的一条 entry 对象（支持字典式访问）

        Returns:
            str | None: 提取到的 DOI 字符串，或 None 表示未找到
        """
        # 策略1：通过 dc_identifier 字段提取
        # dc_identifier 的值格式通常为 "doi:10.1234/example"，需要去掉 "doi:" 前缀
        if "dc_identifier" in entry:
            value = entry["dc_identifier"]
            if "doi:" in value.lower():
                # 以第一个冒号分割，取后半部分作为纯 DOI
                # 使用 split(":", 1) 防止 DOI 本身包含冒号导致切分错误
                return value.split(":", 1)[1].strip()

        # 策略2：通过 prism_doi 字段提取（PRISM 元数据标准）
        # prism_doi 直接存储纯 DOI，无需额外处理
        if "prism_doi" in entry:
            return entry["prism_doi"]

        # 未找到任何 DOI 信息
        return None


if __name__ == "__main__":
    pass
