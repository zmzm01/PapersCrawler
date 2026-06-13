"""
Phase B: CrossRef metadata enrichment.
"""

import json
import logging
from datetime import datetime

import requests

from config import CFG
from db.database import DatabaseClient, FetchStatus
from sources.crossref import CrossrefClient, NotFoundError

logger = logging.getLogger(__name__)


def phase_b_crossref(db):
    """Enrich paper metadata via CrossRef API.

    Parameters
    ----------
    db : DatabaseClient
    """
    if CFG.SKIP_PHASE_B:
        logger.info("Phase B: CFG.SKIP_PHASE_B=True, skipping")
        return
    logger.info("--- Phase B: CrossRef metadata ---")
    crClient = CrossrefClient(mailto=CFG.CROSSREF_MAILTO, timeout=CFG.REQUEST_TIMEOUT)

    paper_tasks = db.get_pendings("cr_metadata_fetched_status")
    if CFG.MAX_PAPERS_PER_PHASE:
        paper_tasks = paper_tasks[:CFG.MAX_PAPERS_PER_PHASE]
    if not paper_tasks:
        logger.info("Phase B: no pending papers")
        return

    logger.info(f"Phase B: {len(paper_tasks)} papers pending")

    for paper_task in paper_tasks:
        paperDOI = paper_task["doi"]
        timestamp = str(datetime.now())

        try:
            crossrefPaper = crClient.fetch_by_doi(paperDOI)
            authors_json = json.dumps(crossrefPaper.authors, ensure_ascii=False) if crossrefPaper.authors else "[]"

            if not crossrefPaper.authors:
                logger.warning(f"CrossRef author data missing: {paperDOI}")

            db.update_crossref_metadata(
                paperDOI, crossrefPaper.title,
                authors_json, crossrefPaper.published,
                crossrefPaper.abstract or "",
            )
            db.update_process_status(
                paperDOI, "cr_metadata_fetched_status",
                FetchStatus.SUCCESS.value,
                "cr_metadata_fetched_date", timestamp,
            )

        except NotFoundError as e:
            logger.warning(f"CrossRef no record: {paperDOI}")
            db.update_error_message(
                paperDOI, "cr_metadata_fetched_status",
                FetchStatus.FAILED.value,
                "cr_metadata_fetched_error", str(e),
                "cr_metadata_fetched_date", timestamp,
            )

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                logger.warning(f"CrossRef rate limited (429) [{paperDOI}]")
            else:
                logger.error(f"CrossRef HTTP error [{paperDOI}]: {e}")
            db.update_error_message(
                paperDOI, "cr_metadata_fetched_status",
                FetchStatus.FAILED.value,
                "cr_metadata_fetched_error", str(e),
                "cr_metadata_fetched_date", timestamp,
            )

        except Exception as e:
            logger.error(f"CrossRef failed [{paperDOI}]: {e}")
            db.update_error_message(
                paperDOI, "cr_metadata_fetched_status",
                FetchStatus.FAILED.value,
                "cr_metadata_fetched_error", str(e),
                "cr_metadata_fetched_date", timestamp,
            )

    logger.info("Phase B done")
