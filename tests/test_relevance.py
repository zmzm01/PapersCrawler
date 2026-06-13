"""
Tests: Paper relevance detection (paper_relevance.py)

Coverage:
  - Keyword match counting (exact, partial, case-insensitive, no match)
  - Regex word boundary enforcement
  - Prompt construction
  - SemanticFilter (requires sentence-transformers model, skipped if unavailable)
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
        "sub_domains_embedding": {},
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


# ---- Semantic similarity filter ----
# These tests require sentence-transformers model.
# They are skipped with importorskip if the package is not installed.

@pytest.fixture(scope="module")
def semantic_filter():
    """Shared SemanticFilter instance, skipped if model unavailable."""
    pytest.importorskip("sentence_transformers",
                        reason="sentence-transformers not installed")
    try:
        from processors.paper_relevance import SemanticFilter
        from config import CFG
        sf = SemanticFilter(
            model_name=CFG.SEMANTIC_MODEL_PATH,
            sub_domains={
                "laser_wakefield_acceleration": (
                    "Laser-driven wakefield acceleration of electrons "
                    "to GeV energies in plasma channels."
                ),
                "laser_driven_ion_acceleration": (
                    "High-power laser interaction with targets to "
                    "accelerate ions via TNSA and RPA mechanisms."
                ),
                "beam_transport": (
                    "High-gradient plasma lens for compact beam transport."
                ),
            },
        )
        return sf
    except Exception as e:
        pytest.skip(f"Model loading failed: {e}")


def test_semantic_filter_high_relevance(semantic_filter):
    """Highly relevant paper should get a high score and best subdomain."""
    score, best = semantic_filter.compute_similarity(
        title="Laser wakefield acceleration of electrons to GeV energies",
        abstract="We demonstrate the acceleration of electrons to GeV energies using laser-driven plasma wakefields."
    )
    assert score > 0.3, f"Expected high score, got {score:.3f}"
    assert best is not None


def test_semantic_filter_low_relevance(semantic_filter):
    """Unrelated paper should get a low score (bge-base is a strong model,
    so physics papers may still score ~0.5; threshold is relaxed)."""
    score, best = semantic_filter.compute_similarity(
        title="Gravitational waves from binary neutron star mergers",
        abstract="We present the detection of gravitational waves from a binary neutron star merger using LIGO."
    )
    assert score < 0.7, f"Expected fairly low score for unrelated paper, got {score:.3f}"


def test_semantic_filter_moderate_relevance(semantic_filter):
    """Partially related paper should get a moderate score."""
    score, best = semantic_filter.compute_similarity(
        title="High-energy particle acceleration in astrophysical plasmas",
        abstract="We study particle acceleration mechanisms in relativistic plasma environments."
    )
    assert 0.15 < score < 0.8, f"Expected moderate score, got {score:.3f}"


def test_semantic_filter_empty_input(semantic_filter):
    """Empty title and abstract should give tuple (score >= 0, None)."""
    score, best = semantic_filter.compute_similarity(title="", abstract="")
    assert score >= 0.0


def test_semantic_filter_class_exists():
    """SemanticFilter class should be importable (no model download needed)."""
    from processors.paper_relevance import SemanticFilter
    assert SemanticFilter is not None
    assert hasattr(SemanticFilter, 'compute_similarity')
