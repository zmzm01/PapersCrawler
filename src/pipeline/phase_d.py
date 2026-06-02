"""
Phase D: Semantic similarity filtering.
"""

from datetime import datetime

from config import (
    SKIP_PHASE_D, MAX_PAPERS_PER_PHASE,
    SEMANTIC_MODEL_PATH, SEMANTIC_SIMILARITY_THRESHOLD,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import logger
from processors.paper_relevance import SemanticFilter


def phase_d_semantic_filter(db, domain_config):
    """Filter papers by semantic similarity to domain description.

    Parameters
    ----------
    db : DatabaseClient
    domain_config : dict
        {"keywords": [...], "domain_description": "..."}
    """
    if SKIP_PHASE_D:
        logger.info("Phase D: SKIP_PHASE_D=True, skipping")
        return
    logger.info("--- Phase D: Semantic similarity filter ---")

    keywords = domain_config.get("keywords", [])
    domain_description = domain_config.get("domain_description", "")

    if not domain_description:
        logger.info("Phase D: no domain description, skipping")
        return

    logger.info(f"Domain: {domain_description[:100]}...")
    logger.info(f"Keywords: {len(keywords)}")

    try:
        sf = SemanticFilter(SEMANTIC_MODEL_PATH, domain_description)
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

    threshold = SEMANTIC_SIMILARITY_THRESHOLD
    passed = 0
    skipped = 0

    for paper in papers:
        doi = paper["doi"]
        title = paper["title"] or ""
        abstract = paper["abstract"] or ""
        timestamp = str(datetime.now())

        try:
            score = sf.compute_similarity(title, abstract)
            db.update_semantic_filter(doi, score, FetchStatus.SUCCESS.value, timestamp)

            if score >= threshold:
                passed += 1
            else:
                db.update_process_status(
                    doi, "llm_relevance_status",
                    FetchStatus.SKIPPED.value,
                    "llm_relevance_date", timestamp,
                )
                skipped += 1

        except Exception as e:
            logger.error(f"Phase D: similarity failed [{doi}]: {e}")
            db.update_error_message(
                doi, "semantic_filter_status",
                FetchStatus.FAILED.value,
                "semantic_filter_error", str(e),
                "semantic_filter_date", timestamp,
            )

    logger.info(f"Phase D done: {passed} passed, {skipped} skipped")
