# config.py

from pathlib import Path
import yaml

# ==============================
# 路径配置
# ==============================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "configs"
DB_PATH = DATA_DIR / "papers.db"
LOG_FILE_PATH = DATA_DIR / "PaperCrawler.log"
BROWSER_SESSION_DIR = DATA_DIR / "session_cached"
RAW_RSS_DIR = DATA_DIR / "raw" / "rss"
RAW_PAGE_DIR = DATA_DIR / "raw" / "page"

# ==============================
# 参数配置
# ==============================
REQUEST_TIMEOUT = 30
CROSSREF_MAILTO = "czmczm01@qq.com" # my test mail
MINERU_TOKEN = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI4ODYwMDQwMiIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3OTA3ODA1MSwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiOGNjZGFhZDUtODZiNy00MTViLTgxOWQtMDQ1NThkMTIzN2ZlIiwiZW1haWwiOiJjem1jem0wMUBxcS5jb20iLCJleHAiOjE3ODY4NTQwNTF9.Or7R0nyxGtxTlLspbrfIYxrTBWPTIwbF4Yo8YEbhIMYwmu9er48ajVqne4kzbV77VfNFJUE0K6iwc-QXalRB_A" # Note: 90 days efficient
LLM_API_CONFIG_DICT = {
    "base_url": "https://api.deepseek.com",
    "api_key": "sk-3cc8e7b0cc4e429da42fbce0b75aa482",
    "model_name": "deepseek-v4-flash", # or deepseek-v4-pro stronger
    "temparatures": 0.0,
    "max_tokens": 128000,
    "thinking": "enabled",
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

# ==============================
# 数据源配置
# ==============================
def load_publishers():
    path = CONFIG_DIR / "publishers.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["publishers"]


if __name__ == "__main__":
    # 数据源读取测试
    publishers = load_publishers()
    print("期刊配置如下:")
    print(publishers)
    for p in publishers:
        print(p["name"], p["rss"])
