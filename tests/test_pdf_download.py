"""
测试: download_pdf 三级兜底链 (sources/publisher.py)

覆盖范围:
  - 三级下载链的编排逻辑（任一成功即短路）
  - 全部失败时抛 RuntimeError
  - on_page_pdf_link 门控：仅 APSScraper 触发文章页同域 PDF 链接提取
  - _is_pdf_bytes 判定

不启动真实浏览器，全部使用 mock。
"""

import os
import sys
import tempfile

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sources.publisher import APSScraper, BasePublisherScraper

PDF_BYTES = b"%PDF-1.4\nfake pdf content"


def _make_scraper(cls, tmp_path):
    """构造指定 scraper，使用临时目录作为 user_data_dir。"""
    user_data_dir = tmp_path / "profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return cls(str(user_data_dir))


def _mock_page(link_extract_result=None):
    """构造带导航/求值能力的 mock page 对象。

    Args:
        link_extract_result: on-page PDF 链接提取脚本的返回值。

    Returns:
        MagicMock: 模拟的 page。
    """
    page = MagicMock()
    if link_extract_result is not None:
        page.evaluate.side_effect = [link_extract_result, "test-ua"]
    else:
        page.evaluate.return_value = "test-ua"
    return page


class TestIsPdfBytes:
    def test_pdf_header(self):
        assert BasePublisherScraper._is_pdf_bytes(b"%PDF-1.4")

    def test_none(self):
        assert not BasePublisherScraper._is_pdf_bytes(None)

    def test_empty(self):
        assert not BasePublisherScraper._is_pdf_bytes(b"")

    def test_html(self):
        assert not BasePublisherScraper._is_pdf_bytes(b"<html>captcha</html>")

    def test_short_body(self):
        assert not BasePublisherScraper._is_pdf_bytes(b"%PDF")


class TestDownloadPdfTiering:
    def test_tier1_success_short_circuits(self, tmp_path, monkeypatch):
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.page = _mock_page()
        scraper.context = MagicMock()

        monkeypatch.setattr(
            scraper, "_http_get_with_cookies", lambda *a, **k: PDF_BYTES
        )
        context_get = MagicMock()
        nav_download = MagicMock()
        monkeypatch.setattr(scraper, "_context_request_get", context_get)
        monkeypatch.setattr(scraper, "_browser_nav_download", nav_download)

        result = scraper.download_pdf("https://example.com/paper.pdf")

        assert result == PDF_BYTES
        context_get.assert_not_called()
        nav_download.assert_not_called()

    def test_tier1_fail_tier2_success(self, tmp_path, monkeypatch):
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.page = _mock_page()
        scraper.context = MagicMock()

        monkeypatch.setattr(scraper, "_http_get_with_cookies", lambda *a, **k: None)
        monkeypatch.setattr(scraper, "_context_request_get", lambda *a, **k: PDF_BYTES)
        nav_download = MagicMock()
        monkeypatch.setattr(scraper, "_browser_nav_download", nav_download)

        result = scraper.download_pdf("https://example.com/paper.pdf")

        assert result == PDF_BYTES
        nav_download.assert_not_called()

    def test_tier1_tier2_fail_tier3_success(self, tmp_path, monkeypatch):
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.page = _mock_page()
        scraper.context = MagicMock()

        monkeypatch.setattr(scraper, "_http_get_with_cookies", lambda *a, **k: None)
        monkeypatch.setattr(
            scraper, "_context_request_get", lambda *a, **k: b"<html>not pdf</html>"
        )
        monkeypatch.setattr(scraper, "_browser_nav_download", lambda *a, **k: PDF_BYTES)

        result = scraper.download_pdf("https://example.com/paper.pdf")

        assert result == PDF_BYTES

    def test_all_fail_raises_runtime_error(self, tmp_path, monkeypatch):
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.page = _mock_page()
        scraper.context = MagicMock()

        monkeypatch.setattr(scraper, "_http_get_with_cookies", lambda *a, **k: None)
        monkeypatch.setattr(
            scraper, "_context_request_get", lambda *a, **k: b"<html>captcha</html>"
        )
        monkeypatch.setattr(scraper, "_browser_nav_download", lambda *a, **k: None)

        with pytest.raises(RuntimeError, match="未返回有效 PDF"):
            scraper.download_pdf("https://example.com/paper.pdf")

    def test_tier2_not_called_when_tier1_returns_non_pdf_html(
            self, tmp_path, monkeypatch):
        # tier1 返回 HTML（如 captcha 页）时应降级，而非当作成功返回
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.page = _mock_page()
        scraper.context = MagicMock()

        monkeypatch.setattr(
            scraper, "_http_get_with_cookies",
            lambda *a, **k: b"<html>Radware captcha</html>",
        )
        monkeypatch.setattr(scraper, "_context_request_get", lambda *a, **k: PDF_BYTES)

        result = scraper.download_pdf("https://example.com/paper.pdf")

        assert result == PDF_BYTES


