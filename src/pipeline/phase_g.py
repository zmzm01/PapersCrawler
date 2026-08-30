"""
Phase G: Report generation.

Two modes:
  - Auto (doi_list=None): pipeline daily run, writes to auto_dir, marks papers reported
  - User (doi_list provided): Web UI custom selection, writes to user_dir, no mark
"""

import logging
from datetime import datetime
from pathlib import Path

from config import CFG, DB_PATH, PUBLIC_EXPORT_DIR, load_keywords
from db.database import (
    EFFECTIVE_RELEVANCE_CATEGORY_SQL,
    LATEST_RELEVANCE_REVIEW_CTE,
)
from processors.paper_report_generator import generate_report
from processors.public_report import write_public_report
from processors.report_presentation import build_report_presentation
from processors.report_snapshot import build_report_papers, make_report_identifier

logger = logging.getLogger(__name__)


def phase_g_report(db, auto_dir, user_dir, doi_list=None):
    """Generate Markdown report from summarized papers.

    Parameters
    ----------
    db : DatabaseClient
    auto_dir : Path
        Output directory for auto-generated daily reports.
    user_dir : Path
        Output directory for user-selected custom reports.
    doi_list : list of str, optional
        If provided, user-selected mode (write to user_dir, no mark).
        If None, auto mode (write to auto_dir, mark papers reported).
    """
    is_auto = doi_list is None
    if CFG.SKIP_PHASE_G and is_auto:
        logger.info("Phase G: SKIP_PHASE_G=True, skipping")
        return
    logger.info("--- Phase G: Report generation ---")

    if is_auto:
        papers = db.get_papers_for_report()
    else:
        placeholders = ",".join("?" for _ in doi_list)
        # 与 get_papers_for_report 保持一致：relevance 过滤必须显式存在，
        # 且最新人工审核结果覆盖 LLM 分类。用户选定模式允许重看已报告论文。
        cur = db.conn.execute(
            f"""
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
            WHERE p.llm_summary_status = 'success'
              AND {EFFECTIVE_RELEVANCE_CATEGORY_SQL} IN ('A', 'B')
              AND p.llm_relevance_status = 'success'
              AND p.llm_relevance_basis = 'fulltext'
              AND p.doi IN ({placeholders})
            """,
            doi_list,
        )
        papers = cur.fetchall()

    if not papers:
        if is_auto:
            logger.info("Phase G: no new summarized papers")
        else:
            logger.info("Phase G: no papers found for selected DOIs")
        return

    logger.info(f"Phase G: {len(papers)} papers for report")

    paper_list = build_report_papers(papers)
    reported_dois = [paper["doi"] for paper in paper_list]

    # 排序统一交给 paper_report_generator._sort_papers()（2026-07-25 起）：
    # 规则 = 相关性等级 A 先 → 同级日期倒序。这里不再 pre-sort。

    if is_auto:
        out_dir = Path(auto_dir)
        date_str = datetime.now().strftime("%Y%m%d")
        md_path = out_dir / f"report_{date_str}.md"
        report_timestamp = str(datetime.now())
    else:
        out_dir = Path(user_dir)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_path = out_dir / f"report_{timestamp_str}.md"

    out_dir.mkdir(parents=True, exist_ok=True)

    # 加载子领域定义用于分组报告；无 scope_definition 时回退平铺模式
    scope_definition = load_keywords().get("scope_definition")
    presentation = build_report_presentation(scope_definition, paper_list)
    # JSON is the canonical report snapshot; Markdown is rendered from the
    # same in-memory paper list after the snapshot has been written.
    public_path = md_path.with_suffix(".public.json")
    write_public_report(
        public_path,
        paper_list,
        date_str if is_auto else timestamp_str[:8],
        scope_definition=scope_definition,
        presentation=presentation,
        report_identifier=(
            None if is_auto else make_report_identifier(md_path.stem)
        ),
        scope={"kind": "automatic" if is_auto else "selected"},
    )
    logger.info(f"Public report snapshot saved: {public_path}")

    md_report = generate_report(
        paper_list, format="markdown", toc=True,
        scope_definition=scope_definition,
        presentation=presentation,
    )
    # 原子写入：先写 .tmp，再 rename，避免崩溃留下半写文件
    tmp_path = md_path.with_suffix(md_path.suffix + ".tmp")
    tmp_path.write_text(md_report, encoding="utf-8")
    tmp_path.replace(md_path)
    logger.info(f"Report saved: {md_path}")

    # Keep the static-site export in sync with the newly generated sidecar.
    # Export failures must not invalidate the canonical report.
    if is_auto:
        try:
            from tools.export_public_reports import export_reports
            exported = export_reports(PUBLIC_EXPORT_DIR, Path(auto_dir), DB_PATH)
            logger.info(f"Public report export updated: {exported} report(s) -> {PUBLIC_EXPORT_DIR}")
        except Exception:
            logger.warning("Public report export failed — canonical report is still complete", exc_info=True)

    # 写完 md 后条件性生成 explained.html（仅自动报告）
    if is_auto and getattr(CFG, "GENERATE_EXPLAINED_HTML", False):
        try:
            from processors.report_explainer import write_explained_html
            html_path = Path(auto_dir) / f"report_{date_str}_explained.html"
            write_explained_html(db, html_path)
            logger.info(f"Explained HTML written: {html_path.name}")
        except Exception:
            logger.warning(
                "Explained HTML generation failed — md report is still complete",
                exc_info=True,
            )

    # 文件落盘成功后再标记 DB — 避免中间崩溃导致永久丢稿
    if is_auto:
        db.mark_papers_reported(reported_dois, report_timestamp)
        logger.info(f"Marked {len(reported_dois)} papers as reported")

    logger.info(f"Phase G done: {len(paper_list)} papers in report")
