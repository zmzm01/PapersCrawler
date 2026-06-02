"""
Shared context for pipeline phases.

Holds SCRAPER_MAP, scraper factory, and logger configuration.
"""

import logging
import os

from config import BROWSER_SESSION_DIR, LOG_FILE_PATH, PUBLISHER_PROXY
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
                  PUBLISHER_PROXY.get("optica")),
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


# ---- Logger ----
file_handler = logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
console_handler = logging.StreamHandler()
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[file_handler, console_handler],
)

logger = logging.getLogger(__name__)
