"""
Tests: Paper relevance detection (paper_relevance.py)

Coverage:
  - Keyword match counting (exact, partial, case-insensitive, no match)
  - Regex word boundary enforcement
  - Prompt construction
  - DeepSeek API call (mocked, offline)

All network-dependent tests are replaced with mocked responses.
"""

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from processors.paper_relevance import PaperRelevanceChecker


# ---- Helper: minimal keywords dict ----

def _make_keywords(keyword_list):
    """Build a minimal keywords dict for PaperRelevanceChecker."""
    return {
        "scope_definition": {
            "test_domain": {
                "description": "A test research domain.",
                "topics": keyword_list,
            }
        },
        "irrelevant_fields": {"description": "", "topics": []},
    }


# ---- Keyword match counting ----

def test_keyword_match_count_full_match():
    """All keywords should be counted when found in title+abstract."""
    checker = PaperRelevanceChecker(_make_keywords(
        ["laser plasma", "wakefield", "proton acceleration"]
    ))

    title = "Laser Plasma Wakefield Acceleration for Proton Generation"
    abstract = "We study laser plasma interactions with proton acceleration."
    count = checker.keyword_match_count(title, abstract)

    assert count == 3


def test_keyword_match_count_partial_no_match():
    """Partial word match should not count (word boundary protection)."""
    checker = PaperRelevanceChecker(_make_keywords(["plasma"]))

    title = "Plasmonic resonance in nanostructures"
    count = checker.keyword_match_count(title, "")
    assert count == 0


def test_keyword_match_count_case_insensitive():
    """Matching should be case-insensitive."""
    checker = PaperRelevanceChecker(_make_keywords(["laser"]))

    count = checker.keyword_match_count("LASER cooling", "")
    assert count == 1


def test_keyword_match_count_no_match():
    """Unrelated paper should return 0."""
    checker = PaperRelevanceChecker(_make_keywords(["laser", "plasma"]))

    count = checker.keyword_match_count(
        "Gravitational waves from binary systems",
        "We detect gravitational waves using LIGO."
    )
    assert count == 0


def test_keyword_match_count_empty_keywords():
    """Empty keyword list should return 0."""
    checker = PaperRelevanceChecker(_make_keywords([]))
    count = checker.keyword_match_count("Laser plasma", "Abstract")
    assert count == 0


def test_keyword_match_count_unique_keywords():
    """Duplicate keyword hits should only count once."""
    checker = PaperRelevanceChecker(_make_keywords(["laser"]))

    count = checker.keyword_match_count("Laser Laser LASER",
                                         "the laser experiment laser")
    assert count == 1


# ---- Prompt construction ----

def test_build_default_prompt():
    """Verify LLM prompt construction includes scope, title, abstract."""
    checker = PaperRelevanceChecker(_make_keywords(
        ["laser plasma", "wakefield"]
    ))

    prompt = checker.build_default_prompt(
        "Laser Wakefield", "Acceleration physics", doi="10.1234/test"
    )

    assert "test_domain" in prompt
    assert "Laser Wakefield" in prompt
    assert "Acceleration physics" in prompt
    assert "PredictedCategory" in prompt
    assert "MatchedSubfields" in prompt
    assert "10.1234/test" in prompt


def test_init_with_whitespace_keywords():
    """Keywords with whitespace should be trimmed and deduplicated."""
    checker = PaperRelevanceChecker(_make_keywords(
        ["  laser  ", "plasma", "", "  wakefield  "]
    ))
    assert len(checker.keywords) == 3
    assert "laser" in checker.keywords


# ---- Prompt structure: 3-step decision tree (a)/(b)/(c)/(d) ----

def _make_full_keywords():
    """Build a keywords dict covering all three steps (gates + denylist + sub-domains)."""
    return {
        "scope_definition": {
            "acceleration": {
                "description": "本方向研究激光驱动离子加速。",
                "topics": ["Target Normal Sheath Acceleration (TNSA)"],
            },
        },
        "context_gates": [
            {
                "term": "plasma",
                "description": '"Plasma" 出现在 fusion 语境时不应视为相关。',
                "relevant_contexts": ["laser-driven particle acceleration"],
                "irrelevant_contexts": ["fusion plasma (tokamak, ITER)"],
            },
        ],
        "irrelevant_fields": {
            "description": "Topic-level 黑名单。",
            "topics": ["Collider physics: Standard Model, dark matter"],
        },
    }


