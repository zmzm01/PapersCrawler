#!/usr/bin/env python3
"""
Publisher URL 调试工具。

对 4 个问题 URL 启动 headful 浏览器（cloakbrowser），
依次诊断：CF 拦截、meta 标签、关键元素、重定向路径、HTTP 状态。

用法:
    python tools/debug_publisher_urls.py
"""

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cloakbrowser import launch_persistent_context
from parsel import Selector


URLS = [
    # ("science",   "https://www.science.org/doi/abs/10.1126/science.aeb6487?af=R"),
    ("aps",       "http://link.aps.org/doi/10.1103/3kf1-jcjp"),
    # ("cambridge", "https://dx.doi.org/10.1017/hpl.2025.10102?rft_dat=source%3Ddrss"),
    # ("aip",       "https://pubs.aip.org/aip/pop/article/33/5/052511/3392588/Neoclassical-transport-and-profile-prediction-in"),
]

CF_KEYWORDS = ["challenge-platform", "_cf_chl_opt", "cf-browser-verification"]


def _detect_cf(html: str) -> list[str]:
    found = []
    for kw in CF_KEYWORDS:
        if kw in html:
            found.append(kw)
    return found


def _check_meta(sel: Selector) -> dict:
    return {
        "citation_title": sel.css('meta[name="citation_title"]::attr(content)').get(),
        "citation_doi": sel.css('meta[name="citation_doi"]::attr(content)').get(),
        "citation_author": sel.css('meta[name="citation_author"]::attr(content)').getall(),
        "citation_date": sel.css('meta[name="citation_date"]::attr(content)').get(),
        "citation_journal_title": sel.css('meta[name="citation_journal_title"]::attr(content)').get(),
        "citation_pdf_url": sel.css('meta[name="citation_pdf_url"]::attr(content)').get(),
        "citation_abstract": sel.css('meta[name="citation_abstract"]::attr(content)').get(),
        "citation_online_date": sel.css('meta[name="citation_online_date"]::attr(content)').get(),
        "dc.Type": sel.css('meta[name="dc.Type"]::attr(content)').get(),
        "dc.Title": sel.css('meta[name="dc.Title"]::attr(content)').get(),
        "dc.Creator": sel.css('meta[name="dc.Creator"]::attr(content)').getall(),
        "dc.Date": sel.css('meta[name="dc.Date"]::attr(content)').get(),
        "dc.Identifier": sel.css('meta[name="dc.Identifier"]::attr(content)').get(),
        "publish_date": sel.css('meta[name="publish_date"]::attr(content)').get(),
    }


def _check_elements(sel: Selector) -> dict:
    return {
        "has_pdf_download_link": bool(sel.css('a[data-test="download-pdf"]').get()),
        "has_pdf_url_with_download": bool(sel.css('a[href*="download=true"]').get()),
        "has_abstract_section": bool(
            sel.css("#abstract-section-content, #Abs1-content, section#abstract, section.abstract").get()
        ),
        "has_article_body": bool(sel.css("#articleBody, #article-body, article").get()),
        "has_json_ld": bool(sel.css('script[type="application/ld+json"]').get()),
    }


def diagnose_url(publisher: str, url: str) -> dict:
    tmpdir = tempfile.mkdtemp(prefix=f"debug_{publisher}_")
    context = launch_persistent_context(
        user_data_dir=tmpdir,
        headless=False,
    )
    page = context.new_page()
    result = {"publisher": publisher, "url": url}

    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(15000)

        result["final_url"] = page.url
        result["http_status"] = resp.status if resp else None
        result["page_title"] = page.title()

        html = page.content()
        result["html_length"] = len(html)

        sel = Selector(text=html)

        result["cf_detected"] = _detect_cf(html)
        result["meta"] = _check_meta(sel)
        result["elements"] = _check_elements(sel)

    except Exception as e:
        result["error"] = str(e)
    finally:
        context.close()

    return result


def main():
    for publisher, url in URLS:
        print(f"\n{'='*60}")
        print(f"  [{publisher}] {url}")
        print(f"{'='*60}")
        result = diagnose_url(publisher, url)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()


if __name__ == "__main__":
    main()
