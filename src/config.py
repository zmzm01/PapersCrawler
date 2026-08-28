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

from common import (
    LLM_PROTOCOL_OPENAI_CHAT,
    build_llm_endpoint_url,
)
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
LOG_DIR = DATA_DIR / "logs"
# Compatibility path for external callers. Entry points use logging_config and
# write date-separated files under LOG_DIR instead of this aggregate filename.
LOG_FILE_PATH = LOG_DIR / "PaperCrawler.log"

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
# 报告模板目录（Markdown/HTML，paper_report_generator.py 加载）
REPORT_TEMPLATE_DIR = BASE_DIR / "templates" / "report"
PUBLIC_EXPORT_DIR = Path(
    os.getenv("PUBLIC_REPORT_EXPORT_DIR", str(BASE_DIR.parent / "MySite" / ".generated" / "reports"))
)
MINERU_OUTPUT_DIR = DATA_DIR / "mineru_output"   # MinerU PDF 解析输出目录

# Web UI journal enable/disable 覆写文件
JOURNAL_OVERRIDES_PATH = DATA_DIR / "journal_overrides.json"

# 流水线运行时状态目录（跨运行持久化的小型 JSON 状态）
STATE_DIR = DATA_DIR / "state"

# Phase A-CR 上次成功运行时间戳记录文件
# 用于「智能回溯」：故障后自动按缺口补拉（封顶 CROSSREF_LOOKBACK_DAYS_MAX）
LAST_RUN_PATH = STATE_DIR / "last_run.json"

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

# ---------- ntfy final run summary ----------
# The endpoint, topic, and token remain environment-only. The topic acts like
# a password on public ntfy servers and must not be placed in YAML.
CFG.NTFY_BASE_URL = os.getenv("NTFY_BASE_URL", "https://ntfy.sh")
CFG.NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
CFG.NTFY_TOKEN = os.getenv("NTFY_TOKEN", "")
CFG.NTFY_ENABLED = False
CFG.NTFY_TIMEOUT = 10
CFG.NTFY_TITLE = "PapersCrawler 运行汇总"
CFG.NTFY_PRIORITY = "default"

# ---------- Multi-protocol LLM API ----------
CFG.LLM_BASE_URL = "https://api.deepseek.com"
CFG.LLM_API_CONFIG_DICT_RELE = {
    "api_url": build_llm_endpoint_url(CFG.LLM_BASE_URL),
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "model": "deepseek-v4-flash",
    "protocol": LLM_PROTOCOL_OPENAI_CHAT,
    "thinking": "disabled",
    "timeout": 300,
    "retry_max_attempts": 3,
    "retry_backoff_max_seconds": 30,
}
CFG.LLM_API_CONFIG_DICT_FULLTEXT = {
    "api_url": build_llm_endpoint_url(CFG.LLM_BASE_URL),
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "model": "deepseek-v4-pro",
    "protocol": LLM_PROTOCOL_OPENAI_CHAT,
    "thinking": "enabled",
    "timeout": 300,
    "retry_max_attempts": 3,
    "retry_backoff_max_seconds": 30,
}
CFG.LLM_API_CONFIG_DICT_SUMM = {
    "api_url": build_llm_endpoint_url(CFG.LLM_BASE_URL),
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "model": "deepseek-v4-pro",
    "protocol": LLM_PROTOCOL_OPENAI_CHAT,
    "thinking": "enabled",
    "timeout": 300,
    "retry_max_attempts": 3,
    "retry_backoff_max_seconds": 30,
}
CFG.LLM_API_CONFIG_DICT_FORMULA = {
    "api_url": build_llm_endpoint_url(CFG.LLM_BASE_URL),
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "model": "deepseek-v4-flash",
    "protocol": LLM_PROTOCOL_OPENAI_CHAT,
    "thinking": "disabled",
    "max_tokens": 4096,
    "timeout": 120,
    "retry_max_attempts": 3,
    "retry_backoff_max_seconds": 30,
}