class TestOnPagePdfLinkGating:
    def test_aps_enables_link_extraction(self, tmp_path):
        scraper = _make_scraper(APSScraper, tmp_path)
        link_url = "https://journals.aps.org/prab/pdf/10.1103/abc-def"
        scraper.page = _mock_page(link_extract_result=link_url)
        scraper.context = MagicMock()
        scraper._http_get_with_cookies = lambda *a, **k: PDF_BYTES

        scraper.download_pdf(
            "http://link.aps.org/pdf/10.1103/abc-def",
            page_url="https://journals.aps.org/prab/abstract/10.1103/abc-def",
        )

        # 验证评估了链接提取脚本（先于 UA 求值）
        ua_call = None
        link_call = None
        for call in scraper.page.evaluate.call_args_list:
            arg = call.args[0]
            if isinstance(arg, str) and arg.strip() == "navigator.userAgent":
                ua_call = call
            elif isinstance(arg, str) and "querySelectorAll('a')" in arg:
                link_call = call
        assert link_call is not None
        assert ua_call is not None
        assert link_call.args[0].find("a.textContent.trim() === 'PDF'") != -1

    def test_base_disables_link_extraction(self, tmp_path):
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.page = _mock_page()  # 无 link 提取返回值
        scraper.context = MagicMock()
        scraper._http_get_with_cookies = lambda *a, **k: PDF_BYTES

        scraper.download_pdf(
            "https://example.com/paper.pdf",
            page_url="https://example.com/abstract/1",
        )

        # 基类不应执行链接提取脚本，只应求值 UA
        for call in scraper.page.evaluate.call_args_list:
            arg = call.args[0]
            if isinstance(arg, str) and "querySelectorAll('a')" in arg:
                pytest.fail("Base scraper should not extract on-page PDF link")

    def test_aps_link_extraction_overrides_pdf_url(self, tmp_path):
        scraper = _make_scraper(APSScraper, tmp_path)
        link_url = "https://journals.aps.org/prl/pdf/10.1103/x1y2-z3w4"
        scraper.page = _mock_page(link_extract_result=link_url)
        scraper.context = MagicMock()

        captured = {}

        def fake_http_get(pdf_url, page_url, ua, **kwargs):
            captured["pdf_url"] = pdf_url
            return PDF_BYTES

        scraper._http_get_with_cookies = fake_http_get

        scraper.download_pdf(
            "http://link.aps.org/pdf/10.1103/x1y2-z3w4",
            page_url="https://journals.aps.org/prl/abstract/10.1103/x1y2-z3w4",
        )

        assert captured["pdf_url"] == link_url


