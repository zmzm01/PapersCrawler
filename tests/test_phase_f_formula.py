"""Tests for the independent and concurrent Phase F FormulaFixer stage."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pipeline.phase_f as phase_f
from processors.llm_summarize_deepseek import FormulaFixer


def test_formula_fix_summary_helper_can_run_in_parallel(monkeypatch):
    """Different paper summaries should be safe to fix in parallel."""
    worker_threads = set()

    class FakeFormulaFixer:
        def __init__(self, llm_api_config, force=False):
            del llm_api_config, force

        def fix_text(self, text, field_name="", circuit_breaker=None):
            del field_name, circuit_breaker
            worker_threads.add(threading.get_ident())
            time.sleep(0.02)
            return text

    monkeypatch.setattr(phase_f, "FormulaFixer", FakeFormulaFixer)
    summary = {
        "schema_version": 3,
        "one_sentence": "一句话",
        "motivation_and_goal": {
            "background": "背景",
            "research_gap": "缺口",
            "objective": "目标",
        },
        "key_setup_and_method": {
            "study_type": "experiment",
            "method": "方法",
            "setup_and_parameters": "参数",
            "analysis_or_model": "模型",
            "key_equations": "公式",
        },
        "main_results_and_physics": [],
        "limitations": [],
        "take_home_message": {
            "contribution": "贡献",
            "implication": "启示",
        },
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                phase_f._fix_summary_with_formula_fixer,
                summary,
                f"10/x/{index}",
                {"model": "test"},
                False,
                phase_f.LLMCircuitBreaker(5),
            )
            for index in range(2)
        ]
        results = [future.result() for future in futures]

    assert len(worker_threads) == 2
    assert all(json.loads(result)["one_sentence"] == "一句话" for result, _ in results)


def test_formula_fixer_uses_its_own_output_limit(monkeypatch):
    """FormulaFixer must pass its role-specific token limit to the API."""
    captured = {}

    def fake_call(config, headers, payload, **kwargs):
        del config, headers, kwargs
        captured.update(payload)
        return "fixed"

    monkeypatch.setattr("common.call_llm_api_with_retry", fake_call)
    fixer = FormulaFixer(
        {
            "api_key": "test-key",
            "api_url": "https://example.test/chat/completions",
            "model": "formula-model",
            "max_tokens": 1234,
        },
        force=True,
    )

    assert fixer.fix_text("x^2") == "fixed"
    assert captured["model"] == "formula-model"
    assert captured["max_tokens"] == 1234
