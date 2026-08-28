"""
common.py
=========
共享数据模型、异常定义与 LLM 调用工具。

集中存放跨模块共享的类型，避免循环导入和重复定义。

数据模型:
    Paper       — 论文元数据 dataclass（RSS / Publisher 统一返回类型）

共享异常:
    LLMConfigurationError   — API Key/URL 缺失或无效
    LLMAPICallError         — 网络请求失败（超时、连接错误、HTTP 4xx/5xx）
    LLMResponseParseError   — API 返回结构异常（缺少预期字段）
    LLMContextLengthExceed  — 输入文本超过模型上下文窗口限制

LLM 调用工具:
    build_llm_endpoint_url       — 按协议规范化 LLM 端点
    build_chat_completions_url   — 兼容旧调用的 Chat Completions 端点
    fix_json_invalid_escapes     — 修复 JSON 字符串中不合法的转义序列
    call_llm_api_with_retry      — 带重试的 LLM API 调用封装

各模块特有的异常（如 PageParseError, NotFoundError, DataBaseDOINotExists）
保留在各自模块中定义。
"""

import html
import json
import logging
import random
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import List, Dict, Any
from urllib.parse import urlsplit, urlunsplit

import requests


def clean_extracted_text(value: str | None) -> str | None:
    """Normalize text extracted from feeds, HTML, XML, or metadata APIs.

    Publishers do not use one consistent representation for line breaks.  In
    particular, some IOP pages expose an encoded carriage return such as
    ``&#xD;`` (and occasionally the double-encoded ``&amp;#xD;``) as literal
    text.  Whitespace-only cleanup cannot remove that value, so decoding must
    happen before control-character and whitespace normalization.

    Parameters
    ----------
    value : str or None
        Extracted text.  Empty strings are returned as empty strings so callers
        that use an empty value as a sentinel keep their existing contract.

    Returns
    -------
    str or None
        Cleaned text, or ``None`` when the input is ``None``.
    """
    if value is None:
        return None

    text = str(value)
    # Decode entities twice at most.  The second pass handles pages that put
    # ``&#xD;`` behind an additional ``&amp;`` layer without looping forever on
    # ordinary ampersands.
    for _ in range(2):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\ufeff", "").replace("\u200b", "")
    # Keep normal whitespace (it is collapsed below), but discard invisible
    # control characters that can leak from HTML/XML serialization.
    text = "".join(
        character
        for character in text
        if character in "\n\r\t" or not unicodedata.category(character) == "Cc"
    )
    # A source may split a hyphenated English word at an encoded line break.
    # Joining only after a hyphen avoids changing ordinary word boundaries.
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "-", text)
    return " ".join(text.split())


# ---------- 数据模型 ----------

@dataclass
class Paper:
    """论文元数据。

    所有字段均为可选，解析失败时对应字段为 None 或空值。

    Attributes:
        doi:      数字对象标识符
        title:    论文标题
        date:     发表日期
        journal:  期刊名称
        abstract: 摘要文本
        authors:  作者列表
        pdf_url:  PDF 下载链接
        url:      标准页面链接（canonical url / page link）
    """
    doi: str | None = None
    title: str | None = None
    date: str | None = None
    journal: str | None = None
    abstract: str | None = None
    authors: List[str] | None = None
    pdf_url: str | None = None
    url: str | None = None


# ---------- 共享异常 ----------

class LLMConfigurationError(Exception):
    """LLM 配置错误——API Key/URL 缺失或无效。"""


class LLMAPICallError(Exception):
    """LLM API 调用失败——网络请求层面错误。"""


class LLMServiceUnavailableError(LLMAPICallError):
    """LLM 服务暂时不可用，可由熔断器统计并在后续任务中重试。"""


class LLMResponseParseError(Exception):
    """LLM 响应解析失败——返回数据结构异常。"""


class LLMContextLengthExceed(Exception):
    """输入文本超长——超过模型上下文窗口限制。"""


# ---------- LLM 调用工具 ----------

_logger = logging.getLogger(__name__)

