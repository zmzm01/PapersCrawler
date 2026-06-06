"""
llm_summarize_deepseek.py
=========================
使用 DeepSeek API 对学术论文全文进行结构化总结。

核心功能：
- 调用 DeepSeek API（支持 thinking mode 和 JSON Output 模式），将论文全文总结为结构化的 JSON。
- 提供 token 估算工具（_estimate_tokens），用于检测输入文本是否超过模型上下文窗口限制。
- 预留分块（chunking）接口，但当前版本未实现分块总结功能。

异常体系设计：
- LLMConfigurationError：配置错误（缺少 api_key 等），在请求发出前即可检测。
- LLMAPICallError：网络请求失败（DNS 解析失败、连接超时、HTTP 非 2xx 状态码等）。
- LLMResponseParseError：API 返回了响应但无法按预期格式解析（缺少字段、类型不匹配）。
- LLMContextLengthExceed：输入文本的估算 token 数超过设定的最大 chunk token 数，或超过模型上下文限制。

这四类异常按层级递进：配置 → 网络 → 解析 → 容量，每层对应不同的问题排查方向。
"""

import os
from pathlib import Path
import json
import re
import logging
import requests
from typing import Dict, Any

from common import LLMConfigurationError, LLMAPICallError, LLMResponseParseError, LLMContextLengthExceed

logger = logging.getLogger(__name__)


class DeepSeekPaperSummarizer:
    """
    使用 DeepSeek API 总结学术论文。

    参数说明：
    - llm_api_config: API 配置字典，包含 api_url, api_key, model 等必要参数。
    - max_chunk_tokens: 单次 API 调用允许的最大 token 数（估算值），默认 1,000,000。
      当前 DeepSeek-V4 的实际上下文窗口约为 128K~256K tokens，此默认值设得较大，
      意味着默认行为是"尽量一次性总结，不拆分"。
    - force_chunk: 是否强制分块。当前未实现分块逻辑，设为 True 会直接抛出错误。

    关于分块（chunking）的设计说明：
    当前版本仅支持一次性将全文发送给 API。分块总结未实现的原因：
    1. 分块需要解决"块间信息丢失"问题——某块可能引用前文定义的缩写或上下文，独立总结会丢失连贯性。
    2. 分块总结后需要"摘要聚合"——将多个块的局部总结合并为全局总结，这本身也需要一次额外的 API 调用。
    3. 分块策略（按段落、按固定 token 数、按语义边界）需要根据论文结构特点调整，难以通用化。
    4. 大多数论文全文（尤其是经过文本提取后的纯文本）不超过 100K tokens，在 DeepSeek-V4 上下文范围内。
    因此，当前版本仅在全文超过 max_chunk_tokens 时抛出 LLMContextLengthExceed，提醒用户处理。
    """

    def __init__(self,
        llm_api_config: Dict[str, Any],
        max_chunk_tokens: int = 1000000,
        force_chunk: bool = False
        ):
        self.llm_api_config = llm_api_config
        self.max_chunk_tokens = max_chunk_tokens
        self.force_chunk = force_chunk


    # ------------------------------------------------------------------
    # API 调用 (委托给 common.call_llm_api_with_retry)
    # ------------------------------------------------------------------
    def call_deepseek_api(self, article_text, system_prompt: str) -> str:
        """调用 DeepSeek API 生成论文结构化总结。

        委托给 ``common.call_llm_api_with_retry``，该函数封装了重试、
        状态码友好提示和 JSON 转义修复逻辑。

        本方法在此基础上增加了 token 估算和分块检查。

        Parameters
        ----------
        article_text : str
            文章全文（通常是 Markdown 或纯文本格式）
        system_prompt : str
            系统提示词。

        Returns
        -------
        content : str
            API 返回的 JSON 字符串。
        """
        from common import call_llm_api_with_retry

        config = self.llm_api_config
        text = article_text

        total_tokens = self._estimate_tokens(text)
        if self.force_chunk:
            raise ValueError("此方法未实现.")
        if total_tokens > self.max_chunk_tokens:
            raise LLMContextLengthExceed(
                f"估计文本长度达到 {total_tokens} tokens "
                f"可能超过上下文长度限制."
            )

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.get("model", "deepseek-v4-pro"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": article_text},
            ],
            "thinking": {"type": config.get("thinking", "enabled")},
            "response_format": {"type": "json_object"},
        }
        return call_llm_api_with_retry(config, headers, payload)


    # ------------------------------------------------------------------
    # Token 估算
    # ------------------------------------------------------------------
    @staticmethod
    def _is_chinese_char(c: str) -> bool:
        """
        判断字符是否为中文字符（包括 CJK 统一表意文字及其扩展区）。

        中文字符的 Unicode 范围涵盖：
        - 基本区（U+4E00~U+9FFF）：常用汉字，约 20,000 个码位
        - 扩展 A（U+3400~U+4DBF）：罕见汉字补充
        - 扩展 B~F（U+20000~U+2EBEF）：更罕见的汉字、古代汉字

        判断中文字符的目的是：中文字符在主流 tokenizer（如 GPT tokenizer, DeepSeek tokenizer）中
        通常占用约 1.5~2 个 token，而英文字母/标点通常占用约 0.25~0.3 个 token。

        该函数是 _estimate_tokens 的辅助函数。
        """
        cp = ord(c)
        return (
            0x4E00 <= cp <= 0x9FFF or      # CJK 统一汉字（基本多文种平面）
            0x3400 <= cp <= 0x4DBF or      # CJK 扩展 A
            0x20000 <= cp <= 0x2A6DF or    # CJK 扩展 B
            0x2A700 <= cp <= 0x2B73F or    # CJK 扩展 C
            0x2B740 <= cp <= 0x2B81F or    # CJK 扩展 D
            0x2B820 <= cp <= 0x2CEAF or    # CJK 扩展 E
            0x2CEB0 <= cp <= 0x2EBEF       # CJK 扩展 F
        )


    @staticmethod
    def _estimate_tokens(text: str) -> float:
        """
        估算文本的 token 数量。

        估算原理（基于经验启发式规则）：
        - 对于基于 BPE（Byte Pair Encoding）或类似算法的 tokenizer，单个英文字母/数字/标点
          通常被编码为约 0.25~0.3 个 token（因为常见字母组合被打包为单个 token）。
          本实现取保守估计 0.3 token/字符。
        - 中文字符（CJK）在 tokenizer 中通常为 1.5~2 个 token（每个汉字可能被拆分为 1~3 个 token）。
          本实现取保守估计 0.6 token/字符（实际往往更高，故意低估以避免误判为"安全"）。
        - 注意：这只是一个粗粒度估算，实际 token 数取决于使用的 tokenizer 实现。
          DeepSeek 使用自研 tokenizer，与 GPT 系列类似但细节不同。
          保守估计意味着：估算值可能低于实际值，因此当估算值接近限制时仍需小心。

        为什么不使用 tiktoken 或其他精确 tokenizer？
        - DeepSeek 的 tokenizer 实现未公开，无法精确计数。
        - tiktoken 是为 OpenAI 模型设计的，与 DeepSeek 的 tokenizer 不完全匹配。
        - 作为安全边际检查，启发式估算已足够满足"是否可能超限"的判断需求。

        Parameters
        ----------
        text : str
            待估算的文本

        Returns
        -------
        float
            估算的 token 数量
        """
        total = 0.0
        for ch in text:
            if DeepSeekPaperSummarizer._is_chinese_char(ch):
                total += 0.6  # 中文字符，保守估计 0.6 token/字
            else:
                # 英文、数字、标点等均按 0.3 token 计
                total += 0.3
        return total


