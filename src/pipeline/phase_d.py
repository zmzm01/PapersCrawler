"""
Phase D: Semantic similarity reference scoring.

Computes cosine similarity between each paper and multiple sub-domain
descriptions. The resulting score is used ONLY for sorting in the WebUI
Papers page. It does NOT gate Phase E (LLM relevance).

When SKIP_PHASE_D = True (default), all papers go directly to Phase E.
"""

from datetime import datetime

from config import (
    SKIP_PHASE_D, MAX_PAPERS_PER_PHASE,
    SEMANTIC_MODEL_PATH,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import logger
from processors.paper_relevance import SemanticFilter


def phase_d_semantic_filter(db, domain_config):
    """Compute semantic similarity scores for WebUI reference sorting.

    Parameters
    ----------
    db : DatabaseClient
    domain_config : dict
        {"keywords": [...], "domain_description": "...", "sub_domains": {...}}
    """
    if SKIP_PHASE_D:
        logger.info("Phase D: SKIP_PHASE_D=True, skipping")
        return
    logger.info("--- Phase D: Semantic similarity (reference only) ---")

    sub_domains = domain_config.get("sub_domains", {})
    if not sub_domains:
        logger.info("Phase D: no sub_domains configured, skipping")
        return

    logger.info(f"Phase D: {len(sub_domains)} sub-domains loaded")

    try:
        sf = SemanticFilter(SEMANTIC_MODEL_PATH, sub_domains)
    except ImportError as e:
        logger.error(f"Phase D: {e}")
        logger.error("Install sentence-transformers: pip install sentence-transformers")
        return
    except Exception as e:
        logger.error(f"Phase D: SemanticFilter init failed: {e}")
        return

    papers = db.get_pendings("semantic_filter_status")
    if MAX_PAPERS_PER_PHASE:
        papers = papers[:MAX_PAPERS_PER_PHASE]
    if not papers:
        logger.info("Phase D: no pending papers")
        return

    logger.info(f"Phase D: {len(papers)} papers pending")
    success_count = 0

    for paper in papers:
        doi = paper["doi"]
        title = paper["title"] or ""
        abstract = paper["abstract"] or ""
        timestamp = str(datetime.now())

        try:
            score, best_label = sf.compute_similarity(title, abstract)
            db.update_semantic_filter(
                doi, score, FetchStatus.SUCCESS.value,
                timestamp, best_subdomain=best_label,
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Phase D: similarity failed [{doi}]: {e}")
            db.update_error_message(
                doi, "semantic_filter_status",
                FetchStatus.FAILED.value,
                "semantic_filter_error", str(e),
                "semantic_filter_date", timestamp,
            )

    logger.info(f"Phase D done: {success_count} scored")