# ---------- LLM 总结提示词 ----------
_SUMMARIES_PROMPT_FALLBACK = """你是一位专业的理论/实验物理学家，尤其擅长激光等离子体物理。请根据提供的论文全文，生成一个 JSON 格式的结构化总结。

【输出格式】
严格输出合法 JSON 对象，不包含任何额外文字或注释。JSON 对象的格式与字段内容要求如下：

{
  "schema_version": 3,
  "one_sentence": "用一句话说明：本文采用什么方法/装置，研究了什么物理问题，得到了什么核心结论",
  "motivation_and_goal": {"background": "研究背景", "research_gap": "研究缺口或争议", "objective": "本文目标"},
  "key_setup_and_method": {"study_type": "experiment、simulation、theory、review 或 mixed 之一", "method": "方法", "setup_and_parameters": "装置与关键参数", "analysis_or_model": "分析方法或模型", "key_equations": "关键公式及符号含义"},
  "main_results_and_physics": [{"key": "result_1", "title": "结果短标题", "finding": "结果", "evidence": "证据", "physical_interpretation": "物理内涵"}],
  "limitations": [{"key": "limitation_1", "limitation": "明确局限", "impact": "对结论或应用的影响", "basis": "explicit 或 inferred"}],
  "take_home_message": {"contribution": "主要贡献", "implication": "物理启示或应用意义"}
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
6. `main_results_and_physics` 必须是数组，每个元素必须有唯一的 `key`，不要输出 Markdown 标题或把多个结果合成一段话。
7. 所有分析内容必须放入示例中的固定 key；信息未提供时写 "未提供"，不要编造。
8. `limitations` 只输出正文能够支持的、有明确含义的局限；没有足够依据时输出空数组 `[]`。
   禁止把 "未提供"、"暂无" 或 "无" 作为 `limitation` 的内容；`basis` 仅用于机器结构化，
   必须是 `explicit` 或 `inferred`。
9. `finding`、`evidence` 和 `physical_interpretation` 分别表示结果、证据和物理解释；没有具体数值时写 "未提供"，不要目测图像或自行补齐。
10. `study_type` 是机器用元数据，必须标记 experiment、simulation、theory、review 或 mixed
    之一。区分实验、模拟、理论推导和作者展望，不要把背景或未来工作写成本文结果。
11. `key_setup_and_method` 必须分别填写 `method`、`setup_and_parameters` 和
    `analysis_or_model`；只要正文包含方法信息，就不能把这些字段全部写成 "未提供"。

【结构化输出要求】
- 结果数组通常输出 2-4 个元素；每个元素分别填写 finding、evidence、physical_interpretation。
- 所有 key 使用稳定的英文 snake_case，便于报告渲染、导出和后续程序分析。
"""

CFG.SUMMARIES_PROMPT = _SUMMARIES_PROMPT_FALLBACK
_loaded_prompt = load_prompt("summary")
if _loaded_prompt:
    CFG.SUMMARIES_PROMPT = _loaded_prompt

# ---------- 阶段开关 ----------
CFG.SKIP_PHASE_A_RSS = False
CFG.SKIP_PHASE_A_CR = False
CFG.SKIP_PHASE_B = False
CFG.SKIP_PHASE_C = False
CFG.SKIP_PHASE_E = False
CFG.SKIP_PHASE_E2 = False
CFG.SKIP_PHASE_E3 = False
CFG.SKIP_PHASE_F = False
CFG.SKIP_PHASE_G = False
CFG.SKIP_PHASE_H = True
CFG.LLM_CONCURRENT_MAX = 20
CFG.FORMULA_FIX_CONCURRENT_MAX = 10
CFG.LLM_CIRCUIT_BREAKER_THRESHOLD = 5

# ---------- 流水线参数 ----------
# 日常回溯天数（默认 1 天，与「每日增量」语义一致）
CFG.CROSSREF_LOOKBACK_DAYS = 1
# 智能回溯硬上限：故障补漏时实际回溯不超过此值
# 实际回溯 = min(CROSSREF_LOOKBACK_DAYS, today - last_successful_run)
CFG.CROSSREF_LOOKBACK_DAYS_MAX = 7
CFG.MAX_PAPERS_PER_PHASE = 0
CFG.SKIP_NATURE_NEWS = True

