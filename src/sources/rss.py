"""
rss.py
负责加载 RSS 数据源与增量更新 paper 的 DOI
所有需要使用的文件路径均通过方法参数传入
"""

import requests
import feedparser
from pathlib import Path
from datetime import datetime
from dateutil import parser


class RSSProcessor:
    """
    RSS 处理类
    使用可复用的 requests.Session 实例管理 HTTP 请求，
    所有路径通过方法参数传入，避免全局依赖。
    """

    def __init__(self):
        # 创建复用的 Session，并预设所有请求都需要的请求头
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/136.0 Safari/537.36"
            ),
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
        通过复用 Session 获取 RSS Feed text

        Args:
            url: 请求 url

        Returns:
            str: 返回的响应文本
        """
        # 不加请求头 cambridge/AIP 会拦截，请求头已在初始化时统一设置
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    def save_raw_rss(self, xml_text: str, save_path: str):
        """
        保存 RSS Feed Raw text

        Args:
            xml_text: RSS Feed 的文本
            sasave_pathve_dir: 保存路径
        ---
        """
        Path(save_path).write_text(xml_text, encoding="utf-8")

    def parse_rss(self, xml_text: str, journal_config: dict) -> list:
        """
        解析 RSS Feed 文本提取关键信息

        Args:
            xml_text: Feed 文本
            journal_config: 与 RSS Feed 对应的期刊配置字典（从数据源中解析得到）

        Returns:
            list[dict]: 记录此 RSS 中 paper 信息的字典列表
            dict 格式: {"doi": str, "title": str, "link": str, "updated": str, "rss_fetched_at": str,}
        """
        feed = feedparser.parse(xml_text)
        papers = []
        for entry in feed.entries:
            doi = self.extract_doi(entry)

            # 不同的神人使用不同的日期格式
            dt = entry.get("published") or entry.get("prism_publicationdate") or entry.get("updated")
            if dt:
                dt = parser.parse(dt)
                dt = dt.strftime('%Y-%m-%d')

            paper = {
                "doi": doi,
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "updated": dt,
                "rss_fetched_at": datetime.now().isoformat(),
            }
            papers.append(paper)
        return papers

    def extract_doi(self, entry) -> str | None:
        """
        不同 publisher 的 DOI 位置可能不同
        """
        # 如果解析为 dc_identifier 字段
        if "dc_identifier" in entry:
            value = entry["dc_identifier"]
            if "doi:" in value.lower():
                return value.split(":", 1)[1].strip()
        # 如果解析为 prism_doi 字段
        if "prism_doi" in entry:
            return entry["prism_doi"]
        return None

if __name__ == "__main__":
    pass