class FormulaFixer:
    """用 LLM 修复单段文本中的 LaTeX 公式格式问题。

    功能：
    1. 将 Unicode 数学符号（希腊字母、上下标、运算符等）转为 LaTeX 命令
    2. 修复裸写的 LaTeX 命令（缺少 \\( 包裹）
    3. 修复缺失反斜杠的分隔符

    纯文本输入/纯文本输出，不涉及 JSON 结构，
    避免 JSON 转义带来的 LLM 理解负担。
    修复失败时回退原内容，不抛异常。
    """

    _FIX_PROMPT_FALLBACK = (
        "你是一个 LaTeX 公式格式修正助手。下面是一段学术文本，"
        "请检查并修复其中的 LaTeX 公式格式问题。\n\n"
        "【转换规则】\n"
        "1. 将所有 Unicode 数学符号转换为对应的 LaTeX 命令\n"
        "2. 修复裸露的 LaTeX 命令\n"
        "3. 修复缺少反斜杠的分隔符\n\n"
        "【修正规则】\n"
        "- 行内公式必须用 \\(...\\) 包裹，独立公式必须用 \\[...\\] 包裹\n"
        "- 不要改变文本内容、语序、标点\n"
        "- 输出中不应保留任何数学类 Unicode 字符\n\n"
        "只输出修正后的文本，不要包含任何额外解释："
    )

    def _get_fix_prompt(self) -> str:
        """获取公式修正提示词。

        优先从 configs/prompts/fix.yaml 加载，失败时使用内嵌后备值。
        结果缓存在类属性中以减少文件 I/O。
        """
        if not hasattr(FormulaFixer, '_fix_prompt_cache'):
            from config import load_prompt
            loaded = load_prompt("fix")
            FormulaFixer._fix_prompt_cache = loaded if loaded else self._FIX_PROMPT_FALLBACK
        return FormulaFixer._fix_prompt_cache

    def __init__(self, llm_api_config: Dict[str, Any], force: bool = False):
        self.config = llm_api_config
        self.force = force
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.config['api_key']}",
            "Content-Type": "application/json",
        })

    @staticmethod
    def needs_fix(text: str, force: bool = False) -> bool:
        """检测文本中是否有 LaTeX 公式格式问题。

        覆盖四类情况：
        1. 裸写 LaTeX 命令（\\alpha 无 \\( 包裹）
        2. 公式分隔符反斜杠丢失（\\( → (，\\[ → [）
        3. 裸上下标（c^2, x_i, E_{kin} 等）
        4. Unicode 数学符号（α, ², ≈ 等希腊字母/上下标/运算符）

        通过移除已正确包裹的 \\(...\\) 和 \\[...\\] 区域后，
        检查剩余文本中是否有 LaTeX 命令、裸上下标或 Unicode 数学字符。

        Parameters
        ----------
        text : str
            待检测的文本
        force : bool
            为 True 时跳过检测直接返回 True（强制修复）
        """
        if force:
            return True
        cleaned = re.sub(r'\\\(.*?\\\)|\\\[.*?\\\]', '', text, flags=re.DOTALL)
        # Unicode 数学字符范围：希腊字母、上下标、箭头、运算符、字母类符号
        unicode_math = (
            r'[\u0370-\u03FF'       # Greek & Coptic
            r'\u2070-\u209F'        # Superscripts & Subscripts
            r'\u2190-\u21FF'        # Arrows
            r'\u2200-\u22FF'        # Mathematical Operators
            r'\u2100-\u214F'        # Letterlike Symbols (ℏ, ℓ, etc.)
            r'\u00B2\u00B3\u00B9'   # ² ³ ¹ (common superscripts)
            r']'
        )
        return bool(re.search(
            r'\\[a-zA-Z]{2,}'       # LaTeX command: \alpha
            r'|[\w\)\]]\^[\w\{\(]'  # Bare superscript: c^2, x^{n}
            r'|[\w\)\]]_[\w\{\(]'   # Bare subscript: x_i, E_{kin}
            r'|' + unicode_math,    # Unicode math characters
            cleaned,
        ))

    def fix_text(self, text: str, field_name: str = "") -> str:
        """修正单段文本中的 LaTeX 公式格式问题。

        Parameters
        ----------
        text : str
            需要修复的文本字符串（纯文本，单反斜杠）
        field_name : str
            字段名（用于日志）

        Returns
        -------
        str
            修复后的文本，失败时回退原内容
        """
        tag = f"[{field_name}] " if field_name else ""
        if not text or text == "未提供":
            logger.debug(f"{tag}跳过修复: 空字段或未提供")
            return text
        if not self.needs_fix(text, force=self.force):
            logger.debug(f"{tag}跳过修复: 无需修复")
            return text
        logger.info(f"{tag}正在修复公式格式 ({len(text)} 字符)")
        payload = {
            "model": self.config.get("model", "deepseek-v4-flash"),
            "messages": [
                {"role": "user", "content": self._get_fix_prompt() + "\n\n" + text},
            ],
            "thinking": {"type": "disabled"},
        }
        try:
            resp = self._session.post(
                self.config["api_url"],
                json=payload,
                timeout=self.config.get("timeout", 60),
            )
            resp.raise_for_status()
            fixed = resp.json()["choices"][0]["message"]["content"]
            logger.info(f"{tag}公式修复成功 ({len(text)}→{len(fixed)} 字符)")
            return fixed
        except Exception as e:
            logger.warning(f"{tag}公式修复失败，回退原内容: {e}")
            return text