# ---------- 非研究论文检测 ----------
CFG.PREFETCH_NON_RESEARCH = True
CFG.POSTFETCH_NON_RESEARCH = True
CFG.GENERATE_EXPLAINED_HTML = True
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
# Cloudflare challenge 页处理：检测到「请稍候…」等挑战页后，reload 的次数上限
# （reload 时持久化 context 中已写入 cf_clearance cookie，可直接放行）。
CFG.PUBLISHER_CHALLENGE_MAX_RELOADS = 2
# reload 后等待时长（毫秒），用于等 Cloudflare 完成验证并返回真实页面。
CFG.PUBLISHER_CHALLENGE_RELOAD_WAIT_MS = 45000
CFG.PUBLISHER_PROXY = {
    "optica": {"server": "http://127.0.0.1:10808"},
}
CFG.PUBLISHER_FALLBACK_PROXY_URL = ""

# ---------- LLM 公式修复 ----------
CFG.SKIP_FORMULA_FIX = False
CFG.FORCE_FORMULA_FIX = False

# ---------- 邮件模板 ----------
CFG.EMAIL_TEMPLATE_DEFAULT = "default"
CFG.EMAIL_TEMPLATE_NAME = "default"
CFG.FULLTEXT_DOWNLOAD_DAILY_MAX = 3
CFG.FULLTEXT_DOWNLOAD_PUBLISHER_MAX = 2
CFG.FULLTEXT_DOWNLOAD_DELAY_MIN = 30
CFG.FULLTEXT_DOWNLOAD_DELAY_MAX = 90
CFG.FULLTEXT_RELEVANCE_MAX_CHARS = 60000


# ==================================================================
# settings.yaml 覆盖: 将 YAML 配置加载到 CFG 属性
# ==================================================================

