"""
Phase E: LLM relevance judgement.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import CFG, load_keywords
from db.database import DatabaseClient, FetchStatus
from processors.paper_relevance import (
    PaperRelevanceChecker,
    LLMAPICallError, LLMResponseParseError,
)

logger = logging.getLogger(__name__)


def phase_e_llm_relevance(db):
    """Judge paper relevance via DeepSeek LLM API.

    Parameters
    ----------
    db : DatabaseClient
    """
    logger.info("--- Phase E: LLM relevance ---")
    if CFG.SKIP_PHASE_E:
        logger.info("Phase E: SKIP_PHASE_E=True, skipping")
        return

    domain_config = load_keywords()
    if not domain_config.get("scope_definition"):
        logger.info("Phase E: no scope_definition config, skipping")
        return

    paper_tasks = db.get_pendings("llm_relevance_status")
    if CFG.MAX_PAPERS_PER_PHASE:
        paper_tasks = paper_tasks[:CFG.MAX_PAPERS_PER_PHASE]
    if not paper_tasks:
        logger.info("Phase E: no pending papers")
        return

    logger.info(f"Phase E: {len(paper_tasks)} papers pending")

    checker = PaperRelevanceChecker(domain_config)

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
        prompt = checker.build_default_prompt(
            paper["title"] or "", abstract, doi=doi,
        )
        tasks.append((paper, prompt))

    if skipped_no_abstract:
        logger.info(f"Phase E: {skipped_no_abstract} skipped (no abstract)")

    if not tasks:
        logger.info("Phase E: no valid papers to judge")
        return

    max_workers = min(len(tasks), CFG.LLM_CONCURRENT_MAX)
    logger.info(f"Phase E: {max_workers} concurrent workers")
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(checker.call_deepseek_api, prompt, CFG.LLM_API_CONFIG_DICT_RELE): (paper, prompt)
            for paper, prompt in tasks
        }
        for future in as_completed(futures):
            paper, _ = futures[future]
            doi = paper["doi"]
            timestamp = str(datetime.now())
            try:
                result_str = future.result()
                result = json.loads(result_str)

                if "PredictedCategory" not in result:
                    logger.warning(f"LLM response missing PredictedCategory [{doi}], marking failed")
                    db.update_llm_relevance_error(
                        doi, "LLM response missing PredictedCategory field",
                        FetchStatus.FAILED.value, timestamp,
                    )
                    continue

                category = result.get("PredictedCategory", "D")

                # 规范化子领域 key：小写化 + 空格→下划线 + 剔除无关字符
                raw_subfields = result.get("MatchedSubfields", [])
                known_keys = set(domain_config.get("scope_definition", {}).keys())
                normalized = []
                for s in raw_subfields:
                    s_norm = s.lower().strip().replace(" ", "_")
                    # 去除可能误带入的标点
                    s_norm = s_norm.strip(".,;:!?")
                    if s_norm in known_keys:
                        normalized.append(s_norm)
                    else:
                        logger.debug(
                            f"Unknown subfield key '{s}' (normalized: '{s_norm}'), "
                            f"storing as-is for DOI {doi}"
                        )
                        normalized.append(s_norm)
                subfields = json.dumps(normalized, ensure_ascii=False)

                confidence = result.get("Confidence", "low")
                notes = result.get("Notes", "")

                db.update_llm_relevance(
                    doi, category, subfields, confidence, notes,
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
