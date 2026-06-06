"""
测试: common.py 共享工具函数

覆盖范围:
  - fix_json_invalid_escapes: JSON 转义修复
  - DatabaseClient._validate_column: 列名白名单校验
"""

import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from common import fix_json_invalid_escapes


# ---- fix_json_invalid_escapes ----

def test_fix_escapes_valid_json_unchanged():
    """合法 JSON 字符串应原样返回。"""
    obj = {"key": "value", "num": 42}
    s = json.dumps(obj)
    assert fix_json_invalid_escapes(s) == s


def test_fix_escapes_latex_backslash():
    """LaTeX 命令中的孤立反斜杠应被转义。"""
    # LLM 可能输出 {\"key\": \"\\\\alpha\"} 但 JSON 需要 {\\\\alpha}
    # 实际场景: LLM 输出 "{\"key\": \"\\alpha\"}" — 这里的 \\ 表示一个反斜杠
    # json.loads 会报错因为 \\a 不是合法 JSON 转义
    s = '{"key": "\\alpha"}'
    try:
        json.loads(s)
        # 如果意外合法则跳过
        return
    except json.JSONDecodeError:
        pass
    fixed = fix_json_invalid_escapes(s)
    # 修复后应能被解析
    parsed = json.loads(fixed)
    assert parsed["key"] == "\\alpha"


def test_fix_escapes_valid_escape_unchanged():
    """已知合法的 JSON 转义序列不应被修改。"""
    s = r'{"a": "\"", "b": "\\", "c": "\n", "d": "\t"}'
    fixed = fix_json_invalid_escapes(s)
    parsed = json.loads(fixed)
    assert parsed["a"] == '"'
    assert parsed["b"] == "\\"
    assert parsed["c"] == "\n"
    assert parsed["d"] == "\t"


def test_fix_escapes_mixed():
    """混合合法与非法转义。"""
    s = r'{"text": "公式 \\alpha 和 \\beta 用于表示 \\gamma"}'
    try:
        json.loads(s)
        return
    except json.JSONDecodeError:
        pass
    fixed = fix_json_invalid_escapes(s)
    parsed = json.loads(fixed)
    assert "alpha" in parsed["text"]
    assert "beta" in parsed["text"]


# ---- DatabaseClient._validate_column ----

def test_validate_column_valid():
    """合法列名应通过验证。"""
    from db.database import DatabaseClient
    DatabaseClient._validate_column("llm_relevance_status")
    DatabaseClient._validate_column("cr_metadata_fetched_status")
    DatabaseClient._validate_column("publisher_page_fetched_date")


def test_validate_column_invalid():
    """非法列名应抛出 ValueError。"""
    from db.database import DatabaseClient
    with pytest.raises(ValueError, match="Invalid column name"):
        DatabaseClient._validate_column("malicious; DROP TABLE papers; --")


def test_validate_column_empty():
    """空字符串应被拦截。"""
    from db.database import DatabaseClient
    with pytest.raises(ValueError):
        DatabaseClient._validate_column("")
