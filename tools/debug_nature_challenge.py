#!/usr/bin/env python3
"""
Nature Fastly Client Challenge 诊断工具。

用 headful 浏览器打开 Nature 文章页，逐步等待并报告页面状态，
帮助你直观地看到浏览器到底遇到了什么（X11 转发可看到真实窗口）。

用法:
    python tools/debug_nature_challenge.py [--url URL] [--timeout TIMEOUT]
"""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cloakbrowser import launch_persistent_context
from parsel import Selector


# 检测 Fastly Client Challenge
def check_client_challenge(html, title=""):
    """检测是否为 Fastly Client Challenge 页面。"""
    title_lower = title.lower()
    html_lower = html.lower()
    return "client challenge" in title_lower


# 检测 Cloudflare Challenge
def check_cloudflare(html):
    """检测是否为 Cloudflare Challenge 页面。"""
    return any(kw in html for kw in [
        "challenge-platform", "_cf_chl_opt", "cf-browser-verification",
    ])


# 检测 Radware
def check_radware(html, title=""):
    html_lower = html.lower()
    title_lower = title.lower()
    return "radware" in html_lower or "radware" in title_lower


# 检测 bot manager
def check_bot_manager(html, title=""):
    html_lower = html.lower()
    title_lower = title.lower()
    return "bot manager" in html_lower or "bot manager" in title_lower


# 检测 JS 禁用
def check_js_disabled(html):
    return "javascript is disabled" in html.lower()


# 检测 Fastly logo (Nature 特有)
def check_fastly_logo(html):
    return "www.nature.com/fastly/logo" in html or "fastly" in html.lower()


# 检测 Error 页面
def check_error_page(html):
    sel = Selector(text=html)
    error_div = sel.css("div.error-page, div.error-container").get()
    error_span = sel.css("span.error-span, span.oops").get()
    return bool(error_div) or bool(error_span)


# 检测 captcha 标题
def check_captcha_title(title):
    return "captcha" in title.lower()


def check_nature_meta(sel):
    """检查 Nature 页面的关键 meta 标签。"""
    return {
        "dc.type": sel.css('meta[name="dc.type"]::attr(content)').get(),
        "dc.Identifier": sel.css('meta[name="dc.Identifier"]::attr(content)').get(),
        "citation_title": sel.css('meta[name="citation_title"]::attr(content)').get(),
        "citation_doi": sel.css('meta[name="citation_doi"]::attr(content)').get(),
        "citation_journal_title": sel.css('meta[name="citation_journal_title"]::attr(content)').get(),
        "has_json_ld": bool(sel.css('script[type="application/ld+json"]').get()),
        "has_dc_type": bool(sel.css('meta[name="dc.type"]').get()),
    }


def anti_detect_js():
    """返回反检测 JS 代码（与 publisher.py 中的注入一致）。"""
    return """
    () => {
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        window.navigator.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
    }
    """


