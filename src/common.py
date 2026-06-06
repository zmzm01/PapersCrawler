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
    fix_json_invalid_escapes     — 修复 JSON 字符串中不合法的转义序列
    call_llm_api_with_retry      — 带重试的 LLM API 调用封装

各模块特有的异常（如 PageParseError, NotFoundError, DataBaseDOINotExists）
保留在各自模块中定义。
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import List, Dict, Any

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


class LLMResponseParseError(Exception):
    """LLM 响应解析失败——返回数据结构异常。"""


class LLMContextLengthExceed(Exception):
    """输入文本超长——超过模型上下文窗口限制。"""


# ---------- LLM 调用工具 ----------

_logger = logging.getLogger(__name__)


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
    _session = session or requests
    last_error = None

    for attempt in range(2):
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
            content = resp.json()["choices"][0]["message"]["content"]

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
            return content

        except requests.exceptions.RequestException as e:
            last_error = e
            status_code = getattr(e.response, 'status_code', None)
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
            if attempt == 0:
                _logger.debug(f"API 失败 ({msg})，{2 ** attempt}s 后重试")
                time.sleep(2 ** attempt)
                continue

        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            last_error = e
            if attempt == 0:
                _logger.debug(f"API 响应异常，{2 ** attempt}s 后重试: {e}")
                time.sleep(2 ** attempt)
                continue

    if isinstance(last_error, requests.exceptions.RequestException):
        status_code = getattr(last_error.response, 'status_code', '?')
        raise LLMAPICallError(
            f"LLM API 失败 (HTTP {status_code}): {last_error}"
        ) from last_error
    raise LLMResponseParseError(
        f"API 返回结构异常: {last_error}"
    ) from last_error
