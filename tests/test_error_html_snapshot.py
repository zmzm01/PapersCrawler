"""回归测试：页面导航早期失败时仍保留原始异常和 HTML 快照。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import sources.publisher as publisher_module
from sources.publisher import BasePublisherScraper, PageParseError


class _FailingPage:
    """在初次导航和重试导航时都失败的最小页面替身。"""

    url = "chrome-error://chromewebdata/"

    def goto(self, *_args, **_kwargs):
        """模拟浏览器导航失败。"""
        raise RuntimeError("navigation failed")

    def wait_for_timeout(self, *_args, **_kwargs):
        """模拟浏览器等待。"""

    def content(self):
        """返回浏览器错误页内容，供错误快照保存。"""
        return "<html><title>Chrome error</title></html>"


def test_navigation_failure_saves_error_html_without_masking_original_error(
    tmp_path, monkeypatch,
):
    """导航尚未捕获页面 HTML 时应保存快照并保留 PageParseError。"""
    monkeypatch.setattr(publisher_module, "RAW_PAGE_DIR", tmp_path / "raw")

    scraper = BasePublisherScraper(tmp_path)
    scraper.page = _FailingPage()

    with pytest.raises(PageParseError, match="Navigation failed after retry"):
        scraper.fetch_page("https://example.test/paper", timeout=0)

    error_files = list((tmp_path / "raw" / "error").glob("*.html"))
    assert len(error_files) == 1
    assert "Chrome error" in error_files[0].read_text(encoding="utf-8")
