"""Full-text URL candidate resolution.

This module deliberately resolves URLs only.  It never downloads OpenAlex's
hosted content, and leaves transport/authentication to the publisher layer.
"""


def resolve_candidates(db, paper):
    """Return deduplicated full-text candidates for a paper.

    Parameters
    ----------
    db : DatabaseClient
        Database containing discovered URL candidates.
    paper : mapping
        Paper row with ``doi`` and optional legacy ``pdf_url`` fields.

    Returns
    -------
    list of dict
        Candidates ordered by source priority, with legacy ``pdf_url`` kept
        as the final fallback for compatibility.
    """
    candidates = []
    try:
        candidates.extend(db.get_fulltext_locations(paper["doi"]))
    except (AttributeError, KeyError):
        pass
    if hasattr(paper, "get"):
        legacy_url = paper.get("pdf_url")
    else:
        try:
            legacy_url = paper["pdf_url"]
        except (KeyError, TypeError, IndexError):
            legacy_url = None
    if legacy_url:
        candidates.append({
            "url": legacy_url,
            "source": "publisher",
            "priority": 100,
        })
    result = []
    seen = set()
    for candidate in sorted(candidates, key=lambda item: item.get("priority", 100)):
        url = candidate.get("url")
        if (not url or url in seen or "content.openalex.org" in url
                or "/accepted/" in url.lower()):
            continue
        seen.add(url)
        result.append(candidate)
    return result
