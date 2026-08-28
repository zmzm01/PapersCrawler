"""Tests for the canonical Phase F summary schema."""

from processors.summary_schema import (
    SUMMARY_SCHEMA_VERSION,
    normalize_summary,
    repair_llm_text_artifacts,
    summary_quality_issues,
)


def test_llm_text_artifacts_restore_json_escapes_and_math_delimiters():
    """Malformed JSON LaTeX escapes and dollar math are repaired locally."""
    damaged = "\x08eta_d + \x0crac{a}{b} + \times + $x^2$ + $$y$$"
    repaired = repair_llm_text_artifacts(damaged)

    assert repaired == r"\beta_d + \frac{a}{b} + \times + \(x^2\) + \[y\]"


def test_summary_quality_gate_rejects_empty_structured_response():
    """A JSON object with only one sentence is not a usable summary."""
    issues = summary_quality_issues({"one_sentence": "只有一句话"})

    assert any("no substantive finding" in issue for issue in issues)
    assert any("minimum 4" in issue for issue in issues)


def test_legacy_summary_is_normalized_to_keyed_sections():
    """Historical Markdown output remains readable as structured data."""
    summary = normalize_summary({
        "one_sentence": "一句话",
        "motivation_and_goal": "背景和目标",
        "key_setup_and_method": "方法",
        "main_results_and_physics": "## 结果一\n发现一\n\n## 结果二\n发现二",
        "take_home_message": "贡献和局限",
    })

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["motivation_and_goal"]["background"] == "背景和目标"
    assert [item["key"] for item in summary["main_results_and_physics"]] == [
        "result_1", "result_2",
    ]
    assert summary["main_results_and_physics"][1]["title"] == "结果二"
    assert summary["limitations"] == []


def test_structured_summary_preserves_result_keys():
    """New result keys survive normalization for downstream consumers."""
    summary = normalize_summary({
        "schema_version": 2,
        "main_results_and_physics": [{
            "key": "electron_reflux",
            "title": "电子回流",
            "finding": "出现双峰",
            "evidence": "图 7",
            "physical_interpretation": "维持鞘层场",
        }],
    })
    assert summary["main_results_and_physics"][0]["key"] == "electron_reflux"
    assert summary["main_results_and_physics"][0]["evidence"] == "图 7"


def test_summary_normalization_drops_placeholder_limitation():
    """A placeholder limitation must not become a visible report item."""
    summary = normalize_summary({
        "limitations": [{
            "key": "limitation_1",
            "limitation": "未提供",
            "impact": "影响信息也无法对应到具体局限",
            "basis": "explicit",
        }],
    })

    assert summary["limitations"] == []


def test_summary_quality_gate_rejects_missing_method_section():
    """Results alone must not make an all-empty method section successful."""
    issues = summary_quality_issues({
        "one_sentence": "本文提出一种新的重建方法并验证了其效果。",
        "key_setup_and_method": {
            "study_type": "mixed",
            "method": "未提供",
            "setup_and_parameters": "未提供",
            "analysis_or_model": "未提供",
            "key_equations": "未提供",
        },
        "main_results_and_physics": [{
            "key": "result_1",
            "title": "结果",
            "finding": "重建结果与参考值一致。",
            "evidence": "图 1",
            "physical_interpretation": "模型能够恢复目标结构。",
        }],
        "take_home_message": {
            "contribution": "提出方法",
            "implication": "具有应用价值",
        },
    })

    assert any("key_setup_and_method.method" in issue for issue in issues)


def test_legacy_takeaway_limitation_is_migrated():
    """The old nested limitation is promoted to the dedicated field."""
    summary = normalize_summary({
        "take_home_message": {
            "contribution": "贡献",
            "implication": "启示",
            "limitation": "样本量有限",
        },
    })
    assert summary["limitations"][0]["limitation"] == "样本量有限"
    assert summary["limitations"][0]["basis"] == "explicit"
