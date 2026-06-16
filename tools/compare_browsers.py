#!/usr/bin/env python3
"""
Playwright vs Cloakbrowser 对比诊断工具。

测试 4 种浏览器配置，找出哪个能正常加载 Nature 文章页。
每种配置各自启动/关闭，报告结果。

用法:
    python tools/compare_browsers.py [--url URL] [--timeout TIMEOUT]
"""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parsel import Selector


# ── HTML 检测函数（与 debug_nature_challenge.py 一致） ──

def check_client_challenge(html, title=""):
    title_lower = title.lower()
    return "client challenge" in title_lower


def check_cloudflare(html):
    return any(kw in html for kw in [
        "challenge-platform", "_cf_chl_opt", "cf-browser-verification",
    ])


def check_nature_meta(sel):
    return {
        "dc.type": sel.css('meta[name="dc.type"]::attr(content)').get(),
        "dc.Identifier": sel.css('meta[name="dc.Identifier"]::attr(content)').get(),
        "citation_title": sel.css('meta[name="citation_title"]::attr(content)').get(),
        "citation_doi": sel.css('meta[name="citation_doi"]::attr(content)').get(),
        "has_json_ld": bool(sel.css('script[type="application/ld+json"]').get()),
    }


# ── 反检测 JS ──

def anti_detect_js():
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


# ── 分析页面结果 ──

def analyze(html, title, final_url):
    sel = Selector(text=html)
    meta = check_nature_meta(sel)
    dc_type = meta.get("dc.type")
    is_normal_page = dc_type == "OriginalPaper" or bool(meta.get("citation_doi"))

    return {
        "success": is_normal_page,
        "title": title,
        "final_url": final_url,
        "html_length": len(html),
        "client_challenge": check_client_challenge(html, title),
        "cloudflare": check_cloudflare(html),
        "meta": meta,
    }


# ── Test 1: Playwright 纯原生（无 cloakbrowser） ──

