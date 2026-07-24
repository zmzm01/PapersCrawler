"""
paper_relevance.py
==================
根据给定的研究领域关键词表，判断一篇论文（通过标题和摘要）的相关性。

提供三种策略：
1. 关键词匹配统计：统计标题和摘要中命中的关键词数量。
2. LLM 判断：调用大语言模型 API，让模型结合关键词表判断论文是否相关。
3. 语义相似度：使用句子嵌入模型计算论文与领域描述的相似度，可作为补充或替代方案，尤其适合同义词、上下位词等非精确匹配场景。

三种策略的设计考量：
- 策略1（关键词匹配）是最轻量、最快的方法，不依赖外部API或模型，适合初筛。但无法识别同义词/近义词（例如 "GNN" vs "graph neural network"），
  也无法理解上下文（例如论文批评了某种方法，不应视为相关）。
- 策略2（LLM判断）利用大语言模型的理解能力，能够综合关键词表与论文语义做出相关性判断，但依赖API调用，存在网络延迟和成本。
- 策略3（语义相似度）通过句子嵌入（Sentence Embedding）计算论文文本与研究领域描述的向量余弦相似度，无需API key，在本地即可运行，
  能较好地捕获同义词、上下位词等语义关系，适合大批量筛选场景。
"""

import re
import json
import logging
from typing import List, Dict, Any

from common import LLMConfigurationError, LLMAPICallError, LLMResponseParseError

logger = logging.getLogger(__name__)


class PaperRelevanceChecker:
    """
    论文相关性检测器

    核心设计：
    - 初始化时传入研究领域定义（scope_definition），包含各子领域的描述和关键词。
    - 关键词正则模式会被预编译（每个关键词加上 \b 单词边界），在后续调用中直接复用，避免重复编译开销。
    - LLM 判断使用 scope_definition + irrelevant_fields 构建完整提示词。

    Parameters
    ----------
    keywords : dict
        由 load_keywords() 返回的完整领域定义字典。
        含 scope_definition、irrelevant_fields 等字段。
    """

    def __init__(self, keywords: dict) -> None:
        self.scope_definition = keywords.get("scope_definition", {})
        self.context_gates = keywords.get("context_gates", [])
        self.irrelevant_fields = keywords.get("irrelevant_fields", {})

        # 从所有 topics 中自动提取关键词列表，用于传统关键词匹配
        all_keywords = []
        for sec in self.scope_definition.values():
            for t in sec.get("topics", []):
                kw = t.split("—")[0].strip() if "—" in t else t.strip()
                if kw:
                    all_keywords.append(kw)
        self.keywords = [k.strip().lower() for k in all_keywords if k.strip()]

        # 预编译关键词正则（忽略大小写，匹配单词边界避免部分命中）
        self.keyword_patterns = [
            re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
            for kw in self.keywords
        ]

    # ------------------------------------------------------------------
    # 方法1：基于关键词精确匹配的数量
    # ------------------------------------------------------------------
    def keyword_match_count(self, title: str, abstract: str) -> int:
        """
        统计标题和摘要中命中的不同关键词数量。

        统计逻辑：
        - 将标题和摘要拼接为一个整体文本（用空格连接）。
        - 遍历所有预编译的关键词正则模式，逐一检查是否在文本中出现。
        - 使用 set 去重，保证每个关键词最多被计数一次（即使多次出现也只算 1 次）。
        - 返回去重后的命中数量。通常命中数 ≥ 1 即视为相关，命中数为 0 表示不相关。

        Parameters
        ----------
        title : str
            论文标题
        abstract : str
            论文摘要

        Returns
        -------
        matched_count : int
            完全不含任何关键词返回 0，通常表示不相关。
        """
        text = f"{title} {abstract}"
        matched = set()
        for pattern in self.keyword_patterns:
            if pattern.search(text):
                matched.add(pattern.pattern)
        return len(matched)

    # ------------------------------------------------------------------
    # 方法2：通过 LLM API 判断相关性
    # ------------------------------------------------------------------
    def _load_relevance_template(self) -> str:
        """加载相关性判断提示词模板。

        从 configs/prompts/relevance.yaml 加载，失败时使用内嵌后备模板。
        模板包含 {scope_block}、{title}、{abstract}、{doi}、{json_example} 占位符，
        由 build_default_prompt 在运行时填充。

        Returns
        -------
        str
        """
        if hasattr(self, '_template_cache'):
            return self._template_cache
        from config import load_prompt
        template = load_prompt("relevance")
        if not template:
            template = (
                "You are an expert in advanced accelerator physics, "
                "laser-plasma interactions, and beam instrumentation.\n\n"
                "Given the following research scope definition, "
                "classify the paper below.\n\n"
                "{scope_block}\n\n"
                "# Task\n\n"
                "Title: {title}\n"
                "Abstract: {abstract}\n"
                "DOI: {doi}\n\n"
                "1. Determine which sub-domains of the research scope "
                "the paper belongs to. List all that apply.\n"
                "2. Assign a relevance category:\n"
                "   - A: Directly studies the core topics\n"
                "   - B: Studies related technologies or methods\n"
                "   - C: Same field but distant from core interests\n"
                "   - D: Irrelevant\n"
                "3. Provide a confidence level: high / medium / low\n"
                "4. Add notes explaining your judgment.\n\n"
                "Output strictly in JSON with NO additional text. Example:\n"
                "{json_example}"
            )
        self._template_cache = template
        return template

    def build_default_prompt(self, title: str, abstract: str, doi: str = "") -> str:
        """
        构造发给 LLM 的相关性判断提示词。

        使用 configs/prompts/relevance.yaml 中的模板，填充 scope_definition、
        论文信息和 JSON 示例。
        输出格式约束：要求输出合法 JSON，包含 PredictedCategory、MatchedSubfields、
        Confidence、Notes 字段。

        Parameters
        ----------
        title : str
            论文标题
        abstract : str
            论文摘要
        doi : str
            论文 DOI

        Returns
        -------
        prompt : str
            可直接发送给 LLM API 的完整提示词字符串。
        """
        from config import build_scope_block
        scope_block = build_scope_block(
            self.scope_definition,
            context_gates=self.context_gates,
            irrelevant_fields=self.irrelevant_fields,
        )
        # 从 scope_definition 中提取合法的子领域 key 列表供 LLM 参考
        known_keys = list(self.scope_definition.keys()) if self.scope_definition else []
        example_keys = known_keys[:2] if len(known_keys) >= 2 else known_keys
        json_example = json.dumps({
            "PredictedCategory": "B",
            "MatchedSubfields": example_keys,
            "Confidence": "high",
            "Notes": "The paper studies laser-driven ion acceleration with plasma diagnostics.",
        }, ensure_ascii=False)

        template = self._load_relevance_template()
        return template.format(
            scope_block=scope_block,
            title=title,
            abstract=abstract,
            doi=doi,
            json_example=json_example,
        )

    # ------------------------------------------------------------------
    # API 调用 (委托给 common.call_llm_api_with_retry)
    # ------------------------------------------------------------------
    def call_deepseek_api(self, prompt: str, llm_api_config: Dict[str, Any]) -> str:
        """调用 DeepSeek API 进行相关性判断。

        委托给 ``common.call_llm_api_with_retry``，该函数封装了重试、
        状态码友好提示和 JSON 转义修复逻辑。

        Parameters
        ----------
        prompt : str
            提示词（由 build_default_prompt 构造）
        llm_api_config : Dict[str, Any]
            LLM API 配置字典，需包含 api_url、api_key、model、thinking、timeout。

        Returns
        -------
        content : str
            LLM 返回的 JSON 字符串。
        """
        from common import call_llm_api_with_retry

        config = llm_api_config
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.get("model", "deepseek-v4-flash"),
            "messages": [
                {"role": "system", "content": "你是一个专业的学术文献分析助手。"},
                {"role": "user", "content": prompt},
            ],
            "thinking": {"type": config.get("thinking", "enabled")},
            "response_format": {"type": "json_object"},
        }
        return call_llm_api_with_retry(config, headers, payload)


