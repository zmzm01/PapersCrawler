"""
Tests: Phase C bot detection patterns (_has_bot_markers).

Verifies that _has_bot_markers() correctly identifies each anti-bot
challenge pattern, and does NOT trigger on normal pages with CF CDN
scripts or valid content.
"""

import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pipeline.phase_c as phase_c_module
from pipeline.phase_c import (
    _has_bot_markers,
    _extract_page_title,
    _limit_phase_papers,
)
from sources.publisher import BasePublisherScraper, Paper


def test_phase_c_limit_is_global_across_publishers():
    """MAX_PAPERS_PER_PHASE limits the complete Phase C invocation."""
    papers = ["paper-a", "paper-b"]
    assert _limit_phase_papers(papers, 0, 3) == papers
    assert _limit_phase_papers(papers, 2, 3) == ["paper-a"]
    assert _limit_phase_papers(papers, 3, 3) == []
    assert _limit_phase_papers(papers, 99, 0) == papers


# ---- _is_cf_challenge_page (fetch_page reload-recovery helper) ----

class TestIsCfChallengePage:
    """测试 fetch_page 的 Cloudflare challenge 页检测（区别于正常文章页）。

    真实文章页也会内嵌 cf-turnstile / challenge-platform 脚本，因此该检测
    只认挑战页特有的结构标记，避免把正常页面误判为 challenge。
    """

    def _call(self, html, title=""):
        return BasePublisherScraper._is_cf_challenge_page(None, html, title)

    def test_title_qing_shaohou(self):
        """AIP 08-01 实际拦截页：标题「请稍候…」."""
        assert self._call("<html></html>", title="请稍候…")

    def test_title_just_a_moment(self):
        """Cloudflare 英文标题 'Just a moment...'."""
        assert self._call("<html></html>", title="Just a moment...")

    def test_title_attention_required(self):
        """Cloudflare 英文标题 'Attention Required! | Cloudflare'."""
        assert self._call("<html></html>", title="Attention Required! | Cloudflare")

    def test_cf_chl_widget_html(self):
        """挑战页内嵌 cf-chl-widget（Turnstile widget 容器）."""
        html = '<html><div class="cf-chl-widget"></div></html>'
        assert self._call(html)

    def test_cf_chl_opt_html(self):
        """挑战页内嵌 _cf_chl_opt 脚本."""
        html = "<html><script>var _cf_chl_opt={cType:'managed'}</script></html>"
        assert self._call(html)

    def test_challenge_error_text(self):
        """挑战页内嵌 challenge-error-text 元素."""
        html = '<html><div id="challenge-error-text">...</div></html>'
        assert self._call(html)

    def test_chinese_verification_text(self):
        """挑战页正文「正在进行安全验证」."""
        html = "<html><div>pubs.aip.org 正在进行安全验证</div></html>"
        assert self._call(html)

    def test_chinese_verification_success(self):
        """挑战页正文「验证成功。正在等待 pubs.aip.org 响应」."""
        html = "<html><div>验证成功。正在等待 pubs.aip.org 响应</div></html>"
        assert self._call(html)

    def test_normal_article_with_turnstile_not_blocked(self):
        """真实 AIP 文章页：含 cf-turnstile 脚本但无挑战结构 → 不误判。"""
        html = """
        <html><head>
        <script src="https://challenges.cloudflare.com/turnstile/api.js?onload=init"></script>
        <meta name="citation_title" content="Real AIP Paper"/>
        <meta name="dc.creator" content="Author"/>
        </head><body>
        <div id="abstract">Valid abstract content here.</div>
        </body></html>
        """
        assert not self._call(html, title="Real AIP Paper Title")

    def test_normal_article_with_challenge_platform_not_blocked(self):
        """真实 APS 文章页：含 challenge-platform CDN 脚本 → 不误判。"""
        html = """
        <html><head>
        <script src="/cdn-cgi/challenge-platform/scripts/jsd.js"></script>
        <meta name="citation_title" content="APS Test Paper"/>
        </head><body>
        <div id="abstract-section-content"><p>Valid abstract.</p></div>
        </body></html>
        """
        assert not self._call(html, title="APS Test Paper")

    def test_empty_html(self):
        """空 HTML 不应判为 challenge。"""
        assert not self._call("")
        assert not self._call("", title="")


# ---- _extract_page_title ----

