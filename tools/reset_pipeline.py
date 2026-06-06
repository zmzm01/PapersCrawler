#!/usr/bin/env python
"""
reset_pipeline.py — 重置流水线状态辅助脚本

 子命令：
  reset-semantic     Phase D 语义相似度分数（仅排序参考）
  reset-relevance    Phase E LLM 相关性判断
  reset-publisher    Phase C Publisher 页面抓取
  reset-mineru       Phase E2 MinerU PDF 解析
  reset-summary      Phase F LLM 总结
  reset-report       Phase G 报告状态

 通用选项：
  --publisher aps  仅重置指定出版社（如 aps, nature）
  --all            重置全部（包括 success），仅 reset-summary / reset-relevance 支持

 示例：
  python tools/reset_pipeline.py reset-relevance                # 历史 skipped/failed
  python tools/reset_pipeline.py reset-relevance --all           # 含 success
  python tools/reset_pipeline.py reset-relevance --publisher aps # 指定出版社
"""
import argparse
import sqlite3
import sys
from pathlib import Path

# 项目根目录（脚本在 tools/ 下，上溯一级）
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "papers.db"

# ------------------------------------------------------------------
# Phase D 重置列（仅清理语义相似度，不影响 LLM 判断结果）
# Phase D 与 Phase E 已解耦：语义分仅供排序参考，不参与过滤
# ------------------------------------------------------------------
SEMANTIC_RESET = [
    "semantic_similarity_score = NULL",
    "semantic_filter_status = 'pending'",
    "semantic_filter_error = NULL",
    "semantic_filter_date = NULL",
    "semantic_best_subdomain = NULL",
]

# ------------------------------------------------------------------
# Phase E 重置列（LLM 相关性判断）
# 重置后触发 Phase E 重判。不级联 E2/F/G（相关性结果不影响已有全文和总结）。
# ------------------------------------------------------------------
RELEVANCE_RESET = [
    "llm_relevance_status = 'pending'",
    "llm_relevance_error = NULL",
    "llm_relevance_date = NULL",
    "llm_relevance_category = NULL",
    "llm_relevance_subfields = NULL",
    "llm_relevance_result = NULL",       # deprecated
    "llm_relevance_confidence = NULL",
    "llm_relevance_reason = NULL",
]


def _confirm(count: int, label: str) -> bool:
    import readline  # noqa: F401 — enables editing in input()
    try:
        resp = input(f"\n将重置 {count} 篇论文的{label}，确认？[y/N] ").strip().lower()
    except EOFError:
        resp = "n"
    return resp in ("y", "yes")


def _run_update(sql: str, params: tuple = ()) -> int:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def cmd_reset_semantic(publisher=None):
    """重置 Phase D 语义相似度分数（仅排序参考）。"""
    where = ""
    params = ()
    if publisher:
        where = "WHERE publisher = ?"
        params = (publisher,)

    count_sql = f"SELECT COUNT(*) FROM papers {where}"
    conn = sqlite3.connect(str(DB_PATH))
    count = conn.execute(count_sql, params).fetchone()[0]
    conn.close()

    if count == 0:
        print(f"无匹配论文（publisher={publisher}），无需操作")
        return

    set_clause = ",\n            ".join(SEMANTIC_RESET)
    sql = f"UPDATE papers SET\n            {set_clause}\n          {where}"

    print(f"\n将重置 {count} 篇论文的语义相似度分数（publisher={publisher or '全部'}）")
    print()
    print("  受影响的状态列:")
    print("    semantic_filter_status       → pending")
    print("    semantic_filter_error        → NULL")
    print("    semantic_filter_date         → NULL")
    print("    semantic_similarity_score    → NULL")
    print("    semantic_best_subdomain      → NULL")
    print("  不受影响（保持不变）:")
    print("    llm_relevance_*, mineru_*, llm_summary_*, report_*")
    print("  级联: 无")
    if not _confirm(count, "语义相似度分数"):
        print("已取消")
        return

    n = _run_update(sql, params)
    print(f"已重置 {n} 篇论文。重新运行 python src/main.py 即可触发 Phase D 重算语义分。")


