"""
测试: common.py 共享工具函数

覆盖范围:
  - fix_json_invalid_escapes: JSON 转义修复
  - DatabaseClient._validate_column: 列名白名单校验
"""

import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from common import (
    clean_extracted_text,
    LLMCircuitBreaker,
    LLM_PROTOCOL_ANTHROPIC_MESSAGES,
    LLM_PROTOCOL_OPENAI_CHAT,
    LLM_PROTOCOL_OPENAI_RESPONSES,
    LLMServiceUnavailableError,
    build_chat_completions_url,
    build_llm_endpoint_url,
    call_llm_api_with_retry,
    fix_json_invalid_escapes,
)


def test_clean_extracted_text_decodes_entities_and_controls():
    """Encoded IOP line breaks must not leak into stored abstracts."""
    value = "first&#xD;second &amp; third&#xD;particlein-&#xD;cell"
    assert clean_extracted_text(value) == "first second & third particlein-cell"


def test_clean_extracted_text_keeps_scientific_unicode_symbols():
    """Useful symbols such as degree and multiplication signs are preserved."""
    assert clean_extracted_text("181.7 MeV, 12◦, 5.5 × 10²⁰") == "181.7 MeV, 12◦, 5.5 × 10²⁰"


@pytest.mark.parametrize(
    ("base_url", "expected_url"),
    [
        ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
        ("https://gateway.example/v1/", "https://gateway.example/v1/chat/completions"),
        (
            "https://gateway.example/v1/chat/completions",
            "https://gateway.example/v1/chat/completions",
        ),
    ],
)
def test_build_chat_completions_url(base_url, expected_url):
    """The configurable LLM base URL should produce one completion endpoint."""
    assert build_chat_completions_url(base_url) == expected_url


@pytest.mark.parametrize("base_url", ["", "gateway.example/v1", "ftp://gateway.example"])
def test_build_chat_completions_url_rejects_invalid_base_url(base_url):
    """LLM endpoints must be absolute HTTP(S) base URLs."""
    with pytest.raises(ValueError):
        build_chat_completions_url(base_url)


@pytest.mark.parametrize(
    ("protocol", "expected_url"),
    [
        (LLM_PROTOCOL_OPENAI_CHAT, "https://gateway.example/v1/chat/completions"),
        (LLM_PROTOCOL_OPENAI_RESPONSES, "https://gateway.example/v1/responses"),
        (LLM_PROTOCOL_ANTHROPIC_MESSAGES, "https://gateway.example/v1/messages"),
    ],
)
def test_build_llm_endpoint_url_supports_multiple_protocols(protocol, expected_url):
    """Each wire protocol should receive its own canonical endpoint."""
    assert build_llm_endpoint_url("https://gateway.example/v1", protocol) == expected_url


def test_build_llm_endpoint_url_rejects_unknown_protocol():
    """Unknown protocols must fail during configuration instead of at runtime."""
    with pytest.raises(ValueError, match="Unsupported LLM protocol"):
        build_llm_endpoint_url("https://gateway.example/v1", "unknown")


def test_build_llm_endpoint_url_preserves_explicit_responses_endpoint():
    """A fully specified Responses endpoint must not receive a second suffix."""
    endpoint = "https://opencode.ai/zen/go/v1/responses"
    assert build_llm_endpoint_url(endpoint, LLM_PROTOCOL_OPENAI_RESPONSES) == endpoint


# ---- fix_json_invalid_escapes ----

def test_fix_escapes_valid_json_unchanged():
    """合法 JSON 字符串应原样返回。"""
    obj = {"key": "value", "num": 42}
    s = json.dumps(obj)
    assert fix_json_invalid_escapes(s) == s


def test_fix_escapes_latex_backslash():
    """LaTeX 命令中的孤立反斜杠应被转义。"""
    # LLM 可能输出 {\"key\": \"\\\\alpha\"} 但 JSON 需要 {\\\\alpha}
    # 实际场景: LLM 输出 "{\"key\": \"\\alpha\"}" — 这里的 \\ 表示一个反斜杠
    # json.loads 会报错因为 \\a 不是合法 JSON 转义
    s = '{"key": "\\alpha"}'
    try:
        json.loads(s)
        # 如果意外合法则跳过
        return
    except json.JSONDecodeError:
        pass
    fixed = fix_json_invalid_escapes(s)
    # 修复后应能被解析
    parsed = json.loads(fixed)
    assert parsed["key"] == "\\alpha"


def test_fix_escapes_valid_escape_unchanged():
    """已知合法的 JSON 转义序列不应被修改。"""
    s = r'{"a": "\"", "b": "\\", "c": "\n", "d": "\t"}'
    fixed = fix_json_invalid_escapes(s)
    parsed = json.loads(fixed)
    assert parsed["a"] == '"'
    assert parsed["b"] == "\\"
    assert parsed["c"] == "\n"
    assert parsed["d"] == "\t"


def test_fix_escapes_mixed():
    """混合合法与非法转义。"""
    s = r'{"text": "公式 \\alpha 和 \\beta 用于表示 \\gamma"}'
    try:
        json.loads(s)
        return
    except json.JSONDecodeError:
        pass
    fixed = fix_json_invalid_escapes(s)
    parsed = json.loads(fixed)
    assert "alpha" in parsed["text"]
    assert "beta" in parsed["text"]


