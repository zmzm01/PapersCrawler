"""
Phase F: LLM paper summarization.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import (
    SKIP_PHASE_F, MAX_PAPERS_PER_PHASE,
    load_keywords, LLM_API_CONFIG_DICT_SUMM, LLM_API_CONFIG_DICT_RELE,
    SUMMARIES_PROMPT, SKIP_FORMULA_FIX, FORCE_FORMULA_FIX, LLM_CONCURRENT_MAX,
)
from db.database import DatabaseClient, FetchStatus
from pipeline.base import logger
from processors.llm_summarize_deepseek import (
    DeepSeekPaperSummarizer, FormulaFixer, LLMContextLengthExceed,
)
from processors.paper_relevance import LLMAPICallError, LLMResponseParseError


def phase_f_llm_summary(db):
    """Generate structured summaries for relevant papers via DeepSeek API.

    Parameters
    ----------
    db : DatabaseClient
    """
    logger.info("--- Phase F: LLM summary ---")
    if SKIP_PHASE_F:
        logger.info("Phase F: SKIP_PHASE_F=True, skipping")
        return

    papers = db.get_pendings("llm_summary_status")
    if MAX_PAPERS_PER_PHASE:
        papers = papers[:MAX_PAPERS_PER_PHASE]
    if not papers:
        logger.info("Phase F: no pending papers")
        return

    relevant_papers = [p for p in papers if p["llm_relevance_result"]]

    domain_config = load_keywords()
    if not domain_config.get("keywords") and not domain_config.get("domain_description"):
        relevant_papers = papers

    if not relevant_papers:
        logger.info("Phase F: no relevant papers to summarize")
        return

    summarizer = DeepSeekPaperSummarizer(llm_api_config=LLM_API_CONFIG_DICT_SUMM)
    fixer = None
    if not SKIP_FORMULA_FIX:
        fixer = FormulaFixer(llm_api_config=LLM_API_CONFIG_DICT_RELE, force=FORCE_FORMULA_FIX)

    tasks = []
    for paper in relevant_papers:
        doi = paper["doi"]
        mineru_text = paper["mineru_fulltext"] or ""
        if not mineru_text.strip():
            logger.info(f"No MinerU text, skipping summary: {doi}")
            db.update_llm_summary_error(
                doi, "No MinerU fulltext available",
                FetchStatus.SKIPPED.value, str(datetime.now()),
            )
            continue
        article_text = f"标题: {paper['title'] or ''}\n\n全文:\n{mineru_text}"
        tasks.append((paper, article_text))

    if not tasks:
        logger.info("Phase F: no full text available")
        return

    logger.info(f"Phase F: {len(tasks)} papers to summarize")

    max_workers = min(len(tasks), LLM_CONCURRENT_MAX)
    logger.info(f"Phase F: {max_workers} concurrent workers")
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(summarizer.call_deepseek_api, article_text, SUMMARIES_PROMPT): paper
            for paper, article_text in tasks
        }
        for future in as_completed(futures):
            paper = futures[future]
            doi = paper["doi"]
            timestamp = str(datetime.now())
            try:
                result_str = future.result()
                result_str = re.sub(r'(?<![\x5C])\\(?![\\"/bfnrtu])', r'\\\\', result_str)
                parsed = json.loads(result_str)
                if fixer:
                    logger.debug(f"FormulaFixer: [{doi}] 检查 5 个字段")
                    FIXER_FIELDS = [
                        "one_sentence", "motivation_and_goal",
                        "key_setup_and_method", "main_results_and_physics",
                        "take_home_message",
                    ]
                    fixed_count = 0
                    for field in FIXER_FIELDS:
                        if field in parsed and isinstance(parsed[field], str):
                            before = parsed[field]
                            after = fixer.fix_text(before, field_name=field)
                            if after != before:
                                fixed_count += 1
                            parsed[field] = after
                    if fixed_count:
                        logger.info(f"FormulaFixer: [{doi}] {fixed_count}/{len(FIXER_FIELDS)} 个字段已修复")
                    result_str = json.dumps(parsed, ensure_ascii=False)
                db.update_llm_summary(
                    doi, result_str, FetchStatus.SUCCESS.value, timestamp,
                )
                success_count += 1

            except (LLMAPICallError, LLMResponseParseError) as e:
                logger.warning(f"LLM summary API error [{doi}]: {e}")
                db.update_llm_summary_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                )

            except LLMContextLengthExceed as e:
                logger.warning(f"LLM context length exceeded [{doi}]: {e}")
                db.update_llm_summary_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                )

            except json.JSONDecodeError as e:
                logger.warning(f"LLM non-JSON response [{doi}]: {e}")
                db.update_llm_summary_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                )

            except Exception as e:
                logger.error(f"LLM summary error [{doi}]: {e}")
                db.update_llm_summary_error(
                    doi, str(e)[:500], FetchStatus.FAILED.value, timestamp,
                )

    logger.info(f"Phase F done: {success_count} summarized")