LLM_PROTOCOL_OPENAI_CHAT = "openai_chat"
LLM_PROTOCOL_OPENAI_RESPONSES = "openai_responses"
LLM_PROTOCOL_ANTHROPIC_MESSAGES = "anthropic_messages"
SUPPORTED_LLM_PROTOCOLS = {
    LLM_PROTOCOL_OPENAI_CHAT,
    LLM_PROTOCOL_OPENAI_RESPONSES,
    LLM_PROTOCOL_ANTHROPIC_MESSAGES,
}


def build_llm_endpoint_url(base_url: str, protocol: str = LLM_PROTOCOL_OPENAI_CHAT) -> str:
    """Build an LLM endpoint for a supported wire protocol.

    Parameters
    ----------
    base_url : str
        Service base URL, optionally including a version prefix such as ``/v1``.
    protocol : str
        Wire protocol. Supported values are ``openai_chat``,
        ``openai_responses``, and ``anthropic_messages``.

    Returns
    -------
    str
        The normalized protocol endpoint URL.

    Raises
    ------
    ValueError
        If ``base_url`` is invalid.
    """
    if protocol not in SUPPORTED_LLM_PROTOCOLS:
        supported_protocols = ", ".join(sorted(SUPPORTED_LLM_PROTOCOLS))
        raise ValueError(
            f"Unsupported LLM protocol {protocol!r}; "
            f"choose one of: {supported_protocols}"
        )

    normalized_base_url = str(base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise ValueError("LLM base_url must not be empty")

    parsed_url = urlsplit(normalized_base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("LLM base_url must be an absolute HTTP(S) URL")
    if parsed_url.query or parsed_url.fragment:
        raise ValueError("LLM base_url must not include a query string or fragment")

    endpoint_suffix = {
        LLM_PROTOCOL_OPENAI_CHAT: "/chat/completions",
        LLM_PROTOCOL_OPENAI_RESPONSES: "/responses",
        LLM_PROTOCOL_ANTHROPIC_MESSAGES: "/messages",
    }[protocol]
    if endpoint_path := parsed_url.path.rstrip("/"):
        if endpoint_path.endswith(endpoint_suffix):
            return urlunsplit(parsed_url)
    else:
        endpoint_path = ""
    return urlunsplit((
        parsed_url.scheme,
        parsed_url.netloc,
        f"{endpoint_path}{endpoint_suffix}",
        "",
        "",
    ))


def build_chat_completions_url(base_url: str) -> str:
    """Build the legacy OpenAI Chat Completions endpoint.

    Parameters
    ----------
    base_url : str
        Service base URL, optionally including a version prefix such as ``/v1``.

    Returns
    -------
    str
        The normalized ``/chat/completions`` endpoint URL.
    """
    return build_llm_endpoint_url(base_url, LLM_PROTOCOL_OPENAI_CHAT)


def _build_protocol_payload(
    config: Dict[str, Any],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Translate the internal canonical payload to a wire-format payload."""
    protocol = config.get("protocol", LLM_PROTOCOL_OPENAI_CHAT)
    if protocol == LLM_PROTOCOL_OPENAI_CHAT:
        return payload
    if protocol == LLM_PROTOCOL_OPENAI_RESPONSES:
        messages = payload.get("messages", [])
        system_parts = [
            message.get("content", "")
            for message in messages
            if message.get("role") == "system"
        ]
        input_messages = [
            {
                "role": message.get("role", "user"),
                "content": message.get("content", ""),
            }
            for message in messages
            if message.get("role") != "system"
        ]
        request_payload = {
            "model": payload.get("model", config.get("model")),
            "input": input_messages,
            "max_output_tokens": payload.get(
                "max_output_tokens",
                payload.get("max_tokens", config.get("max_tokens", 8192)),
            ),
        }
        if system_parts:
            request_payload["instructions"] = "\n\n".join(system_parts)

        response_format = payload.get("response_format")
        if response_format:
            request_payload["text"] = {"format": response_format}

        reasoning_effort = config.get("reasoning_effort")
        if reasoning_effort in {"low", "medium", "high"}:
            request_payload["reasoning"] = {"effort": reasoning_effort}
        return request_payload
    if protocol != LLM_PROTOCOL_ANTHROPIC_MESSAGES:
        raise ValueError(f"Unsupported LLM protocol: {protocol}")

    messages = payload.get("messages", [])
    system_parts = [
        message.get("content", "")
        for message in messages
        if message.get("role") == "system"
    ]
    message_list = [
        {"role": message.get("role"), "content": message.get("content", "")}
        for message in messages
        if message.get("role") != "system"
    ]
    request_payload = {
        "model": payload.get("model", config.get("model")),
        "max_tokens": config.get("max_tokens", 8192),
        "messages": message_list,
    }
    if system_parts:
        request_payload["system"] = "\n\n".join(system_parts)

    thinking = payload.get("thinking", {}).get("type")
    if thinking in {"adaptive", "disabled"}:
        request_payload["thinking"] = {"type": thinking}
    elif thinking == "enabled":
        # ``enabled`` is an OpenAI-compatible gateway convention.  Anthropic's
        # Messages API uses ``adaptive`` or ``disabled`` instead.
        request_payload["thinking"] = {"type": "adaptive"}
    return request_payload


def _build_protocol_headers(
    config: Dict[str, Any],
    headers: Dict[str, str],
) -> Dict[str, str]:
    """Build HTTP headers for the configured wire protocol."""
    protocol = config.get("protocol", LLM_PROTOCOL_OPENAI_CHAT)
    request_headers = dict(headers)
    if protocol == LLM_PROTOCOL_ANTHROPIC_MESSAGES:
        api_key = config.get("api_key", "")
        request_headers.pop("Authorization", None)
        request_headers["x-api-key"] = api_key
        request_headers["anthropic-version"] = config.get(
            "anthropic_version", "2023-06-01"
        )
    request_headers.setdefault("Content-Type", "application/json")
    return request_headers


def _extract_protocol_content(
    protocol: str,
    response_data: Dict[str, Any],
) -> str:
    """Extract text content from an OpenAI or Anthropic response."""
    if protocol == LLM_PROTOCOL_OPENAI_CHAT:
        return response_data["choices"][0]["message"]["content"]
    if protocol == LLM_PROTOCOL_OPENAI_RESPONSES:
        output_text = response_data.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text

        text_parts = []
        for output_item in response_data.get("output", []):
            if not isinstance(output_item, dict):
                continue
            if output_item.get("type") == "output_text":
                text = output_item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            for content_item in output_item.get("content", []):
                if not isinstance(content_item, dict):
                    continue
                if content_item.get("type") == "output_text":
                    text = content_item.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
        if text_parts:
            return "".join(text_parts)
        raise KeyError("output[].content[].text")
    if protocol == LLM_PROTOCOL_ANTHROPIC_MESSAGES:
        content_blocks = response_data["content"]
        text_parts = [
            block.get("text", "")
            for block in content_blocks
            if block.get("type") == "text"
        ]
        if not text_parts:
            raise KeyError("content[].text")
        return "".join(text_parts)
    raise ValueError(f"Unsupported LLM protocol: {protocol}")


def _response_preview(response) -> str:
    """Return a short, non-sensitive preview of an HTTP error response."""
    response_text = getattr(response, "text", "") or ""
    return str(response_text).replace("\n", " ")[:500]


def _extract_json_candidate(content: str) -> str:
    """Extract a JSON object from common LLM Markdown wrappers.

    Parameters
    ----------
    content : str
        Raw text returned by an LLM.

    Returns
    -------
    str
        The most likely JSON object substring.  If no object delimiters are
        present, the stripped input is returned unchanged.
    """
    text = str(content or "").strip()
    fenced_match = re.search(
        r"```(?:json|jsonc)?\s*(\{.*\})\s*```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced_match:
        return fenced_match.group(1).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        return text[first_brace:last_brace + 1].strip()
    return text


def _repair_unescaped_quotes(content: str) -> str:
    """Escape likely prose quotes that occur inside JSON string values.

    This is deliberately conservative: a quote followed by a JSON structural
    delimiter closes a string; a quote followed by ordinary text is treated as
    prose and escaped.  It handles model output such as ``"peeler"`` inside a
    Chinese sentence without changing valid JSON quotes.

    Parameters
    ----------
    content : str
        Candidate JSON text.

    Returns
    -------
    str
        JSON text with likely unescaped prose quotes repaired.
    """
    repaired = []
    in_string = False
    escaped = False
    for index, character in enumerate(content):
        if character == "\\" and in_string:
            repaired.append(character)
            escaped = not escaped
            continue

        if character == '"' and not escaped:
            if not in_string:
                in_string = True
                repaired.append(character)
            else:
                next_index = index + 1
                while next_index < len(content) and content[next_index].isspace():
                    next_index += 1
                next_character = (
                    content[next_index] if next_index < len(content) else ""
                )
                if next_character in ",}]":
                    in_string = False
                    repaired.append(character)
                elif next_character == ":":
                    in_string = False
                    repaired.append(character)
                else:
                    repaired.extend(("\\", character))
            escaped = False
            continue

        repaired.append(character)
        escaped = False
    return "".join(repaired)


class LLMCircuitBreaker:
    """Track consecutive transient LLM failures across concurrent requests."""

    def __init__(self, failure_threshold: int = 5):
        self.failure_threshold = max(1, failure_threshold)
        self._consecutive_failures = 0
        self._is_open = False
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        """Whether new LLM requests must be rejected."""
        with self._lock:
            return self._is_open

    def allow_request(self) -> bool:
        """Return whether a new request may be submitted."""
        return not self.is_open

    def record_success(self) -> None:
        """Reset the consecutive transient-failure count after success."""
        with self._lock:
            self._consecutive_failures = 0

    def record_transient_failure(self) -> None:
        """Open the circuit once the configured threshold is reached."""
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._is_open = True


def _retry_delay(response, attempt: int, max_delay: float) -> float:
    """Return a jittered retry delay, honoring a numeric Retry-After header."""
    retry_after = response.headers.get("Retry-After") if response is not None else None
    try:
        base_delay = float(retry_after) if retry_after else 2 ** attempt
    except ValueError:
        base_delay = 2 ** attempt
    return min(max_delay, base_delay) * random.uniform(0.8, 1.2)


def fix_json_invalid_escapes(content: str) -> str:
    """修复 JSON 字符串中不合法的转义序列。

    LLM 输出中可能包含未正确转义的反斜杠（如 LaTeX 命令的 \\），
    导致 json.loads() 失败。此函数在已知合法的 JSON 转义序列外
    对孤立反斜杠进行额外转义。

    返回修复后的字符串。若无需修复则原样返回。

    Parameters
    ----------
    content : str
        待修复的 JSON 字符串

    Returns
    -------
    str
        修复后的字符串
    """
    candidate = _extract_json_candidate(content)
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        pass

    fixed = re.sub(r'(?<![\x5C])\\(?![\\"/bfnrtu])', r'\\\\', candidate)
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        repaired = _repair_unescaped_quotes(fixed)
        json.loads(repaired)
        return repaired


def call_llm_api_with_retry(
    config: Dict[str, Any],
    headers: Dict[str, str],
    payload: Dict[str, Any],
    session: requests.Session | None = None,
    circuit_breaker: LLMCircuitBreaker | None = None,
    expect_json: bool = True,
) -> str:
    """带重试和错误码友好提示的 LLM API 调用封装。

    Parameters
    ----------
    config : dict
        LLM API 配置，需包含 "api_url" 和 "timeout"（可选，默认 300）。
    headers : dict
        HTTP 请求头（含 Authorization、Content-Type）。
    payload : dict
        API 请求体。
    session : requests.Session | None
        复用的 Session 对象，不传则每次新建。
    expect_json : bool
        Whether to apply JSON escape repair to the returned text. Set to False
        for plain-text tasks such as formula repair.

    Returns
    -------
    str
        API 返回的 content 字段字符串。

    Raises
    ------
    LLMAPICallError
        网络请求失败（超时、HTTP 4xx/5xx）。
        LLMResponseParseError
        响应结构异常（缺少协议对应的文本内容字段）。
    """
    if circuit_breaker is not None and not circuit_breaker.allow_request():
        raise LLMServiceUnavailableError("LLM circuit breaker is open")

    _session = session or requests
    protocol = config.get("protocol", LLM_PROTOCOL_OPENAI_CHAT)
    request_headers = _build_protocol_headers(config, headers)
    request_payload = _build_protocol_payload(config, payload)
    last_error = None
    retryable = False
    max_attempts = max(1, int(config.get("retry_max_attempts", 3)))
    max_delay = float(config.get("retry_backoff_max_seconds", 30))

    for attempt in range(max_attempts):
        try:
            t0 = time.time()
            resp = _session.post(
                config["api_url"],
                headers=request_headers,
                json=request_payload,
                timeout=config.get("timeout", 300),
            )
            t1 = time.time()
            resp.raise_for_status()
            response_data = resp.json()
            try:
                content = _extract_protocol_content(protocol, response_data)
            except (KeyError, IndexError, TypeError) as exc:
                service_message = ""
                if isinstance(response_data, dict):
                    service_message = str(response_data.get("message") or response_data.get("error") or "")
                raise LLMServiceUnavailableError(
                    f"LLM response missing content: {service_message[:200] or exc}"
                ) from exc

            if expect_json:
                try:
                    content = fix_json_invalid_escapes(content)
                except json.JSONDecodeError as error:
                    # 修复后仍非法，交给重试循环
                    raise json.JSONDecodeError(
                        f"Invalid escape after fix: {content[-200:]}",
                        content, 0,
                    ) from error

            _logger.info(
                f"LLM API 响应耗时 {t1 - t0:.1f}s, "
                f"输出 {len(content)} 字符"
            )
            if circuit_breaker is not None:
                circuit_breaker.record_success()
            return content

        except requests.exceptions.RequestException as e:
            last_error = e
            status_code = getattr(e.response, 'status_code', None)
            retryable = status_code is None or status_code == 429 or (
                status_code is not None and 500 <= status_code <= 599
            )
            if status_code == 401:
                msg = "API Key 错误 (401)，请检查 .env 中的密钥"
            elif status_code == 402:
                msg = "账号余额不足 (402)，请充值"
            elif status_code == 429:
                msg = "请求速率上限 (429)，可降低 LLM_CONCURRENT_MAX"
            elif status_code == 503:
                msg = "服务器繁忙 (503)"
            elif status_code:
                response_preview = _response_preview(getattr(e, "response", None))
                msg = f"API HTTP {status_code}"
                if response_preview:
                    msg += f": {response_preview}"
            else:
                msg = str(e)
            if retryable and attempt < max_attempts - 1:
                delay = _retry_delay(getattr(e, "response", None), attempt, max_delay)
                _logger.debug("API 暂时失败 (%s)，%.1fs 后重试", msg, delay)
                time.sleep(delay)
                continue

        except LLMServiceUnavailableError as e:
            last_error = e
            retryable = True
            if attempt < max_attempts - 1:
                delay = _retry_delay(None, attempt, max_delay)
                _logger.debug("API 服务响应异常，%.1fs 后重试: %s", delay, e)
                time.sleep(delay)
                continue
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            last_error = e
            retryable = False
            if attempt < max_attempts - 1:
                _logger.debug(f"API 响应异常，{2 ** attempt}s 后重试: {e}")
                time.sleep(2 ** attempt)
                continue

    if retryable and circuit_breaker is not None:
        circuit_breaker.record_transient_failure()
    if retryable:
        raise LLMServiceUnavailableError(f"LLM service unavailable: {last_error}") from last_error
    if isinstance(last_error, requests.exceptions.RequestException):
        status_code = getattr(last_error.response, 'status_code', '?')
        raise LLMAPICallError(
            f"LLM API 失败 (HTTP {status_code}): {last_error}"
            f"{(': ' + _response_preview(last_error.response)) if last_error.response is not None else ''}"
        ) from last_error
    raise LLMResponseParseError(
        f"API 返回结构异常: {last_error}"
    ) from last_error
