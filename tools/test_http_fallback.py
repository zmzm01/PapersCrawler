#!/usr/bin/env python3
"""
HTTP Fallback 测试工具。

用 requests / curl_cffi 直接测试 Nature 和 IOP 文章 URL，
验证 HTTP 回退能否正常获取页面内容。

用法:
    # 测试 Nature（默认 URL）
    python tools/test_http_fallback.py

    # 指定 URL 测试
    python tools/test_http_fallback.py --url "https://www.nature.com/articles/s41567-026-03320-5"

    # 测试 IOP（requests + curl_cffi 都试）
    python tools/test_http_fallback.py --url "https://iopscience.iop.org/article/XXXX" --iop
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parsel import Selector


# ── 检测函数 ──

def check_nature_meta(sel):
    return {
        "dc.type": sel.css('meta[name="dc.type"]::attr(content)').get(),
        "dc.Identifier": sel.css('meta[name="dc.Identifier"]::attr(content)').get(),
        "citation_title": sel.css('meta[name="citation_title"]::attr(content)').get(),
        "citation_doi": sel.css('meta[name="citation_doi"]::attr(content)').get(),
        "has_json_ld": bool(sel.css('script[type="application/ld+json"]').get()),
    }


def check_iop_meta(sel):
    return {
        "citation_title": sel.css('meta[name="citation_title"]::attr(content)').get(),
        "citation_doi": sel.css('meta[name="citation_doi"]::attr(content)').get(),
        "citation_journal_title": sel.css('meta[name="citation_journal_title"]::attr(content)').get(),
        "citation_author": sel.css('meta[name="citation_author"]::attr(content)').getall(),
        "citation_pdf_url": sel.css('meta[name="citation_pdf_url"]::attr(content)').get(),
        "citation_online_date": sel.css('meta[name="citation_online_date"]::attr(content)').get(),
    }


def is_bot_page(html, title=""):
    title_lower = title.lower() if title else ""
    html_lower = html.lower() if html else ""
    if any(kw in title_lower for kw in [
        "client challenge", "challenge", "captcha", "blocked",
        "access denied", "attention required", "just a moment",
    ]):
        return True
    if any(kw in html_lower for kw in [
        "cf-browser-verification", "challenge-platform",
        "_cf_chl_opt", "g-recaptcha",
    ]):
        return True
    return False


def extract_title(html):
    """从 HTML 中提取 <title> 标签内容。"""
    m = __import__('re').search(r'<title>(.*?)</title>', html, __import__('re').IGNORECASE | __import__('re').DOTALL)
    return m.group(1).strip() if m else "(no title found)"


# ── 测试方法 ──

def test_requests(url, timeout=30):
    """用 requests 获取页面。"""
    import requests
    print(f"\n  📡 [requests] GET {url}")
    t0 = time.time()
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        elapsed = time.time() - t0
        print(f"     Status: {resp.status_code}  |  {elapsed:.1f}s  |  Size: {len(resp.text)} bytes")
        return resp.status_code, resp.text, resp.headers
    except Exception as e:
        elapsed = time.time() - t0
        print(f"     ❌ Failed ({elapsed:.1f}s): {e}")
        return None, "", {}


def test_curl_cffi(url, timeout=30):
    """用 curl_cffi 获取页面（TLS 指纹伪造）。"""
    from curl_cffi import requests as curl_req
    print(f"\n  🌀 [curl_cffi] GET {url}")
    t0 = time.time()
    try:
        resp = curl_req.get(url, impersonate="chrome", timeout=timeout)
        elapsed = time.time() - t0
        print(f"     Status: {resp.status_code}  |  {elapsed:.1f}s  |  Size: {len(resp.text)} bytes")
        return resp.status_code, resp.text, resp.headers
    except Exception as e:
        elapsed = time.time() - t0
        print(f"     ❌ Failed ({elapsed:.1f}s): {e}")
        return None, "", {}


def report(name, status_code, html, headers, url):
    """分析并打印页面内容状态。"""
    if status_code is None:
        print(f"     ⛔ {name}: 请求失败")
        return False

    title = extract_title(html)
    sel = Selector(text=html)
    bot = is_bot_page(html, title)
    content_type = (headers or {}).get("Content-Type", "")

    print(f"     Title: [{title[:100]}]")
    print(f"     Content-Type: {content_type}")
    print(f"     Bot Page: {'⚠️ YES' if bot else '✅ No'}")

    # 检测 meta 标签
    if "nature.com" in url:
        meta = check_nature_meta(sel)
        dc_type = meta.get("dc.type", "")
        citation_doi = meta.get("citation_doi", "")
        print(f"     dc.type: {dc_type or '—'}")
        print(f"     citation_doi: {citation_doi or '—'}")
        is_ok = dc_type == "OriginalPaper" or bool(citation_doi)
        print(f"     ➡  {'✅ 正常文章页' if is_ok else '❌ 非文章页或拦截页'}")
        return is_ok and not bot
    elif "iop.org" in url:
        meta = check_iop_meta(sel)
        citation_doi = meta.get("citation_doi", "")
        citation_title = meta.get("citation_title", "")
        print(f"     citation_title: {citation_title or '—'}")
        print(f"     citation_doi: {citation_doi or '—'}")
        is_ok = bool(citation_title) and bool(citation_doi)
        print(f"     ➡  {'✅ 正常文章页' if is_ok else '❌ 非文章页或拦截页'}")
        return is_ok and not bot
    else:
        # 通用检测：有 title 且不是 bot 页就算成功
        is_ok = bool(title.strip()) and not bot
        print(f"     ➡  {'✅ 有内容' if is_ok else '❌ 疑似空页或拦截'}")
        return is_ok


def main():
    parser = argparse.ArgumentParser(description="HTTP Fallback 测试工具")
    parser.add_argument("--url", help="目标 URL（默认测试 Nature）")
    parser.add_argument("--iop", action="store_true", help="IOP 模式：同时测试 requests 和 curl_cffi")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP 超时秒数，默认 30")
    args = parser.parse_args()

    url = args.url or "https://www.nature.com/articles/s41567-026-03320-5"

    print(f"\n{'='*70}")
    print(f"  🧪 HTTP Fallback 测试")
    print(f"  URL: {url}")
    print(f"  Timeout: {args.timeout}s")
    print(f"{'='*70}")

    is_iop = args.iop or "iop.org" in url

    if is_iop:
        # IOP: 两种方法都试
        for label, fn in [("requests", test_requests), ("curl_cffi", test_curl_cffi)]:
            code, html, headers = fn(url, args.timeout)
            if code:
                ok = report(label, code, html, headers, url)
                if ok:
                    print(f"\n  ✅ {label} 成功获取文章内容")
                else:
                    print(f"\n  ❌ {label} 未能获取有效文章内容")
            else:
                print(f"\n  ❌ {label} 请求失败")
    else:
        # Nature: 只试 requests（curl_cffi 没必要）
        print(f"\n  📋 注: Nature 用 requests 即可（wget 已验证能通）")
        code, html, headers = test_requests(url, args.timeout)
        if code:
            ok = report("requests", code, html, headers, url)
            print(f"\n  {'✅ requests 成功获取' if ok else '❌ requests 失败'}")
        else:
            print(f"\n  ❌ requests 请求失败")

    print(f"\n{'='*70}")
    print(f"  测试完成")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
