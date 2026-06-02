#!/usr/bin/env python
"""
调试 LLM 总结的 JSON 解析失败问题。

用法: python tools/debug_llm_summary.py 10.1063/5.0322895

从数据库读取该 DOI 的 MinerU 全文，调用 DeepSeek API 生成总结，
在 json.loads 失败时打印详细的上下文信息和正则修复对比。
"""

import json
import re
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
# 同时加入项目根目录和 src/，兼容 from config 和 from src.common 两种导入
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import DB_PATH, LLM_API_CONFIG_DICT_SUMM, SUMMARIES_PROMPT
from db.database import DatabaseClient
from processors.llm_summarize_deepseek import DeepSeekPaperSummarizer
from processors.paper_relevance import LLMAPICallError, LLMResponseParseError


def show_context(text: str, error_pos: int, label: str, width: int = 60):
    """打印错误位置附近的上下文。"""
    start = max(0, error_pos - width)
    end = min(len(text), error_pos + width)
    ctx = text[start:end]
    pointer = ' ' * (error_pos - start) + '^^^'
    print(f"\n--- {label} (pos {error_pos}+-{width}) ---")
    print(f"  {ctx!r}")
    print(f"  {pointer}")
    print(f"  字符: {ctx[max(0, error_pos-start-2):error_pos-start+4]!r}")


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/debug_llm_summary.py <doi>")
        sys.exit(1)

    doi = sys.argv[1]
    fix_re = re.compile(r'\\(?![\\"/bfnrtu])')

    # 从数据库读取论文全文
    db = DatabaseClient(DB_PATH)
    cur = db.conn.execute(
        "SELECT title, mineru_fulltext FROM papers WHERE doi = ?", (doi,)
    )
    row = cur.fetchone()
    if not row:
        print(f"DOI 未找到: {doi}")
        sys.exit(1)

    title = row["title"] or ""
    mineru_text = row["mineru_fulltext"] or ""
    if not mineru_text.strip():
        print(f"MinerU 全文为空，无法总结")
        sys.exit(1)

    article_text = f"标题: {title}\n\n全文:\n{mineru_text}"
    print(f"论文: {title}")
    print(f"全文长度: {len(mineru_text)} 字符")
    print("\n--- 调用 DeepSeek API ---")

    summarizer = DeepSeekPaperSummarizer(llm_api_config=LLM_API_CONFIG_DICT_SUMM)

    try:
        result_str = summarizer.call_deepseek_api(article_text, SUMMARIES_PROMPT)
    except (LLMAPICallError, LLMResponseParseError) as e:
        print(f"API 调用失败: {e}")
        sys.exit(1)

    print(f"API 返回长度: {len(result_str)} 字符")
    print(f"\n--- 原始响应 (首 2000 字符) ---")
    print(result_str[:2000])
    print(f"\n... (省略 {len(result_str) - 2000 - 500} 字符) ...")
    print(f"\n--- 原始响应 (尾 500 字符) ---")
    print(result_str[-500:])

    # 尝试 json.loads
    try:
        parsed = json.loads(result_str)
        print(f"\n✅ json.loads 成功，字段: {list(parsed.keys())}")
        return
    except json.JSONDecodeError as e:
        print(f"\n❌ json.loads 失败: {e}")
        error_pos = e.pos
        print(f"   行 {e.lineno} 列 {e.colno} 位置 {e.pos}")

        # 显示原始字符串中错误位置附近的上下文
        show_context(result_str, error_pos, "原始字符串")

    # 应用正则修复
    fixed = fix_re.sub(r'\\\\', result_str)
    print(f"\n正则修复后长度: {len(fixed)} 字符")

    # 显示修复前后差异
    diff_count = 0
    for i, (a, b) in enumerate(zip(result_str, fixed)):
        if a != b:
            diff_count += 1
            if diff_count <= 5:
                ctx = result_str[max(0, i-10):i+10]
                print(f"  差异 {diff_count} @ pos {i}: {a!r} -> {b!r} 上下文: {ctx!r}")

    try:
        parsed = json.loads(fixed)
        print(f"\n✅ 正则修复后 json.loads 成功!")
        print(f"   字段: {list(parsed.keys())}")
    except json.JSONDecodeError as e:
        print(f"\n❌ 正则修复后仍失败: {e}")
        show_context(fixed, e.pos, "修复后字符串")
        # 对修复后的字符串再做一次更激进的修复：所有反斜杠都加倍
        super_fixed = re.sub(r'\\', r'\\\\', result_str)
        try:
            parsed = json.loads(super_fixed)
            print(f"\n✅ 激进修复后 json.loads 成功!")
        except json.JSONDecodeError as e:
            print(f"\n❌ 激进修复也失败")


if __name__ == "__main__":
    main()
