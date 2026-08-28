"""Build the normalized paper records shared by report output formats."""

from __future__ import annotations

import json
import re
from typing import Any

from common import clean_extracted_text
from processors.summary_schema import normalize_summary


def build_report_papers(papers) -> list[dict[str, Any]]:
    """Convert database rows into the common report paper structure.

    Parameters
    ----------
    papers : iterable
        SQLite rows containing the fields used by report generation.

    Returns
    -------
    list of dict
        Normalized records consumed by Markdown and public JSON renderers.
    """
    report_papers = []
    for paper in papers:
        summary = normalize_summary(
            _load_json_object(paper["llm_summary_result"], {})
        )
        authors = _load_json_object(paper["authors_json"], [])
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            authors = [author.get("name", "") for author in authors if author.get("name")]

        subfields = _load_json_object(paper["llm_relevance_subfields"], [])
        report_papers.append({
            "title": paper["title"] or "",
            "authors": authors,
            "date": (
                paper["paperdate_crossref"]
                or paper["paperdate_page"]
                or paper["paperdate_rss"]
                or ""
            ),
            "doi": paper["doi"] or "",
            "journal": paper["journal"] or "",
            "publisher": paper["publisher"] or "",
            "matched_subdomains": subfields,
            "relevance_category": paper["llm_relevance_category"] or "",
            "relevance_reason": paper["llm_relevance_reason"] or "",
            "relevance_basis": paper["llm_relevance_basis"] or "",
            "page_url": paper["page_url"] or "",
            "pdf_url": paper["pdf_url"] or "",
            "abstract": clean_extracted_text(paper["abstract"]) or "",
            "summary": summary,
            "one_sentence": summary.get("one_sentence", ""),
            "motivation_and_goal": summary.get("motivation_and_goal", ""),
            "key_setup_and_method": summary.get("key_setup_and_method", ""),
            "main_results_and_physics": summary.get("main_results_and_physics", ""),
            "limitations": summary.get("limitations", []),
            "take_home_message": summary.get("take_home_message", ""),
            "has_full_summary": paper["llm_summary_status"] == "success",
        })
    return report_papers


def make_report_identifier(stem: str) -> str:
    """Create a stable public-report ID suffix from an output filename stem.

    Parameters
    ----------
    stem : str
        Report filename stem supplied by the caller.

    Returns
    -------
    str
        Identifier accepted by the public export naming rules.
    """
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return f"papers-{normalized or 'report'}"


def _load_json_object(value, default):
    """Decode a JSON column and return a default value on malformed input."""
    try:
        decoded = json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return default
    return decoded
