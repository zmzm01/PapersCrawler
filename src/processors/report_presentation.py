"""Shared structured presentation data for paper reports."""

from __future__ import annotations

from typing import Any

RELEVANCE_LEGEND = [
    {"code": "A", "name": "直接相关", "description": "直接研究课题组核心方向的理论 / 实验 / 模拟"},
    {"code": "B", "name": "间接相关", "description": "研究相关技术或方法，对课题组有潜在参考价值"},
    {"code": "C", "name": "同领域但距离远", "description": "同领域但距离核心方向较远"},
    {"code": "D", "name": "不相关", "description": "与课题组方向不相关"},
]
DISCLAIMERS = [
    "本报告将 C 类作为“邻近观察”一并收录，以缓解严格 A/B 口径导致的条目过少，并为 prompt 设计边界与表达局限可能造成的遗漏提供人工观察缓冲；C 类不等同于正式推荐。",
    "筛选 prompt 调整后，部分历史文献可能被重新召回，使单次报告收录量明显增加。",
    "RSS 历史回溯可能纳入较早发表（数月甚至数年前）的文献。",
    "相关性判定受 prompt 表述、LLM 能力上限及仅以摘要为输入的信息局限影响，结果可能存在偏差，请结合论文全文进一步判断。",
]
SORT_NOTE = "按相关性等级 A → B → C → D 排列，同等级内按日期倒序（最新在前）。"


def build_report_presentation(
    scope_definition: dict[str, dict[str, Any]] | None = None,
    papers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build metadata shared by Markdown, HTML, and public reports.

    Parameters
    ----------
    scope_definition : dict, optional
        Configured subfield definitions used for display labels.
    papers : list of dict, optional
        Papers used to calculate decision summary counters.

    Returns
    -------
    dict
        Structured presentation metadata.
    """
    papers = papers or []
    labels = {
        key: section.get("display_name", key)
        for key, section in (scope_definition or {}).items()
        if isinstance(section, dict)
    }
    return {
        "sortNote": SORT_NOTE,
        "relevanceLegend": RELEVANCE_LEGEND,
        "disclaimers": DISCLAIMERS,
        "decisionSummary": {
            "core": sum(p.get("relevance_category") == "A" for p in papers),
            "watch": sum(p.get("relevance_category") == "B" for p in papers),
            "adjacent": sum(p.get("relevance_category") == "C" for p in papers),
        },
        "subfieldLabels": labels,
    }
