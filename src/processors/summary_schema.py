"""Canonical schema and compatibility helpers for Phase F summaries."""

from __future__ import annotations

import re
from typing import Any, Callable

SUMMARY_SCHEMA_VERSION = 3

_SECTION_DEFAULTS = {
    "motivation_and_goal": {
        "background": "未提供",
        "research_gap": "未提供",
        "objective": "未提供",
    },
    "key_setup_and_method": {
        "study_type": "未提供",
        "method": "未提供",
        "setup_and_parameters": "未提供",
        "analysis_or_model": "未提供",
        "key_equations": "未提供",
    },
    "take_home_message": {
        "contribution": "未提供",
        "implication": "未提供",
    },
}

_SECTION_LABELS = {
    "motivation_and_goal": {
        "background": "研究背景",
        "research_gap": "研究缺口或争议",
        "objective": "本文目标",
    },
    "key_setup_and_method": {
        "method": "方法",
        "setup_and_parameters": "装置与关键参数",
        "analysis_or_model": "分析方法或模型",
        "key_equations": "关键公式",
    },
    "take_home_message": {
        "contribution": "主要贡献",
        "implication": "物理启示或应用意义",
    },
}


_CONTROL_ESCAPE_SUFFIXES = {
    "\b": (
        "eta", "egin", "ar", "oxed", "inom", "oldsymbol", "ig", "igg",
    ),
    "\f": ("rac", "orall", "lat", "box"),
    "\t": (
        "imes", "ext", "heta", "au", "ilde", "o", "an", "anh", "op",
        "riangle", "ranspose",
    ),
    "\r": ("ho", "ight", "angle", "ceil", "floor", "eal"),
    "\n": (
        "abla", "eq", "u", "ot", "atural", "exists", "eg", "leq", "geq",
    ),
}

_CONTROL_ESCAPE_LETTERS = {
    "\b": "b",
    "\f": "f",
    "\t": "t",
    "\r": "r",
    "\n": "n",
}


def _restore_json_latex_escapes(text: str) -> str:
    """Recover LaTeX commands damaged while decoding malformed JSON."""
    repaired = text
    for control, suffixes in _CONTROL_ESCAPE_SUFFIXES.items():
        ordered_suffixes = sorted(suffixes, key=len, reverse=True)
        suffix_pattern = "|".join(re.escape(suffix) for suffix in ordered_suffixes)
        pattern = re.compile(
            re.escape(control) + f"({suffix_pattern})(?![A-Za-z])",
        )
        repaired = pattern.sub(
            lambda match: "\\"
            + _CONTROL_ESCAPE_LETTERS[control]
            + match.group(1),
            repaired,
        )
    return repaired


def _convert_dollar_math(text: str) -> str:
    """Convert common dollar-delimited math to the project delimiters."""
    repaired = re.sub(
        r"(?<!\\)\$\$(.+?)(?<!\\)\$\$",
        lambda match: r"\[" + match.group(1) + r"\]",
        text,
        flags=re.DOTALL,
    )
    return re.sub(
        r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$(?!\$)",
        lambda match: r"\(" + match.group(1) + r"\)",
        repaired,
        flags=re.DOTALL,
    )


def repair_llm_text_artifacts(text: str) -> str:
    """Repair deterministic text artifacts found in LLM summary fields.

    This function is intentionally conservative.  It restores a small set of
    LaTeX commands whose first character was interpreted as a JSON escape
    (for example ``\\beta`` becoming backspace + ``eta``), and converts dollar
    math delimiters to the delimiters used by the report renderer.  Semantic
    LaTeX rewrites, such as flattening ``cases`` or ``pmatrix`` environments,
    remain the responsibility of FormulaFixer.

    Parameters
    ----------
    text : str
        Text returned by an LLM after JSON decoding.

    Returns
    -------
    str
        Text with deterministic encoding and delimiter artifacts repaired.
    """
    if not isinstance(text, str):
        return text
    repaired = _restore_json_latex_escapes(text)
    return _convert_dollar_math(repaired)


def _text(value: Any) -> str:
    """Convert a schema value to a display-safe text string."""
    if value is None:
        return "未提供"
    if isinstance(value, str):
        return repair_llm_text_artifacts(value.strip()) or "未提供"
    return repair_llm_text_artifacts(str(value))


