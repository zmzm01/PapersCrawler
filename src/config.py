"""
config.py
=========
全局配置入口。

职责:
  1. 定义所有文件路径常量（数据库、日志、缓存目录等）
  2. 提供配置文件加载函数（settings.yaml / prompts / publishers.yaml / keywords.yaml / load_email_config）
  3. 从 configs/settings.yaml 加载运行参数（阶段开关、LLM API 配置、爬虫参数等）
  4. 从 configs/prompts/*.yaml 加载 LLM 系统提示词，失败时回退到内嵌后备值
  5. 从 .env 加载敏感信息（API 密钥、SMTP 密码）

注意事项:
  - 此文件包含敏感的 API 密钥和 Token，请勿提交到公开仓库
  - 路径均相对于项目根目录自动计算（无需手动修改 BASE_DIR）
  - 用户可修改 configs/settings.yaml 和 configs/prompts/*.yaml 调整运行参数和提示词
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
REPORT_DIR = DATA_DIR / "reports"                # 报告根目录
AUTO_REPORT_DIR = DATA_DIR / "reports" / "auto"  # 自动日报目录 (Phase G 自动)
USER_REPORT_DIR = DATA_DIR / "reports" / "user"  # 用户自选报告目录 (Web UI)
MINERU_OUTPUT_DIR = DATA_DIR / "mineru_output"   # MinerU PDF 解析输出目录

# LLM Prompt 模板目录 (configs/prompts/*.yaml)
PROMPTS_DIR = CONFIG_DIR / "prompts"


# ==================================================================
# 配置文件加载函数（先定义，后续常量依赖它们）
# ==================================================================

def load_settings():
    """加载 configs/settings.yaml 运行参数配置。

    返回 dict，文件不存在或格式异常时返回 None。
    """
    path = CONFIG_DIR / "settings.yaml"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def load_prompt(name):
    """从 configs/prompts/{name}.yaml 加载 LLM 系统提示词。

    Parameters
    ----------
    name : str
        提示词名称（如 'summary'、'relevance'、'fix'），对应文件名。

    Returns
    -------
    str
        提示词文本。文件不存在或格式异常时返回 None。
    """
    path = PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            return None
        return data.get("system_prompt", "")
    except Exception:
        return None


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
# 模型/思考模式/超时从 settings.yaml 读取，API Key 从 .env 读取
# ==================================================================

_SETTINGS = load_settings() or {}

_llm_cfg = _SETTINGS.get("llm", {})

LLM_API_CONFIG_DICT_RELE = {
    "api_url": "https://api.deepseek.com/chat/completions",
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "model": _llm_cfg.get("relevance", {}).get("model", "deepseek-v4-flash"),
    "thinking": _llm_cfg.get("relevance", {}).get("thinking", "disabled"),
    "timeout": _llm_cfg.get("relevance", {}).get("timeout", 300),
}

LLM_API_CONFIG_DICT_SUMM = {
    "api_url": "https://api.deepseek.com/chat/completions",
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "model": _llm_cfg.get("summary", {}).get("model", "deepseek-v4-pro"),
    "thinking": _llm_cfg.get("summary", {}).get("thinking", "enabled"),
    "timeout": _llm_cfg.get("summary", {}).get("timeout", 300),
}


# ==================================================================
# LLM 论文总结提示词 (System Prompt)
# 指示 DeepSeek 如何从论文文本中提取结构化总结
# 默认从 configs/prompts/summary.yaml 加载，不存在时使用内嵌后备值
# ==================================================================

_SUMMARIES_PROMPT_FALLBACK = """你是一位专业的理论/实验物理学家，尤其擅长激光等离子体物理。请根据提供的论文全文，生成一个 JSON 格式的结构化总结。

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
    行内公式必须用 \(...\) 包裹，禁止用 $...$。
    独立公式（行间公式）必须用 \[...\] 包裹，禁止用 $$...$$。
    **所有 LaTeX 命令必须被数学模式包裹，禁止裸写**。
4. 禁止使用复杂 LaTeX 环境：禁止 \begin{} / \end{}（如 cases、aligned 等），禁止 \\ 换行。公式仅限 \frac、\sqrt、\int、\sum、\partial 等基本命令及上标/下标/希腊字母。
5. 字符串内的换行必须用转义符 \n 表示，**严禁插入真正的换行符**，以保证 JSON 解析无误。

