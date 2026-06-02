"""
T3 真实测试：调用 CrossRef API 并捕获响应作为 fixture。

用法:
  python tests/real/test_crossref_real.py

前置条件:
  - .env 中配置了 CROSSREF_MAILTO
  - 网络连接正常

输出:
  - tests/fixtures/crossref_response.json
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

REAL_DOI = "10.1364/OE.582177"
FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "crossref_response.json"


def main():
    from dotenv import load_dotenv
    load_dotenv()

    mailto = os.getenv("CROSSREF_MAILTO", "")
    if not mailto or "your_" in mailto:
        print("[SKIP] CROSSREF_MAILTO not configured in .env")
        return 1

    from sources.crossref import CrossrefClient
    client = CrossrefClient(mailto=mailto)
    paper = client.fetch_by_doi(REAL_DOI)

    # 验证响应结构完整
    assert paper.doi is not None, "DOI should not be None"
    assert paper.title is not None, "Title should not be None"
    assert paper.authors is not None, "Authors should not be None"

    # 构建 fixture 数据
    fixture = {
        "DOI": paper.doi,
        "title": paper.title,
        "author": [{"name": a["name"], "orcid": a.get("orcid")} for a in paper.authors],
        "published": paper.published,
        "abstract": paper.abstract,
        "journal": paper.journal,
        "publisher": paper.publisher,
        "URL": paper.url,
    }

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[OK] Fixture saved to {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
