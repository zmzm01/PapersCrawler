#!/usr/bin/env python
"""
数据库迁移脚本 v3: 移除 Phase D 语义相似度相关列 (2026-07-24)。

变更:
  - DROP COLUMN semantic_similarity_score
  - DROP COLUMN semantic_filter_status
  - DROP COLUMN semantic_filter_error
  - DROP COLUMN semantic_filter_date
  - DROP COLUMN semantic_best_subdomain

Phase D (sentence-transformers 余弦相似度) 已废弃 (SKIP_PHASE_D=True 默认跳过)，
对应 DB 列在 commit "drop semantic columns and methods from DB layer" 中已不再写入。
本脚本从既有数据库的 schema 中物理删除这些列。

要求:
  - SQLite >= 3.35.0 (2021-03-12 发布, 支持 ALTER TABLE DROP COLUMN)
  - 大多数现代发行版 (Ubuntu 22.04+, Debian 11+, macOS 12+) 均满足

用法:
    python tools/migrate_db_v3.py

幂等: 列已不存在时 DROP COLUMN 会报错但被捕获跳过。
"""

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import DB_PATH

SEMANTIC_COLUMNS = [
    "semantic_similarity_score",
    "semantic_filter_status",
    "semantic_filter_error",
    "semantic_filter_date",
    "semantic_best_subdomain",
]


def _get_existing_columns(conn):
    """返回 papers 表当前所有列名。"""
    cur = conn.execute("PRAGMA table_info(papers)")
    return {row[1] for row in cur.fetchall()}


def main():
    db_path = DB_PATH
    if not Path(db_path).exists():
        print(f"数据库不存在: {db_path}")
        print("请先运行流水线（会自动创建数据库）。")
        sys.exit(1)

    # 校验 SQLite 版本
    sqlite_version = sqlite3.sqlite_version
    print(f"数据库路径: {db_path}")
    print(f"SQLite 版本: {sqlite_version}")
    if tuple(int(x) for x in sqlite_version.split(".")[:2]) < (3, 35):
        print("⚠ 警告: SQLite < 3.35 不支持 ALTER TABLE DROP COLUMN。")
        print("  升级 SQLite 后重试，或手动执行迁移。")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        existing = _get_existing_columns(conn)
        to_drop = [c for c in SEMANTIC_COLUMNS if c in existing]
        if not to_drop:
            print("✓ 所有 semantic 列已不存在，无需迁移。")
            return

        print(f"将删除 {len(to_drop)} 列: {to_drop}")
        for col in to_drop:
            try:
                conn.execute(f"ALTER TABLE papers DROP COLUMN {col}")
                print(f"  ✓ DROP COLUMN {col}")
            except sqlite3.OperationalError as e:
                print(f"  ! DROP COLUMN {col} 失败: {e}")
        conn.commit()

        # 校验
        remaining = _get_existing_columns(conn)
        leftover = [c for c in SEMANTIC_COLUMNS if c in remaining]
        if leftover:
            print(f"✗ 仍有残留列: {leftover}")
            sys.exit(1)
        print("✓ 迁移完成: 所有 semantic 列已从 papers 表删除。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