class TestHttpGetWithCookies:
    def test_skips_cookie_without_domain(self, tmp_path, monkeypatch):
        """domain 为空的 cookie 应被跳过，避免 requests 收到无效 domain（风险点 3）。"""
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.context = MagicMock()
        scraper.context.cookies.return_value = [
            {"name": "cf_clearance", "value": "abc", "domain": "example.com",
             "path": "/"},
            {"name": "no_domain", "value": "x"},
        ]

        set_call = MagicMock()

        class FakeSession:
            headers = {}

            def __init__(self):
                self.cookies = MagicMock()
                self.cookies.set = set_call

            def get(self, *a, **k):
                resp = MagicMock()
                resp.raise_for_status.return_value = None
                resp.content = b"%PDF-1.4"
                return resp

        monkeypatch.setattr(
            "sources.publisher.py_requests.Session", FakeSession
        )

        body = scraper._http_get_with_cookies(
            "https://example.com/paper.pdf", None, "test-ua"
        )

        assert body == b"%PDF-1.4"
        # 只设置有 domain 的 cookie，且带 path
        set_call.assert_called_once()
        args, kwargs = set_call.call_args
        assert args[0] == "cf_clearance"
        assert args[1] == "abc"
        assert kwargs.get("domain") == "example.com"
        assert kwargs.get("path") == "/"

    def test_timeout_threaded_to_context_request(self, tmp_path, monkeypatch):
        """download_pdf 的 timeout 应透传给 _context_request_get（回归 #5 / 风险点 4）。"""
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.page = _mock_page()
        scraper.context = MagicMock()

        monkeypatch.setattr(scraper, "_http_get_with_cookies", lambda *a, **k: None)
        captured = {}

        def fake_context_get(pdf_url, page_url=None, timeout=None):
            captured["timeout"] = timeout
            return b"<html>captcha</html>"

        monkeypatch.setattr(scraper, "_context_request_get", fake_context_get)
        monkeypatch.setattr(scraper, "_browser_nav_download", lambda *a, **k: PDF_BYTES)

        scraper.download_pdf("https://example.com/paper.pdf", timeout=99999)

        assert captured["timeout"] == 99999


class TestFetchPagePrimaryBotCheck:
    def _bot_page_html(self):
        return "<html><head><title>Just a moment...</title></head><body></body></html>"

    def test_primary_bot_page_falls_through_to_browser(self, tmp_path, monkeypatch):
        """primary 策略下 HTTP 返回 bot 页时应降级走浏览器（回归 #9）。"""
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.http_fallback_mode = "requests"
        scraper.http_fallback_strategy = "primary"
        scraper.context = MagicMock()
        scraper.page = MagicMock()
        scraper.page.content.return_value = (
            "<html><head><title>Real Paper Page</title></head><body>ok</body></html>"
        )
        scraper.page.title.return_value = "Real Paper Page"

        def fake_http_fetch(url, timeout_sec=30):
            scraper.html = self._bot_page_html()
            return True

        monkeypatch.setattr(scraper, "_http_fetch", fake_http_fetch)
        monkeypatch.setattr(scraper, "_is_bot_page", lambda html, title="": True)

        scraper.fetch_page("https://example.com/paper")

        # 未被 bot 页短路，浏览器 goto 被执行
        scraper.page.goto.assert_called()
        assert "Real Paper Page" in scraper.html

    def test_primary_clean_page_short_circuits(self, tmp_path, monkeypatch):
        """primary 策略下 HTTP 返回正常页面时应短路返回，不启动浏览器（回归 #9）。"""
        scraper = _make_scraper(BasePublisherScraper, tmp_path)
        scraper.http_fallback_mode = "requests"
        scraper.http_fallback_strategy = "primary"
        scraper.context = MagicMock()
        scraper.page = MagicMock()

        def fake_http_fetch(url, timeout_sec=30):
            scraper.html = "<html><head><title>Real</title></head><body>ok</body></html>"
            return True

        monkeypatch.setattr(scraper, "_http_fetch", fake_http_fetch)

        scraper.fetch_page("https://example.com/paper")

        scraper.page.goto.assert_not_called()
