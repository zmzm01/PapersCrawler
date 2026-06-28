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

架构:
  运行时配置持有在 ``CFG`` 对象上（``types.SimpleNamespace``）。
  消费者通过 ``from config import CFG; CFG.SKIP_PHASE_A_RSS`` 获取**实时值**。
  路径常量、函数等不可变项仍为模块级变量。
  ``reload_config()`` 修改 ``CFG`` 属性，**无需 global 声明**。

注意事项:
  - 此文件包含敏感的 API 密钥和 Token，请勿提交到公开仓库
  - 路径均相对于项目根目录自动计算（无需手动修改 BASE_DIR）
  - 用户可修改 configs/settings.yaml 和 configs/prompts/*.yaml 调整运行参数和提示词
"""

import os
from pathlib import Path
from types import SimpleNamespace

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

# 邮件模板目录
EMAIL_TEMPLATE_DIR = BASE_DIR / "templates" / "email"
MINERU_OUTPUT_DIR = DATA_DIR / "mineru_output"   # MinerU PDF 解析输出目录

# Web UI journal enable/disable 覆写文件
JOURNAL_OVERRIDES_PATH = DATA_DIR / "journal_overrides.json"

# LLM Prompt 模板目录 (configs/prompts/*.yaml)
PROMPTS_DIR = CONFIG_DIR / "prompts"


# ==================================================================
# 配置文件加载函数（先定义，后续依赖它们）
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
# 运行时配置持有对象 (CFG)
#
# 所有可热加载的运行时参数均作为 CFG 属性存在。
# 消费者通过 `from config import CFG; CFG.X` 访问，始终获取当前值。
# reload_config() 修改 CFG 属性，无需 global 声明。
# ==================================================================

CFG = SimpleNamespace()

# ---------- HTTP 请求 ----------
CFG.REQUEST_TIMEOUT = 30

# ---------- CrossRef API ----------
CFG.CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "your_email@example.com")

# ---------- MinerU ----------
CFG.MINERU_TOKEN = os.getenv("MINERU_TOKEN", "")

# ---------- DeepSeek LLM API ----------
CFG.LLM_API_CONFIG_DICT_RELE = {
    "api_url": "https://api.deepseek.com/chat/completions",
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "model": "deepseek-v4-flash",
    "thinking": "disabled",
    "timeout": 300,
}
CFG.LLM_API_CONFIG_DICT_SUMM = {
    "api_url": "https://api.deepseek.com/chat/completions",
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "model": "deepseek-v4-pro",
    "thinking": "enabled",
    "timeout": 300,
}

# ---------- LLM 总结提示词 ----------
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
3. 反斜杠转义规则：JSON 字符串中，每个反斜杠必须双写（写两个 \\\\ 来得到一个 \\）。
    例如，要表示 LaTeX 的行内公式开始标记（反斜杠加左括号），JSON 中必须写为两个反斜杠加左括号。
    如果只写一个反斜杠，JSON 解析器会报 "Invalid escape" 错误。
     行内公式必须用 \\(...\\) 包裹，禁止用 $...$。
     独立公式（行间公式）必须用 \\[...\\] 包裹，禁止用 $$...$$。
    **所有 LaTeX 命令必须被数学模式包裹，禁止裸写**。
4. 禁止使用复杂 LaTeX 环境：禁止 \\begin{} / \\end{}（如 cases、aligned 等），禁止 \\\\ 换行。公式仅限 \\frac、\\sqrt、\\int、\\sum、\\partial 等基本命令及上标/下标/希腊字母。
5. 字符串内的换行必须用转义符 \\n 表示，**严禁插入真正的换行符**，以保证 JSON 解析无误。

【main_results_and_physics 字段的 Markdown 要求】
- 使用标准 Markdown 语法：二级标题 ##，粗体 **，斜体 *，行内代码 `，列表 -，引用 >。
- 每个结果建议自成一段，用标题或列表区分。
- 转义规则同上：反斜杠写双反斜杠，换行写 \\n。
"""

CFG.SUMMARIES_PROMPT = _SUMMARIES_PROMPT_FALLBACK
_loaded_prompt = load_prompt("summary")
if _loaded_prompt:
    CFG.SUMMARIES_PROMPT = _loaded_prompt

# ---------- 语义模型 ----------
CFG.SEMANTIC_MODEL_PATH = str(DATA_DIR / "models" / "bge-base-en-v1.5")

# ---------- 阶段开关 ----------
CFG.SKIP_PHASE_A_RSS = False
CFG.SKIP_PHASE_A_CR = False
CFG.SKIP_PHASE_B = False
CFG.SKIP_PHASE_C = False
CFG.SKIP_PHASE_D = False
CFG.SKIP_PHASE_E = False
CFG.SKIP_PHASE_E2 = False
CFG.SKIP_PHASE_F = False
CFG.SKIP_PHASE_G = False
CFG.SKIP_PHASE_H = True

# ---------- 流水线参数 ----------
CFG.CROSSREF_LOOKBACK_DAYS = 1
CFG.MAX_PAPERS_PER_PHASE = 0
CFG.SKIP_NATURE_NEWS = True

# ---------- 非研究论文检测 ----------
CFG.PREFETCH_NON_RESEARCH = True
CFG.POSTFETCH_NON_RESEARCH = True
CFG.NON_RESEARCH_KEYWORDS = [
    "erratum",
    "author correction:",
    "publisher correction:",
    "comment on",
    "response to",
    "publisher's note",
    "announcement:",
]

# ---------- 爬虫参数 ----------
CFG.PUBLISHER_PAGE_DELAY_MIN = 3
CFG.PUBLISHER_PAGE_DELAY_MAX = 5
CFG.PUBLISHER_MAX_CONSECUTIVE_FAILURES = 3
CFG.PUBLISHER_PROXY = {
    "optica": {"server": "http://127.0.0.1:10808"},
}

# ---------- LLM 公式修复 ----------
CFG.SKIP_FORMULA_FIX = False
CFG.FORCE_FORMULA_FIX = False

# ---------- LLM 并发 ----------
CFG.LLM_CONCURRENT_MAX = 100

# ---------- 邮件模板 ----------
CFG.EMAIL_TEMPLATE_DEFAULT = "default"
CFG.EMAIL_TEMPLATE_NAME = "default"


# ==================================================================
# settings.yaml 覆盖: 将 YAML 配置加载到 CFG 属性
# ==================================================================

def _apply_settings(settings):
    """用 settings dict 更新 CFG 属性。

    同时被模块加载和 reload_config() 调用，避免重复。

    Parameters
    ----------
    settings : dict
        由 load_settings() 返回的配置字典，可为空。
    """
    if not settings:
        return

    # LLM API 配置
    llm_cfg = settings.get("llm", {})
    rele = llm_cfg.get("relevance", {})
    CFG.LLM_API_CONFIG_DICT_RELE["model"] = rele.get("model", CFG.LLM_API_CONFIG_DICT_RELE["model"])
    CFG.LLM_API_CONFIG_DICT_RELE["thinking"] = rele.get("thinking", CFG.LLM_API_CONFIG_DICT_RELE["thinking"])
    CFG.LLM_API_CONFIG_DICT_RELE["timeout"] = rele.get("timeout", CFG.LLM_API_CONFIG_DICT_RELE["timeout"])
    summ = llm_cfg.get("summary", {})
    CFG.LLM_API_CONFIG_DICT_SUMM["model"] = summ.get("model", CFG.LLM_API_CONFIG_DICT_SUMM["model"])
    CFG.LLM_API_CONFIG_DICT_SUMM["thinking"] = summ.get("thinking", CFG.LLM_API_CONFIG_DICT_SUMM["thinking"])
    CFG.LLM_API_CONFIG_DICT_SUMM["timeout"] = summ.get("timeout", CFG.LLM_API_CONFIG_DICT_SUMM["timeout"])
    CFG.LLM_CONCURRENT_MAX = llm_cfg.get("concurrent_max", CFG.LLM_CONCURRENT_MAX)

    # 总结提示词
    _loaded = load_prompt("summary")
    if _loaded:
        CFG.SUMMARIES_PROMPT = _loaded

    # 阶段开关
    skip = settings.get("skip_phases", {})
    CFG.SKIP_PHASE_A_RSS = skip.get("A_RSS", CFG.SKIP_PHASE_A_RSS)
    CFG.SKIP_PHASE_A_CR = skip.get("A_CR", CFG.SKIP_PHASE_A_CR)
    CFG.SKIP_PHASE_B = skip.get("B", CFG.SKIP_PHASE_B)
    CFG.SKIP_PHASE_C = skip.get("C", CFG.SKIP_PHASE_C)
    CFG.SKIP_PHASE_D = skip.get("D", CFG.SKIP_PHASE_D)
    CFG.SKIP_PHASE_E = skip.get("E", CFG.SKIP_PHASE_E)
    CFG.SKIP_PHASE_E2 = skip.get("E2", CFG.SKIP_PHASE_E2)
    CFG.SKIP_PHASE_F = skip.get("F", CFG.SKIP_PHASE_F)
    CFG.SKIP_PHASE_G = skip.get("G", CFG.SKIP_PHASE_G)
    CFG.SKIP_PHASE_H = skip.get("H", CFG.SKIP_PHASE_H)

    # 流水线参数
    pp = settings.get("pipeline", {})
    CFG.CROSSREF_LOOKBACK_DAYS = pp.get("crossref_lookback_days", CFG.CROSSREF_LOOKBACK_DAYS)
    CFG.MAX_PAPERS_PER_PHASE = pp.get("max_papers_per_phase", CFG.MAX_PAPERS_PER_PHASE)
    CFG.SKIP_NATURE_NEWS = pp.get("skip_nature_news", CFG.SKIP_NATURE_NEWS)
    CFG.PREFETCH_NON_RESEARCH = pp.get("prefetch_non_research", CFG.PREFETCH_NON_RESEARCH)
    CFG.POSTFETCH_NON_RESEARCH = pp.get("postfetch_non_research", CFG.POSTFETCH_NON_RESEARCH)
    CFG.NON_RESEARCH_KEYWORDS = pp.get("non_research_keywords", CFG.NON_RESEARCH_KEYWORDS)

    # 爬虫参数
    ps = settings.get("publisher", {})
    CFG.PUBLISHER_PAGE_DELAY_MIN = ps.get("page_delay_min", CFG.PUBLISHER_PAGE_DELAY_MIN)
    CFG.PUBLISHER_PAGE_DELAY_MAX = ps.get("page_delay_max", CFG.PUBLISHER_PAGE_DELAY_MAX)
    CFG.PUBLISHER_MAX_CONSECUTIVE_FAILURES = ps.get("max_consecutive_failures", CFG.PUBLISHER_MAX_CONSECUTIVE_FAILURES)
    cfg_proxy = ps.get("proxy", {})
    if cfg_proxy:
        CFG.PUBLISHER_PROXY = cfg_proxy

    # 公式修复
    ff = settings.get("formula_fix", {})
    CFG.SKIP_FORMULA_FIX = ff.get("skip", CFG.SKIP_FORMULA_FIX)
    CFG.FORCE_FORMULA_FIX = ff.get("force", CFG.FORCE_FORMULA_FIX)

    # 语义模型路径
    sem = settings.get("semantic", {})
    sem_path = sem.get("model_path")
    if sem_path:
        CFG.SEMANTIC_MODEL_PATH = str(DATA_DIR / sem_path)

    # 邮件模板配置
    email_cfg = settings.get("email", {})
    email_default = email_cfg.get("template", "default")
    CFG.EMAIL_TEMPLATE_DEFAULT = email_default
    email_override = DATA_DIR / "email_template_override.txt"
    if email_override.exists():
        CFG.EMAIL_TEMPLATE_NAME = email_override.read_text(encoding="utf-8").strip()
    else:
        CFG.EMAIL_TEMPLATE_NAME = email_default


# 模块加载时执行初始覆盖
_SOURCE_SETTINGS = load_settings()
if _SOURCE_SETTINGS:
    _apply_settings(_SOURCE_SETTINGS)


# ==================================================================
# 配置文件加载函数
# ==================================================================

def load_publishers():
    """
    加载期刊数据源配置。

    从 configs/publishers.yaml 读取需要追踪的期刊列表。
    每个期刊包含: id, name, publisher, rss (RSS 地址), enabled 等字段。

    Returns:
        list[dict]: 期刊配置字典列表。文件不存在或解析失败时返回空列表。
    """
    path = CONFIG_DIR / "publishers.yaml"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("publishers", []) if data else []
    except Exception:
        return []


def load_keywords():
    """
    加载研究领域配置。

    从 configs/keywords.yaml 读取领域定义和关键词配置。
    返回结构化字典，包含 scope_definition（各子领域描述+关键词）、
    irrelevant_fields（不相关领域定义）和 sub_domains_embedding（Phase D 用浓缩英文段落）。

    Returns:
        dict: {
            "scope_definition": dict[str, {"description": str, "topics": list[str]}],
            "context_gates": list[dict],
            "irrelevant_fields": {"description": str, "topics": list[str]},
            "sub_domains_embedding": dict[str, str],
        }
              文件不存在或为空时返回全空结构。
    """
    path = CONFIG_DIR / "keywords.yaml"
    empty = {
        "scope_definition": {},
        "context_gates": [],
        "irrelevant_fields": {"description": "", "topics": []},
        "sub_domains_embedding": {},
    }
    if not path.exists():
        return empty
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return empty
    if data is None:
        return empty
    return {
        "scope_definition": data.get("scope_definition", {}),
        "context_gates": data.get("context_gates", []),
        "irrelevant_fields": data.get("irrelevant_fields", {"description": "", "topics": []}),
        "sub_domains_embedding": data.get("sub_domains_embedding", {}),
    }


def build_scope_block(scope_definition, context_gates=None, irrelevant_fields=None):
    """将 scope_definition 格式化为 LLM prompt 中可用的文本块。

    Parameters
    ----------
    scope_definition : dict
        key 为子领域标识，value 为 {"description": str, "topics": list[str]}
    context_gates : list[dict], optional
        全局语境消歧规则，每个元素含 term, description,
        relevant_contexts, irrelevant_contexts。
    irrelevant_fields : dict, optional
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

    # 1. Global context gates (word sense disambiguation)
    gates = context_gates or []
    if gates:
        lines.append("# Global Context Rules (apply to all sub-domains)")
        lines.append("")
        for gate in gates:
            term = gate.get("term", "")
            desc = gate.get("description", "").strip()
            relevant = gate.get("relevant_contexts", [])
            irrelevant = gate.get("irrelevant_contexts", [])
            lines.append(f"## Term: \"{term}\"")
            if desc:
                lines.append(desc)
                lines.append("")
            if relevant:
                lines.append("Relevant contexts:")
                for ctx in relevant:
                    lines.append(f"  - {ctx}")
                lines.append("")
            if irrelevant:
                lines.append("Irrelevant contexts:")
                for ctx in irrelevant:
                    lines.append(f"  - {ctx}")
                lines.append("")
        lines.append("")

    # 2. Per sub-domain iteration
    for key, section in scope_definition.items():
        lines.append(f"# Sub-Domain: {key}")

        hint = section.get("priority_hint")
        if hint:
            lines.append(f"Typical relevance level: {hint}")
            lines.append("")

        lines.append(section.get("description", "").strip())
        lines.append("")
        lines.append("涉及方向包括：")
        for t in section.get("topics", []):
            lines.append(f"- {t}")
        lines.append("")

    # 3. Irrelevant fields
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
    if not CFG.MINERU_TOKEN:
        return
    import base64
    import json as _json
    import time
    import logging
    try:
        parts = CFG.MINERU_TOKEN.split(".")
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


def reload_config():
    """重新加载 settings.yaml 并刷新 CFG 上全部运行时配置变量。

    调用后 ``CFG`` 的属性（SKIP_PHASE_*、LLM_API_*、SUMMARIES_PROMPT 等）
    将更新为 YAML 文件中的最新值。**无需重启进程。**
    """
    _settings = load_settings()
    if _settings:
        _apply_settings(_settings)


_check_mineru_token()


# ==================================================================
# 模块自测 (直接运行 python config.py 时触发)
# ==================================================================
if __name__ == "__main__":
    publishers = load_publishers()
    print("加载的期刊配置:")
    for p in publishers:
        print(f"  {p['name']} — {p['rss']}")