def _normalize_fixed_section(value: Any, section_name: str) -> dict[str, str]:
    """Normalize a fixed-key section while accepting legacy strings."""
    defaults = _SECTION_DEFAULTS[section_name]
    if isinstance(value, dict):
        return {key: _text(value.get(key, default))
                for key, default in defaults.items()}
    legacy_text = _text(value)
    # A legacy plain-text method section represented the method itself.  The
    # v3 machine metadata ``study_type`` now precedes it in the dict, so do
    # not accidentally migrate old text into that enum field.
    first_key = (
        "method"
        if section_name == "key_setup_and_method"
        else next(iter(defaults))
    )
    normalized = dict(defaults)
    normalized[first_key] = legacy_text
    return normalized


def _legacy_result_items(value: Any) -> list[dict[str, str]]:
    """Turn a legacy Markdown result paragraph into keyed result items."""
    if isinstance(value, list):
        raw_items = value
    else:
        raw_text = _text(value)
        raw_text = raw_text.replace("\\n", "\n")
        heading_matches = list(re.finditer(
            r"(?m)^\s*#{1,6}\s+(.+?)\s*$", raw_text,
        ))
        if heading_matches:
            raw_items = []
            for index, match in enumerate(heading_matches):
                end = (heading_matches[index + 1].start()
                       if index + 1 < len(heading_matches) else len(raw_text))
                raw_items.append({
                    "title": match.group(1).strip().rstrip("#").strip(),
                    "finding": raw_text[match.end():end].strip(),
                })
        else:
            bullets = re.findall(r"(?m)^\s*[-*]\s+(.+)$", raw_text)
            raw_items = bullets or [raw_text]

    normalized_items = []
    used_keys = set()
    for index, item in enumerate(raw_items, start=1):
        if isinstance(item, dict):
            item_key = _text(item.get("key")) if item.get("key") else f"result_{index}"
            if item_key in used_keys or item_key == "未提供":
                item_key = f"result_{index}"
            used_keys.add(item_key)
            normalized_items.append({
                "key": item_key,
                "title": _text(item.get("title") or item.get("label") or f"结果 {index}"),
                "finding": _text(item.get("finding") or item.get("result") or item.get("content")),
                "evidence": _text(item.get("evidence")),
                "physical_interpretation": _text(
                    item.get("physical_interpretation") or item.get("physics")
                ),
            })
        else:
            normalized_items.append({
                "key": f"result_{index}",
                "title": f"结果 {index}",
                "finding": _text(item),
                "evidence": "未提供",
                "physical_interpretation": "未提供",
            })
    return normalized_items or [{
        "key": "result_1",
        "title": "主要结果",
        "finding": "未提供",
        "evidence": "未提供",
        "physical_interpretation": "未提供",
    }]


