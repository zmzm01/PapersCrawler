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
from sources.openalex import OpenAlexClient, OpenAlexNotFoundError

logger = logging.getLogger(__name__)

__all__ = ["phase_b_crossref", "DatabaseClient"]


def _crossref_links(metadata):
    """Extract external full-text links from a Crossref metadata object."""
    links = []
    for link in (getattr(metadata, "raw", None) or {}).get("link", []):
        url = link.get("URL") if isinstance(link, dict) else None
        if url:
            links.append({
                "url": url,
                "source": "crossref",
                "is_oa": bool(link.get("content-version") == "vor"),
                "version": link.get("content-version"),
                "license": None,
            })
    return links


def _fetch_openalex_fallbacks(db, fallback_tasks):
    """Fetch queued OpenAlex fallbacks concurrently, then merge serially."""
    if (not fallback_tasks or not CFG.OPENALEX_ENABLED
            or not hasattr(db, "update_openalex_metadata")):
        return
    client = OpenAlexClient(
        api_key=CFG.OPENALEX_API_KEY,
        timeout=CFG.OPENALEX_TIMEOUT,
        max_retries=CFG.OPENALEX_MAX_ATTEMPTS,
        requests_per_second=CFG.OPENALEX_REQUESTS_PER_SECOND,
        backoff_max_seconds=CFG.OPENALEX_BACKOFF_MAX_SECONDS,
    )
    try:
        metadata_by_doi, errors_by_doi = client.fetch_many(
            [doi for doi, _ in fallback_tasks],
            max_concurrency=CFG.OPENALEX_MAX_CONCURRENCY,
            return_errors=True,
        )
        for doi, timestamp in fallback_tasks:
            metadata = metadata_by_doi.get(doi)
            if metadata is not None:
                db.update_openalex_metadata(doi, metadata, timestamp)
                db.update_openalex_status(
                    doi, FetchStatus.SUCCESS.value, None, timestamp,
                )
                continue
            error = errors_by_doi.get(doi, RuntimeError("No OpenAlex result"))
            if isinstance(error, OpenAlexNotFoundError):
                status = FetchStatus.SKIPPED.value
            else:
                status = FetchStatus.FAILED.value
                logger.warning("OpenAlex fallback failed [%s]: %s", doi, error)
            db.update_openalex_status(doi, status, str(error), timestamp)
    except Exception as error:
        logger.warning("OpenAlex fallback batch failed: %s", error)
        for doi, timestamp in fallback_tasks:
            db.update_openalex_status(
                doi, FetchStatus.FAILED.value, str(error), timestamp,
            )
    finally:
        client.close()


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
    openalex_fallback_tasks = []

    for paper_task in paper_tasks:
        paperDOI = paper_task["doi"]
        timestamp = str(datetime.now())

        try:
            crossrefPaper = crClient.fetch_by_doi(paperDOI)

            if not crossrefPaper.authors:
                # 设计契约：作者为空视为 FAILED（tasks.md 2026-05-23 / design.md）
                # 不再走 SUCCESS 分支，避免下游 Phase F/E 拿不到作者信息时静默失败
                logger.warning(f"CrossRef author data missing: {paperDOI}")
                db.update_error_message(
                    paperDOI, "cr_metadata_fetched_status",
                    FetchStatus.FAILED.value,
                    "cr_metadata_fetched_error", "CrossRef returned no authors",
                    "cr_metadata_fetched_date", timestamp,
                )
                # Crossref can still provide useful title/abstract/links even
                # when its author list is incomplete. Persist those fields,
                # then let OpenAlex fill only what remains missing.
                db.update_crossref_metadata(
                    paperDOI, crossrefPaper.title, "",
                    crossrefPaper.published, crossrefPaper.abstract or "",
                    _crossref_links(crossrefPaper),
                )
                openalex_fallback_tasks.append((paperDOI, timestamp))
            else:
                authors_json = json.dumps(crossrefPaper.authors, ensure_ascii=False)
                db.update_crossref_metadata(
                    paperDOI, crossrefPaper.title,
                    authors_json, crossrefPaper.published,
                    crossrefPaper.abstract or "",
                    _crossref_links(crossrefPaper),
                )
                db.update_process_status(
                    paperDOI, "cr_metadata_fetched_status",
                    FetchStatus.SUCCESS.value,
                    "cr_metadata_fetched_date", timestamp,
                )
                missing_crossref_fields = any((
                    not crossrefPaper.title,
                    not crossrefPaper.authors,
                    not crossrefPaper.published,
                    not crossrefPaper.abstract,
                ))
                if not missing_crossref_fields:
                    if hasattr(db, "update_openalex_status"):
                        db.update_openalex_status(
                            paperDOI, FetchStatus.SKIPPED.value,
                            "Crossref abstract available", timestamp,
                        )
                else:
                    openalex_fallback_tasks.append((paperDOI, timestamp))

        except NotFoundError as e:
            logger.warning(f"CrossRef no record: {paperDOI}")
            db.update_error_message(
                paperDOI, "cr_metadata_fetched_status",
                FetchStatus.FAILED.value,
                "cr_metadata_fetched_error", str(e),
                "cr_metadata_fetched_date", timestamp,
            )
            openalex_fallback_tasks.append((paperDOI, timestamp))

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
            openalex_fallback_tasks.append((paperDOI, timestamp))

        except Exception as e:
            logger.error(f"CrossRef failed [{paperDOI}]: {e}")
            db.update_error_message(
                paperDOI, "cr_metadata_fetched_status",
                FetchStatus.FAILED.value,
                "cr_metadata_fetched_error", str(e),
                "cr_metadata_fetched_date", timestamp,
            )
            openalex_fallback_tasks.append((paperDOI, timestamp))

    _fetch_openalex_fallbacks(db, openalex_fallback_tasks)
    logger.info("Phase B done")