def cmd_reset_publisher(publisher=None):
    """重置 Phase C Publisher 页面抓取失败/跳过的论文。"""
    exclude_non_research = (
        "AND (publisher_page_fetched_error IS NULL"
        " OR publisher_page_fetched_error NOT LIKE 'NonResearchPageError:%')"
    )
    if publisher:
        where = (
            "WHERE publisher_page_fetched_status IN ('failed', 'skipped')"
            f" {exclude_non_research}"
            " AND publisher = ?"
        )
        params = (publisher,)
    else:
        where = (
            "WHERE publisher_page_fetched_status IN ('failed', 'skipped')"
            f" {exclude_non_research}"
        )
        params = ()

    count_sql = f"SELECT COUNT(*) FROM papers {where}"
    conn = sqlite3.connect(str(DB_PATH))
    count = conn.execute(count_sql, params).fetchone()[0]
    conn.close()

    if count == 0:
        print(f"无失败论文（publisher={publisher or '全部'}），无需操作")
        return

    sql = f"""
    UPDATE papers
    SET publisher_page_fetched_status = 'pending',
        publisher_page_fetched_error = NULL
    {where}
    """

    print(f"\n将重置 {count} 篇论文的 Publisher 抓取状态（publisher={publisher or '全部'}）")
    print()
    print("  受影响的状态列:")
    print("    publisher_page_fetched_status  → pending")
    print("    publisher_page_fetched_error   → NULL")
    print("  不受影响（保持不变）:")
    print("    publisher_page_fetched_date, 以及所有其他列")
    print("  级联: 无")
    print("  注意: 跳过 NonResearchPageError（非论文页面重试无意义）")
    if not _confirm(count, "Publisher 抓取状态"):
        print("已取消")
        return

    n = _run_update(sql, params)
    print(f"已重置 {n} 篇论文。重新运行 python src/main.py 即可触发 Phase C 重试。")


# ------------------------------------------------------------------
# Phase E2 — MinerU PDF 解析重置列
# ------------------------------------------------------------------
MINERU_RESET = [
    "mineru_parse_status = 'pending'",
    "mineru_parse_error = NULL",
    "mineru_parse_date = NULL",
    "mineru_fulltext = NULL",
    "mineru_output_dir = NULL",
]


def cmd_reset_mineru(publisher=None):
    """重置 Phase E2 MinerU PDF 解析失败/跳过的论文。"""
    if publisher:
        where = "WHERE mineru_parse_status IN ('failed', 'skipped') AND publisher = ?"
        params = (publisher,)
    else:
        where = "WHERE mineru_parse_status IN ('failed', 'skipped')"
        params = ()

    count_sql = f"SELECT COUNT(*) FROM papers {where}"
    conn = sqlite3.connect(str(DB_PATH))
    count = conn.execute(count_sql, params).fetchone()[0]
    conn.close()

    if count == 0:
        print(f"无失败论文（publisher={publisher or '全部'}），无需操作")
        return

    set_clause = ",\n            ".join(MINERU_RESET)
    sql = f"UPDATE papers SET\n            {set_clause}\n          {where}"

    print(f"\n将重置 {count} 篇论文的 MinerU 解析状态（publisher={publisher or '全部'}）")
    print()
    print("  受影响的状态列:")
    print("    mineru_parse_status  → pending")
    print("    mineru_parse_error   → NULL")
    print("    mineru_parse_date    → NULL")
    print("    mineru_fulltext      → NULL")
    print("    mineru_output_dir    → NULL")
    print("  不受影响（保持不变）:")
    print("    llm_relevance_*, llm_summary_*, semantic_*, report_*")
    print("  级联: 无（重新解析后 E2→F→G 自然流动，因状态变为 pending）")
    if not _confirm(count, "MinerU 解析状态"):
        print("已取消")
        return

    n = _run_update(sql, params)
    print(f"已重置 {n} 篇论文。重新运行 python src/main.py 即可触发 Phase E2 重试。")


# ------------------------------------------------------------------
# Phase E — LLM 相关性判断重置列
# 默认只重置 failed + skipped（旧版 Phase D 门禁留下的历史状态）。
# 使用 --all 时重置全部论文（包括 success），适用于修改 domain_description 后。
# 不级联 E2/F/G（相关性结果不影响已有 MinerU 全文和 LLM 总结）。
# ------------------------------------------------------------------