# ------------------------------------------------------------------
# 使用示例
# ------------------------------------------------------------------
if __name__ == "__main__":
    import os
    # 关键词表——定义你关心的研究领域术语
    keywords = [
        "graph neural network",
        "node classification",
        "link prediction",
        "graph embedding",
        "message passing",
    ]

    # 如果使用 LLM，请配置真实 API（示例使用 OpenAI）
    # 注意：实际使用时请将 api_key 替换为有效的 DeepSeek API Key
    LLM_API_CONFIG_DICT = {
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key": os.getenv("DEEPSEEK_API_KEY", "sk-placeholder"),
        "model_name": "deepseek-v4-flash", # or deepseek-v4-pro stronger
        "thinking": "enabled",
        "timeout": 300,
    }

    checker = PaperRelevanceChecker(keywords)

    title = "Graph Attention Networks for Node Classification"
    abstract = (
        "We present graph attention networks (GATs), novel neural network "
        "architectures that operate on graph-structured data, leveraging "
        "masked self-attentional layers to address the shortcomings of prior "
        "methods based on graph convolutions or their approximations."
    )

    # 1. 关键词匹配数量
    # match_cnt = checker.keyword_match_count(title, abstract)
    # print(f"关键词匹配数量: {match_cnt}")

    # 2. LLM 判断 (需要有效 API key)
    # prompt = checker.build_default_prompt(title, abstract)
    # llm_result = checker.call_deepseek_api(prompt, LLM_API_CONFIG_DICT)
    # print(llm_result)
