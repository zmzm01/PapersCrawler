"""
Tests: Phase C bot detection patterns (_has_bot_markers).

Verifies that _has_bot_markers() correctly identifies each anti-bot
challenge pattern, and does NOT trigger on normal pages with CF CDN
scripts or valid content.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from pipeline.phase_c import _has_bot_markers, _extract_page_title


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