def test_playwright_plain(url, timeout_ms):
    """用原生 Playwright（stock Chromium），不加任何反检测。"""
    from playwright.sync_api import sync_playwright

    print(f"\n  🟦 [1/4] Playwright 原生 — stock Chromium，无改动")
    print(f"  └─ 测试原生 Playwright 的 Chromium 能否通过 Fastly 检测\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(timeout_ms)
        html = page.content()
        title = page.title()
        result = analyze(html, title, page.url)
        browser.close()
    return result


# ── Test 2: Playwright + add_init_script ──

def test_playwright_with_js(url, timeout_ms):
    """原生 Playwright + 用 add_init_script 注入反检测 JS，模拟修复后的 publisher.py。"""
    from playwright.sync_api import sync_playwright

    print(f"\n  🟦 [2/4] Playwright + add_init_script — 与 publisher.py 修复方案一致")
    print(f"  └─ 验证 add_init_script 方案是否有效（排除 cloakbrowser 因素）\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_init_script(anti_detect_js())
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(timeout_ms)
        html = page.content()
        title = page.title()
        result = analyze(html, title, page.url)
        browser.close()
    return result


# ── Test 3: Cloakbrowser（无额外 JS 注入） ──

def test_cloakbrowser_plain(url, timeout_ms):
    """Cloakbrowser，不加 JS 注入。即升级前的 publisher.py 行为。"""
    from cloakbrowser import launch_persistent_context

    print(f"\n  🟥 [3/4] Cloakbrowser 原生 — 无 JS 注入（升级前行为）")
    print(f"  └─ 重现升级前的现象\n")

    tmpdir = tempfile.mkdtemp(prefix="cmp_cb_plain_")
    context = launch_persistent_context(
        user_data_dir=tmpdir,
        headless=False,
    )
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(timeout_ms)
    html = page.content()
    title = page.title()
    result = analyze(html, title, page.url)
    context.close()
    return result


# ── Test 4: Cloakbrowser + add_init_script ──

def test_cloakbrowser_with_js(url, timeout_ms):
    """Cloakbrowser + add_init_script（当前生产配置，即修复后的 publisher.py）。"""
    from cloakbrowser import launch_persistent_context

    print(f"\n  🟥 [4/4] Cloakbrowser + add_init_script — 当前生产配置")
    print(f"  └─ 测试当前 publisher.py 的完整行为\n")

    tmpdir = tempfile.mkdtemp(prefix="cmp_cb_js_")
    context = launch_persistent_context(
        user_data_dir=tmpdir,
        headless=False,
    )
    page = context.new_page()
    context.add_init_script(anti_detect_js())
    page.goto(url, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(timeout_ms)
    html = page.content()
    title = page.title()
    result = analyze(html, title, page.url)
    context.close()
    return result


# ── 结果格式化 ──

def print_result(label, result):
    icon = "✅" if result["success"] else "❌"
    verdict = "正常加载 ✅" if result["success"] else "拦截 ❌"
    print(f"\n  {icon} {label}: {verdict}")
    print(f"    标题:       [{result['title']}]")
    print(f"    HTML 大小:  {result['html_length']} bytes")
    print(f"    最终 URL:   {result['final_url']}")
    if result["client_challenge"]:
        print(f"    ⚠️  检测到 Fastly Client Challenge")
    if result["cloudflare"]:
        print(f"    ⚠️  检测到 Cloudflare Challenge")
    if result["meta"]["dc.type"]:
        print(f"    dc.type:    {result['meta']['dc.type']}")
    if result["meta"]["citation_doi"]:
        print(f"    citation_doi: {result['meta']['citation_doi']}")


# ── 主流程 ──

def main():
    parser = argparse.ArgumentParser(description="Playwright vs Cloakbrowser 对比诊断")
    parser.add_argument("--url", default="",
                        help="Nature 文章 URL")
    parser.add_argument("--timeout", type=int, default=15000,
                        help="页面加载后等待时间 (ms)，默认 15000")
    parser.add_argument("--skip-pw", action="store_true",
                        help="跳过 Playwright 测试")
    parser.add_argument("--skip-cb", action="store_true",
                        help="跳过 cloakbrowser 测试")
    args = parser.parse_args()

    url = args.url or "https://www.nature.com/articles/s41567-026-03320-5"

    print(f"\n{'='*70}")
    print(f"  🧪 Playwright vs Cloakbrowser 对比诊断")
    print(f"  URL: {url}")
    print(f"  等待时间: {args.timeout}ms")
    print(f"  需 X11 环境 (ssh -X)\n")
    print(f"  控制组: wget 成功加载 ({442}KB) — HTTP 层无封锁")
    print(f"{'='*70}")

    results = {}

    if not args.skip_pw:
        results["pw_plain"] = test_playwright_plain(url, args.timeout)
        results["pw_js"] = test_playwright_with_js(url, args.timeout)

    if not args.skip_cb:
        results["cb_plain"] = test_cloakbrowser_plain(url, args.timeout)
        results["cb_js"] = test_cloakbrowser_with_js(url, args.timeout)

    # ── 汇总 ──
    print(f"\n\n{'='*70}")
    print(f"  📊 汇总对比")
    print(f"{'='*70}\n")

    labels = {
        "pw_plain": "Playwright 原生",
        "pw_js": "Playwright + add_init_script",
        "cb_plain": "Cloakbrowser 原生",
        "cb_js": "Cloakbrowser + add_init_script",
    }

    for key, label in labels.items():
        if key in results:
            print_result(label, results[key])

    # ── 结论 ──
    print(f"\n{'='*70}")
    print(f"  🎯 结论")
    print(f"{'='*70}\n")

    pw_ok = results.get("pw_plain", {}).get("success") or results.get("pw_js", {}).get("success")
    cb_ok = results.get("cb_plain", {}).get("success") or results.get("cb_js", {}).get("success")

    if pw_ok and not cb_ok:
        print("  ▶ Playwright (stock Chromium) 正常加载 ✅")
        print("  ▶ Cloakbrowser (patched Chromium) 被拦截 ❌")
        print()
        print("  推断: cloakbrowser 的源代码级 Chromium 补丁引入了")
        print("  可供 Fastly Client Challenge 检测的指纹不一致。")
        print("  add_init_script 在此背景下无法解决根本问题。")
        print()
        print("  💡 可能解决方案:")
        print("  1. 用原生 Playwright 替代 cloakbrowser（最直接）")
        print("  2. 向 cloakbrowser 报告此兼容性问题")
        print("  3. 尝试 cloakbrowser 的 backend='patchright' 模式")
    elif not pw_ok and cb_ok:
        print("  ▶ Playwright 被拦截，Cloakbrowser 正常加载")
        print("  推测: Nature 最近调整了检测策略")
    elif pw_ok and cb_ok:
        print("  ▶ 全部正常加载 ✅ — 问题已解决")
    else:
        print("  ▶ 所有浏览器配置均被拦截 ❌")
        print("  问题可能不限于浏览器指纹，需进一步排查")

    print()


if __name__ == "__main__":
    main()
