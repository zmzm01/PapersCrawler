#!/usr/bin/env python
"""
对已有 LLM 总结运行 FormulaFixer，修复 LaTeX 公式格式。

无需重跑 Phase F 即可修正公式分隔符反斜杠丢失、裸写 LaTeX 命令等问题。

用法:
  python tools/fix_summary_formulas.py                         # 全部已成功总结
  python tools/fix_summary_formulas.py --doi 10.1103/PhysRevLett.136.123456  # 单篇
  python tools/fix_summary_formulas.py --publisher aps         # 按出版社过滤
  python tools/fix_summary_formulas.py --force                 # 跳过正则检测，强制修复所有字段
  python tools/fix_summary_formulas.py --dry-run               # 预览模式，不实际写入
  python tools/fix_summary_formulas.py --verbose               # 显示每个字段的检测结果
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import DB_PATH, LLM_API_CONFIG_DICT_RELE
from db.database import DatabaseClient, FetchStatus
from processors.llm_summarize_deepseek import FormulaFixer

FIXER_FIELDS = [
    "one_sentence", "motivation_and_goal",
    "key_setup_and_method", "main_results_and_physics",
    "take_home_message",
]


def load_papers(db, doi=None, publisher=None):
    """加载有 LLM 总结的论文，支持按 DOI 或 publisher 过滤。"""
    all_papers = db.get_papers_with_summaries()
    if doi:
        papers = [p for p in all_papers if p["doi"] == doi]
        if not papers:
            logger.error(f"未找到 DOI: {doi}")
            sys.exit(1)
        return papers
    if publisher:
        papers = [p for p in all_papers if p["publisher"] == publisher]
        logger.info(f"出版社 [{publisher}]: {len(papers)} 篇论文")
        if not papers:
            logger.error(f"未找到 publisher={publisher} 的论文")
            sys.exit(1)
        return papers
    return all_papers


def analyze_papers(papers, fixer, verbose=False, force=False):
    """分析每篇论文中需要修复的字段，返回统计信息。

    Parameters
    ----------
    papers : list
    fixer : FormulaFixer
    verbose : bool
    force : bool
        为 True 时跳过 needs_fix() 检测，所有非空字段视为需要修复。
    """
    stats = {"total": len(papers), "total_fields": 0, "needs_fix": 0}
    paper_results = []
    for p in papers:
        doi = p["doi"]
        summary_raw = p["llm_summary_result"] or "{}"
        try:
            parsed = json.loads(summary_raw)
        except json.JSONDecodeError:
            logger.warning(f"[{doi}] llm_summary_result 不是合法 JSON，跳过")
            continue
        fields_info = []
        for field in FIXER_FIELDS:
            text = parsed.get(field, "")
            if not isinstance(text, str) or not text or text == "未提供":
                fields_info.append((field, "skip", ""))
                continue
            need = True if force else fixer.needs_fix(text)
            stats["total_fields"] += 1
            if need:
                stats["needs_fix"] += 1
                fields_info.append((field, "fix", text[:80]))
            else:
                fields_info.append((field, "ok", ""))
        paper_results.append({"doi": doi, "fields": fields_info})
        if verbose:
            for field, status, snippet in fields_info:
                if status == "fix":
                    print(f"  [{doi}] {field}: 需要修复 — {snippet}...")
                elif status == "ok" and verbose:
                    print(f"  [{doi}] {field}: 无需修复")
    return stats, paper_results


def fix_papers(papers, fixer, dry_run=False):
    """对论文的总结字段执行公式修复，写回 DB。"""
    db = DatabaseClient(DB_PATH)
    timestamp = str(datetime.now())
    fixed_count = 0
    field_fix_count = 0
    for p in papers:
        doi = p["doi"]
        summary_raw = p["llm_summary_result"] or "{}"
        try:
            parsed = json.loads(summary_raw)
        except json.JSONDecodeError:
            continue
        changed = False
        for field in FIXER_FIELDS:
            if field not in parsed or not isinstance(parsed[field], str):
                continue
            fixed = fixer.fix_text(parsed[field], field_name=f"{doi}/{field}")
            if fixed != parsed[field]:
                parsed[field] = fixed
                changed = True
                field_fix_count += 1
        if changed:
            fixed_count += 1
            if not dry_run:
                result_str = json.dumps(parsed, ensure_ascii=False)
                db.update_llm_summary(doi, result_str, FetchStatus.SUCCESS.value, timestamp)
                logger.info(f"[{doi}] 已写回 DB ({field_fix_count} 个字段修正)")
    if dry_run:
        print(f"\n预览模式完成，未写入任何变更。")
    return fixed_count, field_fix_count


def main():
    parser = argparse.ArgumentParser(
        description="修复 LLM 总结中的 LaTeX 公式格式问题",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--doi", help="仅处理指定 DOI 的论文")
    parser.add_argument("--publisher", help="仅处理指定出版社的论文 (如 aps, nature)")
    parser.add_argument("--force", action="store_true", help="跳过 needs_fix() 检测，强制修复所有字段")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际写入 DB")
    parser.add_argument("--verbose", action="store_true", help="显示每个字段的检测结果")
    args = parser.parse_args()

    db = DatabaseClient(DB_PATH)
    papers = load_papers(db, doi=args.doi, publisher=args.publisher)
    del db

    fixer = FormulaFixer(llm_api_config=LLM_API_CONFIG_DICT_RELE, force=args.force)

    logger.info(f"共 {len(papers)} 篇论文，正在检测公式格式问题...")
    stats, paper_results = analyze_papers(papers, fixer, verbose=args.verbose, force=args.force)

    print(f"\n统计: {stats['total_fields']} 个字段中 {stats['needs_fix']} 个需要修复")
    if stats["needs_fix"] == 0:
        print("无需修复，退出。")
        return

    if not args.dry_run:
        answer = input(f"\n将修复 {stats['needs_fix']} 个字段（{stats['total']} 篇论文），确认？[y/N] ")
        if answer.lower() != "y":
            print("已取消")
            return

    fixed_papers, fixed_fields = fix_papers(papers, fixer, dry_run=args.dry_run)
    print(f"\n完成: {fixed_papers} 篇论文共 {fixed_fields} 个字段已修复")


if __name__ == "__main__":
    main()