def test_fix_escapes_extracts_json_from_markdown_fence():
    """Markdown JSON fences from an LLM must not invalidate the response."""
    content = '```json\n{"ok": true}\n```'
    fixed = fix_json_invalid_escapes(content)
    assert json.loads(fixed) == {"ok": True}


def test_fix_escapes_repairs_prose_quotes_inside_json_string():
    """Unescaped prose quotes should be repaired without changing JSON syntax."""
    content = '{"text": "采用 \"peeler\" 方案"}'
    fixed = fix_json_invalid_escapes(content)
    assert json.loads(fixed)["text"] == '采用 "peeler" 方案'


def test_llm_missing_choices_is_transient_and_opens_circuit():
    """A 200 error payload without choices is a retriable service failure."""
    class Response:
        headers = {}
        def raise_for_status(self):
            return None
        def json(self):
            return {"error": {"message": "service degraded"}}

    class Session:
        def post(self, url, **kwargs):
            return Response()

    circuit = LLMCircuitBreaker(failure_threshold=1)
    with pytest.raises(LLMServiceUnavailableError, match="service unavailable"):
        call_llm_api_with_retry(
            {"api_url": "https://example.invalid", "retry_max_attempts": 1},
            {}, {}, session=Session(), circuit_breaker=circuit,
        )
    assert circuit.is_open


def test_anthropic_messages_request_is_normalized_and_text_is_extracted():
    """Messages protocol should split system prompts and ignore thinking blocks."""
    class Response:
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [
                    {"type": "thinking", "thinking": "internal reasoning"},
                    {"type": "text", "text": '{"ok": true}'},
                ],
            }

    class Session:
        def __init__(self):
            self.url = None
            self.kwargs = None

        def post(self, url, **kwargs):
            self.url = url
            self.kwargs = kwargs
            return Response()

    session = Session()
    content = call_llm_api_with_retry(
        {
            "api_url": "https://gateway.example/v1/messages",
            "api_key": "test-key",
            "model": "minimax-m3",
            "protocol": LLM_PROTOCOL_ANTHROPIC_MESSAGES,
            "max_tokens": 4096,
            "retry_max_attempts": 1,
        },
        {"Authorization": "Bearer test-key"},
        {
            "model": "minimax-m3",
            "messages": [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "Return JSON"},
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        },
        session=session,
    )

    assert content == '{"ok": true}'
    assert session.url.endswith("/messages")
    assert session.kwargs["headers"]["x-api-key"] == "test-key"
    assert session.kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in session.kwargs["headers"]
    request_payload = session.kwargs["json"]
    assert request_payload["system"] == "System prompt"
    assert request_payload["messages"] == [{"role": "user", "content": "Return JSON"}]
    assert request_payload["max_tokens"] == 4096
    assert request_payload["thinking"] == {"type": "disabled"}
    assert "response_format" not in request_payload


def test_openai_responses_request_is_normalized_and_text_is_extracted():
    """Responses protocol must use input/instructions and output text items."""
    class Response:
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "object": "response",
                "output": [{
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": '{"ok": true}',
                    }],
                }],
            }

    class Session:
        def __init__(self):
            self.url = None
            self.kwargs = None

        def post(self, url, **kwargs):
            self.url = url
            self.kwargs = kwargs
            return Response()

    session = Session()
    content = call_llm_api_with_retry(
        {
            "api_url": "https://gateway.example/v1/responses",
            "api_key": "test-key",
            "model": "muse-spark-1.2-contributor",
            "protocol": LLM_PROTOCOL_OPENAI_RESPONSES,
            "max_tokens": 1200,
            "retry_max_attempts": 1,
        },
        {"Authorization": "Bearer test-key"},
        {
            "model": "muse-spark-1.2-contributor",
            "messages": [
                {"role": "system", "content": "Return JSON"},
                {"role": "user", "content": "Summarize"},
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        },
        session=session,
    )

    assert content == '{"ok": true}'
    assert session.url.endswith("/responses")
    request_payload = session.kwargs["json"]
    assert request_payload["instructions"] == "Return JSON"
    assert request_payload["input"] == [{"role": "user", "content": "Summarize"}]
    assert request_payload["max_output_tokens"] == 1200
    assert request_payload["text"] == {"format": {"type": "json_object"}}
    assert "thinking" not in request_payload


# ---- DatabaseClient._validate_column ----

def test_validate_column_valid():
    """合法列名应通过验证。"""
    from db.database import DatabaseClient
    DatabaseClient._validate_column("llm_relevance_status")
    DatabaseClient._validate_column("cr_metadata_fetched_status")
    DatabaseClient._validate_column("publisher_page_fetched_date")


def test_validate_column_invalid():
    """非法列名应抛出 ValueError。"""
    from db.database import DatabaseClient
    with pytest.raises(ValueError, match="Invalid column name"):
        DatabaseClient._validate_column("malicious; DROP TABLE papers; --")


def test_validate_column_empty():
    """空字符串应被拦截。"""
    from db.database import DatabaseClient
    with pytest.raises(ValueError):
        DatabaseClient._validate_column("")
