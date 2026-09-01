"""
db.py
=====
数据库核心模块，负责 SQLite 数据库的创建与操作。

数据库设计:
  ┌────────────────────────────────────────────────────────────────┐
  │                        papers 表                               │
  ├────────────────────────────────────────────────────────────────┤
  │  核心标识: id, doi (UNIQUE)                                    │
  │  基础元数据: title, abstract, journal, publisher,              │
  │             paperdate_rss/crossref/page, authors_json,         │
  │             page_url, pdf_url                                  │
  │                                                                │
  │  处理流水线状态 (每个阶段都有 status/error/date 三个字段):     │
  │    Phase A: rss_fetched_*          → RSS 发现                 │
  │    Phase B: cr_metadata_fetched_*  → CrossRef 元数据补充      │
  │    Phase C: publisher_page_fetched_* → 期刊页面抓取           │
  │    Phase E: llm_relevance_*         → LLM 相关性判断          │
  │    Phase F: llm_summary_*           → LLM 论文总结            │
  │                                                                │
  │  时间戳: created_date, updated_date                            │
  └────────────────────────────────────────────────────────────────┘

状态枚举 (FetchStatus):
  - pending     → 等待处理
  - processing  → 正在处理 (可用于并发认领)
  - success     → 处理成功
  - failed      → 处理失败 (可重试)
  - skipped     → 因条件不满足跳过 (如: 不是学术文章、无关键词命中)

流水线流转:
  新 DOI 入库
    → Phase B: cr_metadata = pending (waiting)
    → Phase C: publisher_page = pending (waiting)
    → Phase D: keywords = pending (waiting)
    → Phase E: llm_relevance = pending (waiting, 关键词命中时)
    → Phase F: llm_summary = pending (waiting, 判定相关时)
    → Phase G: 报告生成 (使用 get_papers_for_report())
"""

import json
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from enum import Enum

from common import clean_extracted_text


# The latest manual decision is an override, not an additional signal.  Keep
# the SQL fragments shared by summary/report queries so all downstream stages
# apply the same effective category semantics.
LATEST_RELEVANCE_REVIEW_CTE = """
WITH latest_relevance_review AS (
    SELECT review.*
    FROM relevance_reviews AS review
    INNER JOIN (
        SELECT doi, MAX(id) AS latest_id
        FROM relevance_reviews
        GROUP BY doi
    ) AS latest
      ON latest.doi = review.doi
     AND latest.latest_id = review.id
)
"""
EFFECTIVE_RELEVANCE_CATEGORY_SQL = """
CASE
    WHEN latest_relevance_review.id IS NOT NULL
        THEN latest_relevance_review.decision
    ELSE p.llm_relevance_category
END
"""


# ------------------------------------------------------------------
# 自定义异常
# ------------------------------------------------------------------

class DataBaseDOINotExists(Exception):
    """DOI 在数据库中不存在时抛出。用于确保更新操作的目标记录已存在。"""
    pass


# ------------------------------------------------------------------
# 状态枚举
# ------------------------------------------------------------------

class FetchStatus(str, Enum):
    """
    处理状态枚举，字符串类型便于直接存储到 TEXT 列。

    使用示例:
        db.update_llm_summary(doi, json_str, FetchStatus.SUCCESS.value, date)
    """
    PENDING = "pending"         # 等待处理 (初始状态)
    PROCESSING = "processing"   # 正在处理中 (并发认领标记，当前未使用)
    SUCCESS = "success"         # 处理成功完成
    FAILED = "failed"           # 处理失败 (可定时重试)
    SKIPPED = "skipped"         # 因条件不满足跳过 (如关键词无命中)


# ------------------------------------------------------------------
# 数据库客户端
# ------------------------------------------------------------------

