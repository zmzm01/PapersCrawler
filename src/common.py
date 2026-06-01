"""
common.py
=========
共享数据模型与异常定义。

集中存放跨模块共享的类型，避免循环导入和重复定义。

数据模型:
    Paper       — 论文元数据 dataclass（RSS / Publisher 统一返回类型）

共享异常:
    LLMConfigurationError   — API Key/URL 缺失或无效
    LLMAPICallError         — 网络请求失败（超时、连接错误、HTTP 4xx/5xx）
    LLMResponseParseError   — API 返回结构异常（缺少预期字段）
    LLMContextLengthExceed  — 输入文本超过模型上下文窗口限制

各模块特有的异常（如 PageParseError, NotFoundError, DataBaseDOINotExists）
保留在各自模块中定义。
"""

from dataclasses import dataclass, field
from typing import List


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
