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
import sys
import json
import re
import time
import logging
import requests
from typing import Optional, Dict, Any

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
    # API 调用
    # ------------------------------------------------------------------
    def call_deepseek_api(self, article_text, system_prompt: str) -> str:
        """
        调用 DeepSeek API 生成论文结构化总结。

        DeepSeek API 关键特性说明：

        1. Thinking Mode（思考模式）：
           - DeepSeek-V4 的思考模式让模型在输出最终答案前进行内部推理（类似 chain-of-thought）。
           - 在复杂的学术论文总结任务中，thinking mode 能显著提升总结质量和对物理内容的把握。
           - 注意：开启 thinking mode 后，temperature、top_p、presence_penalty、frequency_penalty 参数不可用，
             因为这些参数引入的随机性与思考模式的确定性推理逻辑冲突。
           - 配置方式：payload 中设置 "thinking": {"type": "enabled"}。

        2. JSON Output（JSON 模式 / 结构化输出）：
           - DeepSeek 原生支持强制 JSON 输出，无需在 prompt 中反复强调格式要求。
           - 配置方式：payload 中设置 "response_format": {"type": "json_object"}。
           - 开启后，模型会确保输出为合法 JSON 对象，极大降低下游解析失败的概率。
           - 注：部分 API 将此功能称为 "json_mode" 或 "structured output"。

        API 请求 payload 结构（以 DeepSeek Chat Completions 端点为例）：
        {
            "model": "deepseek-v4-pro",           // 模型名（flash 更快，pro 更强）
            "messages": [
                {"role": "system", "content": "..."},  // 系统提示词，定义总结格式和要求
                {"role": "user", "content": "..."},    // 用户消息，包含论文全文
            ],
            "thinking": {"type": "enabled"},       // 开启思考模式
            "response_format": {"type": "json_object"}  // 强制 JSON 输出
        }

        调用流程：
        1. 估算输入文本的 token 数（_estimate_tokens）。
        2. 如果 force_chunk=True → 抛错（未实现），如果超限 → 抛 LLMContextLengthExceed。
        3. 构造请求头（Bearer Token 认证）和 payload，发送 POST 请求。
        4. 检查 HTTP 状态码，解析响应 JSON，提取 content 字段返回。

        异常处理策略：
        - 网络失败（DNS、超时、连接拒绝、HTTP 错误） → LLMAPICallError
        - 响应数据缺少预期字段（choices[0].message.content 不存在） → LLMResponseParseError

        Parameters
        ----------
        article_text : str
            文章全文（通常是 Markdown 或纯文本格式）
        system_prompt : str
            系统提示词，包含总结格式要求、字段定义、输出规范等。详见模块底部的 SUMMARIES_PROMPT 示例。

        Returns
        -------
        content : str
            API 返回的 JSON 字符串，结构为：
            {
                "one_sentence": str,              // 一句话概述
                "motivation_and_goal": str,       // 研究动机与目标
                "key_setup_and_method": str,      // 关键方法与设置
                "main_results_and_physics": str,  // 主要结果与物理内涵（Markdown 格式）
                "take_home_message": str          // 要点总结
            }
        ---
        """
        config = self.llm_api_config
        text = article_text

        # 估算 token 数，用于判断是否超过限制
        total_tokens = self._estimate_tokens(text)

        # 不强制分块且全文在单块容量内 → 一次性总结
        if self.force_chunk:
            # 分块逻辑尚未实现，强制分块时直接报错
            raise ValueError("此方法未实现.")
        if total_tokens > self.max_chunk_tokens:
            # 文本超出单块容量，提醒用户文本可能超过模型上下文窗口
            raise LLMContextLengthExceed(f"估计文本长度达到 {total_tokens} tokens 可能超过 DeepSeek-V4 上下文长度限制.")

        # 构造 HTTP 请求头
        # 使用 Bearer Token 认证——这是 DeepSeek API 的标准认证方式
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }
        # 构造 API 请求 payload
        # - model: 默认 "deepseek-v4-pro"（增强推理能力，适合复杂的论文总结任务）
        # - messages: system 角色定义任务，user 角色提供论文全文
        # - thinking: 启用思考模式（默认 "enabled"），提升总结质量
        # - response_format: json_object 模式，强制输出合法 JSON
        payload = {
            "model": config.get("model", "deepseek-v4-pro"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": article_text},
            ],
            "thinking": {"type": config.get("thinking", "enabled")},
            "response_format": {"type": "json_object"},
        }

        last_error = None
        for attempt in range(2):
            try:
                t0 = time.time()
                resp = requests.post(
                    config["api_url"],
                    headers=headers,
                    json=payload,
                    timeout=config.get("timeout", 300),
                )
                t1 = time.time()
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]

                logger = logging.getLogger(__name__)

                # 验证 inner JSON 是否合法，尝试正则修复
                try:
                    json.loads(content)
                except json.JSONDecodeError:
                    fixed = re.sub(r'(?<!\\)\\(?![\\"/bfnrtu])', r'\\\\', content)
                    try:
                        json.loads(fixed)
                        content = fixed
                        logger.debug("正则修复 inner JSON 成功")
                    except json.JSONDecodeError:
                        # 修复后仍非法，交给重试循环
                        raise json.JSONDecodeError(
                            f"Invalid escape after fix: {fixed[-200:]}",
                            fixed, 0
                        )

                logger.info(
                    f"DeepSeek Summarize API 响应耗时 {t1-t0:.1f}s, "
                    f"输入 {len(article_text)} 字符, 输出 {len(content)} 字符"
                )
                return content
            except requests.exceptions.RequestException as e:
                last_error = e
                status_code = getattr(e.response, 'status_code', None)
                if status_code == 401:
                    msg = f"DeepSeek API Key 错误 (401)，请检查 .env 中的 DEEPSEEK_API_KEY"
                elif status_code == 402:
                    msg = f"DeepSeek 账号余额不足 (402)，请前往 platform.deepseek.com 充值"
                elif status_code == 429:
                    msg = f"DeepSeek 请求速率上限 (429)，可降低 LLM_CONCURRENT_MAX"
                elif status_code == 503:
                    msg = f"DeepSeek 服务器繁忙 (503)"
                elif status_code:
                    msg = f"DeepSeek API HTTP {status_code}"
                else:
                    msg = str(e)
                if attempt == 0:
                    logger.debug(f"API 失败 ({msg})，{2**attempt}s 后重试")
                    time.sleep(2 ** attempt)
                    continue
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
                last_error = e
                if attempt == 0:
                    logger.debug(f"API 响应异常，{2**attempt}s 后重试: {e}")
                    time.sleep(2 ** attempt)
                    continue
        if isinstance(last_error, requests.exceptions.RequestException):
            status_code = getattr(last_error.response, 'status_code', '?')
            raise LLMAPICallError(
                f"DeepSeek API 失败 (HTTP {status_code}): {last_error}"
            ) from last_error
        else:
            raise LLMResponseParseError(f"API 返回结构异常: {last_error}") from last_error


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
    """用 LLM 修复单段文本中裸写的 LaTeX 命令或缺失的分隔符反斜杠。

    纯文本输入/纯文本输出，不涉及 JSON 结构，
    避免 JSON 转义带来的 LLM 理解负担。
    修复失败时回退原内容，不抛异常。
    """

    FIX_PROMPT = """你是一个 LaTeX 公式格式修正助手。下面是一段学术文本，请检查并修复其中的 LaTeX 公式格式问题。

【常见问题】
1. 公式分隔符缺少反斜杠：例如 `(\alpha)` 应该是 `\\(\\alpha\\)`
2. LaTeX 命令裸写：例如 `使用 \alpha 驱动` 应该是 `使用 \\(\\alpha\\) 驱动`
3. 独立公式缺少正确包裹：例如 `[E = mc^2]` 应该是 `\\[E = mc^2\\]`

【修正规则】
- 行内公式必须用 \\(...\\) 包裹
- 独立公式必须用 \\[...\\] 包裹
- 不要改变文本内容、语序、标点

只输出修正后的文本，不要包含任何额外解释："""

    def __init__(self, llm_api_config: Dict[str, Any]):
        self.config = llm_api_config
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.config['api_key']}",
            "Content-Type": "application/json",
        })

    @staticmethod
    def needs_fix(text: str) -> bool:
        """检测文本中是否有 LaTeX 公式格式问题。

        覆盖两类情况：
        1. 裸写 LaTeX 命令（\\alpha 无 \\( 包裹）
        2. 公式分隔符反斜杠丢失（\\( → (，\\[ → [）

        通过移除已正确包裹的 \\(...\\) 和 \\[...\\] 区域后，
        检查剩余文本中是否还有 LaTeX 命令来判断。
        """
        cleaned = re.sub(r'\\\(.*?\\\)|\\\[.*?\\\]', '', text, flags=re.DOTALL)
        return bool(re.search(r'\\[a-zA-Z]{2,}', cleaned))

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
        if not self.needs_fix(text):
            logger.debug(f"{tag}跳过修复: 无需修复")
            return text
        logger.info(f"{tag}正在修复公式格式 ({len(text)} 字符)")
        payload = {
            "model": self.config.get("model", "deepseek-v4-flash"),
            "messages": [
                {"role": "user", "content": self.FIX_PROMPT + "\n\n" + text},
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

    # 系统提示词：定义总结的 JSON 格式、字段含义、内容要求和 Markdown 转义规则
    SUMMARIES_PROMPT = """
    你是一位专业的理论/实验物理学家，尤其擅长激光等离子体物理。请根据提供的论文全文，生成一个 JSON 格式的结构化总结。

    【输出格式】
    严格输出合法 JSON 对象，不包含任何额外文字或注释。JSON 对象的格式与字段内容要求如下：

    {
    "one_sentence": "用一句话说明：本文采用什么方法/装置，研究了什么物理问题，得到了什么核心结论",
    "motivation_and_goal": "研究动机、要解决的具体物理问题、前人工作的缺口或争议，以及本文的明确目标",
    "key_setup_and_method": "详细描述实验/理论/模拟方法与关键参数。例如激光参数（波长、能量、脉宽、焦斑）、靶型、诊断设备，或模拟代码（PIC、流体）与网格设置。如有核心公式，请用 LaTeX 呈现，并解释符号含义",
    "main_results_and_physics": "Markdown 格式字符串，描述 2-4 个主要结果及其背后的物理机制。每个结果应包含：观测到的现象、关键定量数据（如能量、转换效率、标度律指数），以及物理解释或支持的理论模型",
    "take_home_message": "本文对领域的主要贡献或启示，并至少指出 1 条明确局限"
    }

    【内容要求】
    1. 所有字段必须用中文学术语言，信息密度高，不遗漏关键物理内涵。
    2. 如果某项信息在论文中未提及，对应字段的值必须设为 "未提供"。绝不编造内容。
    3. 反斜杠转义规则：JSON 字符串中，每个反斜杠必须双写。行内公式必须用 \\\\(...\\\\) 包裹，禁止用 $...$。独立公式必须用 \\\\\\[...\\\\\\] 包裹，禁止用 $$...$$。
    4. 字符串内的换行必须用转义符 \\n 表示，**严禁插入真正的换行符**，以保证 JSON 解析无误。

    【main_results_and_physics 字段的 Markdown 要求】
    - 使用标准 Markdown 语法：二级标题 ##，粗体 **，斜体 *，行内代码 `，列表 -，引用 >。
    - 每个结果建议自成一段，用标题或列表区分。
    - 转义规则同上：反斜杠写双反斜杠，换行写 \\n。
    """
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