def _apply_llm_role_settings(config_dict, role_settings, base_url, default_protocol):
    """Apply shared LLM settings for one pipeline role.

    Parameters
    ----------
    config_dict : dict
        Mutable runtime configuration for a pipeline role.
    role_settings : dict
        YAML settings for that role.
    base_url : str
        Common provider base URL.
    default_protocol : str
        Protocol used when the role does not override it.
    """
    protocol = role_settings.get("protocol", default_protocol)
    config_dict["protocol"] = protocol
    config_dict["api_url"] = build_llm_endpoint_url(base_url, protocol)
    for key in (
        "model",
        "thinking",
        "reasoning_effort",
        "timeout",
        "max_tokens",
        "max_output_tokens",
    ):
        if key in role_settings:
            config_dict[key] = role_settings[key]

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
    base_url = llm_cfg.get("base_url", CFG.LLM_BASE_URL)
    CFG.LLM_BASE_URL = str(base_url).strip()
    default_protocol = llm_cfg.get("protocol", LLM_PROTOCOL_OPENAI_CHAT)
    rele = llm_cfg.get("relevance", {})
    summ = llm_cfg.get("summary", {})
    fulltext = llm_cfg.get("fulltext_relevance", {})
    formula_cfg = settings.get("formula_fix", {})
    formula_llm = formula_cfg.get("llm", {})
    _apply_llm_role_settings(
        CFG.LLM_API_CONFIG_DICT_RELE, rele, CFG.LLM_BASE_URL, default_protocol,
    )
    _apply_llm_role_settings(
        CFG.LLM_API_CONFIG_DICT_SUMM, summ, CFG.LLM_BASE_URL, default_protocol,
    )
    _apply_llm_role_settings(
        CFG.LLM_API_CONFIG_DICT_FULLTEXT,
        fulltext,
        CFG.LLM_BASE_URL,
        default_protocol,
    )
    formula_base_url = formula_llm.get("base_url", CFG.LLM_BASE_URL)
    _apply_llm_role_settings(
        CFG.LLM_API_CONFIG_DICT_FORMULA,
        formula_llm,
        str(formula_base_url).strip(),
        default_protocol,
    )
    CFG.FULLTEXT_RELEVANCE_MAX_CHARS = fulltext.get(
        "evidence_max_chars", CFG.FULLTEXT_RELEVANCE_MAX_CHARS,
    )
    CFG.LLM_CONCURRENT_MAX = llm_cfg.get("concurrent_max", CFG.LLM_CONCURRENT_MAX)
    retry_cfg = llm_cfg.get("retry", {})
    for config_dict in (CFG.LLM_API_CONFIG_DICT_RELE,
                        CFG.LLM_API_CONFIG_DICT_SUMM,
                        CFG.LLM_API_CONFIG_DICT_FULLTEXT,
                        CFG.LLM_API_CONFIG_DICT_FORMULA):
        config_dict["retry_max_attempts"] = retry_cfg.get(
            "max_attempts", config_dict["retry_max_attempts"],
        )
        config_dict["retry_backoff_max_seconds"] = retry_cfg.get(
            "backoff_max_seconds", config_dict["retry_backoff_max_seconds"],
        )
    CFG.LLM_CIRCUIT_BREAKER_THRESHOLD = llm_cfg.get(
        "circuit_breaker_threshold", CFG.LLM_CIRCUIT_BREAKER_THRESHOLD,
    )

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
    CFG.SKIP_PHASE_E = skip.get("E", CFG.SKIP_PHASE_E)
    CFG.SKIP_PHASE_E2 = skip.get("E2", CFG.SKIP_PHASE_E2)
    CFG.SKIP_PHASE_E3 = skip.get("E3", CFG.SKIP_PHASE_E3)
    CFG.SKIP_PHASE_F = skip.get("F", CFG.SKIP_PHASE_F)
    CFG.SKIP_PHASE_G = skip.get("G", CFG.SKIP_PHASE_G)
    CFG.SKIP_PHASE_H = skip.get("H", CFG.SKIP_PHASE_H)

    # ntfy only publishes the one final summary assembled by the CLI.
    ntfy_cfg = settings.get("ntfy", {})
    CFG.NTFY_ENABLED = bool(ntfy_cfg.get("enabled", CFG.NTFY_ENABLED))
    CFG.NTFY_TIMEOUT = ntfy_cfg.get("timeout_seconds", CFG.NTFY_TIMEOUT)
    CFG.NTFY_TITLE = str(ntfy_cfg.get("title", CFG.NTFY_TITLE))
    CFG.NTFY_PRIORITY = str(ntfy_cfg.get("priority", CFG.NTFY_PRIORITY))

    # 流水线参数
    pp = settings.get("pipeline", {})
    CFG.CROSSREF_LOOKBACK_DAYS = pp.get("crossref_lookback_days", CFG.CROSSREF_LOOKBACK_DAYS)
    CFG.CROSSREF_LOOKBACK_DAYS_MAX = pp.get("crossref_lookback_days_max", CFG.CROSSREF_LOOKBACK_DAYS_MAX)
    CFG.MAX_PAPERS_PER_PHASE = pp.get("max_papers_per_phase", CFG.MAX_PAPERS_PER_PHASE)
    CFG.SKIP_NATURE_NEWS = pp.get("skip_nature_news", CFG.SKIP_NATURE_NEWS)
    CFG.PREFETCH_NON_RESEARCH = pp.get("prefetch_non_research", CFG.PREFETCH_NON_RESEARCH)
    CFG.POSTFETCH_NON_RESEARCH = pp.get("postfetch_non_research", CFG.POSTFETCH_NON_RESEARCH)
    CFG.GENERATE_EXPLAINED_HTML = pp.get("generate_explained_html", CFG.GENERATE_EXPLAINED_HTML)
    CFG.NON_RESEARCH_KEYWORDS = pp.get("non_research_keywords", CFG.NON_RESEARCH_KEYWORDS)
    download = settings.get("fulltext_download", {})
    CFG.FULLTEXT_DOWNLOAD_DAILY_MAX = download.get("daily_max", CFG.FULLTEXT_DOWNLOAD_DAILY_MAX)
    CFG.FULLTEXT_DOWNLOAD_PUBLISHER_MAX = download.get("publisher_daily_max", CFG.FULLTEXT_DOWNLOAD_PUBLISHER_MAX)
    CFG.FULLTEXT_DOWNLOAD_DELAY_MIN = download.get("delay_min_seconds", CFG.FULLTEXT_DOWNLOAD_DELAY_MIN)
    CFG.FULLTEXT_DOWNLOAD_DELAY_MAX = download.get("delay_max_seconds", CFG.FULLTEXT_DOWNLOAD_DELAY_MAX)

    # 爬虫参数
    ps = settings.get("publisher", {})
    CFG.PUBLISHER_PAGE_DELAY_MIN = ps.get("page_delay_min", CFG.PUBLISHER_PAGE_DELAY_MIN)
    CFG.PUBLISHER_PAGE_DELAY_MAX = ps.get("page_delay_max", CFG.PUBLISHER_PAGE_DELAY_MAX)
    CFG.PUBLISHER_MAX_CONSECUTIVE_FAILURES = ps.get("max_consecutive_failures", CFG.PUBLISHER_MAX_CONSECUTIVE_FAILURES)
    CFG.PUBLISHER_CHALLENGE_MAX_RELOADS = ps.get("challenge_max_reloads", CFG.PUBLISHER_CHALLENGE_MAX_RELOADS)
    CFG.PUBLISHER_CHALLENGE_RELOAD_WAIT_MS = ps.get("challenge_reload_wait_ms", CFG.PUBLISHER_CHALLENGE_RELOAD_WAIT_MS)
    cfg_proxy = ps.get("proxy", {})
    if cfg_proxy:
        CFG.PUBLISHER_PROXY = cfg_proxy
    fallback_proxy_url = ps.get(
        "fallback_proxy_url", CFG.PUBLISHER_FALLBACK_PROXY_URL,
    )
    CFG.PUBLISHER_FALLBACK_PROXY_URL = str(fallback_proxy_url or "").strip()

    # 公式修复
    CFG.FORMULA_FIX_CONCURRENT_MAX = max(
        1,
        int(formula_cfg.get(
            "concurrent_max", CFG.FORMULA_FIX_CONCURRENT_MAX,
        )),
    )
    CFG.SKIP_FORMULA_FIX = formula_cfg.get(
        "skip", CFG.SKIP_FORMULA_FIX,
    )
    CFG.FORCE_FORMULA_FIX = formula_cfg.get(
        "force", CFG.FORCE_FORMULA_FIX,
    )

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
    返回结构化字典，包含 scope_definition（各子领域描述+关键词）和
    irrelevant_fields（不相关领域定义）以及 keyword_catalog（可审计的
    术语、别名和子域映射）。

    Returns:
        dict: {
            "scope_definition": dict[str, {"description": str, "topics": list[str]}],
            "context_gates": list[dict],
            "keyword_catalog": list[dict],
            "irrelevant_fields": {"description": str, "topics": list[str]},
        }
              文件不存在或为空时返回全空结构。
    """
    path = CONFIG_DIR / "keywords.yaml"
    empty = {
        "scope_definition": {},
        "core_anchors": [],
        "context_gates": [],
        "keyword_catalog": [],
        "irrelevant_fields": {"description": "", "topics": []},
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
        "core_anchors": data.get("core_anchors", []),
        "context_gates": data.get("context_gates", []),
        "keyword_catalog": data.get("keyword_catalog", []),
        "irrelevant_fields": data.get("irrelevant_fields", {"description": "", "topics": []}),
    }


def build_scope_block(scope_definition, context_gates=None, irrelevant_fields=None,
                      core_anchors=None, keyword_catalog=None):
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
    core_anchors : list[str], optional
        Positive evidence anchors required for the core category.
    keyword_catalog : list[dict], optional
        Literal terms and their sub-domain mappings.  These are recall aids,
        not standalone relevance rules.

    Returns
    -------
    str
        格式化后的文本块，可直接嵌入 LLM prompt。
    """
    lines = [
        "# Research Scope Definition",
        "",
    ]
    if core_anchors:
        lines.extend([
            "# Core anchors (positive evidence gate)",
            "论文主贡献必须明确研究以下对象之一，背景提及或潜在用途不算：",
        ])
        lines.extend(f"- {anchor}" for anchor in core_anchors)
        lines.append("")

    # 1. Global context gates (word sense disambiguation) — Step 1 of the
    # 3-step classification flow. Rendered first so the LLM applies term
    # disambiguation before any other rule.
    gates = context_gates or []
    if gates:
        lines.append("# Step 1: Global Context Rules (term disambiguation, apply to all sub-domains)")
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

    # 2. Irrelevant fields (topic-level denylist) — Step 2 of the
    # 3-step classification flow. Rendered between gates and sub-domains so
    # the LLM has the term senses resolved before consulting the denylist.
    irr = irrelevant_fields or {}
    irr_desc = irr.get("description", "").strip()
    if irr_desc or irr.get("topics"):
        lines.append("# Step 2: Irrelevant Fields (topic-level denylist)")
        if irr_desc:
            lines.append(irr_desc)
            lines.append("")
        for t in irr.get("topics", []):
            lines.append(f"- {t}")
        lines.append("")

    if keyword_catalog:
        lines.extend([
            "# Literal Keyword Catalog (recall aids, not standalone criteria)",
            "以下术语用于覆盖检查和提示模型注意可能的技术对象；仅命中术语不足以判定相关，仍须结合论文主贡献和语境：",
        ])
        for entry in keyword_catalog:
            if not isinstance(entry, dict):
                continue
            terms = entry.get("terms", [])
            subdomains = entry.get("subdomains", [])
            if terms:
                lines.append(
                    f"- {entry.get('id', 'unnamed')}: "
                    f"{', '.join(map(str, terms))}"
                    + (f" -> {', '.join(map(str, subdomains))}" if subdomains else "")
                )
        lines.append("")

    # 3. Per sub-domain iteration — Step 3 of the 3-step classification
    # flow. Rendered last so the LLM only reaches the positive taxonomy
    # after gates + denylist pass.
    for key, section in scope_definition.items():
        lines.append(f"# Sub-Domain: {key}")

        for field, label in (("display_name", "Display name"),
                             ("role", "Role"),
                             ("a_requirements", "A requirements"),
                             ("adjacent_examples", "Concrete B mappings"),
                             ("exclusions", "Exclusions")):
            value = section.get(field)
            if value:
                if isinstance(value, list):
                    lines.append(f"{label}: " + "; ".join(map(str, value)))
                else:
                    lines.append(f"{label}: {value}")

        lines.append(section.get("description", "").strip())
        lines.append("")
        lines.append("涉及方向包括：")
        for t in section.get("topics", []):
            lines.append(f"- {t}")
        lines.append("")

    return "\n".join(lines)