def test_build_scope_block_renders_in_three_step_order():
    """scope_block must render Step 1 (gates) -> Step 2 (denylist) -> Step 3 (sub-domains)."""
    from config import build_scope_block

    block = build_scope_block(
        scope_definition=_make_full_keywords()["scope_definition"],
        context_gates=_make_full_keywords()["context_gates"],
        irrelevant_fields=_make_full_keywords()["irrelevant_fields"],
    )

    pos_gates = block.find("Step 1: Global Context Rules")
    pos_irr = block.find("Step 2: Irrelevant Fields")
    pos_sub = block.find("Sub-Domain: acceleration")

    assert pos_gates != -1, "Step 1 section missing"
    assert pos_irr != -1, "Step 2 section missing"
    assert pos_sub != -1, "Sub-Domain section missing"
    assert pos_gates < pos_irr < pos_sub, (
        f"Rendering order must be gates -> denylist -> sub-domains, "
        f"got positions {pos_gates} {pos_irr} {pos_sub}"
    )


def test_build_scope_block_renders_beam_irradiation_core_anchor():
    """Beam irradiation/applications must be available to the A evidence gate."""
    from config import build_scope_block

    anchor = "束流辐照效应与明确下游应用（材料、辐射生物、成像等）"
    block = build_scope_block(
        scope_definition=_make_full_keywords()["scope_definition"],
        core_anchors=[anchor],
    )

    assert "Core anchors (positive evidence gate)" in block
    assert anchor in block


def test_build_default_prompt_contains_decision_tree_steps():
    """Final prompt must surface the (a)/(b)/(c)/(d) decision tree."""
    checker = PaperRelevanceChecker(_make_full_keywords())
    prompt = checker.build_default_prompt(
        title="Test Title",
        abstract="Test abstract.",
        doi="10.1234/test",
    )

    # Decision tree branches
    assert "(a)" in prompt
    assert "(b)" in prompt
    assert "(c)" in prompt
    assert "(d)" in prompt

    # Step 2 explicit YES/NO branch
    assert "YES" in prompt and "NO" in prompt

    # Step 1/2 section titles rendered into scope_block
    assert "Step 1: Global Context Rules" in prompt
    assert "Step 2: Irrelevant Fields" in prompt


def test_build_default_prompt_contains_category_definitions():
    """A/B/C/D must be defined in the decision tree (c) step."""
    checker = PaperRelevanceChecker(_make_full_keywords())
    prompt = checker.build_default_prompt(
        title="T", abstract="A", doi="10.1/x"
    )

    # Anchored phrases unique to the (c) descriptions
    assert "Directly studies the group's core topics" in prompt
    assert "transferable method/technology" in prompt
    assert "Same broad field, but distant" in prompt
    assert "Outside the research area" in prompt


def test_irrelevant_topic_collision_removed():
    """Topics covered by context_gates must NOT appear in irrelevant_fields.

    Regression guard: if someone re-adds "Fusion" to irrelevant_fields, the
    two layers would conflict (Step 1 says irrelevant_contexts excludes
    fusion plasma, Step 2 says whole Fusion field is D — but Step 1 is
    term-level and Step 2 is topic-level, so the topic Fusion is now
    covered by Step 1's gate "plasma").
    """
    keywords = _make_full_keywords()
    assert "Fusion" not in keywords["irrelevant_fields"]["topics"], (
        "Fusion is covered by context_gates[plasma].irrelevant_contexts; "
        "do not duplicate in irrelevant_fields"
    )
    assert "Space plasma" not in keywords["irrelevant_fields"]["topics"]
    assert "Semiconductor plasma" not in keywords["irrelevant_fields"]["topics"]
    assert "General AI/ML" not in keywords["irrelevant_fields"]["topics"]