if __name__ == "__main__":
    # ===== 配置和运行示例 =====
    # 实际运行前需要设置有效的 DEEPSEEK_API_KEY 环境变量或直接填入 api_key
    LLM_API_CONFIG_DICT = {
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key": os.getenv("DEEPSEEK_API_KEY", "sk-placeholder"),
        "model_name": "deepseek-v4-pro", # or deepseek-v4-pro stronger
        "thinking": "enabled",
        "timeout": 300,
    }

    # 从配置加载系统提示词（如文件不存在则使用内嵌后备值）
    from config import load_prompt
    _prompt = load_prompt("summary")
    if not _prompt:
        # 内嵌后备值（不含 Python 转义干扰）
        _prompt = (
            "你是一位专业的理论/实验物理学家，尤其擅长激光等离子体物理。"
            "请根据提供的论文全文，生成一个 JSON 格式的结构化总结。\n\n"
            "【输出格式】\n"
            '严格输出合法 JSON 对象，不包含任何额外文字或注释。\n'
            "【内容要求】\n"
            "1. 所有字段必须用中文学术语言\n"
            "2. 未提及的信息设为 '未提供'\n"
            "3. 反斜杠必须双写\n"
            "4. 禁止 \\begin{} / \\end{} 等复杂环境\n"
            "5. 换行用 \\n 表示"
        )
    SUMMARIES_PROMPT = _prompt
    # 示例：请先设置 export DEEPSEEK_API_KEY="your-key"
    summarizer = DeepSeekPaperSummarizer(llm_api_config=LLM_API_CONFIG_DICT)
    paperMDpath = Path("/home/user/Code/PapersCrawler/TEST/MinerU_Paper_Parser/qdgp-tydj/full.md")
    full_text = paperMDpath.read_text()
    llm_summary = summarizer.call_deepseek_api(full_text, SUMMARIES_PROMPT)
    from pprint import pprint
    pprint(llm_summary)
    save_dir = Path("/home/user/Code/PapersCrawler/TEST/MinerU_Paper_Parser")
    with open(save_dir / "summary.json", 'w') as f:
        f.write(llm_summary)