def diagnose(url, timeout_ms, use_js):
    """逐步诊断一个 Nature URL。"""
    print(f"\n{'='*70}")
    print(f"  🔍 诊断: {url}")
    print(f"  ⏱  超时: {timeout_ms}ms | JS 注入: {'✅' if use_js else '❌'}")
    print(f"{'='*70}")

    tmpdir = tempfile.mkdtemp(prefix="debug_nature_")

    context = launch_persistent_context(
        user_data_dir=tmpdir,
        headless=False,  # X11 转发可见
    )
    page = context.new_page()

    if use_js:
        page.evaluate(anti_detect_js())
        print("  ✅ 反检测 JS 已注入")

    print("\n  📍 第 1 步: goto() 加载页面...")
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=120000)
        status = resp.status if resp else "N/A"
        print(f"     HTTP 状态: {status}")
        print(f"     当前 URL:  {page.url}")
    except Exception as e:
        print(f"     ⚠️  goto 异常: {e}")
        print(f"     当前 URL:  {page.url}")

    # 首次快照
    html = page.content()
    title = page.title()
    print(f"\n  📍 第 2 步: goto() 后立即抓取 (timeout=0)")
    print(f"     页面标题:   [{title}]")
    print(f"     HTML 大小:  {len(html)} bytes")
    print(f"     标题检测:   {'Client Challenge' if check_client_challenge(html, title) else '—'}")

    # 5 秒后
    print(f"\n  📍 第 3 步: 等待 {timeout_ms}ms 后...")
    page.wait_for_timeout(timeout_ms)
    html = page.content()
    title = page.title()
    print(f"     页面标题:   [{title}]")
    print(f"     HTML 大小:  {len(html)} bytes")
    print(f"     最终 URL:   {page.url}")

    # 综合分析
    print(f"\n  📊 页面分析:")
    analysis = {
        "title": title,
        "final_url": page.url,
        "html_length": len(html),
        "client_challenge": check_client_challenge(html, title),
        "cloudflare": check_cloudflare(html),
        "radware": check_radware(html, title),
        "bot_manager": check_bot_manager(html, title),
        "js_disabled": check_js_disabled(html),
        "fastly_logo": check_fastly_logo(html),
        "error_page": check_error_page(html),
        "captcha_title": check_captcha_title(title),
        "script_src_count": html.count("<script"),
        "meta": check_nature_meta(Selector(text=html)),
    }
    for k, v in analysis.items():
        if k == "meta":
            print(f"\n     🏷️  meta 标签:")
            for mk, mv in v.items():
                print(f"       {mk}: {mv or '—'}")
        elif k in ("client_challenge", "cloudflare", "radware", "bot_manager",
                   "js_disabled", "fastly_logo", "error_page", "captcha_title"):
            print(f"     {'⚠️' if v else '✅'}  {k}: {'YES' if v else 'no'}")
        else:
            print(f"     📌  {k}: {v}")

    # 判断结论
    print(f"\n  🎯 结论:")
    if check_nature_meta(Selector(text=html)).get("dc.type") == "OriginalPaper":
        print("     ✅ 页面正常加载 — 是 Nature 论文页（dc.type = OriginalPaper）")
    elif check_client_challenge(html, title):
        print("     ❌ Fastly Client Challenge — 浏览器指纹未通过验证")
        if not use_js:
            print("     💡 建议: 启用 --js 选项注入反检测 JS 后重试")
    elif check_cloudflare(html):
        print("     ❌ Cloudflare Challenge — 需要更长时间等待")
        print("     💡 建议: 用 --timeout 90000 增加等待时间")
    elif check_error_page(html):
        print("     ❌ 错误页面 — 脚本加载失败或浏览器被拦截")
        print("     💡 建议: 检查 X11 窗口中的实际渲染内容")
    elif check_fastly_logo(html):
        print("     ❌ Fastly 相关页面 — 可能 CDN 层拦截")
    else:
        print("     ❓ 未知状态 — 查看 X11 窗口判断")

    context.close()
    return analysis


def main():
    parser = argparse.ArgumentParser(description="Nature Fastly Client Challenge 诊断工具")
    parser.add_argument("--url", default="",
                        help="Nature 文章 URL（默认取一个近期文章）")
    parser.add_argument("--timeout", type=int, default=45000,
                        help="页面加载后等待时间 (ms)，默认 45000")
    parser.add_argument("--no-js", action="store_true",
                        help="不注入反检测 JS（默认注入）")
    args = parser.parse_args()

    url = args.url or "https://www.nature.com/articles/s41567-026-03320-5"

    print(f"\n🧪 Nature Client Challenge 诊断工具")
    print(f"   确保在 X11 环境下运行（ssh -X 或直接桌面）")
    print(f"   你将看到一个浏览器窗口自动打开和关闭")

    # 第一次：不带 JS 注入
    diagnose(url, args.timeout, use_js=not args.no_js)

    # 如果默认开启了 JS，再跑一次不带 JS 的对比？
    if not args.no_js:
        print(f"\n{'='*70}")
        print(f"  🔄 为对比，再用不带 JS 注入的方式跑一次")
        print(f"{'='*70}")
        diagnose(url, args.timeout, use_js=False)

    print(f"\n✅ 诊断完成")


if __name__ == "__main__":
    main()
