#!/usr/bin/env python
"""
数据库迁移脚本 v2：新增 skipped_dois 表 + 迁移存量 Non-Research 记录。

变更: 2026-06-10
  - 新增 skipped_dois 表（doi TEXT PRIMARY KEY, reason TEXT, created_date TEXT）
  - 扫描 papers 表中标记为 NonResearchPageError 的存量记录，迁移到
    skipped_dois 后从 papers 删除，防止未来被重新发现

用法:
    python tools/migrate_db_v2.py

幂等: 可安全重复执行。
"""

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import DB_PATH
from db.database import DatabaseClient


def _migrate_existing_non_research(db):
    """将存量 Non-Research 记录从 papers 表迁移到 skipped_dois。

    6 月 7 日前 NonResearchPageError 走 cascade skip（保留在 papers），
    这些记录需要迁移到新表。
    """
    timestamp = str(datetime.now())

    # 查找所有标记为 NonResearchPageError 的存量论文
    cur = db.conn.execute(
        "SELECT doi FROM papers "
        "WHERE publisher_page_fetched_status = 'skipped' "
        "  AND publisher_page_fetched_error LIKE 'NonResearchPageError:%'",
    )
    rows = cur.fetchall()
    if not rows:
        print("  未发现存量 Non-Research 记录。")
        return 0

    migrated = 0
    for row in rows:
        doi = row["doi"]
        try:
            db.conn.execute(
                "INSERT OR IGNORE INTO skipped_dois "
                "(doi, reason, created_date) VALUES (?, ?, ?)",
                (doi, "NonResearchPageError", timestamp),
            )
            db.conn.execute("DELETE FROM papers WHERE doi = ?", (doi,))
            migrated += 1
        except Exception as e:
            print(f"  ! 迁移失败 [{doi}]: {e}")

    return migrated


def main():
    db_path = DB_PATH
    if not Path(db_path).exists():
        print(f"数据库不存在: {db_path}")
        print("请先运行流水线（会自动创建数据库）。")
        sys.exit(1)

    print(f"数据库路径: {db_path}")
    db = DatabaseClient(db_path)

    # ---- 1. 建表 ----
    db.init_db_papers()  # 含 CREATE TABLE IF NOT EXISTS skipped_dois
    cur = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='skipped_dois'",
    )
    if cur.fetchone():
        print("✓ skipped_dois 表已就绪")
    else:
        print("✗ skipped_dois 表创建失败")
        sys.exit(1)

    # ---- 2. 迁移存量 Non-Research 记录 ----
    print("正在扫描存量 Non-Research 记录...")
    migrated = _migrate_existing_non_research(db)
    db.conn.commit()
    if migrated:
        print(f"  → 已迁移 {migrated} 条记录到 skipped_dois 并从 papers 删除")
    else:
        print("  无存量记录需要迁移。")

    # ---- 3. 统计 ----
    cur = db.conn.execute("SELECT COUNT(*) FROM skipped_dois")
    total = cur.fetchone()[0]
    print(f"✓ skipped_dois 总记录数: {total}")

    db.conn.close()
    print("迁移完成。")


if __name__ == "__main__":
    main()
