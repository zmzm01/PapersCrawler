#!/usr/bin/env python3
"""
tools/preview_report.py
========================

预览/重跑报告：生成 Markdown 报告（含 explained.html 解释页）但**不**将论文
标记为已报告。与 ``phase_g.py`` 的自动报告
区别：

- **不调用** ``db.mark_papers_reported()`` → 不影响 Phase G 下次"待报告"集合
- **不限制** ``report_date IS NULL`` → 已报告过的论文仍可包含，便于回看历史
- **输出路径** 由 ``--output`` 指定（而非固定的 ``auto/`` 目录）
- **报告范围** 由 ``--scope`` 指定（all / week / today）
- 可用 ``--before-date`` 按入库日期设置严格上限
- 始终生成与 Markdown 同名的 ``.public.json`` 结构化快照
- 使用 ``--export-public`` 才会同步到公开站点

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

    # 只包含截止日期以前入库的论文（不含截止日）
    python tools/preview_report.py --scope all --before-date 2026-08-17 --output /tmp/p.md

    # 生成快照并同步到公开站点（显式选择，默认不公开预览报告）
    python tools/preview_report.py --scope all --output /tmp/p.md --export-public

    # 不生成 explained.html
    python tools/preview_report.py --scope all --output /tmp/p.md --no-explainer

explained.html 与 Phase G 一致：默认生成于 ``<output stem>_explained.html``，
受 ``settings.yaml`` 中 ``generate_explained_html`` 开关控制。
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import AUTO_REPORT_DIR, DB_PATH, PUBLIC_EXPORT_DIR
from db.database import (
    DatabaseClient,
    EFFECTIVE_RELEVANCE_CATEGORY_SQL,
    LATEST_RELEVANCE_REVIEW_CTE,
)
from processors.paper_report_generator import generate_report
from processors.public_report import write_public_report
from processors.report_presentation import build_report_presentation
from processors.report_snapshot import build_report_papers, make_report_identifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 与 phase_g.py 保持一致的基础过滤 + 论文 dict 构建
# ---------------------------------------------------------------------------

# 与 get_papers_for_report() 等价，但**显式不包含** report_date IS NULL
# 过滤——预览工具需要"重看历史"，已报告的论文也包含进来。最新人工审核
# 决定覆盖 LLM 分类，保持预览与自动报告一致。
_BASE_WHERE = (
    "p.llm_summary_status = 'success' "
    f"AND {EFFECTIVE_RELEVANCE_CATEGORY_SQL} IN ('A', 'B') "
    "AND p.llm_relevance_status = 'success' "
    "AND p.llm_relevance_basis = 'fulltext'"
)
# Phase A stores this field as YYYYMMDD, while older/test data may use
# YYYY-MM-DD or an ISO timestamp.  Removing dashes from the date prefix gives
# one sortable YYYYMMDD representation for all supported forms.
_CREATED_DATE_KEY = "replace(substr(p.created_date, 1, 10), '-', '')"


def _build_paper_dicts(papers):
    """Convert database rows using the shared report snapshot structure.

    Returns
    -------
    list[dict]
        Each dict contains the fields consumed by ``generate_report``.
    """
    return build_report_papers(papers)


def _fetch_papers(
    db,
    scope: str,
    ref_date: datetime,
    before_date: str | None = None,
):
    """Fetch papers for report by scope.

    Parameters
    ----------
    db : DatabaseClient
    scope : {'all', 'week', 'today'}
        Selection window based on ``created_date``.
    ref_date : datetime
        Reference date for ``week`` / ``today`` scopes. ``week`` means
        ``created_date >= ref_date - 7 days``; ``today`` means same day.
    before_date : str, optional
        Strict upper bound for ``created_date`` in ``YYYY-MM-DD`` format.
        Papers created on this date or later are excluded.

    Returns
    -------
    list[sqlite3.Row]
    """
    where_clauses = [_BASE_WHERE]
    query_params = []

    if before_date:
        before_date_key = datetime.strptime(
            before_date, "%Y-%m-%d"
        ).strftime("%Y%m%d")
        where_clauses.append(f"{_CREATED_DATE_KEY} < ?")
        query_params.append(before_date_key)

    if scope == "week":
        cutoff = (ref_date - timedelta(days=7)).strftime("%Y%m%d")
        where_clauses.append(f"{_CREATED_DATE_KEY} >= ?")
        query_params.append(cutoff)

    elif scope == "today":
        date_key = ref_date.strftime("%Y%m%d")
        where_clauses.append(f"{_CREATED_DATE_KEY} = ?")
        query_params.append(date_key)

    elif scope != "all":
        raise ValueError(f"Unknown scope: {scope}")

    sql = f"""
        {LATEST_RELEVANCE_REVIEW_CTE}
        SELECT p.*,
               {EFFECTIVE_RELEVANCE_CATEGORY_SQL}
                   AS effective_relevance_category,
               latest_relevance_review.decision
                   AS manual_relevance_decision,
               latest_relevance_review.notes AS manual_relevance_notes
        FROM papers AS p
        LEFT JOIN latest_relevance_review
          ON latest_relevance_review.doi = p.doi
        WHERE {" AND ".join(where_clauses)}
        ORDER BY p.paperdate_rss DESC
    """
    return db.conn.execute(sql, query_params).fetchall()


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
        "--before-date", default=None,
        help="只包含 created_date 早于该日期的论文（YYYY-MM-DD，不含当天）",
    )
    parser.add_argument(
        "--no-explainer", action="store_true",
        help="不生成 explained.html（默认与 Phase G 行为一致，"
             "受 settings.yaml 中 generate_explained_html 控制）",
    )
    parser.add_argument(
        "--export-public", action="store_true",
        help="生成 JSON sidecar 后同步导出到公开站点目录",
    )
    parser.add_argument(
        "--export-root", type=Path, default=PUBLIC_EXPORT_DIR,
        help="公开站点导出根目录（默认 PUBLIC_REPORT_EXPORT_DIR 或 sibling MySite）",
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

    before_date = None
    if args.before_date:
        try:
            before_date = datetime.strptime(
                args.before_date, "%Y-%m-%d"
            ).strftime("%Y-%m-%d")
        except ValueError:
            parser.error(
                "--before-date 格式错误，期望 YYYY-MM-DD: "
                f"{args.before_date}"
            )

    # Imports placed after CLI parse so --help stays fast.
    from config import CFG, load_keywords
    from processors.report_explainer import write_explained_html

    include_explainer = (
        not args.no_explainer
        and getattr(CFG, "GENERATE_EXPLAINED_HTML", False)
    )

    with DatabaseClient(DB_PATH) as db:
        papers = _fetch_papers(db, args.scope, ref_date, before_date)
        filter_note = (
            f", before-date: {before_date}" if before_date else ""
        )
        print(
            f"Scope [{args.scope}] matched {len(papers)} papers "
            f"(reference date: {ref_date.strftime('%Y-%m-%d')}"
            f"{filter_note})"
        )

        if not papers:
            print("No papers match — nothing to write.")
            return

        paper_list = _build_paper_dicts(papers)
        scope_definition = load_keywords().get("scope_definition")
        presentation = build_report_presentation(scope_definition, paper_list)

        public_path = args.output.with_suffix(".public.json")
        write_public_report(
            public_path,
            paper_list,
            ref_date.strftime("%Y%m%d"),
            scope_definition=scope_definition,
            presentation=presentation,
            report_identifier=make_report_identifier(args.output.stem),
            scope={
                "kind": args.scope,
                "referenceDate": ref_date.strftime("%Y-%m-%d"),
                "beforeCreatedDate": before_date,
            },
        )
        print(f"Public JSON snapshot written: {public_path}")

        md_content = generate_report(
            paper_list, format="markdown", toc=True,
            scope_definition=scope_definition,
            presentation=presentation,
        )
        _atomic_write(args.output, md_content)
        print(
            f"Markdown report written: {args.output} "
            f"({len(paper_list)} papers)"
        )

        if args.export_public:
            from tools.export_public_reports import export_reports

            exported = export_reports(
                args.export_root,
                [Path(AUTO_REPORT_DIR), args.output.parent],
                DB_PATH,
            )
            print(
                f"Public JSON export updated: {exported} reports -> "
                f"{args.export_root}"
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
