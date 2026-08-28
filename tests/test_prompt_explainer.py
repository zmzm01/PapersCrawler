"""
Tests: Prompt explainer (prompt_explainer.py)

Coverage:
  - render_relevance_prompt() output structure (scope block replaced,
    paper placeholders kept, JSON example inserted)
  - render_summary_prompt() returns yaml content as-is
  - render_all_prompts() returns both keys
  - Error handling: empty scope_definition keeps {scope_block} literal
  - Double-replacement safety: curly braces in scope block content
"""

from unittest.mock import patch



# ---- Real-data tests (use actual configs/keywords.yaml) ----

def test_relevance_prompt_contains_scope_block():
    """After rendering, {scope_block} placeholder must be replaced
    with actual research scope content."""
    from processors.prompt_explainer import render_relevance_prompt

    prompt = render_relevance_prompt()
    assert "{scope_block}" not in prompt, (
        "{scope_block} was not replaced in relevance prompt"
    )
    # Should contain some sub-domain content from keywords.yaml
    assert "Sub-Domain:" in prompt or "Research Scope" in prompt


def test_relevance_prompt_keeps_paper_placeholders():
    """Paper-specific placeholders {title}, {abstract}, {doi}
    must remain in the system prompt (they're per-instance fields)."""
    from processors.prompt_explainer import render_relevance_prompt

    prompt = render_relevance_prompt()
    assert "{title}" in prompt, "{title} placeholder missing"
    assert "{abstract}" in prompt, "{abstract} placeholder missing"
    assert "{doi}" in prompt, "{doi} placeholder missing"


def test_relevance_prompt_contains_json_example():
    """JSON example must be rendered into the prompt (check typical
    fields from build_default_prompt output)."""
    from processors.prompt_explainer import render_relevance_prompt

    prompt = render_relevance_prompt()
    # Fields present in build_default_prompt() output
    assert "PredictedCategory" in prompt
    assert "MatchedSubfields" in prompt
    assert "Confidence" in prompt
    assert "Notes" in prompt
    # The placeholder itself should be gone
    assert "{json_example}" not in prompt


def test_summary_prompt_unchanged():
    """render_summary_prompt() returns the yaml content directly,
    without any substitution or modification."""
    from processors.prompt_explainer import render_summary_prompt

    prompt = render_summary_prompt()
    assert isinstance(prompt, str) and len(prompt) > 0
    # Key phrases from configs/prompts/summary.yaml
    assert "one_sentence" in prompt
    assert "motivation_and_goal" in prompt
    assert "key_setup_and_method" in prompt
    assert "main_results_and_physics" in prompt
    assert "take_home_message" in prompt


def test_render_all_prompts_returns_both():
    """render_all_prompts() must return a dict with both keys,
    and values must be non-empty strings."""
    from processors.prompt_explainer import render_all_prompts

    result = render_all_prompts()
    assert isinstance(result, dict)
    assert set(result.keys()) == {"relevance", "summary"}
    assert len(result["relevance"]) > 0
    assert len(result["summary"]) > 0
    # relevance should have paper placeholders (not summary's fields)
    assert "{title}" in result["relevance"]
    # summary should have structured JSON field names
    assert "one_sentence" in result["summary"]


# ---- Mock-based edge-case tests ----

def test_handles_empty_scope_definition():
    """When scope_definition is empty, the function must not crash
    and must keep {scope_block} literal (graceful degradation)."""
    from processors.prompt_explainer import render_relevance_prompt

    empty_keywords = {
        "scope_definition": {},
        "context_gates": [],
        "irrelevant_fields": {"description": "", "topics": []},
    }

    with patch("processors.prompt_explainer.load_keywords",
               return_value=empty_keywords):
        prompt = render_relevance_prompt()

    # Must still be a valid string with paper placeholders
    assert isinstance(prompt, str) and len(prompt) > 0
    assert "{title}" in prompt
    assert "{abstract}" in prompt
    assert "{doi}" in prompt
    # {scope_block} kept literal when scope_definition is empty
    assert "{scope_block}" in prompt, (
        "Empty scope_definition should keep {scope_block} literal"
    )
    # json_example should still be replaced
    assert "{json_example}" not in prompt
    assert "PredictedCategory" in prompt


def test_no_double_replacement():
    """Scope block content containing curly braces must not cause
    erroneous double-replacement or format errors.

    str.replace("{scope_block}", ...) is literal, so {} in the
    replacement text are inherently safe. This test verifies that
    a scope block containing {} survives the replacement correctly.
    """
    from processors.prompt_explainer import render_relevance_prompt

    # Simulate a scope block with LaTeX-like curly braces
    curly_scope = "Sub-Domain: test\nLaTeX: $E = mc^2$ with {braces}"
    irrelevant_fields = {"description": "", "topics": []}

    with (
        patch("processors.prompt_explainer.build_scope_block",
              return_value=curly_scope),
        patch("processors.prompt_explainer.load_keywords",
              return_value={
                  "scope_definition": {"test_domain": {
                      "description": "Test",
                      "topics": ["test topic"],
                  }},
                  "context_gates": [],
                  "irrelevant_fields": irrelevant_fields,
              }),
    ):
        prompt = render_relevance_prompt()

    # The curly braces from scope block must be present in output
    assert "{braces}" in prompt, (
        "Curly braces from scope block content must survive replacement"
    )
    assert "Sub-Domain: test" in prompt
    assert "LaTeX:" in prompt
    # {scope_block} must not remain as a literal placeholder
    assert "{scope_block}" not in prompt
    # paper placeholders must survive
    assert "{title}" in prompt


def test_handles_load_prompt_none():
    """When load_prompt('relevance') returns None, render_relevance_prompt
    should return an empty string without crashing."""
    from processors.prompt_explainer import render_relevance_prompt

    with patch("processors.prompt_explainer.load_prompt",
               return_value=None) as mock_load:
        result = render_relevance_prompt()
        mock_load.assert_called_once_with("relevance")
    assert result == ""


def test_summary_prompt_none():
    """When load_prompt('summary') returns None, render_summary_prompt
    returns empty string."""
    from processors.prompt_explainer import render_summary_prompt

    with patch("processors.prompt_explainer.load_prompt",
               return_value=None) as mock_load:
        result = render_summary_prompt()
        mock_load.assert_called_once_with("summary")
    assert result == ""
