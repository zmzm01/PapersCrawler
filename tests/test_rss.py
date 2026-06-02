"""
Tests: RSS Feed parsing (rss.py)

Coverage:
  - RSS XML text parsing with inline Atom feed fixture
  - DOI extraction (dc_identifier / prism_doi)
  - Date field parsing
  - Entry field mapping to Paper dataclass

All tests are offline and use inline XML data.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sources.rss import RSSProcessor

ATOM_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/">
  <entry>
    <title>Laser Wakefield Acceleration of Electrons</title>
    <link href="https://nature.com/articles/s41586-025-00001-x"/>
    <id>https://doi.org/10.1038/s41586-025-00001-x</id>
    <prism:doi>10.1038/s41586-025-00001-x</prism:doi>
    <prism:publicationdate>2025-06-01</prism:publicationdate>
  </entry>
  <entry>
    <title>Proton Radiography of Laser-Driven Plasmas</title>
    <link href="https://nature.com/articles/s41586-025-00002-y"/>
    <dc:identifier>doi:10.1038/s41586-025-00002-y</dc:identifier>
    <updated>2025-06-02T12:00:00Z</updated>
  </entry>
  <entry>
    <title>Paper Without DOI</title>
    <link href="https://nature.com/articles/s41586-025-00003-z"/>
    <updated>2025-06-03T12:00:00Z</updated>
  </entry>
</feed>"""


def test_parse_rss_full_flow():
    """Parse inline Atom RSS XML and verify all Paper fields."""
    rsspro = RSSProcessor()
    journal_config = {"id": "nature", "name": "Nature", "publisher": "nature"}
    papers = rsspro.parse_rss(ATOM_RSS_XML, journal_config)

    assert len(papers) == 3

    # First paper: DOI from prism_doi
    assert papers[0].doi == "10.1038/s41586-025-00001-x"
    assert papers[0].title == "Laser Wakefield Acceleration of Electrons"
    assert papers[0].url == "https://nature.com/articles/s41586-025-00001-x"
    assert papers[0].date == "2025-06-01"

    # Second paper: DOI from dc_identifier, date from updated
    assert papers[1].doi == "10.1038/s41586-025-00002-y"
    assert papers[1].title == "Proton Radiography of Laser-Driven Plasmas"
    assert papers[1].date == "2025-06-02"

    # Third paper: no DOI
    assert papers[2].doi is None
    assert papers[2].title == "Paper Without DOI"
    assert papers[2].date == "2025-06-03"


# ---- DOI extraction ----

def test_extract_doi_from_prism():
    """Extract DOI from prism_doi field."""
    from feedparser import FeedParserDict
    rsspro = RSSProcessor()

    entry = FeedParserDict()
    entry["prism_doi"] = "10.1038/s41586-025-00123-4"
    doi = rsspro.extract_doi(entry)
    assert doi == "10.1038/s41586-025-00123-4"


def test_extract_doi_from_dc_identifier():
    """Extract DOI from dc_identifier (doi:...) field."""
    from feedparser import FeedParserDict
    rsspro = RSSProcessor()

    entry = FeedParserDict()
    entry["dc_identifier"] = "doi:10.1103/PhysRevLett.134.195001"
    doi = rsspro.extract_doi(entry)
    assert doi == "10.1103/PhysRevLett.134.195001"


def test_extract_doi_no_doi():
    """Return None when no DOI field exists."""
    from feedparser import FeedParserDict
    rsspro = RSSProcessor()

    entry = FeedParserDict()
    doi = rsspro.extract_doi(entry)
    assert doi is None
