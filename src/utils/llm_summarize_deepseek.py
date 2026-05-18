import os
from pathlib import Path
import sys
import json
import requests
from typing import Optional, Dict, Any


class LLMConfigurationError(Exception):
    """LLM 配置错误"""


class LLMAPICallError(Exception):
    """LLM API 调用失败"""


class LLMResponseParseError(Exception):
    """LLM 响应解析失败"""


class LLMContextLenghExceed(Exception):
    """发送文本可能过长了"""


class DeepSeekPaperSummarizer:
    """使用 DeepSeek API 总结学术论文"""

    def __init__(self,
        llm_api_config: Dict[str, Any],
        max_chunk_tokens: int = 1000000,
        force_chunk: bool = False
        ):
        self.llm_api_config = llm_api_config
        self.max_chunk_tokens = max_chunk_tokens
        self.force_chunk = force_chunk


    # API 调用
    def call_deepseek_api(self, article_text, system_prompt: str) -> Dict[str, Any]:
        """
        调用 DeepSeek API
        Note the thinking mode does not support temperature、top_p、presence_penalty、frequency_penalty parameters (https://api-docs.deepseek.com/zh-cn/guides/thinking_mode)
        And we use JSON Output function (https://api-docs.deepseek.com/zh-cn/guides/json_mode)
        
        Parameters
        ----------
        article_text: str
            文章文本
        system_prompt : str
            系统提示词
        llm_api_config : Dict[str, Any]
            LLM API 配置字典，需包含：
            - "api_url": API 端点
            - "api_key": 认证密钥
            - "model": 模型名称 (默认 "deepseek-v4-pro")
            - 其他可选参数如 "timeout" 等。

        Returns
        -------
        Dict[str, Any]: 
            {
                "one_sentence": str,
                "motivation_and_goal": str,
                "key_setup_and_method": str,
                "main_results_and_physics": str,
                "take_home_message": str
            }
        ---
        """
        config = self.llm_api_config
        text = article_text

        total_tokens = self._estimate_tokens(text)

        # 不强制分块且全文在单块容量内 → 一次性总结
        if self.force_chunk:
            raise ValueError("此方法未实现.")
        if total_tokens > self.max_chunk_tokens:
            raise LLMContextLenghExceed(f"估计文本长度达到 {total_tokens} tokens 可能超过 DeepSeek-V4 上下文长度限制.")

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


    @staticmethod
    def _is_chinese_char(c: str) -> bool:
        """判断字符是否为中文字符（包括 CJK 统一表意文字）"""
        cp = ord(c)
        return (
            0x4E00 <= cp <= 0x9FFF or      # CJK 统一汉字
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
        估算 token 数：
        1 个英文字符 ≈ 0.3 token
        1 个中文字符 ≈ 0.6 token
        """
        total = 0.0
        for ch in text:
            if DeepSeekPaperSummarizer._is_chinese_char(ch):
                total += 0.6
            else:
                # 英文、数字、标点等均按 0.3 token 计
                total += 0.3
        return total


if __name__ == "__main__":
    LLM_API_CONFIG_DICT = {
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key": "sk-3cc8e7b0cc4e429da42fbce0b75aa482",
        "model_name": "deepseek-v4-pro", # or deepseek-v4-pro stronger
        "thinking": "enabled",
        "timeout": 300,
    }
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
    3. 所有 LaTeX 命令在 JSON 字符串内必须用双反斜杠（如 \\(\\omega\\)，\\(\\frac{}{}\\)）。行内公式用 \\(...\\) 或 $...$，独立公式用 $$...$$。
    4. 字符串内的换行必须用转义符 \n 表示，**严禁插入真正的换行符**，以保证 JSON 解析无误。

    【main_results_and_physics 字段的 Markdown 要求】
    - 使用标准 Markdown 语法：二级标题 ##，粗体 **，斜体 *，行内代码 `，列表 -，引用 >。
    - 每个结果建议自成一段，用标题或列表区分。
    - 转义规则同上：反斜杠写双反斜杠，换行写 \n。
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
