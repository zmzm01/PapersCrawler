"""
prompt_explainer.py
===================
LLM 系统提示词渲染器。

提供两个独立的提示词渲染函数 + 一个组合函数：
- render_relevance_prompt()：渲染 Phase E 相关性判断 system_prompt
- render_summary_prompt()： 渲染 Phase F 论文总结 system_prompt
- render_all_prompts()：    一次调用返回两者的 dict

使用方式
--------
>>> from processors.prompt_explainer import render_relevance_prompt
>>> prompt = render_relevance_prompt()
>>> print(prompt[:200])  # 前 200 字符

设计决策
--------
- render_relevance_prompt() 不展开 {title}/{abstract}/{doi} 占位符，
  因为它们属于「单篇论文实例」而非「本期 snapshot」。
- 当 keywords.yaml 加载失败或 scope_definition 为空时降级为保留
  {scope_block} 字面量，不抛异常。
- 所有异常被捕获并 logging.warning，由调用方决定是否继续。
"""

import logging
from config import load_prompt, build_scope_block, build_default_prompt, load_keywords

logger = logging.getLogger(__name__)


def render_relevance_prompt() -> str:
    """渲染 Phase E 相关性判断的完整 prompt（系统提示词部分）。

    加载 configs/prompts/relevance.yaml 的 system_prompt 模板，
    用 build_scope_block() 替换 {scope_block} 占位符，
    用 build_default_prompt() 返回的 json_example 替换 {json_example} 占位符。

    **不** 展开 {title}、{abstract}、{doi} 等单篇论文占位符（保持原样），
    因为这是「本期 snapshot」，不是「单篇实例」。

    Returns
    -------
    str
        完整可发给 LLM 的 system_prompt 文本。
        当 load_prompt 返回 None 时返回空字符串。

    Notes
    -----
    降级策略：如果 keywords.yaml 加载失败或 scope_definition 为空，
    保留 {scope_block} 字面量不替换并 log warning。
    build_default_prompt 失败时保留 {json_example} 字面量。
    """
    template = load_prompt("relevance")
    if template is None:
        return ""

    keywords = load_keywords()
    scope_definition = keywords.get("scope_definition", {})
    context_gates = keywords.get("context_gates", [])
    irrelevant_fields = keywords.get("irrelevant_fields", {})
    keyword_catalog = keywords.get("keyword_catalog", [])

    # --- 替换 {scope_block} ---
    replace_scope = bool(scope_definition)
    if replace_scope:
        try:
            scope_block = build_scope_block(
                scope_definition,
                context_gates=context_gates,
                irrelevant_fields=irrelevant_fields,
                keyword_catalog=keyword_catalog,
            )
            template = template.replace("{scope_block}", scope_block)
        except Exception as exc:
            logger.warning(
                "build_scope_block failed, keeping {scope_block} literal: %s", exc
            )
            replace_scope = False

    if not replace_scope:
        logger.warning(
            "scope_definition is empty or build_scope_block failed; "
            "{scope_block} kept as literal"
        )

    # --- 替换 {json_example} ---
    try:
        json_example = build_default_prompt(scope_definition)
        template = template.replace("{json_example}", json_example)
    except Exception as exc:
        logger.warning(
            "build_default_prompt failed, keeping {json_example} literal: %s", exc
        )

    #  {{title}}, {{abstract}}, {{doi}} —— 保留原样，不替换
    return template


def render_summary_prompt() -> str:
    """渲染 Phase F 论文总结的完整 prompt。

    加载 configs/prompts/summary.yaml 的 system_prompt。
    该 yaml 无占位符，直接返回原文。

    Returns
    -------
    str
        system_prompt 文本。当 load_prompt 返回 None 时返回空字符串。
    """
    template = load_prompt("summary")
    return template if template is not None else ""


def render_all_prompts() -> dict[str, str]:
    """返回 {'relevance': ..., 'summary': ...} 一次性调用两个渲染函数。

    Returns
    -------
    dict[str, str]
        包含 'relevance' 和 'summary' 两个 key 的字典。
    """
    return {
        "relevance": render_relevance_prompt(),
        "summary": render_summary_prompt(),
    }