【main_results_and_physics 字段的 Markdown 要求】
- 使用标准 Markdown 语法：二级标题 ##，粗体 **，斜体 *，行内代码 `，列表 -，引用 >。
- 每个结果建议自成一段，用标题或列表区分。
- 转义规则同上：反斜杠写双反斜杠，换行写 \n。
"""

SUMMARIES_PROMPT = _SUMMARIES_PROMPT_FALLBACK

# 尝试从 YAML 文件覆盖 SUMMARIES_PROMPT
_loaded_prompt = load_prompt("summary")
if _loaded_prompt:
    SUMMARIES_PROMPT = _loaded_prompt


# ==================================================================
# 语义相似度参考排序配置（Phase D）
# 使用 sentence-transformers 模型计算论文与子领域的余弦相似度。
# 此分数仅作为 WebUI Papers 页面的排序参考，不参与流水线过滤。
# 模型已本地化到 data/models/ 目录，无需网络下载
# ==================================================================

# 模型路径 (本地目录，首次需从 HuggingFace 下载后放入)
SEMANTIC_MODEL_PATH = str(DATA_DIR / "models" / "bge-base-en-v1.5")

# ==================================================================
# 测试/调试开关
# 正式全量运行时全部设为 0 / False
# ==================================================================

# 每阶段最多处理 N 篇论文 (0 = 不限制)
MAX_PAPERS_PER_PHASE = 0
# 阶段开关（True = 跳过该阶段）
SKIP_PHASE_A = False       # 保持兼容: 同时控制 A-RSS + A-CR (不等同于 SKIP_PHASE_A_RSS AND SKIP_PHASE_A_CR)
SKIP_PHASE_A_RSS = False   # RSS 发现路径独立开关
SKIP_PHASE_A_CR = False    # CrossRef 发现路径独立开关
SKIP_PHASE_B = False
SKIP_PHASE_C = False
SKIP_PHASE_D = False  # 启用，计算语义相似度供 WebUI Papers 排序（不参与过滤）
SKIP_PHASE_E = False
SKIP_PHASE_E2 = False
SKIP_PHASE_F = False
SKIP_PHASE_G = False
SKIP_PHASE_H = True  # 邮件推送 (SMTP 已配置)

# Phase A CrossRef 发现: 回溯天数（每日增量模式下取今天往前 N 天）
CROSSREF_LOOKBACK_DAYS = 1

# LLM 公式修复开关（实验性功能，默认关闭）
# 对 json.loads 后的纯文本字段做二次公式包裹修正。
# 先通过 needs_fix() regex 检测，仅命中时调 flash API（纯文本进/纯文本出）。
# True = 跳过，False = 启用
SKIP_FORMULA_FIX = False

# 强制公式修复开关
# 为 True 时跳过 needs_fix() 正则检测，所有字段都送 LLM 修复。
# 适用于正则无法覆盖的边缘情况（如裸上下标 E = m c^2 等）。
# True = 跳过检测直接修复，False = 仅修复正则命中的字段
FORCE_FORMULA_FIX = False

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
# settings.yaml 覆盖: 用 YAML 文件中的值覆写上述 Python 默认值
# ==================================================================

_skip = _SETTINGS.get("skip_phases", {})
SKIP_PHASE_A_RSS = _skip.get("A_RSS", SKIP_PHASE_A_RSS)
SKIP_PHASE_A_CR = _skip.get("A_CR", SKIP_PHASE_A_CR)
SKIP_PHASE_B = _skip.get("B", SKIP_PHASE_B)
SKIP_PHASE_C = _skip.get("C", SKIP_PHASE_C)
SKIP_PHASE_D = _skip.get("D", SKIP_PHASE_D)
SKIP_PHASE_E = _skip.get("E", SKIP_PHASE_E)
SKIP_PHASE_E2 = _skip.get("E2", SKIP_PHASE_E2)
SKIP_PHASE_F = _skip.get("F", SKIP_PHASE_F)
SKIP_PHASE_G = _skip.get("G", SKIP_PHASE_G)
SKIP_PHASE_H = _skip.get("H", SKIP_PHASE_H)

_pp = _SETTINGS.get("pipeline", {})
CROSSREF_LOOKBACK_DAYS = _pp.get("crossref_lookback_days", CROSSREF_LOOKBACK_DAYS)
MAX_PAPERS_PER_PHASE = _pp.get("max_papers_per_phase", MAX_PAPERS_PER_PHASE)
SKIP_NATURE_NEWS = _pp.get("skip_nature_news", SKIP_NATURE_NEWS)

_ps = _SETTINGS.get("publisher", {})
PUBLISHER_PAGE_DELAY_MIN = _ps.get("page_delay_min", PUBLISHER_PAGE_DELAY_MIN)
PUBLISHER_PAGE_DELAY_MAX = _ps.get("page_delay_max", PUBLISHER_PAGE_DELAY_MAX)
PUBLISHER_MAX_CONSECUTIVE_FAILURES = _ps.get("max_consecutive_failures", PUBLISHER_MAX_CONSECUTIVE_FAILURES)
_cfg_proxy = _ps.get("proxy", {})
if _cfg_proxy:
    PUBLISHER_PROXY = _cfg_proxy

_ff = _SETTINGS.get("formula_fix", {})
SKIP_FORMULA_FIX = _ff.get("skip", SKIP_FORMULA_FIX)
FORCE_FORMULA_FIX = _ff.get("force", FORCE_FORMULA_FIX)

LLM_CONCURRENT_MAX = _llm_cfg.get("concurrent_max", LLM_CONCURRENT_MAX)

_sem = _SETTINGS.get("semantic", {})
_sem_path = _sem.get("model_path")
if _sem_path:
    SEMANTIC_MODEL_PATH = str(DATA_DIR / _sem_path)

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

    从 configs/keywords.yaml 读取领域定义和关键词配置。
    返回结构化字典，包含 scope_definition（各子领域描述+关键词）、
    irrelevant_fields（不相关领域定义）和 sub_domains_embedding（Phase D 用浓缩英文段落）。

    Returns:
        dict: {
            "scope_definition": dict[str, {"description": str, "topics": list[str]}],
            "irrelevant_fields": {"description": str, "topics": list[str]},
            "sub_domains_embedding": dict[str, str],
        }
              文件不存在或为空时返回全空结构。
    """
    path = CONFIG_DIR / "keywords.yaml"
    empty = {
        "scope_definition": {},
        "irrelevant_fields": {"description": "", "topics": []},
        "sub_domains_embedding": {},
    }
    if not path.exists():
        return empty
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return empty
    return {
        "scope_definition": data.get("scope_definition", {}),
        "irrelevant_fields": data.get("irrelevant_fields", {"description": "", "topics": []}),
        "sub_domains_embedding": data.get("sub_domains_embedding", {}),
    }


