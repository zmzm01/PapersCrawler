#!/usr/bin/env python
"""
dedup_doi_case.py — 一次性迁移：DOI 大小写去重与规范化

背景：
RSS 源返回大写 DOI（如 `10.1364/OE.605615`），CrossRef 返回小写
（如 `10.1364/oe.605615`）。DOI 本身大小写不敏感，但 papers 表
`doi` 列的 UNIQUE 约束默认大小写敏感，历史数据因此出现同一论文的
两个大小写不同副本。

本脚本将全部非小写 DOI 规范化：
- 有大小写孪生记录的（同一 lower(doi) 出现两次）：按流水线进度评分
  选出"胜者"（report > summary > relevance > publisher），合并
  discovery_source，删除败者，再把胜者 DOI 更新为小写。
- 无孪生记录（单独大写 DOI）：直接 UPDATE 为小写。

安全措施：
- `--dry-run` 默认只打印影响行数与计划，不写库；
- 执行前交互确认；结束后打印前后统计对照。

用法：
  python tools/dedup_doi_case.py --dry-run     # 预览
  python tools/dedup_doi_case.py               # 交互确认后执行
"""
import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "papers.db"

# 流水线进度评分（越大越靠下游，越应保留）
# 列顺序：report > summary > relevance > publisher
_STATUS_SCORE = {
    "reported": 4,
    "success": 3,
    "skipped": 2,
    "failed": 2,
    "pending": 1,
    None: 0,
}
_PROGRESS_COLUMNS = [
    "report_status",
    "llm_summary_status",
    "llm_relevance_status",
    "publisher_page_fetched_status",
]


def _progress_tuple(row):
    """返回一行记录的进度评分元组，用于比较哪个副本更靠下游。"""
    return tuple(_STATUS_SCORE.get(row[c], 0) for c in _PROGRESS_COLUMNS)


def _merge_sources(src1, src2):
    """合并两个 discovery_source 字符串（如 'rss' + 'crossref' → 'rss,crossref'）。"""
    parts = []
    for src in (src1 or "", src2 or ""):
        for s in src.split(","):
            s = s.strip()
            if s and s not in parts:
                parts.append(s)
    return ",".join(parts)


def _load_conn():
    if not DB_PATH.exists():
        print(f"数据库文件不存在: {DB_PATH}")
        print("请确保已运行过 python src/main.py")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def analyze(conn):
    """扫描数据库，返回 (pairs, singletons, skipped)。

    pairs: list of (upper_row, lower_row)，待去重；
    singletons: list of rows，待就地转小写；
    skipped: list of (lower_doi, group_size)，异常分组（>2 副本）仅记录不动。
    """
    rows = conn.execute(
        "SELECT * FROM papers ORDER BY lower(doi), rowid"
    ).fetchall()

    # 按 lower(doi) 分组（含全小写行，用于识别孪生对）
    groups = {}
    for row in rows:
        groups.setdefault(row["doi"].lower(), []).append(row)

    pairs = []
    singletons = []
    skipped = []
    for lower_doi, group in groups.items():
        if len(group) == 2:
            upper = next(r for r in group if r["doi"] != lower_doi)
            lower = next(r for r in group if r["doi"] == lower_doi)
            pairs.append((upper, lower))
        elif len(group) == 1:
            row = group[0]
            if row["doi"] != lower_doi:
                singletons.append(row)
        else:
            skipped.append((lower_doi, len(group)))
    return pairs, singletons, skipped


def plan_pair(upper, lower):
    """为一对孪生记录决定保留哪个、如何合并。

    规则：进度元组更大的胜（report > summary > relevance > publisher）；
    同分则保留 RSS 行（page_url 为真实文章页，Phase C 需要）。
    """
    up_tuple = _progress_tuple(upper)
    lo_tuple = _progress_tuple(lower)
    if up_tuple > lo_tuple:
        winner, loser = upper, lower
    elif lo_tuple > up_tuple:
        winner, loser = lower, upper
    else:
        # 同分：优先 RSS 行（真实 page_url）
        winner, loser = (upper, lower) if upper["discovery_source"] == "rss" else (lower, upper)

    merged_src = _merge_sources(winner["discovery_source"], loser["discovery_source"])
    winner_is_upper = winner["doi"] == upper["doi"]
    return winner, loser, merged_src, winner_is_upper


