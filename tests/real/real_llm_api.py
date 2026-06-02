"""
T3 真实测试：调用 DeepSeek API (相关性 + 总结) 并捕获响应作为 fixture。

用法:
  python tests/real/real_llm_api.py

前置条件:
  - .env 中配置了 DEEPSEEK_API_KEY
  - 网络连接正常
  - DeepSeek 账户有余额

输出:
  - tests/fixtures/llm_relevance_response.json
  - tests/fixtures/llm_summary_response.json

注意:
  - 调用 DeepSeek API 消耗账户额度，约几十 tokens
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def run_relevance():
    from utils.paper_relevance import PaperRelevanceChecker
    from config import LLM_API_CONFIG_DICT_RELE

    config = dict(LLM_API_CONFIG_DICT_RELE)
    if not config.get("api_key"):
        print("[SKIP] DEEPSEEK_API_KEY not configured in .env")
        return False

    keywords = ["laser plasma", "wakefield acceleration", "proton acceleration"]
    checker = PaperRelevanceChecker(keywords)

    prompt = checker.build_default_prompt(
        "Laser wakefield acceleration of electrons to GeV energies",
        "We demonstrate electron acceleration to GeV energies "
        "using laser-driven plasma wakefields."
    )

    result_str = checker.call_deepseek_api(prompt, config)
    parsed = json.loads(result_str)

    assert "relevant" in parsed, "Response missing 'relevant' field"
    assert "confidence" in parsed, "Response missing 'confidence' field"
    assert isinstance(parsed["relevant"], bool), "relevant should be bool"

    fixture_path = FIXTURE_DIR / "llm_relevance_response.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[OK] Relevance fixture saved to {fixture_path}")
    return True


def run_summary():
    from utils.llm_summarize_deepseek import DeepSeekPaperSummarizer
    from config import LLM_API_CONFIG_DICT_SUMM, SUMMARIES_PROMPT

    config = dict(LLM_API_CONFIG_DICT_SUMM)
    if not config.get("api_key"):
        print("[SKIP] DEEPSEEK_API_KEY not configured for summary")
        return False

    summarizer = DeepSeekPaperSummarizer(llm_api_config=config)

    article_text = (
        "标题: Laser wakefield acceleration of electrons\n\n"
        "全文:\nWe demonstrate electron acceleration to GeV energies "
        "using laser-driven plasma wakefields. The experiment was conducted "
        "using a 200 TW laser system with 30 fs pulse duration."
    )

    result_str = summarizer.call_deepseek_api(article_text, SUMMARIES_PROMPT)
    parsed = json.loads(result_str)

    expected_fields = [
        "one_sentence", "motivation_and_goal", "key_setup_and_method",
        "main_results_and_physics", "take_home_message",
    ]
    for field in expected_fields:
        assert field in parsed, f"Response missing '{field}' field"

    fixture_path = FIXTURE_DIR / "llm_summary_response.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[OK] Summary fixture saved to {fixture_path}")
    return True


def main():
    results = []
    results.append(("relevance", run_relevance()))
    results.append(("summary", run_summary()))
    for name, ok in results:
        status = "OK" if ok else "SKIP"
        print(f"[{status}] {name}")
    return 0 if any(ok for _, ok in results) else 0


if __name__ == "__main__":
    sys.exit(main())
