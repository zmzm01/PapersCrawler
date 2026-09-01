"""Phase E3: final relevance adjudication from MinerU full-text evidence."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from common import (
    LLMCircuitBreaker,
    LLMServiceUnavailableError,
    clean_extracted_text,
)
from config import CFG, DATA_DIR, load_keywords
from db.database import FetchStatus
from keyword_catalog import flatten_catalog_terms
from processors.paper_relevance import (
    LLMAPICallError,
    LLMResponseParseError,
    PaperRelevanceChecker,
)

logger = logging.getLogger(__name__)


def build_relevance_evidence(text, max_chars=60000, evidence_terms=None):
    """Extract useful full-text evidence without blindly truncating the head.

    Parameters
    ----------
    text : str
        MinerU Markdown text.
    max_chars : int
        Maximum evidence size sent to the adjudication model.
    evidence_terms : list[str], optional
        Additional literal terms from ``keyword_catalog`` to use when
        selecting context windows from long documents.

    Returns
    -------
    str
        Title/headings, introduction, conclusion and keyword-context windows.
    """
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    headings = [line for line in lines if re.match(r"^#{1,6}\s+", line)]
    sections = []
    lower = text.lower()
    for marker in ("introduction", "background", "conclusion", "discussion", "summary"):
        start = lower.find(marker)
        if start >= 0:
            sections.append(text[max(0, start - 500):start + 9000])
    keyword_hits = []
    base_terms = [
        "laser", "ion", "proton", "target", "diagnos", "accelerat",
        "beamline", "transport", "post-acceler",
    ]
    catalog_terms = [str(term) for term in (evidence_terms or []) if str(term).strip()]
    evidence_pattern = "|".join(
        re.escape(term.casefold()) for term in base_terms + catalog_terms
    )
    for match in re.finditer(evidence_pattern, lower):
        keyword_hits.append(text[max(0, match.start() - 600):match.end() + 1800])
        if len(keyword_hits) >= 12:
            break
    evidence = "\n\n".join(headings[:80] + sections + keyword_hits)
    if len(evidence) < max_chars:
        evidence += "\n\n[正文末尾]\n" + text[-min(12000, max_chars):]
    return evidence[:max_chars]


def _normalise_result(result, domain_config):
    """Normalise model category fields for database storage."""
    category = str(result.get("PredictedCategory", "D")).upper()
    if category not in {"A", "B", "C", "D"}:
        category = "D"
    confidence = str(result.get("Confidence", "low")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    known = set(domain_config.get("scope_definition", {}))
    fields = []
    for field in result.get("MatchedSubfields", []):
        normal = str(field).lower().strip().replace(" ", "_").strip(".,;:!?" )
        if normal in known:
            fields.append(normal)
    return category, json.dumps(fields, ensure_ascii=False), confidence, str(result.get("Notes", ""))


def _call_with_transition_review(checker, prompt, paper, circuit_breaker):
    """Run full-text adjudication and review configured category transitions."""
    initial_response = checker.call_deepseek_api(
        prompt, CFG.LLM_API_CONFIG_DICT_FULLTEXT, circuit_breaker,
    )
    initial_result = json.loads(initial_response)
    screen_category = str(paper["relevance_screen_category"] or "").upper()
    initial_category = str(
        initial_result.get("PredictedCategory", "D")
    ).upper()
    transition = f"{screen_category}->{initial_category}"
    if (
            not CFG.RELEVANCE_ESCALATION_ENABLED
            or transition not in CFG.RELEVANCE_ESCALATION_TRANSITIONS
    ):
        return initial_response, None, None
    review_prompt = checker.build_transition_review_prompt(
        prompt, screen_category, initial_result,
    )
    reviewed_response = checker.call_deepseek_api(
        review_prompt, CFG.LLM_API_CONFIG_DICT_RELE_ESCALATION,
        circuit_breaker,
    )
    return (
        reviewed_response,
        CFG.LLM_API_CONFIG_DICT_RELE_ESCALATION.get("model"),
        initial_category,
    )


def phase_e3_fulltext_relevance(db):
    """Adjudicate screened candidates only when full-text evidence is available."""
    logger.info("--- Phase E3: full-text relevance adjudication ---")
    if CFG.SKIP_PHASE_E3:
        logger.info("Phase E3: SKIP_PHASE_E3=True, skipping")
        return
    domain_config = load_keywords()
    checker = PaperRelevanceChecker(domain_config)
    candidates = db.get_relevance_screen_candidates(
        pending_only=False, final_pending_only=False, require_pdf_url=False,
    )
    if not candidates:
        logger.info("Phase E3: no candidates")
        return

    tasks = []
    for paper in candidates:
        fulltext = paper["mineru_fulltext"] or ""
        if not fulltext and paper["mineru_output_dir"]:
            path = DATA_DIR / paper["mineru_output_dir"] / "full.md"
            try:
                if path.exists():
                    fulltext = path.read_text(encoding="utf-8")
            except OSError as error:
                logger.warning("Cannot read full text %s: %s", path, error)
        if not fulltext.strip():
            # MinerU may succeed on a later daily retry or after a manually
            # supplied PDF.  Keep the final judgement pending until E3 has
            # actual full-text evidence; title/abstract screening never makes
            # an A/B paper reportable on its own.
            continue
        if paper["llm_relevance_basis"] == "fulltext":
            continue
        evidence = build_relevance_evidence(
            fulltext,
            max_chars=CFG.FULLTEXT_RELEVANCE_MAX_CHARS,
            evidence_terms=flatten_catalog_terms(domain_config),
        )
        prompt = checker.build_fulltext_prompt(
            paper["title"] or "", clean_extracted_text(paper["abstract"]) or "", evidence,
            doi=paper["doi"],
        )
        tasks.append((paper, prompt))

    if not tasks:
        return
    breaker = LLMCircuitBreaker(CFG.LLM_CIRCUIT_BREAKER_THRESHOLD)
    with ThreadPoolExecutor(max_workers=min(len(tasks), CFG.LLM_CONCURRENT_MAX)) as executor:
        futures = {
            executor.submit(
                _call_with_transition_review, checker, prompt, paper, breaker,
            ): paper
            for paper, prompt in tasks
        }
        for future in as_completed(futures):
            paper = futures[future]
            timestamp = str(datetime.now())
            try:
                response, review_model_id, pre_review_category = future.result()
                result = json.loads(response)
                category, fields, confidence, notes = _normalise_result(result, domain_config)
                db.update_llm_relevance(
                    paper["doi"], category, fields, confidence, notes,
                    FetchStatus.SUCCESS.value, timestamp, basis="fulltext",
                    model_id=CFG.LLM_API_CONFIG_DICT_FULLTEXT.get("model"),
                    review_model_id=review_model_id,
                    pre_review_category=pre_review_category,
                )
            except (LLMAPICallError, LLMResponseParseError, json.JSONDecodeError) as error:
                if isinstance(error, LLMServiceUnavailableError) and breaker.is_open:
                    continue
                db.update_llm_relevance_error(
                    paper["doi"], str(error)[:500], FetchStatus.FAILED.value,
                    timestamp,
                )
            except Exception as error:
                db.update_llm_relevance_error(
                    paper["doi"], str(error)[:500], FetchStatus.FAILED.value,
                    timestamp,
                )
