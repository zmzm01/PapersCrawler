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
  │    Phase D: semantic_filter_*         → 语义相似度初筛              │
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

import sqlite3
from enum import Enum


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

    def __init__(self, dbPath):
        """
        打开数据库连接。

        Args:
            dbPath: SQLite 数据库文件路径 (字符串或 Path 对象)
                   文件不存在时会自动创建。
        """
        # sqlite3.Row 工厂使查询结果支持通过列名访问: row["doi"]
        self.conn = sqlite3.connect(str(dbPath))
        self.conn.row_factory = sqlite3.Row

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
    Phase D — 语义相似度初筛:   semantic_filter_*
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

            -- Publisher 页面抓取状态
            publisher_page_fetched_status TEXT DEFAULT 'pending',
            publisher_page_fetched_error TEXT,
            publisher_page_fetched_date TEXT,

            -- LLM 相关性判断
            llm_relevance_status TEXT DEFAULT 'pending',
            llm_relevance_result INTEGER DEFAULT 0,
            llm_relevance_confidence TEXT,
            llm_relevance_reason TEXT,
            llm_relevance_error TEXT,
            llm_relevance_date TEXT,

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

            -- 语义相似度初筛
            semantic_similarity_score REAL,
            semantic_filter_status TEXT DEFAULT 'pending',
            semantic_filter_error TEXT,
            semantic_filter_date TEXT,

            -- 报告生成状态
            report_status TEXT DEFAULT 'pending',
            report_date TEXT,

            -- 时间戳
            created_date TEXT,
            updated_date TEXT
        )
        """)

        # 提交 DDL 操作
        self.conn.commit()

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
            col_name = col_def.split()[0]
            try:
                self.conn.execute(f"ALTER TABLE papers ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # 列已存在则跳过

        # ---- 迁移: 为旧数据库添加语义过滤列 ----
        semantic_columns = [
            "semantic_similarity_score REAL",
            "semantic_filter_status TEXT DEFAULT 'pending'",
            "semantic_filter_error TEXT",
            "semantic_filter_date TEXT",
        ]
        for col_def in semantic_columns:
            col_name = col_def.split()[0]
            try:
                self.conn.execute(f"ALTER TABLE papers ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # 列已存在则跳过

        # ---- 迁移: 为旧数据库添加报告状态列 ----
        report_columns = [
            "report_status TEXT DEFAULT 'pending'",
            "report_date TEXT",
        ]
        for col_def in report_columns:
            col_name = col_def.split()[0]
            try:
                self.conn.execute(f"ALTER TABLE papers ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # 列已存在则跳过

    # ==================================================================
    # 基本查询方法
    # ==================================================================

    def paper_doi_exists(self, doi):
        """
        检查某 DOI 是否已存在于数据库中。

        用于 RSS 阶段去重: 同一篇论文不会被重复插入。

        Args:
            doi: 论文 DOI 字符串
        Returns:
            bool: True 表示已存在, False 表示不存在
        """
        cur = self.conn.execute("SELECT 1 FROM papers WHERE doi = ?", (doi,))
        return cur.fetchone() is not None

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
        cur = self.conn.execute(f"""
        SELECT * FROM papers
        WHERE {status_field} = ?
        ORDER BY created_date
        """, (status_value,))
        return cur.fetchall()

    # ==================================================================
    # Phase A: RSS 基本信息写入
    # ==================================================================

    def insert_rss_basicinfo(self, doi, title, link, journal, publisher, updated):
        """
        Phase A 专用: 将 RSS 抓取的论文基本信息写入数据库。

        此方法不做去重检查 — 调用方必须先用 paper_doi_exists() 判断。

        Args:
            doi:       论文 DOI
            title:     论文标题 (来自 RSS)
            link:      论文页面 URL (来自 RSS, 存储在 page_url 列)
            journal:   期刊名称
            publisher: 出版社标识
            updated:   RSS 中显示的发布/更新日期 (存储在 paperdate_rss 列)
        """
        self.conn.execute(
            """
            INSERT INTO papers (doi, title, page_url, journal, publisher, paperdate_rss)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doi, title, link, journal, publisher, updated),
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
        self.conn.execute(
            "UPDATE papers SET created_date = ? WHERE doi = ?",
            (created_date, doi),
        )
        self.conn.commit()

    # ==================================================================
    # Phase B: CrossRef 元数据更新
    # ==================================================================

    def update_crossref_metadata(self, doi, title, authors_json, published, abstract=""):
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
        self.conn.execute(
            """
            UPDATE papers
            SET title = ?, authors_json = ?, paperdate_crossref = ?,
                abstract = CASE WHEN ? != '' THEN ? ELSE abstract END
            WHERE doi = ?
            """,
            (title, authors_json, published, abstract, abstract, doi),
        )
        self.conn.commit()

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
        self.conn.execute(
            """
            UPDATE papers
            SET abstract = CASE WHEN ? != '' THEN ? ELSE abstract END,
                authors_json = ?, pdf_url = ?,
                paperdate_page = ?,
                publisher_page_fetched_status = ?,
                publisher_page_fetched_date = ?
            WHERE doi = ?
            """,
            (abstract, abstract, authors_json, pdf_url, paperdate_page,
             status, status_date, doi),
        )
        self.conn.commit()

    # ==================================================================
    # Phase E: LLM 相关性判断结果
    # ==================================================================

    def update_llm_relevance(self, doi, result, confidence, reason, status, status_date):
        """
        Phase E 专用: 记录 LLM 相关性判断结果。

        Args:
            doi:        论文 DOI
            result:     1 表示相关, 0 表示不相关 (对应 llm_relevance_result 列)
            confidence: "high" / "medium" / "low" — LLM 的置信度
            reason:     判断理由简述 (LLM 返回的 reason 字段)
            status:     FetchStatus 状态值
            status_date: 处理日期时间字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update LLM relevance."
            )
        self.conn.execute(
            """
            UPDATE papers
            SET llm_relevance_result = ?,
                llm_relevance_confidence = ?,
                llm_relevance_reason = ?,
                llm_relevance_status = ?,
                llm_relevance_date = ?
            WHERE doi = ?
            """,
            (result, confidence, reason, status, status_date, doi),
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
    # Phase D: 语义相似度初筛
    # ==================================================================

    def update_semantic_filter(self, doi, score, status, status_date):
        """
        Phase D 专用: 存储语义相似度初筛结果。

        使用 sentence-transformers 计算论文标题+摘要与研究领域描述
        的余弦相似度，作为论文相关性的初筛得分。

        Args:
            doi:        论文 DOI
            score:      余弦相似度得分 (0~1)
            status:     FetchStatus 状态值
            status_date: 处理日期时间字符串
        """
        if not self.paper_doi_exists(doi):
            raise DataBaseDOINotExists(
                f"DOI {doi} not found in DB, cannot update semantic filter."
            )
        self.conn.execute(
            """
            UPDATE papers
            SET semantic_similarity_score = ?,
                semantic_filter_status = ?,
                semantic_filter_date = ?
            WHERE doi = ?
            """,
            (score, status, status_date, doi),
        )
        self.conn.commit()

    # ==================================================================
    # 报告阶段查询方法
    # ==================================================================

    def get_relevant_papers(self):
        """
        获取 LLM 判定为相关的论文。

        查询条件: llm_relevance_result = 1
        排序: 按 RSS 日期倒序

        Returns:
            list[sqlite3.Row]
        """
        cur = self.conn.execute("""
        SELECT * FROM papers
        WHERE llm_relevance_result = 1
          AND llm_relevance_status = 'success'
        ORDER BY paperdate_rss DESC
        """)
        return cur.fetchall()

    def get_papers_for_report(self):
        """
        获取待汇入报告的新论文：LLM 总结成功且尚未被报告过。

        查询条件: llm_summary_status = 'success' AND report_status = 'pending'
        排序: 按 RSS 日期倒序

        Returns:
            list[sqlite3.Row]
        """
        cur = self.conn.execute("""
        SELECT * FROM papers
        WHERE llm_summary_status = 'success'
          AND report_status = 'pending'
        ORDER BY paperdate_rss DESC
        """)
        return cur.fetchall()

    def mark_papers_reported(self, dois, timestamp):
        """
        批量标记论文为已报告。

        将指定 DOI 列表的论文 report_status 设为 'reported'，
        并记录首次报告时间。

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

    def get_all_papers(self):
        """
        获取数据库中所有论文记录。

        排序: 按创建日期倒序

        Returns:
            list[sqlite3.Row]
        """
        cur = self.conn.execute("SELECT * FROM papers ORDER BY created_date DESC")
        return cur.fetchall()

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
        self.conn.execute(f"""
            UPDATE papers
            SET {status_field} = ?, {error_field} = ?, {error_field_date} = ?
            WHERE doi = ?
            """,
            (status_code, message, timestamp, doi),
        )
        self.conn.commit()