def cmd_reset_relevance(publisher=None, reset_all=False):
    """重置 Phase E LLM 相关性判断结果。"""
    if reset_all:
        if publisher:
            where = "WHERE publisher = ?"
            params = (publisher,)
        else:
            where = ""
            params = ()
    else:
        if publisher:
            where = ("WHERE llm_relevance_status IN ('failed', 'skipped')"
                     " AND publisher = ?")
            params = (publisher,)
        else:
            where = "WHERE llm_relevance_status IN ('failed', 'skipped')"
            params = ()

    count_sql = f"SELECT COUNT(*) FROM papers {where}"
    conn = sqlite3.connect(str(DB_PATH))
    count = conn.execute(count_sql, params).fetchone()[0]
    conn.close()

    if count == 0:
        print(f"无匹配论文（publisher={publisher or '全部'}），无需操作")
        return

    set_clause = ",\n            ".join(RELEVANCE_RESET)
    sql = f"UPDATE papers SET\n            {set_clause}\n          {where}"

    mode = "--all，全部" if reset_all else "仅失败/跳过"
    print(f"\n将重置 {count} 篇论文的 LLM 相关性判断状态（{mode}，publisher={publisher or '全部'}）")
    print()
    print("  受影响的状态列:")
    print("    llm_relevance_status      → pending")
    print("    llm_relevance_error       → NULL")
    print("    llm_relevance_date        → NULL")
    print("    llm_relevance_category    → NULL")
    print("    llm_relevance_subfields   → NULL")
    print("    llm_relevance_result      → NULL  (deprecated)")
    print("    llm_relevance_confidence  → NULL")
    print("    llm_relevance_reason      → NULL")
    print("  不受影响（保持不变）:")
    print("    semantic_*, publisher_page_*, mineru_*, llm_summary_*, report_*")
    print("  级联: 无（相关性结果不影响 MinerU 全文和 LLM 总结）")
    if not _confirm(count, "LLM 相关性判断状态"):
        print("已取消")
        return

    n = _run_update(sql, params)
    print(f"已重置 {n} 篇论文。重新运行 python src/main.py 即可触发 Phase E 重判。")


# ------------------------------------------------------------------
# Phase F — LLM 总结重置列
# ------------------------------------------------------------------
SUMMARY_RESET = [
    "llm_summary_status = 'pending'",
    "llm_summary_error = NULL",
    "llm_summary_date = NULL",
    "llm_summary_result = NULL",
]


def cmd_reset_summary(publisher=None, reset_all=False):
    """重置 LLM 总结状态。

    默认只重置 failed + skipped 的论文。
    使用 --all 时重置全部论文（包括 success）。
    """
    if reset_all:
        if publisher:
            where = "WHERE publisher = ?"
            params = (publisher,)
        else:
            where = ""
            params = ()
    else:
        if publisher:
            where = ("WHERE llm_summary_status IN ('failed', 'skipped')"
                     " AND publisher = ?")
            params = (publisher,)
        else:
            where = "WHERE llm_summary_status IN ('failed', 'skipped')"
            params = ()

    count_sql = f"SELECT COUNT(*) FROM papers {where}"
    conn = sqlite3.connect(str(DB_PATH))
    count = conn.execute(count_sql, params).fetchone()[0]
    conn.close()

    if count == 0:
        print(f"无匹配论文（publisher={publisher or '全部'}），无需操作")
        return

    set_clause = ",\n            ".join(SUMMARY_RESET)
    sql = f"UPDATE papers SET\n            {set_clause}\n          {where}"

    mode = "--all，全部" if reset_all else "仅失败/跳过"
    print(f"\n将重置 {count} 篇论文的 LLM 总结状态（{mode}，publisher={publisher or '全部'}）")
    print()
    print("  受影响的状态列:")
    print("    llm_summary_status   → pending")
    print("    llm_summary_error    → NULL")
    print("    llm_summary_date     → NULL")
    print("    llm_summary_result   → NULL")
    print("  不受影响（保持不变）:")
    print("    mineru_*, llm_relevance_*, semantic_*, report_*")
    print("  级联: 无（重新总结后 F→G 自然流动，因状态变为 pending）")
    if not _confirm(count, "LLM 总结状态"):
        print("已取消")
        return

    n = _run_update(sql, params)
    print(f"已重置 {n} 篇论文。重新运行 python src/main.py 即可触发 Phase F 重试。")


# ------------------------------------------------------------------
# Phase G — 报告状态重置列
# ------------------------------------------------------------------
REPORT_RESET = [
    "report_status = 'pending'",
    "report_date = NULL",
]


