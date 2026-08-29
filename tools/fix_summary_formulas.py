#!/usr/bin/env python
"""Repair LaTeX and deterministic text artifacts in existing summaries.

Examples
--------
  python tools/fix_summary_formulas.py --dry-run
  python tools/fix_summary_formulas.py --doi 10.1103/PhysRevLett.136.123456
  python tools/fix_summary_formulas.py --publisher aps --force

The tool uses the dedicated ``formula_fix.llm`` configuration and processes
different papers concurrently. Text nodes inside one paper remain serial so
that one paper does not create an unbounded number of requests.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from common import LLMCircuitBreaker
from config import CFG, DB_PATH
from db.database import DatabaseClient, FetchStatus
from processors.llm_summarize_deepseek import FormulaFixer
from processors.katex_validator import validate_katex_formulas
from processors.summary_schema import normalize_summary, transform_summary_texts


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_papers(db, doi=None, publisher=None):
    """Load successful summaries with optional DOI or publisher filters.

    Parameters
    ----------
    db : DatabaseClient
        Open database connection.
    doi : str, optional
        Exact DOI filter, matched case-insensitively.
    publisher : str, optional
        Publisher filter.

    Returns
    -------
    list
        Matching paper rows.
    """
    all_papers = db.get_papers_with_summaries()
    if doi:
        normalized_doi = doi.strip().lower()
        papers = [
            paper for paper in all_papers
            if (paper["doi"] or "").strip().lower() == normalized_doi
        ]
        if not papers:
            logger.error("未找到 DOI: %s", doi)
            sys.exit(1)
        return papers
    if publisher:
        papers = [paper for paper in all_papers if paper["publisher"] == publisher]
        logger.info("出版社 [%s]: %s 篇论文", publisher, len(papers))
        if not papers:
            logger.error("未找到 publisher=%s 的论文", publisher)
            sys.exit(1)
        return papers
    return all_papers


def _walk_text_nodes(value, path=()):
    """Yield ``(path, text)`` for every non-key text node in a summary."""
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            yield from _walk_text_nodes(child_value, path + (str(child_key),))
    elif isinstance(value, list):
        for index, child_value in enumerate(value):
            yield from _walk_text_nodes(child_value, path + (str(index),))
    elif isinstance(value, str) and (not path or path[-1] != "key"):
        yield ".".join(path), value


def analyze_papers(papers, fixer, verbose=False, force=False):
    """Find papers and text nodes that need deterministic or LLM repair.

    Parameters
    ----------
    papers : list
        Successful summary rows returned by the database.
    fixer : FormulaFixer
        FormulaFixer used only for local detection; no API calls are made.
    verbose : bool
        Print each detected text node.
    force : bool
        Mark every non-placeholder text node for LLM repair.

    Returns
    -------
    tuple[dict, list[dict]]
        Aggregate statistics and per-paper detection results.
    """
    stats = {
        "total": len(papers),
        "candidate_papers": 0,
        "total_fields": 0,
        "needs_fix": 0,
        "local_repairs": 0,
    }
    paper_results = []
    for paper in papers:
        doi = paper["doi"]
        summary_raw = paper["llm_summary_result"] or "{}"
        try:
            parsed = json.loads(summary_raw)
        except json.JSONDecodeError:
            logger.warning("[%s] llm_summary_result 不是合法 JSON，跳过", doi)
            continue

        normalized = normalize_summary(parsed)
        local_changed = normalized != parsed
        if local_changed:
            stats["local_repairs"] += 1
        fields_info = []
        formula_needed = False
        for field_path, text in _walk_text_nodes(normalized):
            if not text or text == "未提供":
                continue
            stats["total_fields"] += 1
            need = fixer.needs_fix(text, force=force) or bool(
                validate_katex_formulas(text),
            )
            if need:
                formula_needed = True
                stats["needs_fix"] += 1
                fields_info.append((field_path, "fix", text[:80]))
                if verbose:
                    print(f"  [{doi}] {field_path}: 需要修复 — {text[:80]}...")
            elif verbose:
                fields_info.append((field_path, "ok", ""))
                print(f"  [{doi}] {field_path}: 无需修复")

        candidate = local_changed or formula_needed
        if candidate:
            stats["candidate_papers"] += 1
        paper_results.append({
            "doi": doi,
            "candidate": candidate,
            "fields": fields_info,
        })
    return stats, paper_results


def _fix_one_paper(paper, llm_config, force, circuit_breaker, max_repair_rounds):
    """Fix one paper in a worker thread and return a DB-ready JSON string."""
    summary_raw = paper["llm_summary_result"] or "{}"
    parsed = json.loads(summary_raw)
    normalized = normalize_summary(parsed)
    fixer = FormulaFixer(
        llm_api_config=llm_config,
        force=force,
        max_repair_rounds=max_repair_rounds,
    )
    fixed_count = 0

    def fix_text(text, field_name):
        nonlocal fixed_count
        fixed = fixer.fix_text(
            text,
            field_name=f"{paper['doi']}/{field_name}",
            circuit_breaker=circuit_breaker,
        )
        if fixed != text:
            fixed_count += 1
        return fixed

    try:
        fixed_summary = transform_summary_texts(normalized, fix_text)
        result_json = json.dumps(fixed_summary, ensure_ascii=False)
        changed = fixed_summary != normalized or normalized != parsed
        return paper["doi"], result_json, fixed_count, changed
    finally:
        fixer._session.close()


def fix_papers(papers, candidate_dois, db, dry_run=False, force=False):
    """Run concurrent FormulaFixer workers and write changed summaries.

    Parameters
    ----------
    papers : list
        Successful summary rows.
    candidate_dois : set[str]
        DOI values selected during :func:`analyze_papers`.
    db : DatabaseClient
        Open database connection used only by the main thread for writes.
    dry_run : bool
        If True, do not call the LLM or write the database.
    force : bool
        Force LLM repair for each non-placeholder text node.

    Returns
    -------
    tuple[int, int]
        Number of changed papers and changed text nodes.
    """
    selected = [paper for paper in papers if paper["doi"] in candidate_dois]
    if dry_run or not selected:
        return 0, 0

    worker_count = min(len(selected), CFG.FORMULA_FIX_CONCURRENT_MAX)
    logger.info(
        "FormulaFixer: %s 篇论文，%s 个并发 worker，model=%s",
        len(selected),
        worker_count,
        CFG.LLM_API_CONFIG_DICT_FORMULA.get("model"),
    )
    circuit_breaker = LLMCircuitBreaker(CFG.LLM_CIRCUIT_BREAKER_THRESHOLD)
    fixed_papers = 0
    fixed_fields = 0
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _fix_one_paper,
                paper,
                CFG.LLM_API_CONFIG_DICT_FORMULA,
                force,
                circuit_breaker,
                CFG.FORMULA_FIX_MAX_REPAIR_ROUNDS,
            ): paper
            for paper in selected
        }
        for future in as_completed(futures):
            paper = futures[future]
            doi = paper["doi"]
            try:
                _, result_json, changed_fields, changed = future.result()
                if not changed:
                    continue
                db.update_llm_summary(
                    doi,
                    result_json,
                    FetchStatus.SUCCESS.value,
                    str(datetime.now()),
                )
                fixed_papers += 1
                fixed_fields += changed_fields
                logger.info("[%s] 已写回 DB (%s 个文本节点修复)", doi, changed_fields)
            except Exception as error:
                logger.warning("[%s] 修复失败，保留原总结: %s", doi, error)
    return fixed_papers, fixed_fields


def main():
    """Parse command-line arguments and repair selected summaries."""
    parser = argparse.ArgumentParser(
        description="修复 LLM 总结中的 LaTeX 公式和 JSON 文本伪转义",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--doi", help="仅处理指定 DOI 的论文")
    parser.add_argument("--publisher", help="仅处理指定出版社的论文 (如 aps, nature)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过 needs_fix() 检测，强制修复所有非占位文本字段",
    )
    parser.add_argument("--dry-run", action="store_true", help="只检测，不调用 LLM 或写入 DB")
    parser.add_argument("--verbose", action="store_true", help="显示每个字段的检测结果")
    args = parser.parse_args()

    if args.doi and args.publisher:
        parser.error("--doi 与 --publisher 不能同时使用")
    if not DB_PATH.exists():
        print(f"数据库文件不存在: {DB_PATH}")
        sys.exit(1)

    with DatabaseClient(DB_PATH) as db:
        papers = load_papers(db, doi=args.doi, publisher=args.publisher)
        detector = FormulaFixer(
            llm_api_config=CFG.LLM_API_CONFIG_DICT_FORMULA,
            force=args.force,
            max_repair_rounds=CFG.FORMULA_FIX_MAX_REPAIR_ROUNDS,
        )
        logger.info("共 %s 篇论文，正在检测公式和文本伪转义...", len(papers))
        stats, paper_results = analyze_papers(
            papers,
            detector,
            verbose=args.verbose,
            force=args.force,
        )
        candidate_dois = {
            result["doi"] for result in paper_results if result["candidate"]
        }

        print(
            f"\n统计: {stats['total_fields']} 个文本字段中 "
            f"{stats['needs_fix']} 个需要 FormulaFixer，"
            f"{stats['local_repairs']} 篇含本地可修复伪转义，"
            f"共 {stats['candidate_papers']} 篇候选论文",
        )
        if not candidate_dois:
            print("无需修复，退出。")
            return
        if args.dry_run:
            print("\n预览模式完成，未调用 LLM，未写入任何变更。")
            return

        answer = input(
            f"\n将修复 {len(candidate_dois)} 篇论文，确认？[y/N] ",
        ).strip().lower()
        if answer != "y":
            print("已取消")
            return

        fixed_papers, fixed_fields = fix_papers(
            papers,
            candidate_dois,
            db,
            force=args.force,
        )
        print(f"\n完成: {fixed_papers} 篇论文共 {fixed_fields} 个文本节点已修复")


if __name__ == "__main__":
    main()
