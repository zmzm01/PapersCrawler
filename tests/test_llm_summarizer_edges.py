"""Coverage for summarizer guards and FormulaFixer fallback behavior."""

import pytest

import common
import config
import processors.llm_summarize_deepseek as summarizer_module
from processors.llm_summarize_deepseek import DeepSeekPaperSummarizer, FormulaFixer


def test_summarizer_token_estimation_and_api_guards(monkeypatch):
    """Token estimation, chunk guards and canonical API payload are covered."""
    assert DeepSeekPaperSummarizer._is_chinese_char("汉")
    assert DeepSeekPaperSummarizer._is_chinese_char("𠀀")
    assert not DeepSeekPaperSummarizer._is_chinese_char("a")
    assert DeepSeekPaperSummarizer._estimate_tokens("a汉") == pytest.approx(0.9)

    calls = []

    def fake_call(config_value, headers, payload, **kwargs):
        calls.append((config_value, headers, payload, kwargs))
        return '{"ok": true}'

    monkeypatch.setattr(common, "call_llm_api_with_retry", fake_call)
    client = DeepSeekPaperSummarizer(
        {"api_key": "key", "model": "model", "thinking": "disabled"}
    )
    assert client.call_deepseek_api("abc", "system") == '{"ok": true}'
    assert calls[0][2]["thinking"] == {"type": "disabled"}
    with pytest.raises(ValueError):
        DeepSeekPaperSummarizer({"api_key": "key"}, force_chunk=True).call_deepseek_api(
            "a", "s"
        )
    with pytest.raises(summarizer_module.LLMContextLengthExceed):
        DeepSeekPaperSummarizer(
            {"api_key": "key"}, max_chunk_tokens=0
        ).call_deepseek_api("a", "s")


def test_formula_fixer_prompt_detection_and_fallback(monkeypatch):
    """FormulaFixer skips clean text, fixes successful responses and falls back."""
    monkeypatch.delattr(FormulaFixer, "_fix_prompt_cache", raising=False)
    monkeypatch.setattr(config, "load_prompt", lambda name: None)
    fixer = FormulaFixer({"api_key": "key", "max_output_tokens": 5})
    assert "LaTeX" in fixer._get_fix_prompt()
    assert fixer._get_fix_prompt() == fixer._get_fix_prompt()
    assert FormulaFixer.needs_fix("normal text") is False
    assert FormulaFixer.needs_fix("normal", force=True)
    assert FormulaFixer.needs_fix("$x$")
    assert FormulaFixer.needs_fix(r"\alpha")
    assert FormulaFixer.needs_fix("α")
    assert FormulaFixer.needs_fix(r"\(x^2\)") is False
    assert FormulaFixer.needs_fix(
        r"\(\begin{matrix} a & b \\ c & d \end{matrix}\)"
    ) is False
    assert fixer.fix_text("") == ""
    assert fixer.fix_text("未提供") == "未提供"
    assert fixer.fix_text("normal") == "normal"

    calls = []
    monkeypatch.setattr(
        common,
        "call_llm_api_with_retry",
        lambda *args, **kwargs: calls.append((args, kwargs)) or r"\(x\)",
    )
    assert fixer.fix_text(r"x^2", field_name="result") == r"\(x\)"
    assert calls[0][0][2]["max_tokens"] == 5

    monkeypatch.setattr(
        common,
        "call_llm_api_with_retry",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    assert fixer.fix_text("x^2") == r"\(x^2\)"


def test_formula_fixer_wraps_bare_formulas_before_repair(monkeypatch):
    """Bare formulas are wrapped before validation and remain wrapped on failure."""
    validated = []
    requested = []
    monkeypatch.setattr(
        summarizer_module,
        "validate_katex_formulas",
        lambda text: validated.append(text) or [],
    )
    monkeypatch.setattr(
        common,
        "call_llm_api_with_retry",
        lambda config, headers, payload, **kwargs: requested.append(
            payload["messages"][0]["content"],
        ) or r"结果仍写成 \Delta n(k,t) \propto |\psi(k,t)|^2。",
    )
    fixer = FormulaFixer({"api_key": "key"})

    fixed = fixer.fix_text(r"核心公式：\Delta n(k,t) \propto |\psi(k,t)|^2。")

    assert validated[0] == r"核心公式：\(\Delta n(k,t) \propto |\psi(k,t)|^2\)。"
    assert requested[0].endswith(validated[0])
    assert fixed == r"结果仍写成 \(\Delta n(k,t) \propto |\psi(k,t)|^2\)。"
    assert FormulaFixer.wrap_unwrapped_formulas(r"已有 \(x^2\)，另有 E = mc^2。") == (
        r"已有 \(x^2\)，另有 \(E = mc^2\)。"
    )
    assert FormulaFixer.wrap_unwrapped_formulas(
        r"The value E = mc^2 is the result."
    ) == r"The value \(E = mc^2\) is the result."
    assert FormulaFixer.wrap_unwrapped_formulas(r"使用 800\,nm 泵浦。") == (
        r"使用 \(800\,nm\) 泵浦。"
    )
    assert FormulaFixer.wrap_unwrapped_formulas("相位差 α + β 很小。") == (
        r"相位差 \(α + β\) 很小。"
    )


def test_formula_fixer_passes_katex_diagnostics_and_rejects_invalid_reply(monkeypatch):
    """FormulaFixer uses strict renderer feedback without accepting bad output."""
    validations = [[{"formula": r"\\bad", "message": "Undefined control sequence"}], []]
    monkeypatch.setattr(
        summarizer_module,
        "validate_katex_formulas",
        lambda text: validations.pop(0),
    )
    captured = {}
    monkeypatch.setattr(
        common,
        "call_llm_api_with_retry",
        lambda config, headers, payload, **kwargs: captured.update(payload) or r"\\(x\\)",
    )
    fixer = FormulaFixer({"api_key": "key"})

    assert fixer.fix_text(r"\\(\\bad\\)") == r"\\(x\\)"
    assert "KaTeX 严格校验错误" in captured["messages"][0]["content"]


def test_formula_fixer_retries_only_for_configured_rounds(monkeypatch):
    """Each configured round is a validation, repair, and revalidation loop."""
    validations = [
        [{"formula": r"\\bad", "message": "first"}],
        [{"formula": r"\\stillbad", "message": "second"}],
        [],
    ]
    monkeypatch.setattr(
        summarizer_module,
        "validate_katex_formulas",
        lambda text: validations.pop(0),
    )
    replies = iter([r"\\(\\stillbad\\)", r"\\(x\\)"])
    monkeypatch.setattr(
        common,
        "call_llm_api_with_retry",
        lambda *args, **kwargs: next(replies),
    )
    fixer = FormulaFixer({"api_key": "key"}, max_repair_rounds=2)

    assert fixer.fix_text(r"\\(\\bad\\)") == r"\\(x\\)"
    assert validations == []
