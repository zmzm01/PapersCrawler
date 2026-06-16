"""
学术出版商论文元数据爬取模块。

本模块通过 cloakbrowser 驱动 Chromium 浏览器，结合 parsel 选择器，从 7 种主流
学术出版商的网页中提取论文元数据（标题、作者、DOI、摘要、期刊、日期、PDF链接等）。

支持的出版商（对应 7 个 Scraper 子类）：
    - APS (Physical Review 系列)        → APSScraper
    - Nature (Nature 系列)              → NatureScraper
    - Science (Science 系列)            → ScienceScraper
    - Cambridge (剑桥大学出版社)        → CambridgeScraper
    - AIP (American Institute of Physics) → AIPScraper
    - IOP (Institute of Physics)        → IOPScraper
    - Optica (OSA/Optica Publishing)    → OpticaScraper

Cloudflare 反爬对抗策略：
    cloakbrowser 自动处理浏览器指纹伪装，无需手动注入反检测 JS。
    页面加载后等待 5 秒（fetch_page 中的 wait_for_timeout），给 Cloudflare
    Challenge 足够时间自动通过。

类继承层次：
    BasePublisherScraper          ← 基类，封装浏览器启动/关闭、页面抓取/保存
        ├── APSScraper           ← APS 期刊解析器
        ├── NatureScraper        ← Nature 期刊解析器（含 News/Podcast 等过滤）
        ├── ScienceScraper       ← Science 期刊解析器（含非 research-article 过滤）
        ├── CambridgeScraper      ← Cambridge 期刊解析器
        ├── AIPScraper           ← AIP 期刊解析器
        ├── IOPScraper           ← IOP 期刊解析器
        └── OpticaScraper        ← Optica 期刊解析器

异常类：
    PageParseError       ← 页面解析通用异常（如 HTML 文件不存在、页面结构变化）
    NonResearchPageError   ← Nature/Science 页面不是论文文章时抛出（如 News/Podcast）

使用流程：
    1. 实例化对应 Scraper，传入浏览器缓存目录。
    2. 调用 start_browser 启动浏览器（可选 proxy）。
    3. 调用 fetch_page 加载目标 URL 或本地 HTML 文件。
    4. 调用 parse_page 提取 Paper 元数据。
    5. 调用 close 关闭浏览器。
"""

import re
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import requests as py_requests
from parsel import Selector
from cloakbrowser import launch_persistent_context

from common import Paper
from config import RAW_PAGE_DIR, DATA_DIR


# ──────────────────────────────────────────────────────────
# Paper 数据类：封装一篇论文的所有元数据
# ──────────────────────────────────────────────────────────




# ──────────────────────────────────────────────────────────
# 基础 Scraper 类：封装浏览器生命周期和通用操作
# ──────────────────────────────────────────────────────────