def cmd_reset_report(publisher=None, days=None, today=False):
    """重置报告状态，使已报告论文重新出现在下次报告中。

    Parameters
    ----------
    publisher : str, optional
        仅重置指定出版社。
    days : int, optional
        按日历日重置最近 N 天的报告（含今天）。
    today : bool
        仅重置今天（当前自然日）的报告。与 --days 互斥，同时指定时 --today 优先。
    """
    if today:
        if publisher:
            where = ("WHERE report_date IS NOT NULL"
                     " AND date(report_date) = date('now', 'localtime')"
                     " AND publisher = ?")
            params = (publisher,)
        else:
            where = ("WHERE report_date IS NOT NULL"
                     " AND date(report_date) = date('now', 'localtime')")
            params = ()
    elif days is not None:
        if publisher:
            where = ("WHERE report_date IS NOT NULL"
                     " AND date(report_date) >= date('now', '-{} days', 'localtime')"
                     " AND publisher = ?").format(days)
            params = (publisher,)
        else:
            where = ("WHERE report_date IS NOT NULL"
                     " AND date(report_date) >= date('now', '-{} days', 'localtime')").format(days)
            params = ()
    else:
        if publisher:
            where = "WHERE report_status = 'reported' AND publisher = ?"
            params = (publisher,)
        else:
            where = "WHERE report_status = 'reported'"
            params = ()

    count_sql = f"SELECT COUNT(*) FROM papers {where}"
    conn = sqlite3.connect(str(DB_PATH))
    count = conn.execute(count_sql, params).fetchone()[0]
    conn.close()

    if count == 0:
        print(f"无匹配论文（publisher={publisher or '全部'}），无需操作")
        return

    set_clause = ",\n            ".join(REPORT_RESET)
    sql = f"UPDATE papers SET\n            {set_clause}\n          {where}"

    if today:
        scope = "今天（当前自然日）的"
    elif days is not None:
        scope = f"最近 {days} 个日历日内的"
    else:
        scope = ""
    print(f"\n将重置 {count} 篇论文的{scope}报告状态（publisher={publisher or '全部'}）")
    if not _confirm(count, "报告状态"):
        print("已取消")
        return

    n = _run_update(sql, params)
    print(f"已重置 {n} 篇论文。重新运行 python src/main.py 即可将论文汇入下次报告。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PapersCrawler 流水线状态重置工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sem = sub.add_parser("reset-semantic",
        help="重置语义相似度分数（仅清理排序参考，不影响 LLM 判断）",
        description=(
            "修改 sub_domains 后使用。仅重置 Phase D 的语义相似度分数，"
            "不影响 Phase E（LLM 相关性判断）结果。"
            "Phase D 与 Phase E 已解耦。"
            "\n\n受影响的状态列:"
            "\n  semantic_filter_*    → pending"
            "\n  semantic_similarity_score → NULL"
            "\n  semantic_best_subdomain   → NULL"
            "\n  不受影响:"
            "\n  llm_relevance_*, mineru_*, llm_summary_*, report_*"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_sem.add_argument("--publisher", help="仅重置指定出版社（如 aps, nature）")

    p_pub = sub.add_parser("reset-publisher",
        help="重置 Publisher 页面抓取失败/跳过的论文",
        description=(
            "将 publisher_page_fetched_status 为 failed / skipped 的论文重置为 pending，"
            "触发 Phase C 重试。跳过非论文页面（NonResearchPageError）。"
            "\n\n受影响的状态列:"
            "\n  publisher_page_fetched_status   → pending"
            "\n  publisher_page_fetched_error    → NULL"
            "\n  不重置: 其他所有列"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pub.add_argument("--publisher", help="仅重置指定出版社")

    p_mineru = sub.add_parser("reset-mineru",
        help="重置 MinerU PDF 解析失败/跳过的论文",
        description=(
            "将 mineru_parse_status 为 failed / skipped 的论文重置为 pending，"
            "触发 Phase E2 重试。"
            "\n\n受影响的状态列:"
            "\n  mineru_parse_status   → pending"
            "\n  mineru_parse_error    → NULL"
            "\n  mineru_parse_date     → NULL"
            "\n  mineru_fulltext       → NULL"
            "\n  mineru_output_dir     → NULL"
            "\n  不重置: 其他所有列"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_mineru.add_argument("--publisher", help="仅重置指定出版社")

    p_rel = sub.add_parser("reset-relevance",
        help="重置 LLM 相关性判断（加 --all 重置包括 success 的全部论文）",
        description=(
            "默认只重置 failed + skipped 的论文（旧版 Phase D 门禁留下的"
            "历史状态以及因 bug failed 的论文）。"
            "使用 --all 可重置全部论文（包括 success 状态的），"
            "适用于修改 domain_description 后重新判断所有论文的相关性。"
            "\n\n受影响的状态列:"
            "\n  llm_relevance_status      → pending"
            "\n  llm_relevance_error       → NULL"
            "\n  llm_relevance_date        → NULL"
            "\n  llm_relevance_result      → NULL"
            "\n  llm_relevance_confidence  → NULL"
            "\n  llm_relevance_reason      → NULL"
            "\n  不受影响（保持不变）:"
            "\n  semantic_*, publisher_page_*, mineru_*,"
            "\n  llm_summary_*, report_*"
            "\n  级联: 无"
            "\n\n示例:"
            "\n  python tools/reset_pipeline.py reset-relevance"
            "\n    → 仅重置失败/跳过的论文（修正历史遗留问题）"
            "\n  python tools/reset_pipeline.py reset-relevance --all"
            "\n    → 重置全部论文（含 success），修改 domain_description 后使用"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rel.add_argument("--publisher", help="仅重置指定出版社")
    p_rel.add_argument("--all", action="store_true",
        help="重置全部论文（含 success），修改 domain_description 后重新判断时使用")

    p_sum = sub.add_parser("reset-summary",
        help="重置 LLM 总结状态（加 --all 重置包括 success 的全部论文）",
        description=(
            "默认只重置 failed + skipped 的论文。"
            "使用 --all 可重置全部论文（包括 success 状态的），"
            "适用于 prompt 修改后重新生成所有总结。"
            "\n\n受影响的状态列:"
            "\n  llm_summary_status   → pending"
            "\n  llm_summary_error    → NULL"
            "\n  llm_summary_date     → NULL"
            "\n  llm_summary_result   → NULL"
            "\n  不受影响:"
            "\n  mineru_*, llm_relevance_*, semantic_*, report_*"
            "\n\n示例:"
            "\n  python tools/reset_pipeline.py reset-summary"
            "\n    → 仅重置失败/跳过的论文"
            "\n  python tools/reset_pipeline.py reset-summary --all"
            "\n    → 重置全部论文（含 success），重新生成所有总结"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_sum.add_argument("--publisher", help="仅重置指定出版社")
    p_sum.add_argument("--all", action="store_true",
        help="重置全部论文（含 success），修改 prompt 后重新生成总结时使用")

    p_rpt = sub.add_parser("reset-report",
        help="重置报告状态，使已报告论文重新出现在下次报告中",
        description=(
            "将 report_date 不为空的论文重置为 NULL，"
            "使其重新汇入下次生成的报告。"
            "支持 --today 和 --days 参数按日历日期重置，适用于同一天重试的场景。"
            "\n\n受影响的状态列:"
            "\n  report_status   → pending"
            "\n  report_date     → NULL"
            "\n  不重置: 其他所有列"
            "\n\n示例:"
            "\n  python tools/reset_pipeline.py reset-report"
            "\n    → 重置全部已报告论文"
            "\n  python tools/reset_pipeline.py reset-report --today"
            "\n    → 仅重置今天（当前自然日）被报告的论文"
            "\n  python tools/reset_pipeline.py reset-report --days 3"
            "\n    → 仅重置最近 3 个自然日内被报告的论文"
            "\n  python tools/reset_pipeline.py reset-report --today --publisher aps"
            "\n    → 仅重置今天 APS 出版社的被报告论文"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rpt.add_argument("--publisher", help="仅重置指定出版社")
    p_rpt.add_argument("--today", action="store_true",
        help="仅重置今天（当前自然日）被报告的论文")
    p_rpt.add_argument("--days", type=int,
        help="按日历日重置最近 N 天被报告的论文（如 --days 3 表示最近 3 个自然日）")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"数据库文件不存在: {DB_PATH}")
        print("请确保已运行过 python src/main.py")
        sys.exit(1)

    if args.command == "reset-semantic":
        cmd_reset_semantic(args.publisher)
    elif args.command == "reset-publisher":
        cmd_reset_publisher(args.publisher)
    elif args.command == "reset-mineru":
        cmd_reset_mineru(args.publisher)
    elif args.command == "reset-relevance":
        cmd_reset_relevance(args.publisher, reset_all=args.all)
    elif args.command == "reset-summary":
        cmd_reset_summary(args.publisher, reset_all=args.all)
    elif args.command == "reset-report":
        cmd_reset_report(args.publisher, days=args.days, today=args.today)