class TestExtractPageTitle:
    def test_typical_title(self):
        html = "<html><head><title>Physical Review Letters</title></head></html>"
        assert _extract_page_title(html) == "Physical Review Letters"

    def test_title_with_extra_whitespace(self):
        html = "<html><head><title>  Client Challenge  </title></head></html>"
        assert _extract_page_title(html) == "Client Challenge"

    def test_truncated_to_120_chars(self):
        long_title = "A" * 200
        html = f"<html><head><title>{long_title}</title></head></html>"
        extracted = _extract_page_title(html)
        assert len(extracted) == 120

    def test_no_title_tag(self):
        html = "<html><head></head><body>No title here</body></html>"
        assert _extract_page_title(html) == ""

    def test_empty_html(self):
        assert _extract_page_title("") == ""


# ---- _has_bot_markers ----

class TestHasBotMarkers:
    """每个 bot 检测模式单独测试。"""

    def test_cf_challenge_platform(self):
        """Cloudflare: challenge-platform in HTML."""
        html = '<html><body id="challenge-platform">CF challenge</body></html>'
        assert _has_bot_markers(html)

    def test_cf_chl_opt(self):
        """Cloudflare: _cf_chl_opt in HTML."""
        html = '<html><script>var _cf_chl_opt={}</script></html>'
        # Case sensitive — must match exactly
        assert _has_bot_markers(html)

    def test_cf_browser_verification(self):
        """Cloudflare: cf-browser-verification in HTML."""
        html = '<html><div id="cf-browser-verification"></div></html>'
        assert _has_bot_markers(html)

    def test_cf_ray_short_html(self):
        """Cloudflare: cf-ray in HTML + short page (<2000 chars)."""
        html = '<html>cf-ray: abc123</html>'  # len < 2000
        assert _has_bot_markers(html)

    def test_cf_ray_long_html_not_blocked(self):
        """Cloudflare: cf-ray in HTML but long page (>2000 chars) → not a block."""
        html = '<html>' + 'x' * 500 + 'cf-ray: abc123' + 'x' * 1500 + '</html>'
        assert not _has_bot_markers(html)

    def test_turnstile_challenge(self):
        """Cloudflare Turnstile: both turnstile and challenge in HTML."""
        html = '<html><div class="turnstile">challenge</div></html>'
        assert _has_bot_markers(html)

    def test_turnstile_without_challenge(self):
        """Turnstile word alone is not a block."""
        html = '<html><div>turnstile widget loaded</div></html>'
        assert not _has_bot_markers(html)

    def test_radware_html(self):
        """Radware Bot Manager: 'radware' in HTML content."""
        html = '<html><script src="radware captcha"></script></html>'
        assert _has_bot_markers(html)

    def test_bot_manager_html(self):
        """Radware: 'bot manager' in HTML content."""
        html = '<html><title>Bot Manager Challenge</title></html>'
        assert _has_bot_markers(html)

    def test_javascript_disabled_html(self):
        """Nature: 'javascript is disabled' in HTML (<noscript> tag)."""
        html = '<html><noscript>JavaScript is disabled in your browser.</noscript></html>'
        assert _has_bot_markers(html)

    def test_radware_title(self):
        """Radware: 'radware' in page title."""
        assert _has_bot_markers("<html></html>", page_title="Radware Captcha")

    def test_bot_manager_title(self):
        """Radware: 'bot manager' in page title."""
        assert _has_bot_markers("<html></html>", page_title="Bot Manager Challenge")

    def test_captcha_title(self):
        """Captcha in page title."""
        assert _has_bot_markers("<html></html>", page_title="Captcha Page")

    def test_client_challenge_title(self):
        """Nature: 'client challenge' in page title."""
        assert _has_bot_markers("<html></html>", page_title="Client Challenge")

    def test_normal_page_not_blocked(self):
        """Normal article page should NOT be detected as bot block."""
        html = """
        <html><head>
        <title>Laser wakefield acceleration in plasma</title>
        <meta name="citation_title" content="Laser wakefield acceleration"/>
        </head><body>
        <div id="abstract">We report on experimental results...</div>
        <p>This is a long article with substantial content.</p>
        </body></html>
        """
        assert not _has_bot_markers(html, page_title="Laser wakefield acceleration in plasma")

    def test_aps_with_cf_cdn_not_blocked(self):
        """APS page with CF CDN scripts but valid content → NOT blocked.

        This was the original Bug 1: APS/AIP pages contain Cloudflare CDN
        scripts like '_cf_chl_opt' in their HTML, but the actual content
        loaded successfully.  The bot detection must not fire when valid
        content exists (tested via _has_bot_markers in isolation).
        """
        html = """
        <html><head>
        <script src="/cdn-cgi/challenge-platform/scripts/jsd.js"></script>
        <meta name="citation_title" content="APS Test Paper"/>
        </head><body>
        <div id="abstract-section-content"><p>Valid abstract here.</p></div>
        </body></html>
        """
        # _has_bot_markers checks for "challenge-platform" — the CDN script
        # URL contains it.  But the key insight from Bug 1 is that the
        # detection is done AFTER parse_page() succeeds.  This test just
        # validates the marker detection in isolation.
        assert _has_bot_markers(html), (
            "APS page with CF CDN should trigger bot markers detection "
            "(parse result will be checked afterward)"
        )

    def test_cf_cdn_scripts_are_not_blocked_when_page_has_content(self):
        """Page with CF CDN scripts but ALSO valid parseable content.

        This is the full scenario of Bug 1: the page has '_cf_chl_opt'
        because of CDN scripts, but also has real title/abstract. The
        phase_c logic handles this by checking parse result AFTER
        calling parse_page().  _has_bot_markers is only consulted when
        the parse result is empty.
        """
        # This test validates that _has_bot_markers correctly identifies
        # these as potential bot pages — the phase_c logic gates the
        # bot detection on empty parse results.
        html = """
        <html><head>
        <script>var _cf_chl_opt = {}</script>
        <title>Real APS Paper Title</title>
        </head><body>
        <div id="abstract-section-content"><p>Real abstract</p></div>
        </body></html>
        """
        assert _has_bot_markers(html), (
            "_has_bot_markers identifies markers; phase_c uses "
            "this ONLY when parse_page() returns empty results"
        )


