"""Build the normalized paper records shared by report output formats."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from common import clean_extracted_text
from config import DATA_DIR
from processors.summary_schema import normalize_summary


def _record_value(record, field_name, default=None):
    """Read a field from either a mapping or a SQLite row safely."""
    try:
        value = record[field_name]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


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
        manual_decision = _record_value(
            paper, "manual_relevance_decision", ""
        )
        manual_notes = _record_value(paper, "manual_relevance_notes", "")
        relevance_category = _record_value(
            paper, "effective_relevance_category",
            paper["llm_relevance_category"] or "",
        )
        abstract = clean_extracted_text(paper["abstract"]) or ""
        abstract = _recover_incomplete_abstract(paper, abstract)
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
            "relevance_category": relevance_category or "",
            "relevance_reason": (
                manual_notes
                if manual_decision and manual_notes
                else paper["llm_relevance_reason"] or ""
            ),
            "relevance_basis": paper["llm_relevance_basis"] or "",
            "page_url": paper["page_url"] or "",
            "pdf_url": paper["pdf_url"] or "",
            "abstract": abstract,
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


def _recover_incomplete_abstract(paper, abstract: str) -> str:
    """Recover formula-damaged metadata abstracts from parsed full text.

    Some publisher pages expose formulas only in nested MathJax nodes. Older
    snapshots therefore contain gaps such as ``intensities of .``. When that
    signature is present and MinerU full text is available, prefer its Abstract
    section and normalize dollar-delimited formulas for report rendering.

    Parameters
    ----------
    paper : mapping or sqlite3.Row
        Database paper record, optionally containing ``mineru_output_dir``.
    abstract : str
        Cleaned metadata abstract.

    Returns
    -------
    str
        Original abstract, or a recovered full-text abstract.
    """
    gap_match = re.search(
        r"\b(?:of|above|below|from|at|between)(?:\s+[A-Za-z]+){0,2}\s+[.,;:]",
        abstract,
        flags=re.IGNORECASE,
    )
    if not gap_match:
        return abstract
    output_dir = _record_value(paper, "mineru_output_dir", "")
    if not output_dir:
        return abstract
    fulltext_path = Path(DATA_DIR) / str(output_dir) / "full.md"
    try:
        fulltext = fulltext_path.read_text(encoding="utf-8")
    except OSError:
        return abstract
    match = re.search(
        r"^#{1,3}\s+Abstract\s*$\n(?P<abstract>.*?)(?=^#{1,3}\s+\S|\Z)",
        fulltext,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    recovered_source = match.group("abstract") if match else ""
    if not recovered_source:
        # MinerU output for some APS PDFs places the abstract after the author
        # block without an explicit heading. Match it by its stable opening
        # phrase instead of assuming a fixed page layout.
        opening = abstract[:min(80, gap_match.start())].strip()
        recovered_source = next(
            (
                paragraph
                for paragraph in re.split(r"\n\s*\n", fulltext)
                if opening and opening in paragraph and len(paragraph) >= len(abstract) // 2
            ),
            "",
        )
    if not recovered_source:
        return abstract
    recovered = clean_extracted_text(recovered_source) or ""
    recovered = re.sub(r"\$\$([^$]+)\$\$", r"\\[\1\\]", recovered)
    recovered = re.sub(r"(?<!\$)\$([^$]+)\$(?!\$)", r"\\(\1\\)", recovered)
    return recovered if len(recovered) >= len(abstract) // 2 else abstract


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