def run(dry_run=False):
    conn = _load_conn()
    pairs, singletons, skipped = analyze(conn)

    total_pairs = len(pairs)
    total_singletons = len(singletons)
    affected = total_pairs * 2 + total_singletons
    print(f"发现 {total_pairs} 对大小写孪生记录（涉及 {total_pairs * 2} 行）")
    print(f"发现 {total_singletons} 条单独非小写 DOI 记录")
    if skipped:
        print(f"警告: {len(skipped)} 组异常分组（同一 lower(doi) 有 >2 条记录），跳过不动:")
        for lower_doi, size in skipped:
            print(f"  {lower_doi} ({size} 条)")
    print(f"共涉及 {affected} 行将被修改")

    if dry_run:
        print("\n[DRY RUN] 去重详情:")
        for i, (upper, lower) in enumerate(pairs[:20], 1):
            winner, loser, merged_src, winner_is_upper = plan_pair(upper, lower)
            action = (
                f"保留 {winner['doi']}，删除 {loser['doi']}，"
                f"discovery_source → {merged_src}"
            )
            print(f"  {i}. {action}")
        if total_pairs > 20:
            print(f"  ... 其余 {total_pairs - 20} 对略")
        print("\n单例转小写示例:")
        for s in singletons[:5]:
            print(f"  {s['doi']} → {s['doi'].lower()}")
        conn.close()
        return

    confirm = input(
        f"\n将修改 {affected} 行（去重 {total_pairs} 对 + 转小写 {total_singletons} 条）。"
        "\n建议先备份 data/papers.db。继续? [y/N] "
    )
    if confirm.strip().lower() != "y":
        print("已取消")
        conn.close()
        return

    # ── 去重：先删败者，再更新胜者转小写（避免 UNIQUE 冲突） ──
    deleted = 0
    merged = 0
    for upper, lower in pairs:
        winner, loser, merged_src, winner_is_upper = plan_pair(upper, lower)
        conn.execute("DELETE FROM papers WHERE doi = ?", (loser["doi"],))
        deleted += 1
        updates = []
        params = []
        if merged_src != (winner["discovery_source"] or ""):
            updates.append("discovery_source = ?")
            params.append(merged_src)
            merged += 1
        if winner["doi"] != winner["doi"].lower():
            updates.append("doi = ?")
            params.append(winner["doi"].lower())
        if updates:
            params.append(winner["doi"])
            conn.execute(
                f"UPDATE papers SET {', '.join(updates)} WHERE doi = ?",
                params,
            )

    # ── 单例转小写 ──
    lowered = 0
    for s in singletons:
        conn.execute(
            "UPDATE papers SET doi = lower(doi) WHERE doi = ?", (s["doi"],)
        )
        lowered += 1

    conn.commit()

    # ── 前后统计对照 ──
    before = "已从快照统计（见输出上方）"
    non_lower_after = conn.execute(
        "SELECT count(*) FROM papers WHERE doi != lower(doi)"
    ).fetchone()[0]
    total_after = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
    print("\n迁移完成:")
    print(f"  删除败者副本:        {deleted}")
    print(f"  合并 discovery_source: {merged}")
    print(f"  单例转小写:          {lowered}")
    print(f"  迁移后剩余非小写 DOI: {non_lower_after}")
    print(f"  迁移后论文总数:      {total_after}（{before}）")
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="DOI 大小写去重与规范化（一次性迁移工具）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只打印计划与影响行数，不修改数据库",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
