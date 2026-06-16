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
        含 scope_definition、irrelevant_fields、sub_domains_embedding 等字段。
    """

    def __init__(self, keywords: dict) -> None:
        self.scope_definition = keywords.get("scope_definition", {})
        self.context_gates = keywords.get("context_gates", [])
        self.irrelevant_fields = keywords.get("irrelevant_fields", {})
        self.sub_domains_embedding = keywords.get("sub_domains_embedding", {})

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
    # 语义相似度（推荐使用 SemanticFilter 类，支持模型一次加载多次复用）
    # 详见本文件下方 SemanticFilter 类的 compute_similarity() 方法
    # ------------------------------------------------------------------


# ------------------------------------------------------------------
# 语义相似度初筛器
# 模型加载一次，复用给多篇论文批量计算相似度
# ------------------------------------------------------------------

class SemanticFilter:
    """
    语义相似度参考排序器。

    使用 sentence-transformers 将论文标题+摘要与多个子领域描述分别编码为向量，
    计算余弦相似度，取最高分作为论文的语义相似度得分。
    该分数仅用作 WebUI Papers 页面的排序参考，不参与流水线过滤。

    相比关键词匹配的优势:
    1. 能捕获同义词（如 "LWFA" ↔ "laser wakefield acceleration"）
    2. 能处理上下位词关系
    3. 模型加载一次后复用，适合大批量论文批量计算
    4. 纯本地运行，不依赖外部 API

    使用示例:
        sf = SemanticFilter(
            model_name="bge-base-en-v1.5",
            sub_domains={
                "ion_acceleration": "Laser-driven ion acceleration...",
                "beam_transport": "High-gradient plasma beam transport...",
            }
        )
        score, best_sub = sf.compute_similarity(
            title="Laser wakefield acceleration of electrons",
            abstract="We demonstrate electron acceleration..."
        )
        # score ≈ 0.65, best_sub ≈ "beam_transport"

    需要安装: pip install sentence-transformers
    """

    def __init__(self, model_name: str, sub_domains: dict[str, str] | str = None):
        """
        初始化语义过滤器，加载模型并预编码各子领域描述。

        Args:
            model_name: HuggingFace 模型名。
                        "bge-base-en-v1.5" 推荐 (512 tokens, 768-dim)
            sub_domains: dict[str, str] — 子领域标签到描述的映射。
                         如 {"ion_acceleration": "Laser-driven ion..."}
                         若传入普通 str，则包装为 {"default": domain_description}
                         保持与旧接口兼容。

        Raises:
            ImportError: sentence-transformers 未安装
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "请安装 sentence-transformers 库: pip install sentence-transformers"
            )

        self.model = SentenceTransformer(model_name, local_files_only=True)

        if isinstance(sub_domains, str):
            self.sub_domain_texts = {"default": sub_domains}
        elif sub_domains is None:
            self.sub_domain_texts = {"default": ""}
        else:
            self.sub_domain_texts = sub_domains

        self.sub_domain_embeddings = {
            label: self.model.encode(text, convert_to_tensor=True)
            for label, text in self.sub_domain_texts.items()
            if text.strip()
        }

    def compute_similarity(self, title: str, abstract: str) -> tuple[float, str | None]:
        """
        计算论文文本与各子领域描述的语义相似度。

        流程:
        1. 拼接 title + abstract 为 paper_text
        2. 编码 paper_text 为向量
        3. 计算与所有子领域嵌入的余弦相似度
        4. 返回最高分及对应的子领域标签

        Args:
            title:    论文标题
            abstract: 论文摘要

        Returns:
            tuple[float, str | None]: (max_score, best_subdomain_label)
                    max_score: 最高余弦相似度 [0, 1]
                    best_label: 匹配最佳的字段域标签，无可用于 None
        """
        from sentence_transformers import util

        paper_text = f"{title}. {abstract}"
        paper_embedding = self.model.encode(
            paper_text, convert_to_tensor=True
        )
        best_score = 0.0
        best_label = None
        for label, emb in self.sub_domain_embeddings.items():
            score = util.cos_sim(emb, paper_embedding).item()
            if score > best_score:
                best_score = score
                best_label = label
        return best_score, best_label


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

    # 3. 语义相似度（使用 SemanticFilter，多子领域模式）
    # from processors.paper_relevance import SemanticFilter
    # from config import SEMANTIC_MODEL_PATH
    # sub_domains = {
    #     "graph_learning": "Graph neural networks for node classification and link prediction.",
    #     "embedding": "Graph embedding and representation learning methods.",
    # }
    # sf = SemanticFilter(SEMANTIC_MODEL_PATH, sub_domains)
    # score, best = sf.compute_similarity(title, abstract)
    # print(f"语义相似度: {score:.3f}, 最佳子领域: {best}")