class BasePublisherScraper:
    """出版商爬虫基类。

    封装了基于 cloakbrowser 的 Chromium 浏览器启动、页面抓取、HTML 保存、
    PDF 下载和浏览器关闭等通用逻辑。子类只需实现 parse_page() 方法即可。

    设计理念：同一个浏览器实例可复用于多个出版商的页面抓取，
    通过持久化 user_data_dir 保留登录态和 Cookie，避免重复登录。

    Attributes:
        user_data_dir (Path): Chromium 持久化数据目录，用于缓存 session/Cookie。
        context:             浏览器上下文。
        page:                浏览器 Page 对象。
        html:                当前页面的 HTML 源码字符串。

    HTTP Fallback 机制：
        部分出版商（如 Nature）的浏览器访问会触发 Fastly Client Challenge 拦截，
        但纯 HTTP 请求（requests / curl_cffi）可正常获取页面。
        子类可通过以下类属性配置回退策略：

        http_fallback_mode (str | None):
            None     — 不使用 HTTP 回退（默认）
            "requests" — 使用 requests 库
            "curl_cffi" — 使用 curl_cffi（TLS 指纹伪造）
        http_fallback_strategy (str):
            "primary"  — 优先尝试 HTTP，失败后降级到浏览器
            "fallback" — 先用浏览器，检测到拦截页面后自动回退 HTTP
    """

    # ── HTTP Fallback 配置（子类可覆盖） ──
    http_fallback_mode: str | None = None
    http_fallback_strategy: str = "fallback"

    # ── Phase C 跳过配置 ──
    # 设为 True 时，Phase C 会检查该 publisher 的论文是否已从 CrossRef 获取到
    # 有效摘要，若是则跳过浏览器访问（减少反爬消耗、加速 Pipeline）。
    # Optica (OA) 使用此优化，其他 publisher 默认为 False。
    skip_phase_c_if_crossref_abstract: bool = False

    def __init__(self, user_data_dir):
        """初始化基础爬虫。

        Args:
            user_data_dir: Chromium 持久化数据目录路径（字符串或 Path）。

        Raises:
            FileNotFoundError: 如果 user_data_dir 目录不存在。
        """
        user_data_dir = Path(user_data_dir)
        if not user_data_dir.is_dir():
            raise FileNotFoundError(f"dir {user_data_dir} does not exist.")

        self.user_data_dir = user_data_dir
        self.context = None
        self.page = None

    def start_browser(self, proxy=None):
        """启动 Chromium 浏览器（通过 cloakbrowser）。

        使用 cloakbrowser.launch_persistent_context 创建持久化浏览器上下文，
        自动处理浏览器指纹伪装和 Cloudflare 绕过。
        浏览器启动后额外注入反检测 JS 掩盖自动化特征（如 navigator.webdriver），
        进一步提升隐身效果。

        Args:
            proxy: 可选代理配置字典，格式如 {"server": "http://127.0.0.1:10808"}，
                   用于需要特定区域 IP 的出版商（如 Optica 可能需要美国 IP）。
        """
        self.context = launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=False,
            proxy=proxy,
        )
        self.page = self.context.new_page()

        # ─── 反检测 JS 注入 ───
        # 覆盖浏览器自动化特征，使指纹更接近真实用户。
        # 使用 add_init_script 而非 evaluate，确保脚本在每次页面导航前注入，
        # 而非仅注入到当前（about:blank）页面上下文。
        # 尤其针对 Nature 的 Fastly Client Challenge 检测。
        self.page.context.add_init_script("""
        () => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
        }
        """)

    # ──────────────────────────────────────────────────────────
    # HTTP Fallback 机制
    # ──────────────────────────────────────────────────────────

    def _http_fetch(self, url: str, timeout_sec: int = 30) -> bool:
        """通过纯 HTTP 请求获取页面 HTML（绕过浏览器 Client Challenge）。

        根据 ``http_fallback_mode`` 选择后端：
        - "requests": 标准 HTTP 请求（适用于 Nature 等无 TLS 指纹检测的站点）
        - "curl_cffi": 带浏览器 TLS 指纹伪造的请求（适用于 IOP 等需要 TLS 指纹的站点）

        Args:
            url:        目标页面 URL。
            timeout_sec: HTTP 请求超时（秒），默认 30。

        Returns:
            bool: 成功获取并设置 self.html 返回 True，失败返回 False。
        """
        logger = logging.getLogger(__name__)
        if self.http_fallback_mode == "requests":
            try:
                resp = py_requests.get(
                    url,
                    timeout=timeout_sec,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                        ),
                        "Accept": (
                            "text/html,application/xhtml+xml,"
                            "application/xml;q=0.9,*/*;q=0.8"
                        ),
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                resp.raise_for_status()
                self.html = resp.text
                logger.info("HTTP fallback (requests) OK: %s", url[:80])
                return True
            except Exception as exc:
                logger.debug("HTTP fallback (requests) failed: %s", exc)
                return False

        elif self.http_fallback_mode == "curl_cffi":
            try:
                from curl_cffi import requests as curl_req
                resp = curl_req.get(
                    url,
                    impersonate="chrome",
                    timeout=timeout_sec,
                )
                resp.raise_for_status()
                self.html = resp.text
                logger.info("HTTP fallback (curl_cffi) OK: %s", url[:80])
                return True
            except ImportError:
                logger.warning("HTTP fallback (curl_cffi) requires 'curl_cffi' package, falling back to browser")
                return False
            except Exception as exc:
                logger.debug("HTTP fallback (curl_cffi) failed: %s", exc)
                return False

        return False

    def _is_bot_page(self, html: str, title: str = "") -> bool:
        """检测页面是否为反爬拦截页（而非正常内容页）。

        Args:
            html:  页面 HTML 源码。
            title: 页面标题（可选，用于标题级别检测）。

        Returns:
            bool: 是拦截页返回 True，否则返回 False。
        """
        title_lower = title.lower() if title else ""
        html_lower = html.lower() if html else ""
        # 从标题检测
        if any(kw in title_lower for kw in [
            "client challenge", "challenge", "captcha", "blocked",
            "access denied", "attention required", "just a moment",
        ]):
            return True
        # 从 HTML 内容检测
        if any(kw in html_lower for kw in [
            "cf-browser-verification", "challenge-platform",
            "_cf_chl_opt", "g-recaptcha",
        ]):
            return True
        return False

    def fetch_page(self, url=None, html_path=None, timeout=8000):
        """获取论文页面 HTML 源码。

        支持两种模式：
        1. 在线模式：提供 url，通过浏览器访问并获取页面 HTML。
           若子类配置了 HTTP Fallback（http_fallback_mode），按策略执行：
           - "primary": 先尝试 HTTP 请求，失败后降级到浏览器。
           - "fallback": 先用浏览器，检测到拦截页后自动回退 HTTP。
        2. 离线模式：提供 html_path，从本地已保存的 HTML 文件读取内容。

        在线模式下会先等待 DOM 加载完成（domcontentloaded），
        再额外等待 timeout 毫秒，以确保 Cloudflare Challenge 等 JS 重定向
        或验证流程完成后再获取页面内容。

        Args:
            url:       论文页面 URL（在线模式）。
            html_path: 本地 HTML 文件路径（离线模式）。
            timeout:   URL 加载后额外等待时间（毫秒），默认 8000ms，
                        用于等待 Cloudflare Challenge 自动通过。

        Raises:
            PageParseError: 如果提供了 html_path 但文件不存在。
        """
        if url:
            self.page_url = url

            # ── 策略 "primary": 先 HTTP，失败再走浏览器 ──
            if self.http_fallback_mode and self.http_fallback_strategy == "primary":
                if self._http_fetch(url, timeout_sec=max(timeout // 1000, 30)):
                    return
                # HTTP 失败，降级到浏览器

            # ── 浏览器导航（原有逻辑） ──
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=120000)
            except Exception:
                # Navigation may be interrupted by fast 302 redirect (e.g. APS
                # link.aps.org → journals.aps.org).  Retry with final URL.
                self.page.wait_for_timeout(3000)
                try:
                    self.page.goto(self.page.url, wait_until="domcontentloaded", timeout=120000)
                except Exception as e2:
                    # 浏览器完全失败 → 尝试 HTTP fallback 兜底
                    if self.http_fallback_mode and self.http_fallback_strategy == "fallback":
                        if self._http_fetch(url, timeout_sec=max(timeout // 1000, 30)):
                            return
                    self._save_error_html(url, "goto_retry_failed")
                    raise PageParseError(
                        f"Navigation failed after retry: {e2}"
                    ) from e2
            # 等待 timeout ms，给 Cloudflare Challenge 足够时间自动通过
            self.page.wait_for_timeout(timeout)
            self.html = self.page.content()

            # ── 策略 "fallback": 浏览器拿到拦截页 → 回退 HTTP ──
            if self.http_fallback_mode and self.http_fallback_strategy == "fallback":
                title = self.page.title()
                if self._is_bot_page(self.html, title):
                    logger = logging.getLogger(__name__)
                    logger.info(
                        "Bot page detected (title=%s), trying HTTP fallback...",
                        title[:60],
                    )
                    if self._http_fetch(url, timeout_sec=max(timeout // 1000, 30)):
                        return
                    # HTTP fallback 也失败，保留浏览器拿到的 HTML
                    logger.warning("HTTP fallback also failed, using browser HTML")

        elif html_path:
            html_path = Path(html_path)
            if not html_path.exists():
                raise PageParseError(f"HTML file {html_path} does not exist.")
            with open(html_path, "r", encoding="utf-8") as f:
                self.html = f.read()

    def parse_page(self):
        """解析页面 HTML，提取论文元数据。

        这是一个抽象方法，每个子类必须重写以适配不同出版商的页面结构。

        Returns:
            Paper: 包含提取的元数据的 Paper 实例。

        Raises:
            NotImplementedError: 基类未实现，子类必须重写。
        """
        raise NotImplementedError("parse_page method is defined by each child class.")

    def save_page(self, path):
        """保存当前页面的 HTML 内容到本地文件。

        用于调试或离线解析：首次在线抓取后保存 HTML，后续可直接用 fetch_page
        的离线模式加载，避免重复请求。

        Args:
            path: 保存路径（字符串）。
        """
        html = self.page.content()
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    def _save_error_html(self, url_or_doi: str, tag: str = "") -> bool:
        """保存出错时的页面 HTML 快照到 data/raw/page/ 目录。

        用于诊断抓取失败原因（Cloudflare 拦截、页面结构变更、网络超时等）。
        文件命名格式: error_{safe_name}[_{safe_tag}]_{timestamp}.html
        url_or_doi 和 tag 中的特殊字符（/ 等）会被替换为 _ 以确保文件名合法。

        Args:
            url_or_doi: 论文 URL 或 DOI，用于生成文件名标识。
            tag:        错误标签（如 "goto_retry_failed"），追加在文件名中。

        Returns:
            bool: 保存成功返回 True，失败返回 False。
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[^\w\-]', '_', url_or_doi)[:60]
        safe_tag = re.sub(r'[^\w\-]', '_', tag)[:40] if tag else ""
        tag_part = f"_{safe_tag}" if safe_tag else ""
        filename = f"error_{safe_name}{tag_part}_{timestamp}.html"
        error_dir = RAW_PAGE_DIR / "error"
        error_dir.mkdir(parents=True, exist_ok=True)
        save_path = error_dir / filename
        try:
            html = self.page.content()
            save_path.write_text(html, encoding="utf-8")
            logger = logging.getLogger(__name__)
            logger.warning(f"Error HTML saved to {save_path}")
            return True
        except Exception as save_err:
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to save error HTML: {save_err}")
            return False

    def download_pdf(self, pdf_url: str, page_url: str | None = None,
                     timeout: int = 60000) -> bytes:
        """利用已有浏览器上下文下载 PDF。

        先访问文章页面（page_url）建立正确的 referrer/session 上下文，
        再在当前页面中用 fetch 请求 PDF 链接。

        这解决了部分出版商（如 APS closed OA）直接访问 pdf_url 会被
        302 重定向到文章页的问题。

        Args:
            pdf_url:  PDF 下载链接。
            page_url: 论文页面 URL，提供后先访问此页面建立上下文。
            timeout:  goto 超时时间（毫秒），默认 60000。

        Returns:
            bytes: PDF 文件的原始字节。

        Raises:
            RuntimeError: 无法获取有效 PDF。
        """
        logger = logging.getLogger(__name__)

        # 先在论文页面建立上下文（referrer / cookie / session）
        if page_url:
            logger.debug(f"访问论文页面建立上下文: {page_url}")
            self.page.goto(page_url, wait_until="domcontentloaded",
                           timeout=max(timeout, 120000))
            self.page.wait_for_timeout(15000)

            # 从页面提取同域 PDF 链接（解决 APS link.aps.org 跨域问题）
            on_page_url = None
            for _attempt in range(2):
                try:
                    on_page_url = self.page.evaluate("""
                        () => {
                            for (const a of document.querySelectorAll('a')) {
                                if (a.textContent.trim() === 'PDF') {
                                    return new URL(a.getAttribute('href'),
                                                   location.origin).href;
                                }
                            }
                            return null;
                        }
                    """)
                    break
                except Exception:
                    if _attempt == 0:
                        logger.debug("上下文可能因导航被销毁，3s 后重试...")
                        self.page.wait_for_timeout(3000)
            if on_page_url:
                logger.debug(f"页面中找到同域 PDF 链接: {on_page_url}")
                pdf_url = on_page_url

        # 先尝试 requests + 浏览器 cookies（最快，避免 AIP 等 publisher 的
        # JS fetch 因 CSP 长时间等待超时）。失败则降级为 JS fetch 兜底。
        logger.debug(f"下载 PDF: {pdf_url}")
        try:
            cookies = self.context.cookies()
            session = py_requests.Session()
            for c in cookies:
                session.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain", ""),
                )
            try:
                ua = self.page.evaluate("navigator.userAgent")
            except Exception:
                ua = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            session.headers.update({
                "User-Agent": ua,
                "Referer": page_url or "",
            })
            resp = session.get(pdf_url, timeout=120)
            resp.raise_for_status()
            pdf_body = resp.content
        except Exception as http_err:
            # 兜底：JS fetch（完全继承浏览器上下文，应对 requests 无法处理的场景）
            logger.debug(f"HTTP download failed ({http_err}), trying JS fetch...")
            url_escaped = json.dumps(pdf_url)
            try:
                raw = self.page.evaluate(f"""
                    async () => {{
                        const resp = await fetch({url_escaped});
                        const buf = await resp.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    }}
                """)
                pdf_body = bytes(raw) if raw else None
            except Exception as fetch_err:
                logger.debug(f"JS fetch also failed ({fetch_err})")
                pdf_body = None

        if pdf_body is None or pdf_body[:5] != b'%PDF-':
            raise RuntimeError(
                "页面未返回有效 PDF（可能需登录或链接不可用）"
            )

        return pdf_body

    def close(self):
        """关闭浏览器上下文并清理 Chromium profile 数据。

        释放所有 Chromium 相关资源（浏览器进程、网络连接等），
        同时清理持久化 Session 数据目录，避免 data/session_cached/
        目录无限膨胀（单个 publisher 的 Chromium profile 可达数百 MB）。

        关闭顺序：
        1. context.close() — cloakbrowser 的 patched close，先调 Playwright
           原版 context.close() 关闭页面/context，再调 pw.stop() 断开 WebSocket
        2. browser.close() — 确保 Chromium 子进程退出，防止 orphan 进程泄漏
           单独 pw.stop() 不保证 Chrome 进程退出，需要显式 kill。
        """
        try:
            if hasattr(self, 'context') and self.context:
                self.context.close()
                # context.close() 之后单独杀进程（pw.stop() 不保证 Chrome 退出）
                try:
                    browser = self.context.browser
                    if browser:
                        browser.close()
                except Exception:
                    pass
        except Exception:
            pass
        if self.user_data_dir and self.user_data_dir.exists():
            shutil.rmtree(self.user_data_dir, ignore_errors=True)


# ──────────────────────────────────────────────────────────
# 自定义异常类
# ──────────────────────────────────────────────────────────

class PageParseError(Exception):
    """页面解析异常。

    当 HTML 文件不存在、页面结构发生变化、或无法找到预期的元素时抛出。
    """
    pass


class NonResearchPageError(Exception):
    """非论文页面异常。

    在 Nature 或 Science 爬虫中，当检测到页面类型不是学术论文时抛出。
    例如：Nature 中的 News（新闻）、Podcast（播客）、Highlight（亮点）页面，
          或 Science 中非 research-article 类型的页面。

    上层调用方可以捕获此异常并跳过该页面的处理。
    """
    pass


class AcceptedPaperError(NonResearchPageError):
    """Accepted Paper 异常，继承自 NonResearchPageError。

    APS 在正式发表前会发布 Accepted Paper 版本（URL 含 /accepted/ 路径，
    页面含 li.article-feature-tag:contains("Accepted Paper") 标签）。
    这类页面有摘要但页面结构与正式论文不同（当前选择器无法提取 abstract，
    且不提供 PDF 链接），无正文内容可供 MinerU 解析和 LLM 总结。

    检测到后标记 skipped 并级联跳过下游所有阶段。
    不为此类页面编写专门的选择器适配。
    """
    pass


# ──────────────────────────────────────────────────────────
# 各出版商 Scraper 实现
# ──────────────────────────────────────────────────────────

class APSScraper(BasePublisherScraper):
    """APS (American Physical Society) 期刊爬虫。

    支持 Physical Review Letters、Physical Review A/B/C/D/E/X 等 APS 系列期刊。

    元数据提取策略：主要依赖 HTML <meta> 标签中的 citation_* 系列元数据，
    摘要通过 CSS 选择器从 #abstract-section-content 区域提取。

    已知限制：APS 页面中的数学公式通过 MathJAX 渲染，HTML 源码中不包含
    原始 LaTeX 源码，因此无法直接从页面提取全文中的公式内容。
    """

    def parse_page(self):
        """解析 APS 论文页面。

        元数据提取来源：
            - title:     <meta name="citation_title"> 的 content 属性
            - date:      <meta name="citation_date"> 的 content 属性
            - doi:       <meta name="citation_doi"> 的 content 属性
            - journal:   <meta name="citation_journal_title"> 的 content 属性
            - authors:   <meta name="citation_author"> 的 content 属性（多值）
            - pdf_url:   <meta name="citation_pdf_url"> 的 content 属性
                         （注意：该链接会产生重定向，且可能需要认证才能下载）
            - abstract:  从 #abstract-section-content 内所有 <p> 标签文本提取

        Returns:
            Paper: 包含提取元数据的 Paper 实例。

        Raises:
            AcceptedPaperError: 当页面是 APS 预发布 Accepter Paper（页面结构不
                                同，不提供 PDF，无正文）时抛出，上游将标记 skipped。
        """
        sel = Selector(text=self.html)

        # Accepted Paper 检测（页面结构与正式论文不同，不专门适配）
        # 特征 1: URL 路径含 /accepted/
        page_url = getattr(self, 'page_url', '') or ''
        if '/accepted/' in page_url:
            raise AcceptedPaperError(
                "AcceptedPaper: page structure differs (Accepted Paper, no full text available)"
            )
        # 特征 2: HTML 含 Accepted Paper 特征标签
        if sel.css('ul.flex.justify-start li.article-feature-tag::text').get() == 'Accepted Paper':
            raise AcceptedPaperError(
                "AcceptedPaper: page structure differs (Accepted Paper, no full text available)"
            )

        # ─── 从 <meta> 标签提取元数据 ───
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        date = sel.css('meta[name="citation_date"]::attr(content)').get() or ""
        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        # 注意：citation_pdf_url 链接会产生重定向，且下载 PDF 通常需要认证
        pdf_url = (
            sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""
        )

        # 从 meta description 获取简短描述（备用摘要信息）
        description = (
            sel.css('meta[name="description"]::attr(content)').get() or ""
        )

        # ─── 从正文区域提取摘要 ───
        # CSS 选择器：#abstract-section-content 是 APS 页面的摘要容器，
        # 内部可能包含多个 <p> 标签（理论上物理期刊摘要单段，但做兼容处理）
        paragraphs = sel.css("#abstract-section-content p::text").getall()
        paragraphs = [
            p.strip() for p in paragraphs if p.strip()
        ]
        abstract = " ".join(paragraphs)

        # 注意：APS 正文中的数学公式由 MathJAX 渲染，HTML 源码中不含原始 TeX，
        #       因此无法直接从 HTML 页面抓取全文公式内容。

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
    # Nature 的 Fastly Client Challenge 会拦截所有自动化浏览器，
    # 但纯 HTTP 请求（wget/requests）可以正常获取。优先走 HTTP。
    http_fallback_mode = "requests"
    http_fallback_strategy = "primary"

    """Nature 系列期刊爬虫。

     支持 Nature、Nature Physics、Nature Photonics 等 Nature 旗下期刊。

    边界情况处理：
        - 页面类型过滤：通过 <meta name="dc.type"> 检查是否为 OriginalPaper。
          若不是（如 News、Podcast、Highlight），则抛出 NonResearchPageError 异常，
          由调用方跳过该页面。
        - 摘要来源优先级：优先使用正文 #Abs1-content 中的摘要文本，
          JSON-LD 中的 description 可能混杂非摘要内容（如期刊宣传语），
          仅作为备用。
        - PDF URL：通过 data-test="download-pdf" 属性定位下载链接，
          获取的是相对路径（如 /articles/s41567-026-03184-9.pdf），
          需要拼接 "https://www.nature.com" 前缀。
    """

    def parse_page(self):
        """解析 Nature 论文页面。

        元数据提取来源：
            - doi:       <meta name="dc.Identifier"> 的 content 属性
            - title:     JSON-LD (application/ld+json) 中 mainEntity.headline
            - date:      JSON-LD 中 mainEntity.datePublished
            - journal:   优先 <meta name="citation_journal_title">，
                         备用 <meta name="dc.Publisher">
            - authors:   JSON-LD 中 mainEntity.author[].name 列表
            - abstract:  优先从 #Abs1-content 区域文本提取（比 JSON-LD 更干净），
                         备用 JSON-LD 的 mainEntity.description
            - pdf_url:   通过 <a data-test="download-pdf"> 的 href 属性获取，
                         拼接 "https://www.nature.com" 前缀
            - url:       <link rel="canonical"> 的 href 属性
            - keywords:  JSON-LD 中 mainEntity.keywords（预留）

        边界处理：
            - 若 dc.type 不是 "OriginalPaper"，抛出 NonResearchPageError
            - 若 dc.type 为空，说明页面结构可能已变化，抛出 PageParseError
            - JSON-LD 解析失败时各字段使用空默认值，不影响流程

        Returns:
            Paper: 包含提取元数据的 Paper 实例。

        Raises:
            NonResearchPageError: 页面不是学术论文（如 News/Podcast）。
            PageParseError:     无法获取 dc.type，页面结构可能已变化。
        """
        sel = Selector(text=self.html)

        # ─── 页面类型过滤：通过 dc.type 排除非论文页面 ───
        # Nature 页面的 dc.type 值：
        #   "OriginalPaper" → 正常研究论文，需要解析
        #   "News" / "Podcast" / "Highlight" / ... → 非论文，抛异常跳过
        dctype = sel.css('meta[name="dc.type"]::attr(content)').get() or ""
        if dctype == "":
            raise PageParseError(
                "No dc.type in Nature page, maybe the page structure has changed."
            )
        if dctype != "OriginalPaper":
            raise NonResearchPageError("This Nature page is not OriginalPaper.")

        # ─── 获取 PDF 下载链接 ───
        # Nature 的 PDF 链接格式为相对路径：/articles/s41567-026-03184-9.pdf
        # 通过 data-test="download-pdf" 属性的 a 标签定位
        pdf_url_part = sel.css('a[data-test="download-pdf"]::attr(href)').get() or ""
        if pdf_url_part:
            # 拼接完整 URL
            pdf_url = "https://www.nature.com" + pdf_url_part
        else:
            pdf_url = None

        # 初始化默认值（防止 JSON-LD 或 meta 标签缺失时出错）
        title = ""
        date = ""
        journal = ""
        abstract = ""
        authors = []

        # ─── 从 <meta> 标签提取 DOI 和 URL ───
        # dc.Identifier 带有 scheme="doi" 属性，精确匹配 DOI (注意 nature page 拿到的是 doi: 开头的 DOI)
        doi_raw = sel.css('meta[name="dc.Identifier"]::attr(content)').get() or ""
        doi = doi_raw.removeprefix("doi:") if doi_raw else ""
        # 从 canonical link 获取标准 URL
        url = sel.css('link[rel="canonical"]::attr(href)').get() or ""

        # ─── 从 JSON-LD 结构化数据中提取元数据 ───
        # Nature 页面在 <script type="application/ld+json"> 中提供了丰富的
        # 结构化元数据，包含 headline(标题)、description(描述)、keywords、
        # author(作者)、datePublished(日期) 等信息。
        # 注意：JSON-LD 中的 description 有时会混入期刊宣传语而非纯摘要，
        #       因此优先使用正文区域的摘要文本，JSON-LD 数据作为备用。
        json_ld_text = sel.css('script[type="application/ld+json"]::text').get()
        if json_ld_text:
            try:
                data = json.loads(json_ld_text).get("mainEntity")
            except (json.JSONDecodeError, KeyError):
                data = None
            if data:
                title = data.get("headline", "")
                # abstract_jsonld = data.get("description", "")  # 备用摘要（当前未使用，保留供后续参考）
                # keywords = data.get("keywords", [])  # 备用关键词（当前未使用，保留供后续参考）
                authors = [a["name"] for a in data.get("author", [])]
                date = data.get("datePublished", "")
                # 标准化日期格式: "2026-05-19T00:00:00Z" → "2026-05-19"
                if "T" in date:
                    date = date.split("T")[0]

        # ─── 从 <meta> 标签提取期刊名称 ───
        # 优先使用 citation_journal_title（标准引用格式）
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        # 备用方案：使用 dc.Publisher（如 "Nature Publishing Group"）
        if not journal:
            journal = sel.css('meta[name="dc.Publisher"]::attr(content)').get() or ""

        # ─── 从正文区域提取摘要（优先于 JSON-LD） ───
        # #Abs1-content 是 Nature 文章页面的摘要正文区域，
        # 其文本比 JSON-LD 中的 description 更纯净，后者可能混入非摘要内容。
        paragraphs = sel.css("#Abs1-content *::text").getall()
        paragraphs = [
            p.strip() for p in paragraphs if p.strip()
        ]
        abstract_article = " ".join(paragraphs)
        if abstract_article:
            abstract = abstract_article

        # Nature 正文在 HTML 中直接包含 MathJAX 的原始 LaTeX 源码，
        # 可以直接从页面中提取全文内容，页面结构清晰易解析。

        return Paper(doi=doi, title=title, date=date, journal=journal,
                     abstract=abstract, authors=authors, pdf_url=pdf_url, url=url)


class ScienceScraper(BasePublisherScraper):
    """Science 系列期刊爬虫。

    支持 Science 主刊及其子刊。

    元数据提取策略：
        - 主要依赖 <meta> 标签中的 dc.* 系列元数据。
        - 摘要通过 XPath 定位 section#abstract 下 role="paragraph" 的 div 元素。
        - 页面类型通过 dc.Type 过滤，仅处理 "research-article"。

    与 Nature 的差异：
        - Science 的元数据主要存放在 dc.* 标签中，而非 JSON-LD。
        - 作者字段使用 dc.Creator（多值，而非 JSON-LD 的 author 数组）。
        - PDF 下载链接通过 href 包含 "download=true" 的 a 标签定位。
    """

    def parse_page(self):
        """解析 Science 论文页面。

        元数据提取来源：
            - title:     <meta name="dc.Title"> 的 content 属性
            - journal:   <meta name="citation_journal_title"> 的 content 属性
            - authors:   <meta name="dc.Creator"> 的 content 属性（多值）
            - date:      <meta name="dc.Date"> 的 content 属性
            - doi:       <meta name="dc.Identifier" scheme="doi"> 的 content 属性
            - pdf_url:   通过 a[href*="download=true"] 的 href 获取，
                         拼接 "https://www.science.org" 前缀
            - abstract:  通过 XPath 定位 section#abstract 下
                         div[role="paragraph"] 的全部文本内容

        边界处理：
            - 若 dc.Type 不是 "research-article"，抛出 NonResearchPageError
            - 若 dc.Type 为空，说明页面结构可能已变化，抛出 PageParseError

        Returns:
            Paper: 包含提取元数据的 Paper 实例。

        Raises:
            NonResearchPageError: 页面不是研究论文。
            PageParseError:     无法获取 dc.Type，页面结构可能已变化。
        """
        sel = Selector(text=self.html)

        # ─── 页面类型过滤 ───
        # 一级：altmetric_type 检测（覆盖 CrossRef 发现的非研究文章，如 news/blog）
        # 这类页面通常没有 dc.Type meta，但仍可被识别为非研究文章
        altmetric_type = sel.css(
            'meta[name="altmetric_type"]::attr(content)'
        ).get()
        if altmetric_type is not None:
            raise NonResearchPageError(
                f"Science page has altmetric_type='{altmetric_type}', "
                "not a research article"
            )

        # 二级：dc.Type 检测（覆盖 RSS 来源的标准页面）
        dctype = sel.css('meta[name="dc.Type"]::attr(content)').get() or ""
        if dctype == "":
            # 三级：og:type 兜底 — 当 dc.Type 缺失但 og:type 存在时，
            # 说明页面正常加载（有 meta），只是不属于有 dc.Type 注释的
            # 研究论文（如 Careers / Working Life / News 等），视为非研究文章。
            og_type = sel.css(
                'meta[property="og:type"]::attr(content)'
            ).get() or ""
            if og_type:
                raise NonResearchPageError(
                    f"Science page has og:type='{og_type}' but no dc.Type, "
                    "not a research article"
                )
            raise PageParseError(
                "No dc.Type or og:type in Science page, "
                "maybe the page structure has changed."
            )
        if dctype != "research-article":
            raise NonResearchPageError("This Science page is not research-article.")

        # ─── 从 <meta> 标签提取元数据 ───
        title = sel.css('meta[name="dc.Title"]::attr(content)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="dc.Creator"]::attr(content)').getall()  # Science 用 dc.Creator 存作者
        date = sel.css('meta[name="dc.Date"]::attr(content)').get() or ""
        doi = (
            sel.css('meta[name="dc.Identifier"][scheme="doi"]::attr(content)').get()
            or ""
        )

        # ─── 获取 PDF 下载链接 ───
        # PDF 链接格式如 "/doi/pdf/10.1126/science.adx9954?download=true"
        pdf_url_part = sel.css('a[href*="download=true"]::attr(href)').get()
        if pdf_url_part:
            pdf_url = "https://www.science.org" + pdf_url_part
        else:
            pdf_url = None

        # ─── 从正文区域提取摘要 ───
        # 使用 XPath 的 string() 函数获取 section#abstract 下
        # 所有 div[role="paragraph"] 的完整文本内容（含嵌套元素文本）。
        # string() 函数会递归获取所有后代文本节点并拼接。
        abstract = (
            sel.xpath('string(//section[@id="abstract"]//div[@role="paragraph"])').get()
            or ""
        )
        # 清理不可见字符（多个空白字符压缩为单个空格）
        abstract = (
            re.sub(r"\s+", " ", abstract).strip() if abstract else ""
        )

        # Science 的正文 HTML 结构相对规整，可直接提取全文内容。

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
    """Cambridge University Press（剑桥大学出版社）期刊爬虫。

    元数据提取策略：
        - 主要依赖 <meta> 标签中的 citation_* 系列元数据。
        - 剑桥出版社的特有优势：摘要直接写入 <meta name="citation_abstract">
          标签中，无需从正文 HTML 区域提取，提取简单且不易出错。
        - 关键词通过 citation_keywords 获取，以分号分隔。
    """

    def parse_page(self):
        """解析 Cambridge 论文页面。

        元数据提取来源：
            - title:     <meta name="citation_title"> 的 content 属性
            - url:       <link rel="canonical"> 的 href 属性
            - journal:   <meta name="citation_journal_title"> 的 content 属性
            - authors:   <meta name="citation_author"> 的 content 属性（多值）
            - date:      <meta name="citation_online_date"> 的 content 属性
            - keywords:  <meta name="citation_keywords"> 的 content 属性，
                         分号分隔的字符串，解析为列表。
                         末尾可能出现单独 ; 导致的空字符串，已做过滤处理。
            - pdf_url:   <meta name="citation_pdf_url"> 的 content 属性
            - doi:       <meta name="citation_doi"> 的 content 属性
            - abstract:  <meta name="citation_abstract"> 的 content 属性
                         （剑桥的亮点：摘要直接写在 meta 标签中）

        Returns:
            Paper: 包含提取元数据的 Paper 实例。
        """
        sel = Selector(text=self.html)

        # ─── 从 <meta> 标签提取元数据 ───
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        canonical_url = sel.css('link[rel="canonical"]::attr(href)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        date = sel.css('meta[name="citation_online_date"]::attr(content)').get() or ""

        # 解析关键词（分号分隔的字符串）
        keywords_str = sel.css('meta[name="citation_keywords"]::attr(content)').get()
        if keywords_str:
            # 过滤末尾可能出现的单独分号导致的空字符串
            keywords_str = [
                item.strip() for item in keywords_str.split(";") if item.strip()
            ]

        pdf_url = sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""

        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""

        # ─── 从 <meta> 标签提取摘要 ───
        # 剑桥大学出版社在 citation_abstract 中直接提供了摘要文本，
        # 无需从复杂的 HTML 正文区域解析，这是其尤为便利的特点。
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
    """AIP (American Institute of Physics) 期刊爬虫。

    支持 Applied Physics Letters、Journal of Applied Physics 等 AIP 旗下期刊。

    元数据提取策略：
        - 主要依赖 <meta> 标签中的 citation_* 系列元数据。
        - 日期字段使用 <meta name="publish_date">（非 citation_date），
          这是 AIP 的特有标签名。
        - 摘要通过 XPath 定位 section.abstract[aria-label="Main abstract"]
          区域提取。
    """

    def parse_page(self):
        """解析 AIP 论文页面。

        元数据提取来源：
            - title:     <meta name="citation_title"> 的 content 属性
            - url:       <link rel="canonical"> 的 href 属性
            - journal:   <meta name="citation_journal_title"> 的 content 属性
            - authors:   <meta name="citation_author"> 的 content 属性（多值）
            - date:      <meta name="publish_date"> 的 content 属性
                         （注意：AIP 使用 publish_date 而非 citation_date）
            - pdf_url:   <meta name="citation_pdf_url"> 的 content 属性
            - doi:       <meta name="citation_doi"> 的 content 属性
            - abstract:  通过 XPath 定位 section.abstract[aria-label="Main abstract"]
                         的全部文本内容

        技术细节：
            - XPath string() 函数会递归获取所有后代文本节点，适合提取
              包含嵌套格式标签（如 <sup>, <sub>, <i>）的摘要文本。
             - 提取后使用正则 re.sub(r"\\s+", " ", ...) 清理多余的空白字符。

        Returns:
            Paper: 包含提取元数据的 Paper 实例。
        """
        sel = Selector(text=self.html)

        # ─── 从 <meta> 标签提取元数据 ───
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        canonical_url = sel.css('link[rel="canonical"]::attr(href)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        # AIP 的日期存放在 publish_date 而非 citation_date 标签中
        date = sel.css('meta[name="publish_date"]::attr(content)').get() or ""

        pdf_url = sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""

        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""

        # ─── 从正文区域提取摘要 ───
        # 通过 XPath 定位：具有 class="abstract" 且 aria-label="Main abstract"
        # 的 section 元素，使用 string() 获取其全部文本内容。
        # aria-label="Main abstract" 用于区分页面可能存在的其他摘要区域。
        abstract = (
            sel.xpath(
                'string(//section[@class="abstract"][@aria-label="Main abstract"])'
            ).get()
            or ""
        )
        # 清理不可见字符，压缩多个空白为单个空格
        abstract = (
            re.sub(r"\s+", " ", abstract).strip() if abstract else ""
        )

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
    # IOP 对部分文章有 TLS 指纹检测（wget 无法获取），
    # 浏览器失败时用 curl_cffi（带 TLS 指纹伪造）回退。
    http_fallback_mode = "curl_cffi"
    http_fallback_strategy = "fallback"

    """IOP (Institute of Physics) 期刊爬虫。

    支持 IOP Science 平台上的期刊，如 Journal of Physics 系列、
    Plasma Physics and Controlled Fusion 等。

    元数据提取策略：
        - 主要依赖 <meta> 标签中的 citation_* 系列元数据。
        - 摘要通过 XPath 定位 div.article-abstract 下
          div.article-text（含 class 匹配）区域提取。
    """

    def parse_page(self):
        """解析 IOP 论文页面。

        元数据提取来源：
            - title:     <meta name="citation_title"> 的 content 属性
            - url:       <link rel="canonical"> 的 href 属性
            - journal:   <meta name="citation_journal_title"> 的 content 属性
            - authors:   <meta name="citation_author"> 的 content 属性（多值）
            - date:      <meta name="citation_online_date"> 的 content 属性
            - pdf_url:   <meta name="citation_pdf_url"> 的 content 属性
            - doi:       <meta name="citation_doi"> 的 content 属性
            - abstract:  通过 XPath 定位 div.article-abstract 下
                         div[contains(@class, "article-text")] 的全部文本内容

        技术细节：
            - 摘要区域 class 名可能包含多个值（如 "article-text clearfix"），
              因此使用 contains(@class, "article-text") 进行模糊匹配。
             - 提取后使用正则 re.sub(r"\\s+", " ", ...) 清理多余的空白字符。

        Returns:
            Paper: 包含提取元数据的 Paper 实例。
        """
        sel = Selector(text=self.html)

        # ─── 从 <meta> 标签提取元数据 ───
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        canonical_url = sel.css('link[rel="canonical"]::attr(href)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        date = sel.css('meta[name="citation_online_date"]::attr(content)').get() or ""

        pdf_url = sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""

        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""

        # ─── 从正文区域提取摘要 ───
        # 通过 XPath 定位：class 为 article-abstract 的 div 下，
        # 带有 article-text class（可能含多个 class）的 div 元素，
        # 使用 string() 获取其全部文本内容。
        abstract = (
            sel.xpath(
                'string(//div[@class="article-abstract"]//div[contains(@class, "article-text")])'
            ).get()
            or ""
        )
        # 清理不可见字符，压缩多个空白为单个空格
        abstract = (
            re.sub(r"\s+", " ", abstract).strip() if abstract else ""
        )

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
    """Optica（原 OSA）期刊爬虫。

    支持 Optica、Optics Express、Optics Letters 等 Optica Publishing Group
    旗下的光学领域期刊。

    Optica / Optics Express 是 Open Access 期刊，CrossRef 返回完整 abstract，
    因此 Phase C 会跳过浏览器访问（通过 ``skip_phase_c_if_crossref_abstract``
    类属性控制），仅在有需要时才在 Phase E2 做延迟页面访问补齐 pdf_url。

    元数据提取策略：
        - 主要依赖 <meta> 标签中的 citation_* 系列元数据。
        - 摘要通过 XPath 定位 div#articleBody 下 h2#Abstract 之后
          的第一个兄弟 div 元素，这是 Optica 页面摘要区域的固定 DOM 结构。

    特殊说明：
        - Optica 网站对非美国 IP 较为敏感，可能触发额外的反爬检测。
          建议通过 start_browser 的 proxy 参数配置美国代理，例如：
          proxy={"server": "http://127.0.0.1:10808"}
        - Optica / Optics Express 的反爬策略具有"积累效应"：短时间连续成功
          爬取一定篇数后会触发 CF 拦截，且成功率随连续成功数递减。
          默认的 3-5s 页面间隔偏低，如需高频抓取建议放宽到 10-20s。
        - optica 和 opex 都映射到 publisher: optica，共享同一 browser session
          和连续失败熔断计数器。一个期刊被拦会连带影响另一个。
          如两者都启用，考虑拆分为独立 publisher 标识。

    Attributes:
        skip_phase_c_if_crossref_abstract: True（Phase C 跳过拥有 Crossref 摘要的论文）
    """
    skip_phase_c_if_crossref_abstract = True

    def parse_page(self):
        """解析 Optica 论文页面。

        元数据提取来源：
            - title:     <meta name="citation_title"> 的 content 属性
            - journal:   <meta name="citation_journal_title"> 的 content 属性
            - authors:   <meta name="citation_author"> 的 content 属性（多值）
            - date:      <meta name="citation_online_date"> 的 content 属性
            - pdf_url:   <meta name="citation_pdf_url"> 的 content 属性
            - doi:       <meta name="citation_doi"> 的 content 属性
            - abstract:  通过 XPath 定位 div#articleBody 下
                         h2#Abstract/following-sibling::div[1] 的全部文本内容

        技术细节：
            - 使用 following-sibling::div[1] 精确定位 Abstract 标题之后
              的第一个 div 兄弟元素，这是 Optica 页面中摘要的固定位置。
             - 提取后使用正则 re.sub(r"\\s+", " ", ...) 清理多余的空白字符。

        Returns:
            Paper: 包含提取元数据的 Paper 实例。
        """
        sel = Selector(text=self.html)

        # ─── 从 <meta> 标签提取元数据 ───
        title = sel.css('meta[name="citation_title"]::attr(content)').get() or ""
        journal = (
            sel.css('meta[name="citation_journal_title"]::attr(content)').get() or ""
        )
        authors = sel.css('meta[name="citation_author"]::attr(content)').getall()
        date = sel.css('meta[name="citation_online_date"]::attr(content)').get() or ""

        pdf_url = sel.css('meta[name="citation_pdf_url"]::attr(content)').get() or ""

        doi = sel.css('meta[name="citation_doi"]::attr(content)').get() or ""

        # ─── 从正文区域提取摘要 ───
        # 通过 XPath 定位：#articleBody 容器内，id="Abstract" 的 h2 标题后的
        # 第一个 div 兄弟元素（following-sibling::div[1]），即摘要内容区域。
        abstract = (
            sel.xpath(
                'string(//div[@id="articleBody"]/h2[@id="Abstract"]/following-sibling::div[1])'
            ).get()
            or ""
        )
        # 清理不可见字符，压缩多个空白为单个空格
        abstract = (
            re.sub(r"\s+", " ", abstract).strip() if abstract else ""
        )

        # 检测反爬拦截：title 有值但 abstract 为空，
        # #articleBody 缺失说明正文被拦截（非 Cloudflare，不会触发现有 CF 检测）
        if title and not abstract:
            if not sel.xpath('//div[@id="articleBody"]'):
                raise PageParseError(
                    "Optica anti-bot blocked: article body (#articleBody) not found"
                )

        return Paper(
            doi=doi,
            date=date,
            journal=journal,
            title=title,
            abstract=abstract,
            authors=authors,
            pdf_url=pdf_url,
        )


# ──────────────────────────────────────────────────────────
# 测试入口（各出版商的测试代码已注释，按需取消注释使用）
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pprint import pprint

    # Nature 测试
    # url = "https://www.nature.com/articles/s41567-026-03184-9" # OriginalPaper
    # url = "https://www.nature.com/articles/d41586-026-01575-9" # podcast
    # url = "https://www.nature.com/articles/d41586-026-01504-w" # highlight
    # url = "https://www.nature.com/articles/d41586-026-01558-w" # news
    # nScraper = NatureScraper("./TEST/publisher_test/chrome_cache/nature")
    # nScraper.start_browser()
    # nScraper.fetch_page(url)
    # paper = nScraper.parse_page()
    # pprint(paper)
    # html_path = Path("./TEST/publisher_test/html_example/nature_news.html")
    # nScraper.save_page(html_path)
    # nScraper.close()

    # Science 测试
    # url = "https://www.science.org/doi/abs/10.1126/science.adx9954?af=R"
    # sScraper = ScienceScraper("./TEST/publisher_test/chrome_cache/science")
    # sScraper.start_browser()
    # sScraper.fetch_page(url)
    # paper = sScraper.parse_page()
    # pprint(paper)
    # html_path = Path("./TEST/publisher_test/html_example/science.html")
    # sScraper.save_page(html_path)
    # sScraper.close()

    # APS 测试
    # url = "https://journals.aps.org/prl/abstract/10.1103/yq7c-8bsv"
    # apsScraper = APSScraper("./TEST/publisher_test/chrome_cache/aps")
    # apsScraper.start_browser()
    # apsScraper.fetch_page(url)
    # paper = apsScraper.parse_page()
    # pprint(paper)
    # html_path = Path("./TEST/publisher_test/html_example/aps.html")
    # apsScraper.save_page(html_path)
    # apsScraper.close()

    # Cambridge 测试
    # url = "https://dx.doi.org/10.1017/hpl.2025.10090?rft_dat=source%3Ddrss"
    # cScraper = CambridgeScraper("./TEST/publisher_test/chrome_cache/cambridge")
    # cScraper.start_browser()
    # cScraper.fetch_page(url)
    # paper = cScraper.parse_page()
    # pprint(paper)
    # html_path = Path("./TEST/publisher_test/html_example/cambridge.html")
    # cScraper.save_page(html_path)
    # cScraper.close()

    # AIP 测试
    # url = "https://pubs.aip.org/aip/apl/article/128/19/194001/3391238/A-cavity-mediated-reconfigurable-coupling-scheme"
    # aipScraper = AIPScraper("./TEST/publisher_test/chrome_cache/AIP")
    # aipScraper.start_browser()
    # aipScraper.fetch_page(url)
    # paper = aipScraper.parse_page()
    # pprint(paper)
    # html_path = Path("./TEST/publisher_test/html_example/aip.html")
    # aipScraper.save_page(html_path)
    # aipScraper.close()

    # IOP 测试
    # url = "https://iopscience.iop.org/article/10.1088/1361-6587/ae5adb"
    # iopScraper = IOPScraper("./TEST/publisher_test/chrome_cache/IOP")
    # iopScraper.start_browser()
    # iopScraper.fetch_page(url)
    # paper = iopScraper.parse_page()
    # pprint(paper)
    # html_path = Path("./TEST/publisher_test/html_example/iop.html")
    # iopScraper.save_page(html_path)
    # iopScraper.close()

    # Optica 测试
    # url = "https://opg.optica.org/abstract.cfm?URI=optica-13-5-951"
    # url = "https://opg.optica.org/optica/fulltext.cfm?uri=optica-13-5-867"
    # optScraper = OpticaScraper("./TEST/publisher_test/chrome_cache/Optica")
    # optScraper.start_browser(proxy={"server": "http://127.0.0.1:10808"}) # Optica 可能需要美国代理才不触发检测
    # optScraper.fetch_page(url, 5000)
    # paper = optScraper.parse_page()
    # pprint(paper)
    # html_path = Path("./TEST/publisher_test/html_example/optica.html")
    # optScraper.save_page(html_path)
    # optScraper.close()