def test_decision_tree_a_assigns_d_on_irrelevant_term():
    """Step (a) must instruct: PRIMARY SUBJECT in Irrelevant Context → D.

    Topic-level judgment, not term-level: a minor passing mention of an
    out-of-scope term does not trigger D — only when the out-of-scope
    usage is what the paper is fundamentally about.
    """
    checker = PaperRelevanceChecker(_make_full_keywords())
    prompt = checker.build_default_prompt(title="T", abstract="A", doi="10.1/x")

    a_block = prompt.split("(a) Apply Context Gates", 1)[1].split("(b)", 1)[0]
    # Must surface the topic-level D trigger
    assert "Assign D directly" in a_block
    assert "PRIMARY SUBJECT" in a_block or "primary subject" in a_block.lower()
    # Must explicitly carve out minor mentions
    assert "Minor passing mentions" in a_block, (
        "Step (a) must clarify that minor passing mentions of an "
        "out-of-scope term do NOT trigger D"
    )
    # Out-of-scope term usages must still be excluded from sub-domain matching
    assert "MUST NOT contribute to sub-domain matching" in a_block


def test_boundary_rules_allow_transferable_but_not_out_of_scope_a():
    """The prompt must encode the three recently reviewed boundary cases."""
    checker = PaperRelevanceChecker(_make_full_keywords())
    prompt = checker.build_default_prompt(title="T", abstract="A", doi="10.1/x")

    assert "ICF/cryogenic fusion target injection is not A" in prompt
    assert "high-repetition laser-focus" in prompt
    assert "plasma waveguide or channel" in prompt
    assert "even when its demonstrated application is pure electron LWFA" in prompt
    assert "FLASH/MHD algorithms" in prompt
    assert "mere FLASH/tool-name mention is not B" in prompt
    assert "concrete method, device, algorithm" in prompt


def test_context_gate_does_not_make_transferable_methods_automatically_d():
    """Out-of-scope context forbids A but leaves the explicit B exception."""
    checker = PaperRelevanceChecker(_make_full_keywords())
    prompt = checker.build_default_prompt(title="T", abstract="A", doi="10.1/x")
    a_block = prompt.split("(a) Apply Context Gates", 1)[1].split("(b)", 1)[0]

    assert "cannot be category A" in a_block
    assert "allow B" in a_block
    assert "Assign D directly only when" in a_block


def test_irrelevant_fields_remain_hard_rejects():
    """Topic-level blacklists must not become a broad B back door."""
    checker = PaperRelevanceChecker(_make_full_keywords())
    prompt = checker.build_default_prompt(title="T", abstract="A", doi="10.1/x")
    b_block = prompt.split("(b) Check Irrelevant Fields", 1)[1].split("(c)", 1)[0]

    assert "YES → assign D" in b_block
    assert "no B exception" in b_block


# ---- DeepSeek API call (mocked) ----

def test_call_deepseek_api_mocked():
    """Mock DeepSeek API response and verify JSON parsing with new format."""
    checker = PaperRelevanceChecker(_make_keywords(
        ["laser plasma", "wakefield acceleration"]
    ))
    prompt = checker.build_default_prompt(
        "Laser wakefield acceleration of electrons",
        "We demonstrate electron acceleration to GeV energies using laser wakefields.",
        doi="10.1103/PhysRevLett.136.123456",
    )
    config = {
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key": "sk-test-key",
        "model": "deepseek-v4-flash",
        "thinking": "disabled",
        "timeout": 30,
    }

    with patch('requests.post') as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "PredictedCategory": "A",
                        "MatchedSubfields": ["Laser Wakefield Acceleration"],
                        "Confidence": "high",
                        "Notes": "Direct LWFA experiment with GeV electron acceleration.",
                    })
                }
            }]
        }
        mock_post.return_value = mock_resp

        result_str = checker.call_deepseek_api(prompt, config)
        result = json.loads(result_str)

        assert result["PredictedCategory"] == "A"
        assert result["MatchedSubfields"] == ["Laser Wakefield Acceleration"]
        assert result["Confidence"] == "high"
        assert "GeV" in result["Notes"]
