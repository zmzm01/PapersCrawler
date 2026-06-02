#!/usr/bin/env python
"""
重置 abstract 为空字符串的论文的语义/相关性/报告状态。
MinerU 和 LLM 总结结果保留不变。

用法: python tools/reset_empty_abstract.py
"""
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "papers.db"

RESET_SQL = """
UPDATE papers
SET semantic_similarity_score = NULL,
    semantic_filter_status = 'pending',
    semantic_filter_error = NULL,
    semantic_filter_date = NULL,
    llm_relevance_status = 'pending',
    llm_relevance_result = 0,
    llm_relevance_confidence = NULL,
    llm_relevance_reason = NULL,
    llm_relevance_error = NULL,
    llm_relevance_date = NULL,
    report_status = 'pending',
    report_date = NULL
WHERE abstract = ''
"""

if __name__ == "__main__":
    conn = sqlite3.connect(str(DB_PATH))
    count = conn.execute("SELECT COUNT(*) FROM papers WHERE abstract = ''").fetchone()[0]
    conn.close()

    print(f"摘要为空的论文: {count} 篇")
    if count == 0:
        print("无需操作")
        exit()

    print("将重置这些论文的: 语义初筛 / LLM 相关性 / 报告状态")
    print("保留: MinerU 全文 / LLM 总结")
    resp = input(f"确认重置 {count} 篇？[y/N] ").strip().lower()
    if resp not in ("y", "yes"):
        print("已取消")
        exit()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(RESET_SQL)
    conn.commit()
    conn.close()
    print(f"已重置 {count} 篇论文的 Phase D/E/G 状态")
