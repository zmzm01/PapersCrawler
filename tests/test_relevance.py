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
# (Removed in commit 1 — Phase D semantic filter is deprecated; tests
#  moved out together with the code to keep test suite green.)



