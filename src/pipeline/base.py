"""
Shared context for pipeline phases.

Holds SCRAPER_MAP, scraper factory, logger configuration,
and shared utilities (journal overrides loading).
"""

import json
import os

from config import CFG, BROWSER_SESSION_DIR, JOURNAL_OVERRIDES_PATH
from sources.publisher import (
    NatureScraper, ScienceScraper, APSScraper,
    AIPScraper, IOPScraper, CambridgeScraper, OpticaScraper,
)

SCRAPER_MAP = {
    "nature":    (NatureScraper, BROWSER_SESSION_DIR / "nature",    None),
    "science":   (ScienceScraper, BROWSER_SESSION_DIR / "science",   None),
    "aps":       (APSScraper, BROWSER_SESSION_DIR / "aps",       None),
    "aip":       (AIPScraper, BROWSER_SESSION_DIR / "aip",       None),
    "iop":       (IOPScraper, BROWSER_SESSION_DIR / "iop",       None),
    "cambridge": (CambridgeScraper, BROWSER_SESSION_DIR / "cambridge", None),
    "optica":    (OpticaScraper, BROWSER_SESSION_DIR / "optica",
                  CFG.PUBLISHER_PROXY.get("optica")),
}


def create_scraper(publisher):
    """Create and initialize a scraper instance for the given publisher.

    Parameters
    ----------
    publisher : str
        Publisher identifier (e.g. "nature", "aps").

    Returns
    -------
    BasePublisherScraper
        Initialized scraper with browser started.

    Raises
    ------
    ValueError
        Publisher not found in SCRAPER_MAP.
    """
    config = SCRAPER_MAP.get(publisher)
    if not config:
        raise ValueError(f"No scraper config for publisher: {publisher}")
    scraper_class, user_data_dir, proxy = config
    os.makedirs(user_data_dir, exist_ok=True)
    scraper = scraper_class(user_data_dir)
    scraper.start_browser(proxy)
    return scraper


# ---- Journal override utilities (shared by phase_a and web/app) ----

def load_journal_overrides():
    """Load per-journal enable/disable overrides from journal_overrides.json.

    Returns a dict keyed by journal id, with fields:
    enabled, rss_enabled, cr_enabled.
    Missing keys fall back to publishers.yaml defaults.

    Returns
    -------
    dict
        {"journals": {jid: {...}, ...}} or {"journals": {}} on file missing/error.
    """
    if not JOURNAL_OVERRIDES_PATH.exists():
        return {"journals": {}}
    try:
        return json.loads(JOURNAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return {"journals": {}}


def journal_effective(journal, overrides, field):
    """Resolve effective setting for a journal field.

    Priority: journal_overrides.json > publishers.yaml.

    Parameters
    ----------
    journal : dict
        Single journal config entry from publishers.yaml.
    overrides : dict
        Loaded from journal_overrides.json (keyed by journal id).
    field : str
        One of 'enabled', 'rss_enabled', 'cr_enabled'.

    Returns
    -------
    bool
    """
    jid = journal["id"]
    ov = overrides.get("journals", {}).get(jid, {})
    if field in ov:
        return ov[field]
    if field in ("rss_enabled", "cr_enabled") and "enabled" in ov:
        return ov["enabled"]
    if field in ("rss_enabled", "cr_enabled"):
        if field in journal:
            return journal[field]
        return journal.get("enabled", True)
    return journal.get(field, True)
