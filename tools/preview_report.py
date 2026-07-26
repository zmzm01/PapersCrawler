#!/usr/bin/env python3
"""
tools/preview_report.py
========================

预览/重跑报告：生成 Markdown 报告（含 explained.html 解释页）但**不**将论文
标记为已报告。与 ``tools/schedule_weekly.py`` / ``phase_g.py`` 的自动报告
区别：

- **不调用** ``db.mark_papers_reported()`` → 不影响 Phase G 下次"待报告"集合
- **不限制** ``report_date IS NULL`` → 已报告过的论文仍可包含，便于回看历史
- **输出路径** 由 ``--output`` 指定（而非固定的 ``auto/`` 目录）
- **报告范围** 由 ``--scope`` 指定（all / week / today）

适用场景
--------
- 测试报告模板 / 元信息 / 排序规则变更后的渲染效果
- 抽查特定时间窗口的论文集合
- 备份报告到自定义路径
- 给 LLM 提供"再生成一次报告"的入口而不影响正式流水线

用法
----
::

    # 全部 A/B 相关论文（默认）
    python tools/preview_report.py --scope all --output /tmp/preview_all.md

    # 本周入库的论文
    python tools/preview_report.py --scope week --output /tmp/preview_week.md

    # 当天入库的论文
    python tools/preview_report.py --scope today --output /tmp/preview_today.md

    # 指定基准日期（用于 week/today 范围；默认今天）
    python tools/preview_report.py --scope week --date 2026-07-25 --output /tmp/p.md

    # 不生成 explained.html
    python tools/preview_report.py --scope all --output /tmp/p.md --no-explainer

explained.html 与 Phase G 一致：默认生成于 ``<output stem>_explained.html``，
受 ``settings.yaml`` 中 ``generate_explained_html`` 开关控制。
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import DB_PATH
from db.database import DatabaseClient
from processors.paper_report_generator import generate_report

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 与 phase_g.py 保持一致的基础过滤 + 论文 dict 构建
# ---------------------------------------------------------------------------

# 与 get_papers_for_report() 等价，但**显式不包含** report_date IS NULL
# 过滤——预览工具需要"重看历史"，已报告的论文也包含进来。
_BASE_WHERE = (
    "llm_summary_status = 'success' "
    "AND llm_relevance_category IN ('A', 'B') "
    "AND llm_relevance_status = 'success'"
)


def _build_paper_dicts(papers):
    """Convert sqlite3.Row → report generator paper dict (mirrors phase_g.py).

    Returns
    -------
    list[dict]
        Each dict contains the fields consumed by ``generate_report``.
    """
    paper_list = []
    for p in papers:
        summary = {}
        try:
            summary = json.loads(p["llm_summary_result"] or "{}")
        except json.JSONDecodeError:
            pass

        authors = []
        try:
            authors = json.loads(p["authors_json"] or "[]")
        except json.JSONDecodeError:
            pass

        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            authors = [a.get("name", "") for a in authors if a.get("name")]

        subfields = []
        try:
            subfields = json.loads(p["llm_relevance_subfields"] or "[]")
        except json.JSONDecodeError:
            pass

        paper_list.append({
            "title": p["title"] or "",
            "authors": authors,
            "date": (
                p["paperdate_crossref"]
                or p["paperdate_page"]
                or p["paperdate_rss"]
                or ""
            ),
            "doi": p["doi"] or "",
            "journal": p["journal"] or "",
            "publisher": p["publisher"] or "",
            "matched_subdomains": subfields,
            "relevance_category": p["llm_relevance_category"] or "",
            "relevance_reason": p["llm_relevance_reason"] or "",
            "page_url": p["page_url"] or "",
            "pdf_url": p["pdf_url"] or "",
            "abstract": p["abstract"] or "",
            "one_sentence": summary.get("one_sentence", ""),
            "motivation_and_goal": summary.get("motivation_and_goal", ""),
            "key_setup_and_method": summary.get("key_setup_and_method", ""),
            "main_results_and_physics": summary.get("main_results_and_physics", ""),
            "take_home_message": summary.get("take_home_message", ""),
        })
    return paper_list


def _fetch_papers(db, scope: str, ref_date: datetime):
    """Fetch papers for report by scope.

    Parameters
    ----------
    db : DatabaseClient
    scope : {'all', 'week', 'today'}
        Selection window based on ``created_date``.
    ref_date : datetime
        Reference date for ``week`` / ``today`` scopes. ``week`` means
        ``created_date >= ref_date - 7 days``; ``today`` means same day.

    Returns
    -------
    list[sqlite3.Row]
    """
    if scope == "all":
        sql = (
            f"SELECT * FROM papers "
            f"WHERE {_BASE_WHERE} "
            f"ORDER BY paperdate_rss DESC"
        )
        return db.conn.execute(sql).fetchall()

    if scope == "week":
        cutoff = (ref_date - timedelta(days=7)).strftime("%Y-%m-%d")
        sql = (
            f"SELECT * FROM papers "
            f"WHERE {_BASE_WHERE} "
            f"AND substr(created_date, 1, 10) >= ? "
            f"ORDER BY paperdate_rss DESC"
        )
        return db.conn.execute(sql, (cutoff,)).fetchall()

    if scope == "today":
        date_str = ref_date.strftime("%Y-%m-%d")
        sql = (
            f"SELECT * FROM papers "
            f"WHERE {_BASE_WHERE} "
            f"AND substr(created_date, 1, 10) = ? "
            f"ORDER BY paperdate_rss DESC"
        )
        return db.conn.execute(sql, (date_str,)).fetchall()

    raise ValueError(f"Unknown scope: {scope}")


def _atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` via tmp+rename (mirrors phase_g.py).

    Avoids leaving a half-written file on crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="预览/重跑报告：生成报告但不标记论文为已报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--scope", choices=["all", "week", "today"], default="all",
        help="报告范围：all=全部 A/B 论文；week=本周入库；"
             "today=今天入库（默认 all）",
    )
    parser.add_argument(
        "--output", type=Path, required=True,
        help="输出 Markdown 报告路径（必须含 .md 后缀，"
             "explained.html 写入同目录 <stem>_explained.html）",
    )
    parser.add_argument(
        "--date", default=None,
        help="基准日期 YYYY-MM-DD（用于 week/today 范围；默认今天）",
    )
    parser.add_argument(
        "--no-explainer", action="store_true",
        help="不生成 explained.html（默认与 Phase G 行为一致，"
             "受 settings.yaml 中 generate_explained_html 控制）",
    )
    args = parser.parse_args()

    if args.output.suffix.lower() not in (".md", ".markdown"):
        parser.error(f"--output 必须以 .md 结尾: {args.output}")

    if args.date:
        try:
            ref_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            parser.error(f"--date 格式错误，期望 YYYY-MM-DD: {args.date}")
    else:
        ref_date = datetime.now()

    # Imports placed after CLI parse so --help stays fast.
    from config import CFG, load_keywords
    from processors.report_explainer import write_explained_html

    include_explainer = (
        not args.no_explainer
        and getattr(CFG, "GENERATE_EXPLAINED_HTML", False)
    )

    with DatabaseClient(DB_PATH) as db:
        papers = _fetch_papers(db, args.scope, ref_date)
        print(
            f"Scope [{args.scope}] matched {len(papers)} papers "
            f"(reference date: {ref_date.strftime('%Y-%m-%d')})"
        )

        if not papers:
            print("No papers match — nothing to write.")
            return

        paper_list = _build_paper_dicts(papers)
        scope_definition = load_keywords().get("scope_definition")
        md_content = generate_report(
            paper_list, format="markdown", toc=True,
            scope_definition=scope_definition,
        )
        _atomic_write(args.output, md_content)
        print(
            f"Markdown report written: {args.output} "
            f"({len(paper_list)} papers)"
        )

        if include_explainer:
            # Use the Phase G-style filename so ``_extract_date_from_path``
            # inside the explainer can correctly recover the report date.
            # (The explainer only recognizes ``report_YYYY-MM-DD_*`` stems.)
            ref_str = ref_date.strftime("%Y-%m-%d")
            explained_path = args.output.with_name(
                f"report_{ref_str}_explained.html"
            )
            try:
                write_explained_html(db, explained_path)
                print(f"Explained HTML written: {explained_path}")
            except Exception:
                logger.warning(
                    "Explained HTML generation failed — "
                    "md report is still complete",
                    exc_info=True,
                )
        else:
            reason = (
                "--no-explainer" if args.no_explainer
                else "CFG.GENERATE_EXPLAINED_HTML=False"
            )
            print(f"Explained HTML skipped ({reason})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
