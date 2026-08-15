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
    build_chat_completions_url   — 规范化 OpenAI Chat Completions 端点
    fix_json_invalid_escapes     — 修复 JSON 字符串中不合法的转义序列
    call_llm_api_with_retry      — 带重试的 LLM API 调用封装

各模块特有的异常（如 PageParseError, NotFoundError, DataBaseDOINotExists）
保留在各自模块中定义。
"""

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import List, Dict, Any
from urllib.parse import urlsplit, urlunsplit

import requests


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


def build_chat_completions_url(base_url: str) -> str:
    """Build the Chat Completions endpoint from a configurable base URL.

    Parameters
    ----------
    base_url : str
        Service base URL, optionally including a version prefix such as ``/v1``.

    Returns
    -------
    str
        The normalized ``/chat/completions`` endpoint URL.

    Raises
    ------
    ValueError
        If ``base_url`` is invalid.
    """
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise ValueError("LLM base_url must not be empty")

    parsed_url = urlsplit(normalized_base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("LLM base_url must be an absolute HTTP(S) URL")
    if parsed_url.query or parsed_url.fragment:
        raise ValueError("LLM base_url must not include a query string or fragment")

    endpoint_path = parsed_url.path.rstrip("/")
    if endpoint_path.endswith("/chat/completions"):
        return urlunsplit(parsed_url)
    return urlunsplit((
        parsed_url.scheme,
        parsed_url.netloc,
        f"{endpoint_path}/chat/completions",
        "",
        "",
    ))


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
    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r'(?<![\x5C])\\(?![\\"/bfnrtu])', r'\\\\', content)
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        raise


def call_llm_api_with_retry(
    config: Dict[str, Any],
    headers: Dict[str, str],
    payload: Dict[str, Any],
    session: requests.Session | None = None,
    circuit_breaker: LLMCircuitBreaker | None = None,
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

    Returns
    -------
    str
        API 返回的 content 字段字符串。

    Raises
    ------
    LLMAPICallError
        网络请求失败（超时、HTTP 4xx/5xx）。
    LLMResponseParseError
        响应结构异常（缺少 choices[0].message.content）。
    """
    if circuit_breaker is not None and not circuit_breaker.allow_request():
        raise LLMServiceUnavailableError("LLM circuit breaker is open")

    _session = session or requests
    last_error = None
    retryable = False
    max_attempts = max(1, int(config.get("retry_max_attempts", 3)))
    max_delay = float(config.get("retry_backoff_max_seconds", 30))

    for attempt in range(max_attempts):
        try:
            t0 = time.time()
            resp = _session.post(
                config["api_url"],
                headers=headers,
                json=payload,
                timeout=config.get("timeout", 300),
            )
            t1 = time.time()
            resp.raise_for_status()
            response_data = resp.json()
            try:
                content = response_data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                service_message = ""
                if isinstance(response_data, dict):
                    service_message = str(response_data.get("message") or response_data.get("error") or "")
                raise LLMServiceUnavailableError(
                    f"LLM response missing choices: {service_message[:200] or exc}"
                ) from exc

            try:
                content = fix_json_invalid_escapes(content)
            except json.JSONDecodeError:
                # 修复后仍非法，交给重试循环
                raise json.JSONDecodeError(
                    f"Invalid escape after fix: {content[-200:]}",
                    content, 0,
                )

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
                msg = f"API Key 错误 (401)，请检查 .env 中的密钥"
            elif status_code == 402:
                msg = f"账号余额不足 (402)，请充值"
            elif status_code == 429:
                msg = f"请求速率上限 (429)，可降低 LLM_CONCURRENT_MAX"
            elif status_code == 503:
                msg = f"服务器繁忙 (503)"
            elif status_code:
                msg = f"API HTTP {status_code}"
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
        ) from last_error
    raise LLMResponseParseError(
        f"API 返回结构异常: {last_error}"
    ) from last_error
