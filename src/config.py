"""
config.py
=========
全局配置文件。

职责:
  1. 定义所有文件路径常量（数据库、日志、缓存目录等）
  2. 定义运行参数（超时时间、API 密钥等）
  3. 提供配置文件加载函数（publishers.yaml / keywords.yaml / email.yaml）
  4. 存放 LLM 系统提示词

注意事项:
  - 此文件包含敏感的 API 密钥和 Token，请勿提交到公开仓库
  - 路径均相对于项目根目录自动计算（无需手动修改 BASE_DIR）
"""

import os
from pathlib import Path

from dotenv import load_dotenv
import yaml

# 从 .env 文件加载密钥（如不存在则静默跳过）
load_dotenv()


# ==================================================================
# 路径配置
# 所有路径基于 BASE_DIR（项目根目录）自动计算
# ==================================================================

# BASE_DIR = PapersCrawler/ （项目根目录，config.py 的父目录的父目录）
BASE_DIR = Path(__file__).parent.parent

# 各级目录
DATA_DIR = BASE_DIR / "data"                   # 数据根目录
CONFIG_DIR = BASE_DIR / "configs"              # 配置文件目录

# 数据库文件路径 (SQLite)
DB_PATH = DATA_DIR / "papers.db"

# 运行日志文件路径
LOG_FILE_PATH = DATA_DIR / "PaperCrawler.log"

# 浏览器 Session 缓存目录（cloakbrowser 持久化 Session 存放处）
# 按 publisher 分子目录，如 data/session_cached/nature/
BROWSER_SESSION_DIR = DATA_DIR / "session_cached"

# RSS XML 原始文件缓存目录
RAW_RSS_DIR = DATA_DIR / "raw" / "rss"

# 抓取的网页 HTML 保存目录（调试用）
RAW_PAGE_DIR = DATA_DIR / "raw" / "page"

# 生成的报告输出目录
REPORT_DIR = DATA_DIR / "reports"
MINERU_OUTPUT_DIR = DATA_DIR / "mineru_output"   # MinerU PDF 解析输出目录


# ==================================================================
# 运行参数配置
# ==================================================================

# HTTP 请求默认超时 (秒)
REQUEST_TIMEOUT = 30

# CrossRef API 要求的联系邮箱（礼貌标识，CrossRef 强烈建议提供）
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "your_email@example.com")

# MinerU PDF 解析 API Token（从 .env 加载，未配置则跳过 E2 阶段）
MINERU_TOKEN = os.getenv("MINERU_TOKEN", "")


# ==================================================================
# DeepSeek LLM API 配置
# 用于论文相关性判断和内容总结
# ==================================================================
LLM_API_CONFIG_DICT_RELE = {
    # API 端点: DeepSeek Chat Completions 接口
    "api_url": "https://api.deepseek.com/chat/completions",
    # API 密钥: 从 .env 的 DEEPSEEK_API_KEY 加载
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    # 模型选择: deepseek-v4-flash (快速) 或 deepseek-v4-pro (更强)
    "model": "deepseek-v4-flash",
    # 思考模式: "enabled" 表示开启深度思考, "disabled" 表示关闭
    # 注意: 思考模式下不支持 temperature/top_p 等参数
    "thinking": "disabled",
    # API 调用超时 (秒)
    "timeout": 300,
}

LLM_API_CONFIG_DICT_SUMM = {
    # API 端点: DeepSeek Chat Completions 接口
    "api_url": "https://api.deepseek.com/chat/completions",
    # API 密钥: 从 .env 的 DEEPSEEK_API_KEY 加载
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    # 模型选择: deepseek-v4-flash (快速) 或 deepseek-v4-pro (更强)
    "model": "deepseek-v4-pro",
    # 思考模式: "enabled" 表示开启深度思考, "disabled" 表示关闭
    # 注意: 思考模式下不支持 temperature/top_p 等参数
    "thinking": "enabled",
    # API 调用超时 (秒)
    "timeout": 300,
}


