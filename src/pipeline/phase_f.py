"""
Phase F: LLM paper summarization.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import CFG, DATA_DIR, load_keywords
from common import (
    LLMCircuitBreaker,
    LLMServiceUnavailableError,
    format_error_for_record,
)
from db.database import FetchStatus
from processors.llm_summarize_deepseek import (
    DeepSeekPaperSummarizer, FormulaFixer, LLMContextLengthExceed,
)
from processors.paper_relevance import LLMAPICallError, LLMResponseParseError
from processors.summary_schema import (
    normalize_summary,
    summary_quality_issues,
    transform_summary_texts,
)

logger = logging.getLogger(__name__)


def _effective_relevance_category(paper):
    """Return the latest human-overridden category when one is available."""
    try:
        effective_category = paper["effective_relevance_category"]
    except (KeyError, IndexError):
        effective_category = None
    return effective_category or paper["llm_relevance_category"]


def _fix_summary_with_formula_fixer(
    summary: dict,
    doi: str,
    llm_config: dict,
    force: bool,
    circuit_breaker: LLMCircuitBreaker,
    max_repair_rounds: int = 1,
) -> tuple[str, int]:
    """Fix formula formatting in one normalized summary.

    Parameters
    ----------
    summary : dict
        Normalized structured summary.
    doi : str
        Paper DOI used in progress logs.
    llm_config : dict
        Dedicated FormulaFixer LLM configuration.
    force : bool
        Whether to send every non-empty text node to the fixer.
    circuit_breaker : LLMCircuitBreaker
        Circuit breaker shared by FormulaFixer workers.
    max_repair_rounds : int
        Maximum KaTeX-validation repair rounds for each text node.

    Returns
    -------
    tuple[str, int]
        JSON-encoded fixed summary and the number of changed text nodes.
    """
    fixer = FormulaFixer(
        llm_api_config=llm_config,
        force=force,
        max_repair_rounds=max_repair_rounds,
    )
    fixed_count = 0

    def fix_text(text, field_name):
        nonlocal fixed_count
        fixed = fixer.fix_text(
            text,
            field_name=field_name,
            circuit_breaker=circuit_breaker,
        )
        if fixed != text:
            fixed_count += 1
        return fixed

    logger.debug("FormulaFixer: [%s] 检查结构化总结字段", doi)
    fixed_summary = transform_summary_texts(summary, fix_text)
    return json.dumps(fixed_summary, ensure_ascii=False), fixed_count


def phase_f_llm_summary(db):
    """Generate structured summaries for relevant papers via DeepSeek API.

    Parameters
    ----------
    db : DatabaseClient
    """
    logger.info("--- Phase F: LLM summary ---")
    if CFG.SKIP_PHASE_F:
        logger.info("Phase F: SKIP_PHASE_F=True, skipping")
        return

    domain_config = load_keywords()
    if domain_config.get("scope_definition"):
        papers = db.get_pending_summary_papers(
            limit=CFG.MAX_PAPERS_PER_PHASE,
        )
    else:
        # Keep the legacy fallback for installations without a scope file.
        papers = db.get_pendings("llm_summary_status")
        if CFG.MAX_PAPERS_PER_PHASE:
            papers = papers[:CFG.MAX_PAPERS_PER_PHASE]
    if not papers:
        logger.info("Phase F: no pending papers")
        return

    relevant_papers = [
        p for p in papers
        if _effective_relevance_category(p) in ("A", "B")
    ]

    if not domain_config.get("scope_definition"):
        relevant_papers = papers

    skipped_count = len(papers) - len(relevant_papers)
    if not relevant_papers:
        logger.info(f"Phase F: no relevant papers to summarize ({skipped_count} skipped)")
        return

    if skipped_count:
        logger.info(f"Phase F: {skipped_count} papers skipped (not relevant)")

    summarizer = DeepSeekPaperSummarizer(llm_api_config=CFG.LLM_API_CONFIG_DICT_SUMM)
    formula_enabled = not CFG.SKIP_FORMULA_FIX

    tasks = []
    for paper in relevant_papers:
        doi = paper["doi"]

        mineru_text = ""
        output_dir = paper["mineru_output_dir"] or ""
        if output_dir:
            full_md_path = DATA_DIR / output_dir / "full.md"
            try:
                if full_md_path.exists():
                    mineru_text = full_md_path.read_text(encoding="utf-8")
            except Exception:
                logger.warning(f"Cannot read fulltext file: {full_md_path}")

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

    max_workers = min(len(tasks), CFG.LLM_CONCURRENT_MAX)
    logger.info(f"Phase F: {max_workers} concurrent workers")
    formula_executor = None
    formula_futures = {}
    formula_circuit_breaker = None
    if formula_enabled:
        formula_workers = min(len(tasks), CFG.FORMULA_FIX_CONCURRENT_MAX)
        formula_executor = ThreadPoolExecutor(max_workers=formula_workers)
        formula_circuit_breaker = LLMCircuitBreaker(
            CFG.LLM_CIRCUIT_BREAKER_THRESHOLD,
        )
        logger.info(
            "Phase F FormulaFixer: %s concurrent workers, model=%s",
            formula_workers,
            CFG.LLM_API_CONFIG_DICT_FORMULA.get("model"),
        )
    success_count = 0
    circuit_breaker = LLMCircuitBreaker(CFG.LLM_CIRCUIT_BREAKER_THRESHOLD)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    summarizer.call_deepseek_api, article_text, CFG.SUMMARIES_PROMPT,
                    circuit_breaker,
                ): paper
                for paper, article_text in tasks
            }
            for future in as_completed(futures):
                paper = futures[future]
                doi = paper["doi"]
                timestamp = str(datetime.now())
                try:
                    result_str = future.result()
                    decoded_result = json.loads(result_str)
                    if not isinstance(decoded_result, dict):
                        raise LLMResponseParseError(
                            "LLM summary must be a JSON object"
                        )
                    parsed = normalize_summary(decoded_result)
                    quality_issues = summary_quality_issues(parsed)
                    if quality_issues:
                        raise LLMResponseParseError(
                            "Summary content validation failed: "
                            + "; ".join(quality_issues),
                        )
                    if formula_executor is not None:
                        formula_future = formula_executor.submit(
                            _fix_summary_with_formula_fixer,
                            parsed,
                            doi,
                            CFG.LLM_API_CONFIG_DICT_FORMULA,
                            CFG.FORCE_FORMULA_FIX,
                            formula_circuit_breaker,
                            CFG.FORMULA_FIX_MAX_REPAIR_ROUNDS,
                        )
                        formula_futures[formula_future] = (paper, timestamp)
                    else:
                        db.update_llm_summary(
                            doi, result_str, FetchStatus.SUCCESS.value, timestamp,
                        )
                        success_count += 1

                except (LLMAPICallError, LLMResponseParseError) as e:
                    if isinstance(e, LLMServiceUnavailableError) and circuit_breaker.is_open:
                        logger.warning("LLM circuit open; retaining pending summary: %s", doi)
                        continue
                    logger.warning(f"LLM summary API error [{doi}]: {e}")
                    db.update_llm_summary_error(
                        doi, format_error_for_record(e), FetchStatus.FAILED.value, timestamp,
                    )

                except LLMContextLengthExceed as e:
                    logger.warning(f"LLM context length exceeded [{doi}]: {e}")
                    db.update_llm_summary_error(
                        doi, format_error_for_record(e), FetchStatus.FAILED.value, timestamp,
                    )

                except json.JSONDecodeError as e:
                    logger.warning(f"LLM non-JSON response [{doi}]: {e}")
                    db.update_llm_summary_error(
                        doi, format_error_for_record(e), FetchStatus.FAILED.value, timestamp,
                    )

                except Exception as e:
                    logger.exception("LLM summary error [%s]", doi)
                    db.update_llm_summary_error(
                        doi, format_error_for_record(e), FetchStatus.FAILED.value, timestamp,
                    )

        for future in as_completed(formula_futures):
            paper, timestamp = formula_futures[future]
            doi = paper["doi"]
            try:
                result_str, fixed_count = future.result()
                if fixed_count:
                    logger.info(
                        "FormulaFixer: [%s] %s 个文本节点已修复",
                        doi,
                        fixed_count,
                    )
                db.update_llm_summary(
                    doi, result_str, FetchStatus.SUCCESS.value, timestamp,
                )
                success_count += 1
            except Exception as e:
                logger.exception("FormulaFixer summary error [%s]", doi)
                db.update_llm_summary_error(
                    doi, format_error_for_record(e), FetchStatus.FAILED.value, timestamp,
                )
    finally:
        if formula_executor is not None:
            formula_executor.shutdown(wait=True)

    if circuit_breaker.is_open:
        logger.warning("Phase F circuit breaker opened; remaining papers will retry next run")
    logger.info(f"Phase F done: {success_count} summarized")
