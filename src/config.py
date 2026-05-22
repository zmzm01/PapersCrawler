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

from pathlib import Path
import yaml


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

# 浏览器 Session 缓存目录（Playwright 持久化 Session 存放处）
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
CROSSREF_MAILTO = "czmczm01@qq.com"

# MinerU PDF 解析 API Token（有效期 90 天，过期后需重新获取）
MINERU_TOKEN = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI4ODYwMDQwMiIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3OTA3ODA1MSwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiOGNjZGFhZDUtODZiNy00MTViLTgxOWQtMDQ1NThkMTIzN2ZlIiwiZW1haWwiOiJjem1jem0wMUBxcS5jb20iLCJleHAiOjE3ODY4NTQwNTF9.Or7R0nyxGtxTlLspbrfIYxrTBWPTIwbF4Yo8YEbhIMYwmu9er48ajVqne4kzbV77VfNFJUE0K6iwc-QXalRB_A"


# ==================================================================
# DeepSeek LLM API 配置
# 用于论文相关性判断和内容总结
# ==================================================================
LLM_API_CONFIG_DICT_RELE = {
    # API 端点: DeepSeek Chat Completions 接口
    "api_url": "https://api.deepseek.com/chat/completions",
    # API 密钥: 从 https://platform.deepseek.com 获取
    "api_key": "sk-3cc8e7b0cc4e429da42fbce0b75aa482",
    # 模型选择: deepseek-v4-flash (快速) 或 deepseek-v4-pro (更强)
    "model": "deepseek-v4-flash",
    # 思考模式: "enabled" 表示开启深度思考, "disabled" 表示关闭
    # 注意: 思考模式下不支持 temperature/top_p 等参数
    "thinking": "enabled",
    # API 调用超时 (秒)
    "timeout": 300,
}

LLM_API_CONFIG_DICT_SUMM = {
    # API 端点: DeepSeek Chat Completions 接口
    "api_url": "https://api.deepseek.com/chat/completions",
    # API 密钥: 从 https://platform.deepseek.com 获取
    "api_key": "sk-3cc8e7b0cc4e429da42fbce0b75aa482",
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
3. 所有 LaTeX 命令在 JSON 字符串内必须用双反斜杠（如 \\(\\omega\\)，\\(\\frac{}{}\\)）。行内公式用 \\(...\\) 或 $...$，独立公式用 $$...$$。
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
SKIP_PHASE_C = False
SKIP_PHASE_E = False
SKIP_PHASE_E2 = False
SKIP_PHASE_F = False
SKIP_PHASE_H = False  # 邮件推送 (SMTP 已配置)

# 过滤 Nature 新闻 (d41586 DOI)，只保留研究论文
SKIP_NATURE_NEWS = True


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
    加载研究领域关键词表。

    从 configs/keywords.yaml 读取关键词列表。
    支持两种格式:
      1. 纯列表: ["keyword1", "keyword2", ...]
      2. 字典: {"keywords": ["keyword1", "keyword2", ...]}

    Returns:
        list[str]: 关键词列表。文件不存在或为空时返回空列表 []。
    """
    path = CONFIG_DIR / "keywords.yaml"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # YAML 空文件解析为 None
    if data is None:
        return []
    # 兼容两种格式
    return data if isinstance(data, list) else data.get("keywords", [])


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
# 模块自测 (直接运行 python config.py 时触发)
# ==================================================================
if __name__ == "__main__":
    publishers = load_publishers()
    print("加载的期刊配置:")
    for p in publishers:
        print(f"  {p['name']} — {p['rss']}")