# ==================================================================
# LLM 论文总结提示词 (System Prompt)
# 指示 DeepSeek 如何从论文文本中提取结构化总结
# ==================================================================
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
3. 反斜杠转义规则：JSON 字符串中，每个反斜杠必须双写（写两个 \\ 来得到一个 \）。
   例如，要表示 LaTeX 的行内公式开始标记（反斜杠加左括号），JSON 中必须写为两个反斜杠加左括号。
   如果只写一个反斜杠，JSON 解析器会报 "Invalid escape" 错误。
    行内公式必须用 \\(...\\) 包裹，禁止用 $...$。
    独立公式（行间公式）必须用 \\[...\\] 包裹，禁止用 $$...$$。
    **所有 LaTeX 命令必须被数学模式包裹，禁止裸写**。
4. 字符串内的换行必须用转义符 \\n 表示，**严禁插入真正的换行符**，以保证 JSON 解析无误。

【main_results_and_physics 字段的 Markdown 要求】
- 使用标准 Markdown 语法：二级标题 ##，粗体 **，斜体 *，行内代码 `，列表 -，引用 >。
- 每个结果建议自成一段，用标题或列表区分。
- 转义规则同上：反斜杠写双反斜杠，换行写 \\n。
"""


# ==================================================================
# 语义相似度初筛配置
# 使用 sentence-transformers 模型判断论文与领域的语义相似度
# 模型已本地化到 data/models/ 目录，无需网络下载
# ==================================================================

# 模型路径 (本地目录，首次需从 hf-mirror.com 下载后放入)
# HuggingFace 镜像 (国内直连 huggingface.co 可能失败)
# 改为本地模型后不再需要网络访问
SEMANTIC_MODEL_PATH = str(DATA_DIR / "models" / "all-MiniLM-L6-v2")

# 相似度阈值 (0~1)，低于此值的论文直接跳过 LLM 判断
#   0.3 推荐起点 — 滤掉明显不相关的
#   0.2 宽松 — 会放过较多无关论文进 LLM
#   0.4 严格 — 可能漏掉有用但表述不同的论文
SEMANTIC_SIMILARITY_THRESHOLD = 0.3

# ==================================================================
# 测试/调试开关
# 正式全量运行时全部设为 0 / False
# ==================================================================

# 每阶段最多处理 N 篇论文 (0 = 不限制)
MAX_PAPERS_PER_PHASE = 0
# 阶段开关（True = 跳过该阶段）
SKIP_PHASE_A = False
SKIP_PHASE_B = False
SKIP_PHASE_C = False
SKIP_PHASE_D = False
SKIP_PHASE_E = False
SKIP_PHASE_E2 = False
SKIP_PHASE_F = False
SKIP_PHASE_G = False
SKIP_PHASE_H = True  # 邮件推送 (SMTP 已配置)

# LLM 公式修复开关（实验性功能，默认关闭）
# 对 json.loads 后的纯文本字段做二次公式包裹修正。
# 先通过 needs_fix() regex 检测，仅命中时调 flash API（纯文本进/纯文本出）。
# True = 跳过，False = 启用
SKIP_FORMULA_FIX = True

# Phase C Publisher 爬虫: 同 publisher 内页面间随机延迟范围 (秒)
# 避免连续请求触发 Cloudflare 速率限制，降低 IP 信誉受损风险
PUBLISHER_PAGE_DELAY_MIN = 3
PUBLISHER_PAGE_DELAY_MAX = 5

# Phase C Publisher 爬虫: 同 publisher 内连续抓取失败 N 篇后中止该 publisher
# 避免在被 Cloudflare 拦截时持续请求，进一步损害 IP 信誉
PUBLISHER_MAX_CONSECUTIVE_FAILURES = 3

# LLM API 并发上限: Phase E/F 同时发起的 DeepSeek 请求数
# DeepSeek-V4-flash 官方限制 2500 并发，保守设 100
LLM_CONCURRENT_MAX = 100

# 过滤 Nature 新闻 (d41586 DOI)，只保留研究论文
SKIP_NATURE_NEWS = True

# Publisher 爬虫代理配置（按 publisher 标识）
# 需要代理的出版商在此配置，key 为 publisher 标识（如 "optica"），
# value 为 cloakbrowser proxy 字典（{"server": "..."})
PUBLISHER_PROXY = {
    "optica": {"server": "http://127.0.0.1:10808"},
}


# ==================================================================
# 配置文件加载函数
# ==================================================================

def load_publishers():
    """
    加载期刊数据源配置。

    从 configs/publishers.yaml 读取需要追踪的期刊列表。
    每个期刊包含: id, name, publisher, rss (RSS 地址), enabled 等字段。

    Returns:
        list[dict]: 期刊配置字典列表
    """
    path = CONFIG_DIR / "publishers.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["publishers"]


def load_keywords():
    """
    加载研究领域配置。

    从 configs/keywords.yaml 读取关键词和领域描述。
    支持三种格式:
      1. 纯列表: ["keyword1", "keyword2", ...]
         → domain_description 回退为关键词拼接
      2. 字典 {"keywords": [...], "domain_description": "..."}
         → 有 domain_description 则使用，无则回退
      3. 字典 {"keywords": [...]}
         → domain_description 回退为关键词拼接

    Returns:
        dict: {"keywords": list[str], "domain_description": str}
              文件不存在或为空时返回 {"keywords": [], "domain_description": ""}
    """
    path = CONFIG_DIR / "keywords.yaml"
    if not path.exists():
        return {"keywords": [], "domain_description": ""}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {"keywords": [], "domain_description": ""}

    # 纯列表格式 → 包装为 dict
    if isinstance(data, list):
        keywords = data
        domain_description = ""
    else:
        keywords = data.get("keywords", [])
        domain_description = data.get("domain_description", "")

    # 未提供 domain_description 时回退到关键词拼接
    if not domain_description and keywords:
        domain_description = "研究领域涵盖：" + ", ".join(keywords)

    return {"keywords": keywords, "domain_description": domain_description}


def load_email_config():
    """
    加载邮件发送配置。

    从 configs/email.yaml 读取 SMTP 服务器信息和收件人列表。
    字段: smtp_host, smtp_port, use_tls, username, password, from_addr, to_addrs

    Returns:
        dict: 邮件配置字典。文件不存在时返回空字典 {}。
    """
    path = CONFIG_DIR / "email.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ==================================================================
# MinerU Token 过期检测
# ==================================================================

def _check_mineru_token():
    """检查 MINERU_TOKEN（JWT）是否即将过期。"""
    if not MINERU_TOKEN:
        return
    import base64
    import json as _json
    import time
    import logging
    try:
        parts = MINERU_TOKEN.split(".")
        if len(parts) != 3:
            return
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        data = _json.loads(base64.b64decode(payload))
        exp = data.get("exp", 0)
        if not exp:
            return
        days_left = (exp - time.time()) / 86400
        if days_left < 30:
            logging.warning(
                f"MinerU Token 将在 {days_left:.0f} 天后过期，"
                f"请及时从 https://mineru.net 更新"
            )
        elif days_left < 7:
            logging.error(
                f"MinerU Token 将在 {days_left:.0f} 天后过期，"
                f"请立即更新，否则 MinerU 解析将失败"
            )
    except Exception:
        pass


_check_mineru_token()


# ==================================================================
# 模块自测 (直接运行 python config.py 时触发)
# ==================================================================
if __name__ == "__main__":
    publishers = load_publishers()
    print("加载的期刊配置:")
    for p in publishers:
        print(f"  {p['name']} — {p['rss']}")