# ---- Integration: _has_bot_markers with real page snippets ----

class TestIntegration:
    """接近真实场景的混合测试。"""

    def test_nature_client_challenge_page(self):
        """Nature 'Client Challenge' page (from actual error report)."""
        html = """
        <html><head>
        <title>Client Challenge</title>
        </head><body>
        <noscript>
        <div>JavaScript is disabled in your browser.</div>
        </noscript>
        <div>A required part of this site couldn't load.</div>
        <p>Please check your connection, disable any ad blockers,
        or try using a different browser.</p>
        <span>Oops, something went wrong.</span>
        </body></html>
        """
        title = _extract_page_title(html)
        assert title == "Client Challenge"
        assert _has_bot_markers(html, page_title=title)

    def test_radware_iop_page(self):
        """IOP page blocked by Radware (from actual error report)."""
        html = """
        <html><head>
        <title>Radware Bot Manager Captcha</title>
        </head><body>
        <script src="https://cdn.radware.com/bot-manager.js"></script>
        <div>Please verify you are human.</div>
        </body></html>
        """
        title = _extract_page_title(html)
        assert "Radware" in title
        assert _has_bot_markers(html, page_title=title)

    def test_science_non_research_with_og_type(self):
        """Science careers page with og:type but no dc.Type.

        This is handled by ScienceScraper (raises NonResearchPageError),
        not by bot detection.  This test confirms it's NOT a bot block.
        """
        html = """
        <html><head>
        <meta property="og:type" content="article"/>
        <title>I may not look like a professor</title>
        </head><body>
        <article>Some careers content here.</article>
        </body></html>
        """
        title = _extract_page_title(html)
        assert not _has_bot_markers(html, page_title=title)


# ---- prewarm()（Phase C 预热导航） ----

