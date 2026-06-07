#!/usr/bin/env python
"""
删除数据库中所有被标记为 Accepted Paper 的论文记录。

APS Accepted Paper 后续会以正式论文形式（同 DOI）发表，
当前记录会永久阻塞重新发现。此脚本清理这些记录。

用法:
  python tools/delete_accepted_papers.py              # 交互式确认后删除
  python tools/delete_accepted_papers.py --force       # 跳过确认直接删除
  python tools/delete_accepted_papers.py --dry-run     # 仅预览，不删除
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from db.database import DatabaseClient
from config import DB_PATH


def find_accepted_papers(db):
    """Find all papers marked as Accepted Paper."""
    cur = db.conn.execute("""
        SELECT doi, title, paperdate_rss, created_date
        FROM papers
        WHERE publisher_page_fetched_error LIKE 'AcceptedPaper:%'
        ORDER BY created_date DESC
    """)
    return cur.fetchall()


def main():
    parser = argparse.ArgumentParser(description="删除数据库中的 Accepted Paper 记录")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅预览，不执行删除",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="跳过确认直接删除",
    )
    args = parser.parse_args()

    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    papers = find_accepted_papers(db)

    if not papers:
        print("未发现 Accepted Paper 记录。")
        return

    print(f"发现 {len(papers)} 篇 Accepted Paper：")
    print(f"{'DOI':<40} {'标题':<50} {'日期':<12}")
    print("-" * 105)
    for p in papers:
        title = (p["title"] or "N/A")[:48]
        date = p["paperdate_rss"] or p["created_date"] or "N/A"
        print(f"{p['doi']:<40} {title:<50} {date:<12}")

    if args.dry_run:
        print(f"\nDry-run 模式，未执行删除。共 {len(papers)} 篇论文将被删除。")
        return

    if not args.force:
        confirm = input(f"\n确认删除以上 {len(papers)} 篇论文？(y/N): ")
        if confirm.lower() != "y":
            print("已取消。")
            return

    for p in papers:
        db.delete_paper(p["doi"])
        print(f"已删除: {p['doi']}")

    print(f"\n完成！共删除 {len(papers)} 篇 Accepted Paper。")


if __name__ == "__main__":
    main()