class DatabaseClient:
    """
    SQLite 数据库客户端，封装对 papers 表的所有读写操作。

    设计原则:
      - 每个流水线阶段有专用的写入方法 (insert/update_xxx)
      - 查询方法支持按状态字段筛选
      - 调用方负责检查前置条件 (如: 先检查 DOI 是否存在再插入)
      - 所有更新方法在 DOI 不存在时抛出 DataBaseDOINotExists

    使用示例:
        db = DatabaseClient("data/papers.db")
        db.init_db_papers()                              # 初始化表结构
        db.insert_rss_basicinfo(doi, title, ...)         # Phase A 写入
        papers = db.get_pendings("cr_metadata_fetched_status")  # 查待办
        db.update_crossref_metadata(doi, title, ...)     # Phase B 更新
    """

    # ---- 可安全用于动态 SQL 拼接的列名白名单 (防止 SQL 注入) ----
    _VALID_STATUS_COLUMNS = frozenset({
        "cr_metadata_fetched_status", "cr_metadata_fetched_error",
        "cr_metadata_fetched_date",
        "openalex_metadata_fetched_status", "openalex_metadata_fetched_error",
        "openalex_metadata_fetched_date",
        "publisher_page_fetched_status", "publisher_page_fetched_error",
        "publisher_page_fetched_date",
        "publisher_page_retry_count", "publisher_page_retry_after",
        "publisher_page_failure_kind",
        "llm_relevance_status", "llm_relevance_error",
        "llm_relevance_date",
        "llm_summary_status", "llm_summary_error", "llm_summary_date",
        "mineru_parse_status", "mineru_parse_error", "mineru_parse_date",
        "report_status", "report_date",
        "llm_relevance_result",  # deprecated — use llm_relevance_category
        "llm_relevance_category", "llm_relevance_subfields",
        "llm_relevance_confidence",
        "llm_relevance_reason", "llm_summary_result",
        "llm_relevance_basis", "llm_relevance_model",
        "llm_relevance_review_model", "llm_relevance_pre_review_category",
        "relevance_screen_status", "relevance_screen_error",
        "relevance_screen_date", "relevance_screen_category",
        "relevance_screen_subfields", "relevance_screen_confidence",
        "relevance_screen_reason", "relevance_screen_model",
        "relevance_screen_is_backfill",
        "mineru_fulltext", "mineru_output_dir",
    })

    @classmethod
    def _validate_column(cls, col_name):
        """检查列名是否在白名单中。

        Parameters
        ----------
        col_name : str

        Raises
        ------
        ValueError
            列名不在白名单中。
        """
        if col_name not in cls._VALID_STATUS_COLUMNS:
            raise ValueError(
                f"Invalid column name '{col_name}' — not in allowed whitelist"
            )

    def __init__(self, dbPath):
        """
        打开数据库连接。

        启用 WAL (Write-Ahead Logging) 模式:
          - 允许 WebUI 读取与 Pipeline 写入并发执行不互相阻塞
          - 同步策略降为 NORMAL（牺牲极端崩溃下的少量已提交事务换取 ~10x 写入吞吐）
          - 对所有现有读写语义透明，向后兼容

        Args:
            dbPath: SQLite 数据库文件路径 (字符串或 Path 对象)
                   文件不存在时会自动创建。
        """
        # sqlite3.Row 工厂使查询结果支持通过列名访问: row["doi"]
        self.conn = sqlite3.connect(str(dbPath))
        self.conn.row_factory = sqlite3.Row
        # 启用 WAL 模式（Write-Ahead Logging）— 写不阻塞读，
        # 适合 WebUI 频繁查询 + Pipeline 后台写入的并发场景
        self.conn.execute("PRAGMA journal_mode=WAL")
        # WAL 模式下推荐搭配 NORMAL 同步（默认 FULL 在 WAL 下过度保守）
        self.conn.execute("PRAGMA synchronous=NORMAL")

    def close(self) -> None:
        """Close the underlying SQLite connection.

        Idempotent — safe to call multiple times.
        """
        conn = getattr(self, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self.conn = None

    def __enter__(self) -> "DatabaseClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 建表
    # ------------------------------------------------------------------

    def init_db_papers(self):
        """
        初始化 papers 表结构。

        使用 CREATE TABLE IF NOT EXISTS，多次调用安全。
        表结构汇总:

        ---- 核心标识 ----
        id:            自增主键
        doi:           论文 DOI，UNIQUE 约束保证不重复

        ---- 基础元数据 (各阶段逐步填充) ----
        title:         论文标题
        abstract:      论文摘要
        journal:       期刊名称
        publisher:     出版社标识 (如 nature, aps, science)
        paperdate_rss:        RSS 中获取的出版日期
        paperdate_crossref:   CrossRef 返回的出版日期
        paperdate_page:       出版商页面中的出版日期
        authors_json:         作者列表 (JSON 格式字符串)
        page_url:             论文页面 URL
        pdf_url:              PDF 下载链接

        ---- 流水线处理状态 ----
        每个阶段 xxx 有三个字段:
          xxx_status: 状态 (pending/processing/success/failed/skipped)
          xxx_error:  错误信息
          xxx_date:   处理时间

    Phase A — RSS 抓取: 无单独状态列（DOI 入库即完成）
    Phase B — CrossRef 元数据: cr_metadata_fetched_*
    Phase C — 出版商页面:      publisher_page_fetched_*
    Phase E — LLM 相关性:      llm_relevance_*
    Phase F — LLM 总结:        llm_summary_*
    Phase G — 报告生成:        report_*

        ---- 时间戳 ----
        created_date:  记录创建时间
        updated_date:  记录最后更新时间
        """
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- 核心标识
            doi TEXT UNIQUE,

            -- 基础 metadata
            title TEXT,
            abstract TEXT,
            journal TEXT,
            publisher TEXT,
            paperdate_rss TEXT,
            paperdate_crossref TEXT,
            paperdate_page TEXT,
            authors_json TEXT,
            page_url TEXT,
            pdf_url TEXT,

            -- CrossRef 元数据状态
            cr_metadata_fetched_status TEXT DEFAULT 'pending',
            cr_metadata_fetched_error TEXT,
            cr_metadata_fetched_date TEXT,

            -- OpenAlex fallback metadata status
            openalex_metadata_fetched_status TEXT DEFAULT 'pending',
            openalex_metadata_fetched_error TEXT,
            openalex_metadata_fetched_date TEXT,
            openalex_id TEXT,
            abstract_source TEXT,
            metadata_provenance_json TEXT,

            -- Publisher 页面抓取状态
            publisher_page_fetched_status TEXT DEFAULT 'pending',
            publisher_page_fetched_error TEXT,
            publisher_page_fetched_date TEXT,
            publisher_page_retry_count INTEGER DEFAULT 0,
            publisher_page_retry_after TEXT,
            publisher_page_failure_kind TEXT,

            -- LLM 相关性判断
            llm_relevance_status TEXT DEFAULT 'pending',
            llm_relevance_result INTEGER DEFAULT 0,  -- deprecated, use category
            llm_relevance_category TEXT,              -- A/B/C/D
            llm_relevance_subfields TEXT,             -- JSON array of matched sub-domains
            llm_relevance_confidence TEXT,
            llm_relevance_reason TEXT,
            llm_relevance_basis TEXT,             -- fulltext/abstract_clear_reject
            llm_relevance_model TEXT,             -- primary final-adjudication model
            llm_relevance_review_model TEXT,      -- optional transition reviewer
            llm_relevance_pre_review_category TEXT,
            llm_relevance_error TEXT,
            llm_relevance_date TEXT,

            -- 标题+摘要初筛（Phase E）；最终判定仍使用 llm_relevance_*。
            relevance_screen_status TEXT DEFAULT 'pending',
            relevance_screen_category TEXT,
            relevance_screen_subfields TEXT,
            relevance_screen_confidence TEXT,
            relevance_screen_reason TEXT,
            relevance_screen_model TEXT,
            relevance_screen_error TEXT,
            relevance_screen_date TEXT,
            relevance_screen_is_backfill INTEGER DEFAULT 0,

            -- LLM 论文总结
            llm_summary_status TEXT DEFAULT 'pending',
            llm_summary_error TEXT,
            llm_summary_date TEXT,
            llm_summary_result TEXT,

            -- MinerU PDF 全文解析
            mineru_parse_status TEXT DEFAULT 'pending',
            mineru_parse_error TEXT,
            mineru_parse_date TEXT,
            mineru_fulltext TEXT,
            mineru_output_dir TEXT,

            -- 报告生成状态
            report_status TEXT DEFAULT 'pending',
            report_date TEXT,

            -- 论文发现来源 (逗号分隔，如 "rss" / "crossref" / "rss,crossref")
            discovery_source TEXT,

            -- 时间戳
            created_date TEXT,
            updated_date TEXT
        )
        """)
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS skipped_dois (
            doi         TEXT PRIMARY KEY,
            reason      TEXT,
            created_date TEXT
        )
        """)
        self.conn.commit()

        # 下载审计表：配额占位和下载结果在同一 SQLite 数据库中持久化。
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS fulltext_download_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT NOT NULL,
            publisher TEXT,
            local_date TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            location_source TEXT,
            route TEXT,
            requested_url TEXT,
            final_url TEXT,
            http_status INTEGER,
            content_type TEXT,
            failure_kind TEXT,
            details_json TEXT
        )
        """)
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_fulltext_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL,
            version TEXT,
            is_oa INTEGER DEFAULT 0,
            license TEXT,
            priority INTEGER DEFAULT 100,
            discovered_at TEXT NOT NULL,
            UNIQUE(doi, url)
        )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fulltext_locations_doi "
            "ON paper_fulltext_locations(doi, priority, id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_download_events_date "
            "ON fulltext_download_events(local_date)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_download_events_date_publisher "
            "ON fulltext_download_events(local_date, publisher)"
        )
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS relevance_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (
                decision IN ('A', 'B', 'C', 'D', 'uncertain')
            ),
            notes TEXT NOT NULL DEFAULT '',
            reviewer TEXT NOT NULL DEFAULT '',
            source_final_category TEXT,
            source_final_confidence TEXT,
            source_screen_model TEXT,
            source_final_model TEXT,
            source_review_model TEXT,
            created_date TEXT NOT NULL
        )
        """)
        for col_def in [
            "source_screen_model TEXT",
            "source_final_model TEXT",
            "source_review_model TEXT",
        ]:
            self._add_column_if_missing(
                col_def, table_name="relevance_reviews",
            )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relevance_reviews_doi_id "
            "ON relevance_reviews(doi, id DESC)"
        )
        self.conn.commit()

        for col_def in [
            "location_source TEXT", "route TEXT", "requested_url TEXT",
            "final_url TEXT", "http_status INTEGER", "content_type TEXT",
            "failure_kind TEXT", "details_json TEXT",
        ]:
            self._add_column_if_missing(
                col_def, table_name="fulltext_download_events",
            )

        # ---- 迁移: 为旧数据库添加 MinerU 列 (如果不存在) ----
        # SQLite 3.35.0+ 支持 ALTER TABLE ADD COLUMN IF NOT EXISTS
        mineru_columns = [
            "mineru_parse_status TEXT DEFAULT 'pending'",
            "mineru_parse_error TEXT",
            "mineru_parse_date TEXT",
            "mineru_fulltext TEXT",
            "mineru_output_dir TEXT",
        ]
        for col_def in mineru_columns:
            self._add_column_if_missing(col_def)

        # ---- 迁移: OpenAlex fallback metadata columns ----
        for col_def in [
            "openalex_metadata_fetched_status TEXT DEFAULT 'pending'",
            "openalex_metadata_fetched_error TEXT",
            "openalex_metadata_fetched_date TEXT",
            "openalex_id TEXT",
            "abstract_source TEXT",
            "metadata_provenance_json TEXT",
        ]:
            self._add_column_if_missing(col_def)

        # ---- 迁移: 为旧数据库添加报告状态列 ----
        report_columns = [
            "report_status TEXT DEFAULT 'pending'",
            "report_date TEXT",
        ]
        for col_def in report_columns:
            self._add_column_if_missing(col_def)

        # ---- 迁移: Publisher Bot 阻断重试状态列 ----
        # 这些列只记录 Phase C 的反爬失败，不改变已有论文状态语义。
        for col_def in [
            "publisher_page_retry_count INTEGER DEFAULT 0",
            "publisher_page_retry_after TEXT",
            "publisher_page_failure_kind TEXT",
        ]:
            self._add_column_if_missing(col_def)

        # ---- 迁移: 为旧数据库添加发现来源列 ----
        self._add_column_if_missing("discovery_source TEXT")

        # ---- 迁移: 为旧数据库添加 LLM 相关性分类列 ----
        for col_def in [
            "llm_relevance_category TEXT",
            "llm_relevance_subfields TEXT",
        ]:
            self._add_column_if_missing(col_def)

        # ---- 迁移：摘要初筛与最终判定依据列 ----
        for col_def in [
            "llm_relevance_basis TEXT",
            "llm_relevance_model TEXT",
            "llm_relevance_review_model TEXT",
            "llm_relevance_pre_review_category TEXT",
            "relevance_screen_status TEXT DEFAULT 'pending'",
            "relevance_screen_category TEXT",
            "relevance_screen_subfields TEXT",
            "relevance_screen_confidence TEXT",
            "relevance_screen_reason TEXT",
            "relevance_screen_model TEXT",
            "relevance_screen_error TEXT",
            "relevance_screen_date TEXT",
            "relevance_screen_is_backfill INTEGER DEFAULT 0",
        ]:
            self._add_column_if_missing(col_def)
        self.conn.commit()

        # Existing databases keep their final judgement as a screening
        # snapshot; this does not trigger an LLM call or a PDF download.
        self.migrate_relevance_screen_snapshot()
        self.normalize_metadata_text()

    def _add_column_if_missing(self, column_definition, table_name="papers"):
        """Add a schema column, ignoring only duplicate-column errors.

        Parameters
        ----------
        column_definition : str
            Column name followed by its SQLite type/default declaration.
        table_name : str
            Existing table to migrate.

        Raises
        ------
        sqlite3.OperationalError
            If the migration fails for a reason other than the column already
            existing.
        """
        try:
            if table_name not in {
                    "papers", "fulltext_download_events", "relevance_reviews",
            }:
                raise ValueError(f"Unsupported migration table: {table_name}")
            self.conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"
            )
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error).lower():
                raise

        # ==================================================================
    # 基本查询方法
    # ==================================================================

    def normalize_metadata_text(self) -> int:
        """Repair legacy encoded title/abstract values in the local database.

        Returns
        -------
        int
            Number of paper rows changed.  This lightweight migration is
            idempotent and makes existing rows follow the same contract as
            newly fetched metadata.
        """
        rows = self.conn.execute(
            "SELECT id, title, abstract FROM papers"
        ).fetchall()
        updates = []
        for row in rows:
            title = clean_extracted_text(row["title"]) or ""
            abstract = clean_extracted_text(row["abstract"]) or ""
            if title != (row["title"] or "") or abstract != (row["abstract"] or ""):
                updates.append((title, abstract, row["id"]))
        if updates:
            self.conn.executemany(
                "UPDATE papers SET title = ?, abstract = ? WHERE id = ?",
                updates,
            )
            self.conn.commit()
        return len(updates)

    def paper_doi_exists(self, doi):
        """
        检查某 DOI 是否已存在于数据库中。

        用于 RSS 阶段去重: 同一篇论文不会被重复插入。

        Args:
            doi: 论文 DOI 字符串
        Returns:
            bool: True 表示已存在, False 表示不存在

        Note:
            使用 LOWER(doi) 做大小写不敏感比较：RSS 与 CrossRef 返回的 DOI
            大小写可能不同，避免同一论文因大小写差异被重复插入。
        """
        cur = self.conn.execute(
            "SELECT 1 FROM papers WHERE LOWER(doi) = LOWER(?)", (doi,),
        )
        return cur.fetchone() is not None

    def is_doi_skipped(self, doi):
        """检查某 DOI 是否已被标记为跳过（如 Non-Research Paper）。

        被跳过的论文不参与流水线处理。
        Phase A 在插入新论文前应同时检查 paper_doi_exists() 和此方法。

        Parameters
        ----------
        doi : str
            论文 DOI。

        Returns
        -------
        bool
            True 表示该 DOI 已被跳过。

        Note:
            使用 LOWER(doi) 做大小写不敏感比较（DOI 大小写不敏感）。
        """
        cur = self.conn.execute(
            "SELECT 1 FROM skipped_dois WHERE LOWER(doi) = LOWER(?)", (doi,),
        )
        return cur.fetchone() is not None

    def insert_skipped_doi(self, doi, reason, created_date=None):
        """记录一个被跳过/删除的 DOI，防止未来被重新发现。

        用于 NonResearchPageError：非研究文章永远不会变成研究论文，
        删除后下次 Phase A 仍会重新发现。此表阻止这种循环。

        Parameters
        ----------
        doi : str
            论文 DOI。
        reason : str
            跳过原因，如 'NonResearchPageError'
        created_date : str, optional
            记录时间，默认当前时间。
        """
        from datetime import datetime
        if created_date is None:
            created_date = str(datetime.now())
        # DOI 规范为小写（与 papers 表一致，保证大小写不敏感的跳过判定）
        self.conn.execute(
            "INSERT OR IGNORE INTO skipped_dois (doi, reason, created_date) "
            "VALUES (?, ?, ?)",
            (doi.lower(), reason, created_date),
        )
        self.conn.commit()

    def get_pendings(self, status_field):
        """
        获取某状态列的值为 'pending' 的所有论文。

        这是流水线中最常用的查询方法。
        每个 Phase 通过此方法获取自己的待处理队列。

        Args:
            status_field: 要查询的状态列名
                          例如 "cr_metadata_fetched_status" 获取待补充 CrossRef 元数据的论文
        Returns:
            list[sqlite3.Row]: 可以使用 row["doi"], row["title"] 等方式访问字段
        """
        self._validate_column(status_field)
        cur = self.conn.execute(f"""
        SELECT * FROM papers
        WHERE {status_field} = 'pending'
        ORDER BY created_date
        """)
        return cur.fetchall()

    def get_papers_by_status(self, status_field, status_value):
        """
        按指定状态值筛选论文，比 get_pendings 更通用。

        Args:
            status_field:   状态列名
            status_value:   状态值 (如 "success", "failed")
        Returns:
            list[sqlite3.Row]
        """
        self._validate_column(status_field)
        cur = self.conn.execute(f"""
        SELECT * FROM papers
        WHERE {status_field} = ?
        ORDER BY created_date
        """, (status_value,))
        return cur.fetchall()

    def get_pending_publisher_papers(self, publisher, skip_crossref_abstract=False):
        """获取指定 publisher 待抓取的论文列表。

        Parameters
        ----------
        publisher : str
            Publisher 标识（如 "nature", "aps"）。
        skip_crossref_abstract : bool
            为 True 时排除已有有效 CrossRef 摘要的论文（节省浏览器资源）。

        Returns
        -------
        list[sqlite3.Row]
        """
        self._validate_column("publisher_page_fetched_status")
        query = """
            SELECT * FROM papers
            WHERE publisher_page_fetched_status = 'pending'
              AND publisher = ?
        """
        if skip_crossref_abstract:
            query += """AND NOT (
                (cr_metadata_fetched_status = 'success'
                 OR openalex_metadata_fetched_status = 'success')
                AND abstract IS NOT NULL AND abstract != ''
            )"""
        cur = self.conn.execute(query, (publisher,))
        return cur.fetchall()

    def get_papers_by_status_and_publisher(self, status_field, status_value, publisher):
        """按状态值和 publisher 筛选论文。

        Parameters
        ----------
        status_field : str
            状态列名（如 "publisher_page_fetched_status"）。
        status_value : str
            状态值（如 "pending", "success"）。
        publisher : str
            Publisher 标识。

        Returns
        -------
        list[sqlite3.Row]
        """
        self._validate_column(status_field)
        cur = self.conn.execute(f"""
            SELECT * FROM papers
            WHERE {status_field} = ? AND publisher = ?
            ORDER BY created_date
        """, (status_value, publisher))
        return cur.fetchall()

    # ==================================================================
    # Phase A: RSS 基本信息写入
    # ==================================================================

    def insert_rss_basicinfo(self, doi, title, link, journal, publisher, updated):
        """
        Phase A 专用: 将 RSS 抓取的论文基本信息写入数据库。

        此方法不做去重检查 — 调用方必须先用 paper_doi_exists() 判断。
        自动设置 discovery_source = 'rss'。

        Args:
            doi:       论文 DOI
            title:     论文标题 (来自 RSS)
            link:      论文页面 URL (来自 RSS, 存储在 page_url 列)
            journal:   期刊名称
            publisher: 出版社标识
            updated:   RSS 中显示的发布/更新日期 (存储在 paperdate_rss 列)
        """
        # DOI 规范为小写（DOI 本身大小写不敏感，避免 RSS/CrossRef 双插不同大小写副本）
        self.conn.execute(
            """
            INSERT INTO papers (doi, title, page_url, journal, publisher,
                                paperdate_rss, discovery_source)
            VALUES (?, ?, ?, ?, ?, ?, 'rss')
            """,
            (doi.lower(), title, link, journal, publisher, updated),
        )
        self.conn.commit()

    def insert_paper_created_date(self, doi, created_date):
        """
        为已存在的论文记录设置创建日期。

        使用 UPDATE 而非 INSERT（记录已由 insert_rss_basicinfo 创建）。

        Args:
            doi:          论文 DOI
            created_date: 创建日期字符串 (如 "2026-05-18")
        """
        # 与 insert_*_basicinfo 一致，DOI 先转小写再匹配
        self.conn.execute(
            "UPDATE papers SET created_date = ? WHERE LOWER(doi) = LOWER(?)",
            (created_date, doi),
        )
        self.conn.commit()

    def insert_paper_basicinfo(self, doi, title, link, journal, publisher,
                                date, source):
        """
        通用: 将论文基本信息和发现来源写入数据库。

        适用于 RSS 和 CrossRef 发现两条路径，通过 source 参数区分。
        此方法不做去重检查 — 调用方必须先用 paper_doi_exists() 判断。

        Args:
            doi:       论文 DOI
            title:     论文标题
            link:      论文页面 URL (page_url 列)
            journal:   期刊名称
            publisher: 出版社标识
            date:      发布日期 (paperdate_rss 列)
            source:    发现来源，如 "rss" / "crossref"
        """
        # DOI 规范为小写（DOI 本身大小写不敏感，避免 RSS/CrossRef 双插不同大小写副本）
        self.conn.execute(
            """
            INSERT INTO papers (doi, title, page_url, journal, publisher,
                                paperdate_rss, discovery_source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (doi.lower(), title, link, journal, publisher, date, source),
        )
        self.conn.commit()

    def append_discovery_source(self, doi, source):
        """
        在已有论文的 discovery_source 后追加新的发现来源。

        不会重复添加（如果已有此来源则跳过）。
        例如: discovery_source='rss', source='crossref' → 'rss,crossref'
              discovery_source='rss,crossref', source='crossref' → 不变

        Args:
            doi:    论文 DOI
            source: 要追加的来源名称（如 "crossref"）
        """
        cur = self.conn.execute(
            "SELECT discovery_source FROM papers WHERE LOWER(doi) = LOWER(?)",
            (doi,),
        )
        row = cur.fetchone()
        if row is None:
            return

        existing = row["discovery_source"] or ""
        sources = [s.strip() for s in existing.split(",") if s.strip()]
        if source not in sources:
            sources.append(source)
            new_value = ",".join(sources)
            self.conn.execute(
                "UPDATE papers SET discovery_source = ? WHERE LOWER(doi) = LOWER(?)",
                (new_value, doi),
            )
            self.conn.commit()

    # ==================================================================
    # Phase B: CrossRef 元数据更新
    # ==================================================================

    def update_crossref_metadata(self, doi, title, authors_json, published,
                                 abstract="", fulltext_links=None):
        """
        Phase B 专用: 用 CrossRef 返回的元数据更新数据库记录。

        更新字段:
          - title:               可能比 RSS 标题更完整/准确
          - authors_json:        作者列表 (JSON 格式)
          - paperdate_crossref:  CrossRef 返回的出版日期
          - abstract:            CrossRef 返回的摘要（空字符串不覆盖已有值）

        Raises:
            DataBaseDOINotExists: DOI 在数据库中不存在

        Args:
            doi:          论文 DOI
            title:        来自 CrossRef 的标题
            authors_json: 作者列表的 JSON 字符串 (json.dumps(meta.authors))
            published:    CrossRef 返回的出版日期
            abstract:     CrossRef 返回的摘要（可能为空）
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update CrossRef metadata."
            )
        title = clean_extracted_text(title) or ""
        abstract = clean_extracted_text(abstract) or ""
        existing_row = self.conn.execute(
            "SELECT metadata_provenance_json FROM papers "
            "WHERE LOWER(doi) = LOWER(?)", (doi,),
        ).fetchone()
        try:
            provenance = json.loads(
                existing_row["metadata_provenance_json"] or "{}"
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            provenance = {}
        if title:
            provenance["title"] = "crossref"
        if authors_json and authors_json not in ("[]", "null"):
            provenance["authors"] = "crossref"
        if published:
            provenance["published"] = "crossref"
        if abstract:
            provenance["abstract"] = "crossref"
        self.conn.execute(
            """
            UPDATE papers
            SET title = CASE WHEN ? != '' THEN ? ELSE title END,
                authors_json = CASE
                    WHEN ? NOT IN ('', '[]', 'null') THEN ? ELSE authors_json END,
                paperdate_crossref = CASE
                    WHEN ? != '' THEN ? ELSE paperdate_crossref END,
                abstract = CASE WHEN ? != '' THEN ? ELSE abstract END,
                abstract_source = CASE WHEN ? != '' THEN 'crossref'
                    ELSE abstract_source END,
                metadata_provenance_json = ?
            WHERE doi = ?
            """,
            (title, title, authors_json, authors_json, published, published,
             abstract, abstract, abstract,
             json.dumps(provenance, ensure_ascii=False), doi),
        )
        self.conn.commit()
        if fulltext_links:
            self.add_fulltext_locations(doi, fulltext_links, "crossref")

    def update_openalex_metadata(self, doi, metadata, status_date,
                                 fulltext_locations=None):
        """Merge OpenAlex metadata into fields missing from Crossref/RSS.

        Parameters
        ----------
        doi : str
            Existing paper DOI.
        metadata : object or dict
            Normalized OpenAlex metadata.
        status_date : str
            Fetch timestamp.
        fulltext_locations : list of dict, optional
            Candidate locations to persist.
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(f"DOI {doi} not found in DB")
        if isinstance(metadata, dict):
            get_value = metadata.get
        else:
            get_value = lambda key, default=None: getattr(metadata, key, default)
        authors = get_value("authors")
        authors_json = json.dumps(authors, ensure_ascii=False) if authors else None
        abstract = clean_extracted_text(get_value("abstract")) or ""
        existing_row = self.conn.execute(
            "SELECT title, authors_json, journal, paperdate_crossref, abstract, "
            "metadata_provenance_json FROM papers WHERE LOWER(doi) = LOWER(?)",
            (doi,),
        ).fetchone()
        try:
            provenance = json.loads(existing_row["metadata_provenance_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            provenance = {}
        if not existing_row["abstract"] and abstract:
            provenance["abstract"] = "openalex"
        if not existing_row["title"] and get_value("title"):
            provenance["title"] = "openalex"
        if not existing_row["authors_json"] and authors_json:
            provenance["authors"] = "openalex"
        if not existing_row["journal"] and get_value("journal"):
            provenance["journal"] = "openalex"
        if not existing_row["paperdate_crossref"] and get_value("published"):
            provenance["published"] = "openalex"
        self.conn.execute(
            """UPDATE papers SET
                title = CASE WHEN COALESCE(title, '') = '' THEN ? ELSE title END,
                authors_json = CASE WHEN COALESCE(authors_json, '') IN ('', '[]', 'null')
                    THEN ? ELSE authors_json END,
                journal = CASE WHEN COALESCE(journal, '') = '' THEN ? ELSE journal END,
                paperdate_crossref = CASE
                    WHEN COALESCE(paperdate_crossref, '') = '' THEN ?
                    ELSE paperdate_crossref END,
                abstract = CASE WHEN COALESCE(abstract, '') = '' AND ? != ''
                    THEN ? ELSE abstract END,
                abstract_source = CASE WHEN COALESCE(abstract, '') = '' AND ? != ''
                    THEN 'openalex' ELSE abstract_source END,
                openalex_id = ?, metadata_provenance_json = ?
                WHERE LOWER(doi) = LOWER(?)""",
            (get_value("title"), authors_json, get_value("journal"),
             get_value("published"), abstract, abstract, abstract,
             get_value("openalex_id"), json.dumps(provenance), doi),
        )
        self.conn.commit()
        if fulltext_locations is None:
            fulltext_locations = get_value("locations")
        if fulltext_locations:
            self.add_fulltext_locations(doi, fulltext_locations, "openalex")

    def update_openalex_status(self, doi, status, error, status_date):
        """Persist the independent OpenAlex fetch status for a paper."""
        self.update_process_status(
            doi, "openalex_metadata_fetched_status", status,
            "openalex_metadata_fetched_date", status_date,
        )
        self.conn.execute(
            "UPDATE papers SET openalex_metadata_fetched_error = ? "
            "WHERE LOWER(doi) = LOWER(?)", (str(error)[:500] if error else None, doi)
        )
        self.conn.commit()

    def add_fulltext_locations(self, doi, locations, source=None):
        """Store deduplicated full-text URL candidates for a paper."""
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        for offset, location in enumerate(locations or []):
            if isinstance(location, str):
                location = {"url": location}
            url = location.get("url") or location.get("pdf_url")
            if not url or "content.openalex.org" in url:
                continue
            location_source = location.get("source") or source or "unknown"
            self.conn.execute(
                """INSERT OR IGNORE INTO paper_fulltext_locations
                   (doi, url, source, version, is_oa, license, priority,
                    discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (doi.lower(), url, location_source, location.get("version"),
                 int(bool(location.get("is_oa"))), location.get("license"),
                 int(location.get("priority", offset + {
                     "crossref": 0,
                     "openalex": 20,
                     "publisher": 40,
                 }.get(location_source, 60))), now),
            )
        self.conn.commit()

    def get_fulltext_locations(self, doi):
        """Return full-text candidates ordered by resolver priority."""
        rows = self.conn.execute(
            """SELECT url, source, version, is_oa, license, priority
               FROM paper_fulltext_locations
               WHERE LOWER(doi) = LOWER(?) ORDER BY priority, id""", (doi,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ==================================================================
    # Phase C: Publisher 页面信息更新
    # ==================================================================

    def update_publisher_page(self, doi, abstract, authors_json, pdf_url,
                              paperdate_page, status, status_date):
        """
        Phase C 专用: 将从出版商页面抓取的信息写入数据库。

        更新字段:
          - abstract:        论文摘要 (来自页面解析)
          - authors_json:    作者列表 (来自页面元数据, 可能比 CrossRef 更准确)
          - pdf_url:         PDF 下载链接
          - paperdate_page:  页面显示的出版日期
          - publisher_page_fetched_status: 状态标记
          - publisher_page_fetched_date:   处理时间

        Raises:
            DataBaseDOINotExists: DOI 在数据库中不存在

        Args:
            doi, abstract, authors_json, pdf_url: 见上
            paperdate_page: 页面日期
            status:         FetchStatus 状态值
            status_date:    处理日期时间字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update publisher page."
            )
        abstract = clean_extracted_text(abstract) or ""
        self.conn.execute(
            """
            UPDATE papers
            SET abstract = CASE WHEN ? != '' THEN ? ELSE abstract END,
                abstract_source = CASE
                    WHEN ? != '' AND COALESCE(abstract, '') = ''
                    THEN 'publisher' ELSE abstract_source END,
                authors_json = ?, pdf_url = ?,
                paperdate_page = ?,
                publisher_page_fetched_status = ?,
                publisher_page_fetched_date = ?,
                publisher_page_fetched_error = NULL,
                publisher_page_retry_count = 0,
                publisher_page_retry_after = NULL,
                publisher_page_failure_kind = NULL
            WHERE doi = ?
            """,
            (abstract, abstract, abstract, authors_json, pdf_url, paperdate_page,
             status, status_date, doi),
        )
        self.conn.commit()

    def record_publisher_page_failure(
            self, doi, error, status_date, failure_kind=None,
            retry_after=None):
        """Record a Publisher failure and its retry/quarantine metadata.

        Parameters
        ----------
        doi : str
            DOI of the paper being updated.
        error : str
            Human-readable failure message.
        status_date : str
            Failure timestamp.
        failure_kind : str, optional
            Stable failure class. ``"bot_block"`` enables cooldown and
            quarantine handling; other values are treated as ordinary
            retryable failures.
        retry_after : str, optional
            Earliest timestamp for the next automatic retry.

        Returns
        -------
        int
            The consecutive Bot-block failure count after this update, or
            ``0`` for a non-Bot failure.
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(f"DOI {doi} not found in DB.")

        row = self.conn.execute(
            """
            SELECT publisher_page_retry_count, publisher_page_failure_kind
            FROM papers WHERE LOWER(doi) = LOWER(?)
            """,
            (doi,),
        ).fetchone()
        previous_count = int(row["publisher_page_retry_count"] or 0)
        previous_kind = row["publisher_page_failure_kind"]
        if failure_kind == "bot_block":
            retry_count = (
                previous_count + 1
                if previous_kind == "bot_block" else 1
            )
        else:
            retry_count = 0
            retry_after = None

        self.conn.execute(
            """
            UPDATE papers
            SET publisher_page_fetched_status = ?,
                publisher_page_fetched_error = ?,
                publisher_page_fetched_date = ?,
                publisher_page_retry_count = ?,
                publisher_page_retry_after = ?,
                publisher_page_failure_kind = ?
            WHERE LOWER(doi) = LOWER(?)
            """,
            (
                FetchStatus.FAILED.value,
                str(error)[:500],
                status_date,
                retry_count,
                retry_after,
                failure_kind,
                doi,
            ),
        )
        self.conn.commit()
        return retry_count

    def reset_retryable_publisher_pages(
            self, bot_max_retries, force_bot_blocks=False):
        """Reset failed Publisher pages that are eligible for retry.

        Ordinary failures remain retryable on the next run. Bot-blocked
        papers are reset only after their persisted cooldown and before the
        configured retry limit; once the limit is reached they stay failed
        until ``force_bot_blocks`` is requested. Legacy rows whose error text
        already says ``bot block`` are treated as quarantined as well.

        Parameters
        ----------
        bot_max_retries : int
            Maximum automatic Bot-block retries before quarantine.
        force_bot_blocks : bool, optional
            Reset Bot-block rows regardless of cooldown or quarantine.

        Returns
        -------
        int
            Number of rows reset to ``pending``.
        """
        max_retries = max(1, int(bot_max_retries))
        conditions = ["publisher_page_fetched_status = 'failed'"]
        parameters = []
        if not force_bot_blocks:
            conditions.append(
                """
                (
                    (
                        COALESCE(publisher_page_failure_kind, '')
                            != 'bot_block'
                        AND LOWER(COALESCE(publisher_page_fetched_error, ''))
                            NOT LIKE '%bot block%'
                    )
                    OR (
                        publisher_page_failure_kind = 'bot_block'
                        AND COALESCE(publisher_page_retry_count, 0) < ?
                        AND (
                            publisher_page_retry_after IS NULL
                            OR publisher_page_retry_after <= ?
                        )
                    )
                )
                """,
            )
            parameters.extend([
                max_retries,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ])

        query = "UPDATE papers SET publisher_page_fetched_status = 'pending'"
        query += " WHERE " + " AND ".join(conditions)
        cur = self.conn.execute(query, tuple(parameters))
        self.conn.commit()
        return cur.rowcount

    def update_publisher_pdf_url(self, doi, pdf_url):
        """
        仅更新 pdf_url 字段，不改变 Phase C 状态。

        用于 Phase E2 对新论文的延迟页面访问（Optica OA 论文跳过了
        Phase C 浏览器访问，但在 Phase E2 下载 PDF 前仍需获取 pdf_url）。

        Args:
            doi:     论文 DOI
            pdf_url: 从出版商页面提取的 PDF 下载链接

        Raises:
            DataBaseDOINotExists: DOI 在数据库中不存在
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update pdf_url."
            )
        self.conn.execute(
            "UPDATE papers SET pdf_url = ? WHERE doi = ?",
            (pdf_url, doi),
        )
        self.conn.commit()

    # ==================================================================
    # Phase E: LLM 相关性判断结果
    # ==================================================================

    def update_relevance_screen(
            self, doi, category, subfields, confidence, notes, status,
            status_date, model_id=None):
        """Persist the title/abstract relevance screening result.

        Parameters
        ----------
        doi : str
            Paper DOI.
        category : str
            Screening category A/B/C/D.
        subfields : str
            JSON encoded matched subfield keys.
        confidence : str
            LLM confidence (high/medium/low).
        notes : str
            Chinese evidence note returned by the LLM.
        status : str
            FetchStatus value.
        status_date : str
            Timestamp of the screening operation.
        model_id : str, optional
            Exact configured model identifier that produced the result.
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(f"DOI {doi} not found in DB")
        self.conn.execute(
            """UPDATE papers SET relevance_screen_category = ?,
                relevance_screen_subfields = ?, relevance_screen_confidence = ?,
                relevance_screen_reason = ?, relevance_screen_status = ?,
                relevance_screen_date = ?, relevance_screen_model = ?,
                relevance_screen_error = NULL
                WHERE doi = ?""",
            (category, subfields, confidence, notes, status, status_date,
             model_id, doi),
        )
        self.conn.commit()

    def update_relevance_screen_error(self, doi, error, status, status_date):
        """Record a screening error without changing the final judgement."""
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(f"DOI {doi} not found in DB")
        self.conn.execute(
            """UPDATE papers SET relevance_screen_error = ?,
                relevance_screen_status = ?, relevance_screen_date = ?
                WHERE doi = ?""",
            (error, status, status_date, doi),
        )
        self.conn.commit()

    def get_relevance_screen_candidates(self, limit=0, pending_only=True,
                                        final_pending_only=False,
                                        require_pdf_url=True):
        """Return only papers eligible for full-text download.

        The queue is deliberately limited to screen A/B/C and low-confidence
        D. Medium/high-confidence D is a terminal rejection and never enters
        the publisher download path.
        """
        conditions = [
            "relevance_screen_status = 'success'",
            "(relevance_screen_category IN ('A', 'B', 'C') "
            "OR (relevance_screen_category = 'D' "
            "AND lower(relevance_screen_confidence) = 'low'))",
        ]
        if pending_only:
            conditions.append("mineru_parse_status = 'pending'")
        if require_pdf_url:
            conditions.append(
                "((pdf_url IS NOT NULL AND pdf_url != '') "
                "OR publisher = 'optica')"
            )
        if final_pending_only:
            conditions.append("llm_relevance_status = 'pending'")
        query = "SELECT * FROM papers WHERE " + " AND ".join(conditions)
        query += """ ORDER BY COALESCE(relevance_screen_is_backfill, 0),
            CASE relevance_screen_category
              WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2 ELSE 3 END,
            created_date DESC"""
        if limit:
            query += " LIMIT ?"
            return self.conn.execute(query, (limit,)).fetchall()
        return self.conn.execute(query).fetchall()

    # ==================================================================
    # 人工相关性审核
    # ==================================================================

    def get_relevance_review_queue(
            self, status_filter="pending", category_filter="all",
            confidence_filter="all", disagreement_only=False,
            search_text="", sort_by="priority", limit=100, offset=0):
        """Return the full-text relevance papers for manual review.

        Parameters
        ----------
        status_filter : str
            ``pending``, ``reviewed`` or ``all``.
        category_filter : str
            Final LLM category, ``all`` or one of A/B/C/D.
        confidence_filter : str
            LLM confidence, ``all`` or high/medium/low.
        disagreement_only : bool
            Restrict results to papers whose screen and final categories differ.
        search_text : str
            Case-insensitive substring matched against DOI and title.
        sort_by : str
            ``priority`` keeps the review-priority order; ``summary`` sorts
            by LLM summary time, newest first, with unsummarized papers last.
        limit : int
            Maximum number of rows.
        offset : int
            Number of rows to skip.

        Returns
        -------
        list[sqlite3.Row]
            Papers with the latest manual review, if any, attached.
        """
        allowed_status = {"pending", "reviewed", "all"}
        allowed_categories = {"all", "A", "B", "C", "D"}
        allowed_confidence = {"all", "high", "medium", "low"}
        allowed_sort = {"priority", "summary"}
        if status_filter not in allowed_status:
            status_filter = "pending"
        if category_filter not in allowed_categories:
            category_filter = "all"
        if confidence_filter not in allowed_confidence:
            confidence_filter = "all"
        if sort_by not in allowed_sort:
            sort_by = "priority"

        conditions = [
            "p.llm_relevance_status = 'success'",
            "p.llm_relevance_basis = 'fulltext'",
        ]
        params = []
        if status_filter == "pending":
            conditions.append("latest_review.id IS NULL")
        elif status_filter == "reviewed":
            conditions.append("latest_review.id IS NOT NULL")
        if category_filter != "all":
            conditions.append("p.llm_relevance_category = ?")
            params.append(category_filter)
        if confidence_filter != "all":
            conditions.append("p.llm_relevance_confidence = ?")
            params.append(confidence_filter)
        if disagreement_only:
            conditions.append(
                "p.relevance_screen_category IS NOT NULL "
                "AND p.relevance_screen_category != p.llm_relevance_category"
            )
        if search_text.strip():
            conditions.append("(LOWER(p.doi) LIKE ? OR LOWER(p.title) LIKE ?)")
            search_pattern = f"%{search_text.strip().lower()}%"
            params.extend([search_pattern, search_pattern])

        where_clause = " AND ".join(conditions)
        query = f"""
            WITH latest_review AS (
                SELECT review.*
                FROM relevance_reviews AS review
                INNER JOIN (
                    SELECT doi, MAX(id) AS latest_id
                    FROM relevance_reviews
                    GROUP BY doi
                ) AS latest
                  ON latest.doi = review.doi
                 AND latest.latest_id = review.id
            )
            SELECT p.id, p.doi, p.title, p.abstract, p.journal, p.publisher,
                   p.page_url, p.pdf_url, p.mineru_output_dir,
                   p.relevance_screen_category,
                   p.relevance_screen_confidence,
                   p.relevance_screen_reason,
                   p.relevance_screen_model,
                   p.llm_relevance_category,
                   p.llm_relevance_subfields,
                   p.llm_relevance_confidence,
                   p.llm_relevance_reason,
                   p.llm_relevance_basis,
                   p.llm_relevance_model,
                   p.llm_relevance_review_model,
                   p.llm_relevance_pre_review_category,
                   p.llm_relevance_date,
                   latest_review.id AS review_id,
                   latest_review.decision AS review_decision,
                   latest_review.notes AS review_notes,
                   latest_review.reviewer AS review_reviewer,
                   latest_review.created_date AS review_date,
                   p.llm_summary_date,
                   CASE
                     WHEN latest_review.id IS NULL THEN 0
                     ELSE 1
                   END AS is_reviewed,
                   CASE
                     WHEN p.relevance_screen_category = 'C'
                          AND p.llm_relevance_pre_review_category IN ('A', 'B')
                       THEN 0
                     WHEN p.llm_relevance_category = 'B'
                          AND p.llm_relevance_confidence = 'medium'
                       THEN 1
                     WHEN p.relevance_screen_category != p.llm_relevance_category
                       THEN 2
                     WHEN p.llm_relevance_category = 'A'
                          AND p.llm_relevance_confidence = 'medium'
                       THEN 3
                     ELSE 4
                   END AS review_priority
            FROM papers AS p
            LEFT JOIN latest_review
              ON latest_review.doi = p.doi
            WHERE {where_clause}
            ORDER BY
                CASE WHEN ? = 'summary'
                     THEN CASE WHEN p.llm_summary_date IS NULL
                                    OR p.llm_summary_date = ''
                               THEN 1 ELSE 0 END
                     ELSE 0 END ASC,
                CASE WHEN ? = 'summary'
                     THEN p.llm_summary_date END DESC,
                CASE WHEN ? = 'summary' THEN is_reviewed END ASC,
                CASE WHEN ? = 'summary' THEN review_priority END ASC,
                CASE WHEN ? = 'summary' THEN p.id END DESC,
                is_reviewed ASC, review_priority ASC,
                p.llm_relevance_date DESC, p.id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([
            sort_by, sort_by, sort_by, sort_by, sort_by,
            max(1, min(int(limit), 200)), max(0, int(offset)),
        ])
        return self.conn.execute(query, tuple(params)).fetchall()

    def count_relevance_review_queue(
            self, status_filter="pending", category_filter="all",
            confidence_filter="all", disagreement_only=False,
            search_text=""):
        """Count papers matching the manual relevance review filters."""
        # Reuse the same filter semantics without loading the queue rows.
        allowed_status = {"pending", "reviewed", "all"}
        allowed_categories = {"all", "A", "B", "C", "D"}
        allowed_confidence = {"all", "high", "medium", "low"}
        if status_filter not in allowed_status:
            status_filter = "pending"
        if category_filter not in allowed_categories:
            category_filter = "all"
        if confidence_filter not in allowed_confidence:
            confidence_filter = "all"
        conditions = [
            "p.llm_relevance_status = 'success'",
            "p.llm_relevance_basis = 'fulltext'",
        ]
        params = []
        if status_filter == "pending":
            conditions.append("r.latest_id IS NULL")
        elif status_filter == "reviewed":
            conditions.append("r.latest_id IS NOT NULL")
        if category_filter != "all":
            conditions.append("p.llm_relevance_category = ?")
            params.append(category_filter)
        if confidence_filter != "all":
            conditions.append("p.llm_relevance_confidence = ?")
            params.append(confidence_filter)
        if disagreement_only:
            conditions.append(
                "p.relevance_screen_category IS NOT NULL "
                "AND p.relevance_screen_category != p.llm_relevance_category"
            )
        if search_text.strip():
            conditions.append("(LOWER(p.doi) LIKE ? OR LOWER(p.title) LIKE ?)")
            search_pattern = f"%{search_text.strip().lower()}%"
            params.extend([search_pattern, search_pattern])
        where_clause = " AND ".join(conditions)
        query = f"""
            WITH latest_review AS (
                SELECT doi, MAX(id) AS latest_id
                FROM relevance_reviews
                GROUP BY doi
            )
            SELECT COUNT(*)
            FROM papers AS p
            LEFT JOIN latest_review AS r ON r.doi = p.doi
            WHERE {where_clause}
        """
        return self.conn.execute(query, tuple(params)).fetchone()[0]

    def save_relevance_review(
            self, doi, decision, notes="", reviewer=""):
        """Append a manual relevance review and return its database id.

        Parameters
        ----------
        doi : str
            DOI of an existing paper.
        decision : str
            One of A/B/C/D/uncertain.
        notes : str
            Human evidence and reasoning.
        reviewer : str
            Optional reviewer name or initials.

        Returns
        -------
        int
            Newly created review id.
        """
        normalized_doi = (doi or "").strip().lower()
        normalized_decision = (decision or "").strip().lower()
        if normalized_decision not in {"a", "b", "c", "d", "uncertain"}:
            raise ValueError("decision must be A, B, C, D or uncertain")
        if not self.paper_doi_exists(normalized_doi):
            raise DataBaseDOINotExists(f"DOI {doi} not found in DB")
        paper = self.conn.execute(
            """SELECT llm_relevance_status, llm_relevance_basis,
                      llm_relevance_category, llm_relevance_confidence,
                      relevance_screen_model, llm_relevance_model,
                      llm_relevance_review_model
               FROM papers WHERE LOWER(doi) = LOWER(?)""",
            (normalized_doi,),
        ).fetchone()
        if (
            paper["llm_relevance_status"] != FetchStatus.SUCCESS.value
            or paper["llm_relevance_basis"] != "fulltext"
        ):
            raise ValueError(
                "manual review requires a successful full-text relevance result"
            )
        stored_decision = (
            normalized_decision
            if normalized_decision == "uncertain"
            else normalized_decision.upper()
        )
        timestamp = str(datetime.now())
        cursor = self.conn.execute(
            """INSERT INTO relevance_reviews
               (doi, decision, notes, reviewer, source_final_category,
                source_final_confidence, source_screen_model,
                source_final_model, source_review_model, created_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (normalized_doi, stored_decision,
             (notes or "").strip(), (reviewer or "").strip(),
             paper["llm_relevance_category"],
             paper["llm_relevance_confidence"],
             paper["relevance_screen_model"], paper["llm_relevance_model"],
             paper["llm_relevance_review_model"], timestamp),
        )
        self.conn.commit()
        return cursor.lastrowid

    @staticmethod
    def _local_date():
        """Return the project-local calendar date (Asia/Shanghai)."""
        return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    def claim_fulltext_download(self, doi, publisher, daily_max=3,
                                publisher_daily_max=2):
        """Atomically reserve one daily PDF attempt.

        Failed attempts consume the reservation too.  ``BEGIN IMMEDIATE``
        serializes concurrent callers, so repeated/manual runs cannot bypass
        the hard limits.

        Returns
        -------
        bool
            True when a reservation was inserted, otherwise False.
        """
        local_date = self._local_date()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            total = self.conn.execute(
                "SELECT COUNT(*) FROM fulltext_download_events "
                "WHERE local_date = ? AND status != 'skipped'",
                (local_date,),
            ).fetchone()[0]
            source = self.conn.execute(
                "SELECT COUNT(*) FROM fulltext_download_events "
                "WHERE local_date = ? AND publisher = ? AND status != 'skipped'",
                (local_date, publisher or "__unknown__"),
            ).fetchone()[0]
            already_claimed = self.conn.execute(
                "SELECT 1 FROM fulltext_download_events "
                "WHERE local_date = ? AND doi = ? LIMIT 1",
                (local_date, doi),
            ).fetchone()
            if already_claimed:
                self.conn.rollback()
                return False
            if total >= int(daily_max) or source >= int(publisher_daily_max):
                self.conn.rollback()
                return False
            self.conn.execute(
                """INSERT INTO fulltext_download_events
                   (doi, publisher, local_date, attempted_at, status)
                   VALUES (?, ?, ?, ?, 'reserved')""",
                (doi, publisher or "__unknown__", local_date,
                 datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()),
            )
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def finish_fulltext_download(self, doi, status, error=None, details=None):
        """Update the most recent reservation for ``doi``.

        Parameters
        ----------
        details : dict, optional
            Structured transport diagnostics persisted as JSON columns.
        """
        details = details or {}
        import json
        self.conn.execute(
            """UPDATE fulltext_download_events SET status = ?, error = ?,
               location_source = ?, route = ?, requested_url = ?,
               final_url = ?, http_status = ?, content_type = ?,
               failure_kind = ?, details_json = ?
               WHERE id = (SELECT id FROM fulltext_download_events
                           WHERE doi = ? ORDER BY id DESC LIMIT 1)""",
            (status, error, details.get("location_source"), details.get("route"),
             details.get("requested_url"), details.get("final_url"),
             details.get("http_status"), details.get("content_type"),
             details.get("failure_kind"), json.dumps(details, ensure_ascii=False),
             doi),
        )
        self.conn.commit()

    def get_fulltext_download_failures(self, since_date=None):
        """Return failed PDF/MinerU attempts grouped by their audit dates.

        Parameters
        ----------
        since_date : str, optional
            Inclusive local date in ``YYYY-MM-DD`` format. If omitted, all
            recorded failed attempts are returned.

        Returns
        -------
        list of dict
            Each item contains ``doi``, ``local_date`` and ``error``.
        """
        where = "WHERE status = 'failed'"
        params = []
        if since_date:
            where += " AND local_date >= ?"
            params.append(str(since_date))
        rows = self.conn.execute(
            "SELECT doi, local_date, error FROM fulltext_download_events "
            f"{where} ORDER BY local_date, doi, id",
            params,
        ).fetchall()
        return [
            {
                "doi": row["doi"],
                "local_date": row["local_date"],
                "error": row["error"] or "",
            }
            for row in rows
        ]

    def migrate_relevance_screen_snapshot(self):
        """Backfill screen columns from existing final relevance results."""
        # Repair snapshots created by the first migration revision, which
        # copied the final result but left the default is_backfill=0.  Exact
        # status/date equality plus a missing final basis distinguishes those
        # legacy copies from a genuinely new Phase E screen.
        self.conn.execute("""UPDATE papers
            SET relevance_screen_is_backfill = 1
            WHERE COALESCE(relevance_screen_is_backfill, 0) = 0
              AND llm_relevance_basis IS NULL
              AND relevance_screen_status IN ('success', 'skipped')
              AND relevance_screen_status = llm_relevance_status
              AND relevance_screen_date IS llm_relevance_date""")
        self.conn.execute("""UPDATE papers SET relevance_screen_status =
            CASE WHEN llm_relevance_status IN ('success', 'skipped')
                 THEN llm_relevance_status ELSE COALESCE(relevance_screen_status, 'pending') END,
            relevance_screen_category = COALESCE(relevance_screen_category, llm_relevance_category),
            relevance_screen_subfields = COALESCE(relevance_screen_subfields, llm_relevance_subfields),
            relevance_screen_confidence = COALESCE(relevance_screen_confidence, llm_relevance_confidence),
            relevance_screen_reason = COALESCE(relevance_screen_reason, llm_relevance_reason),
            relevance_screen_date = COALESCE(relevance_screen_date, llm_relevance_date),
            relevance_screen_is_backfill = 1
            WHERE (relevance_screen_status IS NULL
                   OR relevance_screen_status = 'pending')
              AND llm_relevance_status IN ('success', 'skipped')""")

        # ``abstract_fallback`` was a temporary design that allowed A/B
        # screening results into reports before full-text adjudication.  Keep
        # the screen snapshot but reopen those legacy records so E2/E3 can
        # retry them; never let a legacy abstract-only summary stand in for a
        # full-text review.
        self.conn.execute("""UPDATE papers
            SET llm_relevance_status = 'pending',
                llm_relevance_category = NULL,
                llm_relevance_subfields = NULL,
                llm_relevance_confidence = NULL,
                llm_relevance_reason = NULL,
                llm_relevance_basis = NULL,
                llm_relevance_model = NULL,
                llm_relevance_review_model = NULL,
                llm_relevance_pre_review_category = NULL,
                llm_relevance_error = NULL,
                llm_relevance_date = NULL,
                llm_summary_status = 'pending',
                llm_summary_error = NULL,
                llm_summary_date = NULL,
                llm_summary_result = NULL
            WHERE llm_relevance_basis = 'abstract_fallback'""")
        self.conn.commit()

    def update_llm_relevance(
            self, doi, category, subfields, confidence, notes, status,
            status_date, basis=None, model_id=None, review_model_id=None,
            pre_review_category=None):
        """Persist the final LLM relevance decision and model provenance.

        Parameters
        ----------
        doi : str
            Paper DOI.
        category : str
            Final A/B/C/D category.
        subfields : str
            JSON encoded matched subfield keys.
        confidence : str
            Model-reported confidence.
        notes : str
            Evidence note returned by the final decision model.
        status : str
            FetchStatus value.
        status_date : str
            Processing timestamp.
        basis : str, optional
            Evidence basis such as ``fulltext``.
        model_id : str, optional
            Primary model used for full-text adjudication.
        review_model_id : str, optional
            Independent model used for a configured transition review.
        pre_review_category : str, optional
            Primary model category before transition review.
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update LLM relevance."
            )
        self.conn.execute(
            """
            UPDATE papers
            SET llm_relevance_category = ?,
                llm_relevance_subfields = ?,
                llm_relevance_confidence = ?,
                llm_relevance_reason = ?,
                llm_relevance_basis = ?,
                llm_relevance_model = ?,
                llm_relevance_review_model = ?,
                llm_relevance_pre_review_category = ?,
                llm_relevance_status = ?,
                llm_relevance_date = ?
            WHERE doi = ?
            """,
            (category, subfields, confidence, notes, basis, model_id,
             review_model_id, pre_review_category, status, status_date, doi),
        )
        self.conn.commit()

    def update_llm_relevance_error(self, doi, error, status, status_date):
        """
        Phase E 错误处理: 记录 LLM 相关性判断失败信息。

        Args:
            doi:         论文 DOI
            error:       错误描述字符串
            status:      FetchStatus.FAILED.value
            status_date: 处理日期时间字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update LLM relevance error."
            )
        self.conn.execute(
            """
            UPDATE papers
            SET llm_relevance_error = ?,
                llm_relevance_status = ?,
                llm_relevance_date = ?
            WHERE doi = ?
            """,
            (error, status, status_date, doi),
        )
        self.conn.commit()

    # ==================================================================
    # Phase F: LLM 论文总结结果
    # ==================================================================

    def update_llm_summary(self, doi, summary_json, status, status_date):
        """
        Phase F 专用: 存储 LLM 生成的论文结构化总结。

        summary_json 是一个合法的 JSON 字符串，包含:
          one_sentence, motivation_and_goal, key_setup_and_method,
          main_results_and_physics, take_home_message

        Raises:
            DataBaseDOINotExists: DOI 在数据库中不存在

        Args:
            doi:          论文 DOI
            summary_json: LLM 返回的 JSON 字符串 (已验证合法)
            status:       FetchStatus 状态值
            status_date:  处理日期时间字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update LLM summary."
            )
        self.conn.execute(
            """
            UPDATE papers
            SET llm_summary_result = ?,
                llm_summary_status = ?,
                llm_summary_date = ?
            WHERE doi = ?
            """,
            (summary_json, status, status_date, doi),
        )
        self.conn.commit()

    def update_llm_summary_error(self, doi, error, status, status_date):
        """
        Phase F 错误处理: 记录 LLM 总结失败信息。

        Args:
            doi:         论文 DOI
            error:       错误描述字符串
            status:      FetchStatus.FAILED.value
            status_date: 处理日期时间字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update LLM summary error."
            )
        self.conn.execute(
            """
            UPDATE papers
            SET llm_summary_error = ?,
                llm_summary_status = ?,
                llm_summary_date = ?
            WHERE doi = ?
            """,
            (error, status, status_date, doi),
        )
        self.conn.commit()

    def get_pending_summary_papers(self, limit=0):
        """Return only full-text A/B papers eligible for Phase F.

        Parameters
        ----------
        limit : int, optional
            Maximum number of papers. ``0`` means no limit.

        Returns
        -------
        list[sqlite3.Row]
            Pending summary records ordered from oldest to newest.
        """
        query = f"""
        {LATEST_RELEVANCE_REVIEW_CTE}
        SELECT p.*,
               {EFFECTIVE_RELEVANCE_CATEGORY_SQL}
                   AS effective_relevance_category,
               latest_relevance_review.decision
                   AS manual_relevance_decision,
               latest_relevance_review.notes AS manual_relevance_notes
        FROM papers AS p
        LEFT JOIN latest_relevance_review
          ON latest_relevance_review.doi = p.doi
        WHERE p.llm_summary_status = 'pending'
          AND p.llm_relevance_status = 'success'
          AND {EFFECTIVE_RELEVANCE_CATEGORY_SQL} IN ('A', 'B')
          AND p.llm_relevance_basis = 'fulltext'
        ORDER BY p.created_date
        """
        parameters = ()
        if limit:
            query += " LIMIT ?"
            parameters = (limit,)
        return self.conn.execute(query, parameters).fetchall()

    # ==================================================================
    # Phase E2: MinerU PDF 全文解析
    # ==================================================================

    def update_mineru_result(self, doi, fulltext, output_dir, status, status_date):
        """
        Phase E2 专用: 存储 MinerU PDF 解析得到的全文 Markdown 文本和输出路径。

        fulltext 来自 MinerU 输出目录下的 full.md 文件内容。
        output_dir 为 MinerU 输出目录的相对路径（如 mineru_output/10_1103_xxx）。
        该文本将在 Phase F (LLM 总结) 中替代标题+摘要作为输入。

        Raises:
            DataBaseDOINotExists: DOI 在数据库中不存在

        Args:
            doi:         论文 DOI
            fulltext:    MinerU 解析出的 Markdown 全文
            output_dir:  MinerU 输出目录相对路径（含 paper.pdf）
            status:      FetchStatus 状态值
            status_date: 处理日期时间字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update MinerU result."
            )
        self.conn.execute(
            """
            UPDATE papers
            SET mineru_fulltext = ?,
                mineru_output_dir = ?,
                mineru_parse_status = ?,
                mineru_parse_error = NULL,
                mineru_parse_date = ?
            WHERE doi = ?
            """,
            (fulltext, output_dir, status, status_date, doi),
        )
        self.conn.commit()

    def update_mineru_error(self, doi, error, status, status_date):
        """
        Phase E2 错误处理: 记录 MinerU 解析失败信息。

        Args:
            doi:         论文 DOI
            error:       错误描述字符串
            status:      FetchStatus.FAILED.value
            status_date: 处理日期时间字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update MinerU error."
            )
        self.conn.execute(
            """
            UPDATE papers
            SET mineru_parse_error = ?,
                mineru_parse_status = ?,
                mineru_parse_date = ?
            WHERE doi = ?
            """,
            (error, status, status_date, doi),
        )
        self.conn.commit()

    # ==================================================================
    # 报告阶段查询方法
    # ==================================================================

    def get_relevant_papers(self):
        """
        获取当前有效判定为相关的论文（A/B 类）。

        查询条件: 无人工审核时使用 LLM 分类，有审核时使用最新人工分类；有效分类为 A/B。
        排序: 按 RSS 日期倒序

        Returns:
            list[sqlite3.Row]
        """
        cur = self.conn.execute(f"""
        {LATEST_RELEVANCE_REVIEW_CTE}
        SELECT p.*,
               {EFFECTIVE_RELEVANCE_CATEGORY_SQL}
                   AS effective_relevance_category,
               latest_relevance_review.decision
                   AS manual_relevance_decision,
               latest_relevance_review.notes AS manual_relevance_notes
        FROM papers AS p
        LEFT JOIN latest_relevance_review
          ON latest_relevance_review.doi = p.doi
        WHERE {EFFECTIVE_RELEVANCE_CATEGORY_SQL} IN ('A', 'B')
          AND p.llm_relevance_status = 'success'
        ORDER BY p.paperdate_rss DESC
        """)
        return cur.fetchall()

    def get_papers_for_report(self):
        """
        获取待汇入报告的新论文：全文终审和 LLM 总结均成功且尚未被报告过。

        查询条件: llm_summary_status = 'success'
                  AND report_date IS NULL
                  AND 有效相关性分类 IN ('A', 'B')；最新人工审核结果覆盖 LLM 分类
                  AND llm_relevance_status = 'success'
                  AND llm_relevance_basis = 'fulltext'
        用 report_date 替代 report_status 作为过滤条件，支持按日期重置重报。
        显式加 relevance 过滤是必要的：相关性重判不会重置 llm_summary_* 字段，若论文
        被从 A/B 重判为 C/D，summary_status 仍为 'success'，没有此过滤会被误入报。
        排序: 按 RSS 日期倒序。

        Returns:
            list[sqlite3.Row]
        """
        cur = self.conn.execute(f"""
        {LATEST_RELEVANCE_REVIEW_CTE}
        SELECT p.*,
               {EFFECTIVE_RELEVANCE_CATEGORY_SQL}
                   AS effective_relevance_category,
               latest_relevance_review.decision
                   AS manual_relevance_decision,
               latest_relevance_review.notes AS manual_relevance_notes
        FROM papers AS p
        LEFT JOIN latest_relevance_review
          ON latest_relevance_review.doi = p.doi
        WHERE p.llm_summary_status = 'success'
          AND p.report_date IS NULL
          AND {EFFECTIVE_RELEVANCE_CATEGORY_SQL} IN ('A', 'B')
          AND p.llm_relevance_status = 'success'
          AND p.llm_relevance_basis = 'fulltext'
        ORDER BY p.paperdate_rss DESC
        """)
        return cur.fetchall()

    def mark_papers_reported(self, dois, timestamp):
        """
        批量标记论文为已报告。

        将指定 DOI 列表的论文 report_status 设为 'reported'，
        并记录报告时间。get_papers_for_report 使用 report_date IS NULL 过滤，
        因此设置了 report_date 的论文将不再出现在后续报告中，除非通过
        reset-report --days 重置。

        Args:
            dois:      论文 DOI 列表
            timestamp: 报告生成时间戳字符串
        """
        for doi in dois:
            self.conn.execute(
                """
                UPDATE papers
                SET report_status = 'reported', report_date = ?
                WHERE doi = ?
                """,
                (timestamp, doi),
            )
        self.conn.commit()

    def get_papers_with_summaries(self):
        """
        获取所有有 LLM 总结的论文（含总结日期）。

        用于 Web UI 报告页面展示可选论文列表。

        Returns:
            list[sqlite3.Row]
        """
        cur = self.conn.execute("""
        SELECT doi, title, abstract, journal, publisher,
               paperdate_rss, llm_summary_date,
               llm_summary_result, authors_json,
               page_url, pdf_url
        FROM papers
        WHERE llm_summary_status = 'success'
        ORDER BY paperdate_rss DESC
        """)
        return cur.fetchall()

    def get_papers(
        self, limit=100, offset=0, sort_by="created", category_filter=None,
        has_summary=False,
    ):
        """
        返回论文列表，支持按入库日期或发表日期排序。

        Parameters
        ----------
        limit : int
            返回最大行数（每页条数）
        offset : int
            跳过的行数（分页偏移）
        sort_by : str
            "created" = 按入库日期降序（默认）
            "published" = 按发表日期降序（COALESCE page > crossref > rss）
            "summary" = 按 LLM 总结生成时间（llm_summary_date）降序
        category_filter : str | None
            None / "all" = 不过滤（所有论文）
            "a" = 仅 LLM 判定为 A（直接相关）的论文
            "b" = 仅 LLM 判定为 B（方法相关）的论文
            "ab" = A 和 B 全部
        has_summary : bool
            If True, return only papers with a successful LLM summary.

        Returns
        -------
        list[sqlite3.Row]
        """
        order_clause = {
            "created": "created_date DESC",
            "published": ("COALESCE(paperdate_page, paperdate_crossref, "
                          "paperdate_rss) DESC, created_date DESC"),
            "summary": "llm_summary_date DESC, created_date DESC",
        }
        order = order_clause.get(sort_by, order_clause["created"])
        category_where = {
            "ab": ("llm_relevance_status = 'success' "
                   "AND llm_relevance_category IN ('A', 'B')"),
            "a":  ("llm_relevance_status = 'success' "
                   "AND llm_relevance_category = 'A'"),
            "b":  ("llm_relevance_status = 'success' "
                   "AND llm_relevance_category = 'B'"),
        }
        conditions = []
        cond = category_where.get(category_filter)
        if cond:
            conditions.append(cond)
        if has_summary:
            conditions.append("llm_summary_status = 'success'")
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cur = self.conn.execute(f"""
        SELECT doi, title, abstract, journal, publisher,
               paperdate_rss, paperdate_crossref, paperdate_page,
               created_date,
               llm_relevance_result, llm_relevance_category,
               llm_relevance_subfields, llm_relevance_status,
               llm_relevance_date,
               llm_summary_status, llm_summary_date, llm_summary_result
        FROM papers
        {where_clause}
        ORDER BY
          CASE WHEN llm_relevance_status IN ('skipped', 'pending') THEN 1 ELSE 0 END,
          {order}
        LIMIT ? OFFSET ?
        """, (limit, offset))
        return cur.fetchall()

    def get_papers_count(self, category_filter=None, has_summary=False):
        """
        统计满足分类筛选的论文总数（不受 limit/offset 影响），用于分页。

        Parameters
        ----------
        category_filter : str | None
            同 get_papers()。注意 sort_by 不影响计数。
        has_summary : bool
            If True, count only papers with a successful LLM summary.

        Returns
        -------
        int
        """
        category_where = {
            "ab": ("llm_relevance_status = 'success' "
                   "AND llm_relevance_category IN ('A', 'B')"),
            "a":  ("llm_relevance_status = 'success' "
                   "AND llm_relevance_category = 'A'"),
            "b":  ("llm_relevance_status = 'success' "
                   "AND llm_relevance_category = 'B'"),
        }
        conditions = []
        cond = category_where.get(category_filter)
        if cond:
            conditions.append(cond)
        if has_summary:
            conditions.append("llm_summary_status = 'success'")
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cur = self.conn.execute(f"SELECT COUNT(*) FROM papers {where_clause}")
        return cur.fetchone()[0]

    def count_reset_impact(self, columns_where):
        """
        统计重置操作将影响哪些列及各自的行数。

        columns_where 格式: [(col1, cond1), (col2, cond2), ...]
        其中 cond 是 SQL WHERE 子句片段（不含 WHERE 关键字），
        或 None 表示该列全部重置。

        Returns:
            dict[str, int]: {列名: 影响行数}
        """
        result = {}
        for col, cond in columns_where:
            self._validate_column(col)
            sql = f"SELECT COUNT(*) FROM papers WHERE {cond}" if cond else "SELECT COUNT(*) FROM papers"
            cur = self.conn.execute(sql)
            result[col] = cur.fetchone()[0]
        return result

    def batch_reset_status(self, updates, conditions):
        """
        批量重置指定列的状态。

        Args:
            updates: [(列名, 新值), ...] 如 [("llm_relevance_status", "pending")]
            conditions: SQL WHERE 子句片段（不含 WHERE），如 "doi IN (?,?,?)"
                         或 None 表示全部

        Returns:
            int: 受影响行数
        """
        for col, _ in updates:
            self._validate_column(col)
        set_clause = ", ".join(f"{col} = ?" for col, _ in updates)
        values = [val for _, val in updates]
        sql = f"UPDATE papers SET {set_clause}"
        if conditions:
            sql += f" WHERE {conditions}"
        cur = self.conn.execute(sql, values)
        self.conn.commit()
        return cur.rowcount

    def get_all_papers(self):
        """
        获取数据库中所有论文记录。

        排序: 按创建日期倒序

        Returns:
            list[sqlite3.Row]
        """
        cur = self.conn.execute("SELECT * FROM papers ORDER BY created_date DESC")
        return cur.fetchall()

    def get_run_metrics(self, run_started_at):
        """Collect status metrics changed during one pipeline run.

        Parameters
        ----------
        run_started_at : datetime or str
            Lower bound for the phase status timestamps. The phase modules
            persist local ``datetime.now()`` strings, so the comparison is
            intentionally made against the same lexically sortable format.

        Returns
        -------
        dict
            Counts for E screening, E3 final relevance, F summaries, a
            bounded list of database error samples from this run, and the
            recent DOI-level failed PDF/MinerU download history.
        """
        started_text = str(run_started_at)

        def collect(status_column, date_column, category_column=None):
            rows = self.conn.execute(
                f"SELECT COALESCE({status_column}, 'pending') AS status, "
                f"COUNT(*) AS count FROM papers "
                f"WHERE {date_column} >= ? GROUP BY status",
                (started_text,),
            ).fetchall()
            status_counts = {
                "success": 0, "failed": 0, "skipped": 0, "pending": 0,
            }
            for row in rows:
                status_counts[row["status"]] = row["count"]

            category_counts = {category: 0 for category in ("A", "B", "C", "D")}
            if category_column:
                category_rows = self.conn.execute(
                    f"SELECT {category_column} AS category, COUNT(*) AS count "
                    f"FROM papers WHERE {date_column} >= ? "
                    f"AND {status_column} IN ('success', 'skipped') "
                    f"AND {category_column} IN ('A', 'B', 'C', 'D') "
                    f"GROUP BY {category_column}",
                    (started_text,),
                ).fetchall()
                for row in category_rows:
                    category_counts[row["category"]] = row["count"]
            return {
                "status_counts": status_counts,
                "category_counts": category_counts,
            }

        metrics = {
            "relevance_screen": collect(
                "relevance_screen_status", "relevance_screen_date",
                "relevance_screen_category",
            ),
            "final_relevance": collect(
                "llm_relevance_status", "llm_relevance_date",
                "llm_relevance_category",
            ),
            "summary": collect("llm_summary_status", "llm_summary_date"),
        }

        error_columns = [
            ("B", "cr_metadata_fetched_error", "cr_metadata_fetched_date"),
            ("C", "publisher_page_fetched_error", "publisher_page_fetched_date"),
            ("E", "relevance_screen_error", "relevance_screen_date"),
            ("E2", "mineru_parse_error", "mineru_parse_date"),
            ("E3", "llm_relevance_error", "llm_relevance_date"),
            ("F", "llm_summary_error", "llm_summary_date"),
        ]
        error_samples = []
        for stage, error_column, date_column in error_columns:
            rows = self.conn.execute(
                f"SELECT doi, {error_column} AS error FROM papers "
                f"WHERE {date_column} >= ? AND {error_column} IS NOT NULL "
                f"AND {error_column} != '' ORDER BY {date_column} LIMIT 20",
                (started_text,),
            ).fetchall()
            for row in rows:
                error_samples.append({
                    "stage": stage,
                    "doi": row["doi"],
                    "message": row["error"],
                })
        metrics["error_samples"] = error_samples
        if isinstance(run_started_at, datetime):
            run_date = run_started_at.date()
        else:
            run_date = datetime.fromisoformat(str(run_started_at)[:19]).date()
        metrics["mineru_download_failures"] = self.get_fulltext_download_failures(
            (run_date - timedelta(days=13)).isoformat()
        )
        return metrics

    # ── Phase stats (用于 WebUI Pipeline 看板) ────────────────────────────

    def get_phase_stats(self):
        """获取每个阶段的论文状态分布和错误文本。

        对每个阶段返回:
            status_counts: dict[str, int] — success/failed/skipped/pending 计数
            error_texts: list[str]       — status 为 failed/skipped 的论文的原始 error 文本

        Returns:
            list[dict]: 每个阶段一个 dict, 包含 label / status_counts / error_texts 字段。
        """
        phase_configs = [
            ("cr_metadata_fetched", "cr_metadata_fetched_status", "cr_metadata_fetched_error"),
            ("publisher_page", "publisher_page_fetched_status", "publisher_page_fetched_error"),
            ("relevance_screen", "relevance_screen_status", "relevance_screen_error"),
            ("mineru_parse", "mineru_parse_status", "mineru_parse_error"),
            ("llm_relevance", "llm_relevance_status", "llm_relevance_error"),
            ("llm_summary", "llm_summary_status", "llm_summary_error"),
            ("report", "report_status", None),
        ]
        results = []
        for label, status_col, error_col in phase_configs:
            # Status counts
            rows = self.conn.execute(
                f"SELECT COALESCE({status_col}, 'pending') AS status, COUNT(*) AS cnt "
                f"FROM papers GROUP BY status"
            ).fetchall()
            counts = {"success": 0, "failed": 0, "skipped": 0, "pending": 0}
            for r in rows:
                status = r["status"]
                if label == "report" and status == "reported":
                    status = "success"
                counts[status] = counts.get(status, 0) + r["cnt"]

            # Error texts for failed/skipped papers. Report status has no
            # dedicated error column, so it contributes an empty list.
            error_texts: list[str] = []
            if error_col:
                err_rows = self.conn.execute(
                    f"SELECT {error_col} FROM papers "
                    f"WHERE {status_col} IN ('failed','skipped') "
                    f"AND {error_col} IS NOT NULL AND {error_col} != ''"
                ).fetchall()
                for r in err_rows:
                    error_texts.append(r[error_col])

            results.append({
                "label": label,
                "status_counts": counts,
                "error_texts": error_texts,
            })
        return results


    # ==================================================================
    # 通用状态更新方法（向后兼容 + 灵活场景）
    # ==================================================================

    # ==================================================================
    # 通用状态更新方法（向后兼容 + 灵活场景）
    # ==================================================================

    def update_process_status(self, doi, status_field, status_code,
                               status_field_date, timestamp):
        """
        通用方法: 更新任意处理阶段的状态和日期。

        这是最灵活的状态更新方法，适用于不需要存储额外数据（如作者、摘要等）
        的场景。例如: 将 Phase B 标记为 success 同时记录处理时间。

        Args:
            doi:              论文 DOI
            status_field:     状态列名 (如 "cr_metadata_fetched_status")
            status_code:      状态值 (如 FetchStatus.SUCCESS.value)
            status_field_date: 日期列名 (如 "cr_metadata_fetched_date")
            timestamp:        时间戳字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(f"DOI {doi} not found in DB.")
        self._validate_column(status_field)
        self._validate_column(status_field_date)
        self.conn.execute(f"""
            UPDATE papers
            SET {status_field} = ?, {status_field_date} = ?
            WHERE doi = ?
            """,
            (status_code, timestamp, doi),
        )
        self.conn.commit()

    def update_error_message(self, doi, status_field, status_code,
                              error_field, message, error_field_date, timestamp):
        """
        通用方法: 更新任意处理阶段的错误状态、错误信息和日期。

        用于记录处理失败时的详细错误信息。

        Args:
            doi:              论文 DOI
            status_field:     状态列名 (如 "cr_metadata_fetched_status")
            status_code:      状态值 (如 FetchStatus.FAILED.value)
            error_field:      错误信息列名 (如 "cr_metadata_fetched_error")
            message:          错误描述 (会被截断到 500 字符以内)
            error_field_date: 日期列名
            timestamp:        时间戳字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(f"DOI {doi} not found in DB.")
        self._validate_column(status_field)
        self._validate_column(error_field)
        self._validate_column(error_field_date)
        self.conn.execute(f"""
            UPDATE papers
            SET {status_field} = ?, {error_field} = ?, {error_field_date} = ?
            WHERE doi = ?
            """,
            (status_code, message, timestamp, doi),
        )
        self.conn.commit()

    def delete_paper(self, doi):
        """从数据库中删除指定 DOI 的论文记录。

        Parameters
        ----------
        doi : str
            要删除的论文 DOI。
        """
        self.conn.execute("DELETE FROM papers WHERE doi = ?", (doi,))
        self.conn.commit()

    def get_publisher_page_stats(self, days: int = 7):
        """获取各出版社页面抓取状态统计，可选时间范围。

        Parameters
        ----------
        days : int or None
            统计最近 N 天内的记录。为 None 时不限时间，统计全部。

        Returns
        -------
        dict[str, dict[str, int]]
            {publisher: {"success": N, "failed": N, "skipped": N, "pending": N}}
        """
        if days is not None:
            cur = self.conn.execute(
                "SELECT publisher, publisher_page_fetched_status, COUNT(*) as cnt "
                "FROM papers "
                "WHERE publisher_page_fetched_date "
                ">= datetime('now', ? || ' days', 'localtime') "
                "GROUP BY publisher, publisher_page_fetched_status",
                (str(-days),),
            )
        else:
            cur = self.conn.execute(
                "SELECT publisher, publisher_page_fetched_status, COUNT(*) as cnt "
                "FROM papers GROUP BY publisher, publisher_page_fetched_status"
            )
        rows = cur.fetchall()
        stats: dict[str, dict[str, int]] = {}
        for row in rows:
            pub = row["publisher"] or "unknown"
            status = row["publisher_page_fetched_status"] or "pending"
            cnt = row["cnt"]
            if pub not in stats:
                stats[pub] = {"success": 0, "failed": 0, "skipped": 0, "pending": 0}
            if status in stats[pub]:
                stats[pub][status] = cnt
        return stats