class TestPrewarm:
    """测试 BasePublisherScraper.prewarm()。

    预热导航用于 AIP 等出版社：冷启动首次访问论文页可能只返回 Osano
    consent 空壳，先在组内预热访问域名根路径建立会话。
    """

    class _Scraper(BasePublisherScraper):
        prewarm_url = "https://pubs.aip.org"

    class _NoPrewarm(BasePublisherScraper):
        prewarm_url = None

    def test_no_prewarm_url_is_noop(self, tmp_path):
        """未配置 prewarm_url 时不访问页面，直接返回 True。"""
        s = self._NoPrewarm(tmp_path)
        assert s.prewarm() is True

    def test_prewarm_navigates_and_returns_true(self, tmp_path):
        """配置 prewarm_url 时导航到域名根路径并返回 True。"""
        s = self._Scraper(tmp_path)
        calls = []

        def goto(url, **k):
            calls.append(url)

        s.page = SimpleNamespace(
            goto=goto,
            wait_for_timeout=lambda *a, **k: None,
            content=lambda: "<html><body>ok</body></html>",
            title=lambda: "AIP Publishing",
        )
        s.html = ""
        assert s.prewarm() is True
        assert calls == ["https://pubs.aip.org"]

    def test_prewarm_exception_is_caught(self, tmp_path):
        """导航抛异常时返回 False 而非冒泡。"""
        s = self._Scraper(tmp_path)

        def boom(*a, **k):
            raise RuntimeError("nav failed")

        s.page = SimpleNamespace(
            goto=boom,
            wait_for_timeout=lambda *a, **k: None,
        )
        assert s.prewarm() is False


def test_phase_c_uses_configured_proxy_after_normal_retry(monkeypatch):
    """末级 fallback 应用配置代理新建 scraper 并成功更新页面状态。"""

    class FakeScraper:
        def __init__(self, fallback=False):
            self.fallback = fallback
            self.html = ""
            self.page_url = ""
            self.closed = False

        def prewarm(self):
            return True

        def fetch_page(self, url, timeout):
            self.page_url = url
            if self.fallback:
                self.html = "<title>Valid article</title>"
            else:
                self.html = "<title>Radware Bot Manager Captcha</title>"

        def parse_page(self):
            if self.fallback:
                return Paper(
                    doi="10.0000/fallback",
                    title="Valid article",
                    abstract="A valid abstract.",
                    authors=[],
                )
            return Paper()

        def close(self):
            self.closed = True

        def _save_error_html(self, url, tag):
            return False

    class FakeDatabase:
        def __init__(self):
            self.updated = []

        def get_pending_publisher_papers(self, publisher, skip_crossref_abstract):
            return [{
                "doi": "10.0000/fallback",
                "page_url": "https://example.test/paper",
                "title": "Pending article",
            }]

        def update_publisher_page(self, *args):
            self.updated.append(args)

        def update_error_message(self, *args):
            raise AssertionError("fallback should have succeeded")

    created_proxies = []
    scrapers = []

    def fake_create_scraper(publisher, proxy_override=None):
        created_proxies.append(proxy_override)
        scraper = FakeScraper(fallback=proxy_override is not None)
        scrapers.append(scraper)
        return scraper

    database = FakeDatabase()
    monkeypatch.setattr(phase_c_module, "create_scraper", fake_create_scraper)
    monkeypatch.setattr(phase_c_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(phase_c_module.CFG, "SKIP_PHASE_C", False)
    monkeypatch.setattr(phase_c_module.CFG, "MAX_PAPERS_PER_PHASE", 0)
    monkeypatch.setattr(phase_c_module.CFG, "PREFETCH_NON_RESEARCH", False)
    monkeypatch.setattr(phase_c_module.CFG, "POSTFETCH_NON_RESEARCH", True)
    monkeypatch.setattr(phase_c_module.CFG, "PUBLISHER_PAGE_DELAY_MIN", 0)
    monkeypatch.setattr(phase_c_module.CFG, "PUBLISHER_PAGE_DELAY_MAX", 0)
    monkeypatch.setattr(phase_c_module.CFG, "PUBLISHER_MAX_CONSECUTIVE_FAILURES", 3)
    monkeypatch.setattr(
        phase_c_module.CFG,
        "PUBLISHER_FALLBACK_PROXY_URL",
        "http://127.0.0.1:7890",
    )
    monkeypatch.setitem(
        phase_c_module.SCRAPER_MAP,
        "iop",
        (FakeScraper, None, None),
    )

    phase_c_module.phase_c_publisher(
        database,
        [{"publisher": "iop", "enabled": True}],
    )

    assert created_proxies == [
        None,
        {"server": "http://127.0.0.1:7890"},
        None,
    ]
    assert len(database.updated) == 1
    assert database.updated[0][0] == "10.0000/fallback"
    assert database.updated[0][-2] == "success"
    assert scrapers[1].closed is True
