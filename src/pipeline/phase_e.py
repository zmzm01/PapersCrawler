"""
Phase E: LLM relevance judgement.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import (
    SKIP_PHASE_E, MAX_PAPERS_PER_PHASE,
    load_keywords, LLM_API_CONFIG_DICT_RELE, LLM_CONCURRENT_MAX,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import logger
from processors.paper_relevance import (
    PaperRelevanceChecker,
    LLMAPICallError, LLMResponseParseError,
)


def phase_e_llm_relevance(db):
    """Judge paper relevance via DeepSeek LLM API.

    Parameters
    ----------
    db : DatabaseClient
    """
    logger.info("--- Phase E: LLM relevance ---")
    if SKIP_PHASE_E:
        logger.info("Phase E: SKIP_PHASE_E=True, skipping")
        return

    domain_config = load_keywords()
    keywords = domain_config.get("keywords", [])
    domain_description = domain_config.get("domain_description", "")
    if not keywords and not domain_description:
        logger.info("Phase E: no keywords/domain config, skipping")
        return

    paper_tasks = db.get_pendings("llm_relevance_status")
    if MAX_PAPERS_PER_PHASE:
        paper_tasks = paper_tasks[:MAX_PAPERS_PER_PHASE]
    if not paper_tasks:
        logger.info("Phase E: no pending papers")
        return

    logger.info(f"Phase E: {len(paper_tasks)} papers pending")

    checker = PaperRelevanceChecker(keywords, domain_description)

    tasks = []
    skipped_no_abstract = 0
    for paper in paper_tasks:
        doi = paper["doi"]
        abstract = (paper["abstract"] or "").strip()
        if not abstract:
            logger.info(f"No abstract, skipping LLM: {doi}")
            db.update_process_status(
                doi, "llm_relevance_status",
                FetchStatus.SKIPPED.value,
                "llm_relevance_date", str(datetime.now()),
            )
            skipped_no_abstract += 1
            continue
        prompt = checker.build_default_prompt(paper["title"] or "", abstract)
        tasks.append((paper, prompt))

    if skipped_no_abstract:
        logger.info(f"Phase E: {skipped_no_abstract} skipped (no abstract)")

    if not tasks:
        logger.info("Phase E: no valid papers to judge")
        return

    max_workers = min(len(tasks), LLM_CONCURRENT_MAX)
    logger.info(f"Phase E: {max_workers} concurrent workers")
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(checker.call_deepseek_api, prompt, LLM_API_CONFIG_DICT_RELE): (paper, prompt)
            for paper, prompt in tasks
        }
        for future in as_completed(futures):
            paper, _ = futures[future]
            doi = paper["doi"]
            timestamp = str(datetime.now())
            try:
                result_str = future.result()
                result_str = re.sub(r'(?<!\\)\\(?![\\"/bfnrtu])', r'\\\\', result_str)
                result = json.loads(result_str)
                relevant = 1 if result.get("relevant", False) else 0
                confidence = result.get("confidence", "low")
                reason = result.get("reason", "")

                db.update_llm_relevance(
                    doi, relevant, confidence, reason,
                    FetchStatus.SUCCESS.value, timestamp,
                )
                success_count += 1

            except (LLMAPICallError, LLMResponseParseError) as e:
                logger.warning(f"LLM relevance API error [{doi}]: {e}")
                db.update_llm_relevance_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                )

            except json.JSONDecodeError as e:
                logger.warning(f"LLM non-JSON response [{doi}]: {e}")
                db.update_llm_relevance_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                )

            except Exception as e:
                logger.error(f"LLM relevance error [{doi}]: {e}")
                db.update_llm_relevance_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                )

    logger.info(f"Phase E done: {success_count} succeeded")