def _normalize_limitations(source: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize meaningful explicit and inferred limitations into records.

    ``未提供`` is a valid placeholder for a missing scalar field, but it is
    not a meaningful limitation.  Dropping such records prevents a malformed
    model response from becoming a report item such as ``局限 1: 未提供``.
    """
    value = source.get("limitations")
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, dict):
        raw_items = [value]
    elif value:
        raw_items = [value]
    else:
        legacy_takeaway = source.get("take_home_message")
        if isinstance(legacy_takeaway, dict) and legacy_takeaway.get("limitation"):
            raw_items = [{
                "limitation": legacy_takeaway.get("limitation"),
                "basis": "explicit",
            }]
        else:
            raw_items = []

    normalized_items = []
    used_keys = set()
    for index, item in enumerate(raw_items, start=1):
        if isinstance(item, dict):
            item_key = _text(item.get("key")) if item.get("key") else f"limitation_{index}"
            if item_key in used_keys or item_key == "未提供":
                item_key = f"limitation_{index}"
            used_keys.add(item_key)
            normalized_item = {
                "key": item_key,
                "limitation": _text(
                    item.get("limitation") or item.get("description")
                ),
                "impact": _text(item.get("impact")),
                "basis": _text(item.get("basis") or "inferred"),
            }
            if _has_meaningful_text(normalized_item["limitation"]):
                normalized_items.append(normalized_item)
        else:
            normalized_item = {
                "key": f"limitation_{index}",
                "limitation": _text(item),
                "impact": "未提供",
                "basis": "inferred",
            }
            if _has_meaningful_text(normalized_item["limitation"]):
                normalized_items.append(normalized_item)

    return normalized_items


def normalize_summary(summary: Any) -> dict[str, Any]:
    """Return a versioned, predictable summary structure.

    The function accepts both the new schema and historical summaries whose
    sections were plain strings or Markdown.  This lets old rows continue to
    render while new Phase F rows expose stable keys for reports and analysis.

    Parameters
    ----------
    summary : Any
        Parsed LLM result, usually a JSON object.

    Returns
    -------
    dict
        Canonical summary with ``schema_version`` and keyed sections.
    """
    source = summary if isinstance(summary, dict) else {}
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "one_sentence": _text(source.get("one_sentence")),
        "motivation_and_goal": _normalize_fixed_section(
            source.get("motivation_and_goal"), "motivation_and_goal",
        ),
        "key_setup_and_method": _normalize_fixed_section(
            source.get("key_setup_and_method"), "key_setup_and_method",
        ),
        "main_results_and_physics": _legacy_result_items(
            source.get("main_results_and_physics"),
        ),
        "limitations": _normalize_limitations(source),
        "take_home_message": _normalize_fixed_section(
            source.get("take_home_message"), "take_home_message",
        ),
    }


def _has_meaningful_text(value: Any) -> bool:
    """Return whether a normalized value contains substantive text."""
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    return bool(normalized and normalized not in {"未提供", "暂无", "无"})


def summary_quality_issues(summary: Any) -> list[str]:
    """Validate the minimum substantive content of a Phase F summary.

    JSON validity and schema normalization alone cannot distinguish a useful
    summary from a response that fills nearly every field with ``未提供``.
    This gate requires a sentence, at least one concrete result, and enough
    additional content to make the record useful for reports and downstream
    analysis.  Missing equations remain acceptable because many papers do not
    present a compact equation suitable for the summary.

    Parameters
    ----------
    summary : Any
        Parsed LLM response or an already normalized summary.

    Returns
    -------
    list[str]
        Human-readable validation issues.  An empty list means the summary
        passes the minimum quality gate.
    """
    normalized = normalize_summary(summary)
    issues = []
    if not _has_meaningful_text(normalized["one_sentence"]):
        issues.append("one_sentence is empty")

    result_items = normalized["main_results_and_physics"]
    meaningful_results = [
        item for item in result_items
        if _has_meaningful_text(item.get("finding"))
    ]
    if not meaningful_results:
        issues.append("main_results_and_physics has no substantive finding")

    method_section = normalized["key_setup_and_method"]
    if not _has_meaningful_text(method_section.get("method")):
        issues.append("key_setup_and_method.method has no substantive method")
    if not any(
        _has_meaningful_text(method_section.get(field))
        for field in ("method", "setup_and_parameters", "analysis_or_model")
    ):
        issues.append(
            "key_setup_and_method has no substantive method/setup/analysis",
        )

    content_values = [normalized["one_sentence"]]
    for section_name in (
        "motivation_and_goal", "key_setup_and_method", "take_home_message",
    ):
        content_values.extend(normalized[section_name].values())
    for item in result_items:
        content_values.extend(
            item.get(field, "")
            for field in ("finding", "evidence", "physical_interpretation")
        )
    content_values.extend(
        item.get(field, "")
        for item in normalized["limitations"]
        for field in ("limitation", "impact")
    )
    meaningful_count = sum(
        _has_meaningful_text(value) for value in content_values
    )
    if meaningful_count < 4:
        issues.append(
            f"only {meaningful_count} substantive content fields (minimum 4)",
        )
    return issues


def transform_summary_texts(
    summary: dict[str, Any],
    transform: Callable[[str, str], str],
) -> dict[str, Any]:
    """Apply a text transform recursively while preserving schema keys.

    Parameters
    ----------
    summary : dict
        Canonical summary returned by :func:`normalize_summary`.
    transform : callable
        Function receiving ``text`` and its key, returning transformed text.

    Returns
    -------
    dict
        A transformed copy of the summary.
    """
    def visit(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {child_key: visit(child_value, child_key)
                    for child_key, child_value in value.items()}
        if isinstance(value, list):
            return [visit(item, key) for item in value]
        if isinstance(value, str) and key != "key":
            return transform(value, key)
        return value

    return visit(summary)


def summary_section_labels(section_name: str) -> dict[str, str]:
    """Return human-readable labels for a fixed summary section."""
    return _SECTION_LABELS.get(section_name, {})
