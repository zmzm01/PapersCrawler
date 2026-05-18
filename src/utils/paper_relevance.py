"""
paper_relevance.py
==================
根据给定的研究领域关键词表，判断一篇论文（通过标题和摘要）的相关性。

提供三种策略：
1. 关键词匹配统计：统计标题和摘要中命中的关键词数量。
2. LLM 判断：调用大语言模型 API，让模型结合关键词表判断论文是否相关。
3. 语义相似度：使用句子嵌入模型计算论文与领域描述的相似度，可作为补充或替代方案，尤其适合同义词、上下位词等非精确匹配场景。
"""

import re
import json
import logging
from typing import List, Optional, Dict, Any

import requests  # 用于 LLM API 调用；也可改用 openai 库


class LLMConfigurationError(Exception):
    """LLM 配置错误"""


class LLMAPICallError(Exception):
    """LLM API 调用失败"""


class LLMResponseParseError(Exception):
    """LLM 响应解析失败"""


class PaperRelevanceChecker:
    """
    论文相关性检测器

    Parameters
    ----------
    keywords : List[str]
        研究领域关键词表，例如 ["graph neural network", "node classification", ...]
    ---
    """

    def __init__(self, keywords: List[str]) -> None:
        self.keywords = [k.strip().lower() for k in keywords if k.strip()]

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
        统计标题和摘要中命中的不同关键词数量
        
        Parameters
        ----------
        title
        abstract

        Returns
        -------
        matched_count: int
            完全不含任何关键词返回 0，通常表示不相关。
        ---
        """
        text = f"{title} {abstract}"
        matched = set()
        for pattern in self.keyword_patterns:
            if pattern.search(text):
                # 为了返回匹配到的原始关键词，可从 pattern.pattern 恢复
                matched.add(pattern.pattern)
        return len(matched)

    # ------------------------------------------------------------------
    # 方法2：通过 LLM API 判断相关性
    # ------------------------------------------------------------------
    # 提示词构造
    def build_default_prompt(self, title: str, abstract: str) -> str:
        keywords_str = ", ".join(self.keywords)
        json_example = json.dumps({
            "relevant": False,
            "confidence": "low",
            "reason": "摘要未明确提及核心关键词"
        }, ensure_ascii=False)
        
        return (
            f"你是一个研究领域文献筛选助手。给定关键词列表：\n"
            f"{keywords_str}\n\n"
            f"请根据以下论文信息判断其与关键词的相关性。\n\n"
            f"标题：{title}\n"
            f"摘要：{abstract}\n\n"
            f"直接输出一个 JSON 对象，格式如下：\n"
            f"{json_example}\n\n"
            f"要求：\n"
            f"- relevant: true 表示相关，false 表示不相关\n"
            f"- confidence: high / medium / low，表示你对判断的把握程度\n"
            f"- reason: 一句话说明判断依据\n"
            f"只输出 JSON，不要包含任何其他内容。"
        )

    # ------------------------------------------------------------------
    # API 调用
    # ------------------------------------------------------------------
    def call_deepseek_api(self, prompt: str, llm_api_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 DeepSeek API
        Note the thinking mode does not support temperature、top_p、presence_penalty、frequency_penalty parameters (https://api-docs.deepseek.com/zh-cn/guides/thinking_mode)
        And we use JSON Output function (https://api-docs.deepseek.com/zh-cn/guides/json_mode)
        
        Parameters
        ----------
        prompt : str
            提示词
        llm_api_config : Dict[str, Any]
            LLM API 配置字典，需包含：
            - "api_url": API 端点
            - "api_key": 认证密钥
            - "model": 模型名称 (默认 "gpt-3.5-turbo")
            - 其他可选参数如 "temperature", "max_tokens", "timeout" 等。

        Returns
        -------
        Dict[str, Any]
            {
                "relevant": bool,
                "confidence": "high"/"medium"/"low",
                "reason": str
            }
        ---
        """
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

        try:
            resp = requests.post(
                config["api_url"],
                headers=headers,
                json=payload,
                timeout=config.get("timeout", 300),
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return content
        except requests.exceptions.RequestException as e:
            raise LLMAPICallError(f"网络请求失败: {e}") from e
        except (KeyError, IndexError, TypeError) as e:
            raise LLMResponseParseError(f"API 返回结构异常: {e}") from e

    # ------------------------------------------------------------------
    # 更好的方法（推荐作为补充）：
    # 基于语义相似度（sentence embeddings）
    # 可安装 sentence-transformers 库后使用
    # ------------------------------------------------------------------
    def semantic_similarity(
        self,
        title: str,
        abstract: str,
        model_name: str = "all-MiniLM-L6-v2",
        domain_description: Optional[str] = None,
    ) -> float:
        """
        使用句子嵌入模型计算论文与领域的语义相似度。
        需要安装 sentence-transformers: pip install sentence-transformers

        Parameters
        ----------
        title, abstract : str
            论文标题和摘要。
        model_name : str
            HuggingFace 上的句子嵌入模型名称。
        domain_description : Optional[str]
            对研究领域的自然语言描述，若为空则用关键词拼接。

        Returns
        -------
        float
            余弦相似度得分（0~1），越高越相关。
        """
        try:
            from sentence_transformers import SentenceTransformer, util
        except ImportError:
            raise ImportError(
                "请安装 sentence-transformers 库: pip install sentence-transformers"
            )

        if domain_description is None:
            domain_description = (
                "研究领域涵盖：" + ", ".join(self.keywords)
            )

        model = SentenceTransformer(model_name)
        paper_text = f"{title}. {abstract}"
        embeddings = model.encode(
            [domain_description, paper_text],
            convert_to_tensor=True,
        )
        cosine_score = util.cos_sim(embeddings[0], embeddings[1]).item()
        return cosine_score


# ------------------------------------------------------------------
# 使用示例
# ------------------------------------------------------------------
if __name__ == "__main__":
    # 关键词表
    keywords = [
        "graph neural network",
        "node classification",
        "link prediction",
        "graph embedding",
        "message passing",
    ]

    # 如果使用 LLM，请配置真实 API（示例使用 OpenAI）
    LLM_API_CONFIG_DICT = {
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key": "sk-3cc8e7b0cc4e429da42fbce0b75aa482",
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

    # 3. (更好) 语义相似度
    # sim = checker.semantic_similarity(title, abstract)
    # print(f"语义相似度: {sim:.3f}")