def build_scope_block(scope_definition, irrelevant_fields):
    """将 scope_definition 格式化为 LLM prompt 中可用的文本块。

    Parameters
    ----------
    scope_definition : dict
        key 为子领域标识，value 为 {"description": str, "topics": list[str]}
    irrelevant_fields : dict
        {"description": str, "topics": list[str]}

    Returns
    -------
    str
        格式化后的文本块，可直接嵌入 LLM prompt。
    """
    lines = [
        "# Research Scope Definition",
        "",
    ]
    for key, section in scope_definition.items():
        lines.append(f"# Sub-Domain: {key}")
        lines.append(section.get("description", "").strip())
        lines.append("")
        lines.append("涉及方向包括：")
        for t in section.get("topics", []):
            lines.append(f"- {t}")
        lines.append("")

    irr = irrelevant_fields or {}
    irr_desc = irr.get("description", "").strip()
    if irr_desc or irr.get("topics"):
        lines.append("# Irrelevant Fields")
        if irr_desc:
            lines.append(irr_desc)
            lines.append("")
        for t in irr.get("topics", []):
            lines.append(f"- {t}")
        lines.append("")

    return "\n".join(lines)


def load_email_config():
    """
    加载邮件发送配置。

    从 .env 环境变量读取 SMTP 服务器信息和收件人列表。
    字段: smtp_host, smtp_port, use_tls, username, password, from_addr, to_addrs

    .env 配置项:
        SMTP_HOST      — SMTP 服务器地址
        SMTP_PORT      — 端口 (TLS=587, SSL=465)
        SMTP_USE_TLS   — true=STARTTLS, false=SSL 直连
        SMTP_USERNAME  — 登录用户名
        SMTP_PASSWORD  — 授权码
        SMTP_FROM_ADDR — 发件人地址
        SMTP_TO_ADDRS  — 收件人列表（逗号分隔）

    Returns:
        dict: 邮件配置字典。必要字段缺失时返回空字典 {}。
    """
    host = os.getenv("SMTP_HOST", "")
    port_str = os.getenv("SMTP_PORT", "")
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM_ADDR", "")
    to_addrs_str = os.getenv("SMTP_TO_ADDRS", "")

    if not host or not port_str or not username or not password or not from_addr:
        return {}

    try:
        port = int(port_str)
    except ValueError:
        return {}

    use_tls_str = os.getenv("SMTP_USE_TLS", "true")
    use_tls = use_tls_str.strip().lower() in ("true", "1", "yes")

    to_addrs = [addr.strip() for addr in to_addrs_str.split(",") if addr.strip()]

    return {
        "smtp_host": host,
        "smtp_port": port,
        "use_tls": use_tls,
        "username": username,
        "password": password,
        "from_addr": from_addr,
        "to_addrs": to_addrs,
    }


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
        data = _json.loads(base64.urlsafe_b64decode(payload + "=="))
        exp = data.get("exp", 0)
        if not exp:
            return
        days_left = (exp - time.time()) / 86400
        if days_left < 7:
            logging.error(
                f"MinerU Token 将在 {days_left:.0f} 天后过期，"
                f"请立即更新，否则 MinerU 解析将失败"
            )
        elif days_left < 30:
            logging.warning(
                f"MinerU Token 将在 {days_left:.0f} 天后过期，"
                f"请及时从 https://mineru.net 更新"
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
