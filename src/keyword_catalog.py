"""Utilities for maintaining and auditing the literal keyword catalog.

The catalog is deliberately separate from the natural-language research
scope.  Literal terms are useful for coverage checks and evidence extraction,
but a term hit alone is not a relevance decision.
"""

from __future__ import annotations

import re
from typing import Any


def normalise_term(term: str) -> str:
    """Return a stable representation used for duplicate detection.

    Parameters
    ----------
    term : str
        A literal keyword or alias.

    Returns
    -------
    str
        Case-folded text with collapsed whitespace and normalised hyphens.
    """
    value = " ".join(str(term or "").strip().split())
    return value.replace("‐", "-").replace("‑", "-").casefold()


def iter_catalog_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return valid keyword catalog entries from a loaded configuration.

    Parameters
    ----------
    config : dict
        The dictionary returned by :func:`config.load_keywords`.

    Returns
    -------
    list[dict[str, Any]]
        Catalog entries.  Missing optional fields are filled with safe
        defaults so callers can inspect older configurations.
    """
    entries = config.get("keyword_catalog", []) if config else []
    if not isinstance(entries, list):
        return []
    normalised = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        terms = entry.get("terms", [])
        if isinstance(terms, str):
            terms = [terms]
        subdomains = entry.get("subdomains", [])
        if isinstance(subdomains, str):
            subdomains = [subdomains]
        normalised.append({
            "id": str(entry.get("id", "")).strip(),
            "terms": [str(term).strip() for term in terms if str(term).strip()],
            "subdomains": [str(item).strip() for item in subdomains if str(item).strip()],
            "note": str(entry.get("note", "")).strip(),
        })
    return normalised


def validate_catalog(config: dict[str, Any]) -> list[str]:
    """Validate catalog IDs, terms and sub-domain references.

    Parameters
    ----------
    config : dict
        Loaded keyword configuration.

    Returns
    -------
    list[str]
        Human-readable validation errors.  An empty list means valid.
    """
    raw_entries = (config or {}).get("keyword_catalog", [])
    if not isinstance(raw_entries, list):
        return ["keyword_catalog must be a list of mappings"]
    entries = iter_catalog_entries(config)
    known_subdomains = set((config or {}).get("scope_definition", {}))
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_terms: dict[str, str] = {}
    for entry in entries:
        entry_id = entry["id"]
        if not entry_id:
            errors.append("keyword_catalog entry has no id")
        elif entry_id in seen_ids:
            errors.append(f"duplicate keyword catalog id: {entry_id}")
        seen_ids.add(entry_id)
        if not entry["terms"]:
            errors.append(f"{entry_id or '<unnamed>'} has no terms")
        for term in entry["terms"]:
            normalised = normalise_term(term)
            previous_id = seen_terms.get(normalised)
            if previous_id and previous_id != entry_id:
                errors.append(
                    f"duplicate keyword term {term!r}: {previous_id} and {entry_id}"
                )
            seen_terms[normalised] = entry_id
        for subdomain in entry["subdomains"]:
            if subdomain not in known_subdomains:
                errors.append(
                    f"{entry_id or '<unnamed>'} references unknown subdomain: {subdomain}"
                )
    return errors


def _compile_term(term: str) -> re.Pattern[str]:
    """Compile a boundary-aware, case-insensitive literal term pattern."""
    return re.compile(
        rf"(?<!\w){re.escape(term)}(?!\w)",
        re.IGNORECASE,
    )


def match_catalog(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Find catalog terms in text and return their semantic mappings.

    Parameters
    ----------
    text : str
        Title, abstract or other text to inspect.
    config : dict
        Loaded keyword configuration.

    Returns
    -------
    list[dict[str, Any]]
        One record per matched catalog entry, containing ``id``, ``terms`` and
        ``subdomains``.  Each entry is reported once even if aliases repeat.
    """
    haystack = str(text or "")
    matches = []
    for entry in iter_catalog_entries(config):
        hit_terms = [
            term for term in entry["terms"]
            if _compile_term(term).search(haystack)
        ]
        if hit_terms:
            matches.append({
                "id": entry["id"],
                "terms": hit_terms,
                "subdomains": entry["subdomains"],
            })
    return matches


def flatten_catalog_terms(config: dict[str, Any]) -> list[str]:
    """Return unique literal terms in catalog order."""
    terms: list[str] = []
    seen: set[str] = set()
    for entry in iter_catalog_entries(config):
        for term in entry["terms"]:
            normalised = normalise_term(term)
            if normalised and normalised not in seen:
                seen.add(normalised)
                terms.append(term)
    return terms