def build_default_prompt(scope_definition=None):
    """生成 JSON 格式示例字符串，用于 LLM prompt 的 {json_example} 占位符替换。

    从 scope_definition 中提取合法的子领域 key 作为示例值，
    使 LLM 输出格式与实际分类标签保持一致。

    Parameters
    ----------
    scope_definition : dict, optional
        由 load_keywords() 返回的 scope_definition 字段。
        各 key 对应子领域标识。为 None 或空时使用默认占位子领域。

    Returns
    -------
    str
        JSON 示例字符串（单行，无额外空白），可直接嵌入 prompt。
    """
    import json as _json
    if scope_definition:
        known_keys = list(scope_definition.keys())
        example_keys = known_keys[:2] if len(known_keys) >= 2 else known_keys
    else:
        example_keys = ["sub_domain_a", "sub_domain_b"]
    return _json.dumps({
        "PredictedCategory": "B",
        "MatchedSubfields": example_keys,
        "Confidence": "high",
        "Notes": "The paper studies laser-driven ion acceleration with plasma diagnostics.",
    }, ensure_ascii=False)


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


def load_email_recipients():
    """
    加载邮件收件人列表。

    优先从 data/email.yaml 读取（每条 {email, name, enabled}，仅保留 enabled=true）。
    文件不存在或解析失败/为空时，回退到 .env SMTP_TO_ADDRS（向后兼容）。

    Returns
    -------
    list[str]
        收件人邮箱地址列表。
    """
    path = DATA_DIR / "email.yaml"
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            recipients = data.get("recipients", [])
            return [r["email"].strip() for r in recipients
                    if r.get("enabled", True) and r.get("email")]
        except (yaml.YAMLError, KeyError, TypeError, AttributeError):
            pass  # fall through to .env
    return load_email_config().get("to_addrs", [])


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


# 注意：_check_mineru_token() 不再在模块导入时自动调用。
# 原因：logging.warning/error 会触发 logging.basicConfig() 偷装默认 handler，
# 导致入口脚本后续的 logging.basicConfig(...) 失效（root 已有 handler 时为空操作）。
# 入口脚本必须在 logging.basicConfig(...) 之后显式调用 _check_mineru_token()。


# ==================================================================
# 模块自测 (直接运行 python config.py 时触发)
# ==================================================================
if __name__ == "__main__":
    publishers = load_publishers()
    print("加载的期刊配置:")
    for p in publishers:
        print(f"  {p['name']} — {p['rss']}")
