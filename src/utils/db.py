"""
db.py
负责建立与操作数据库
"""

import sqlite3
from enum import Enum


class DataBaseDOINotExists(Exception):
    pass

class FetchStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DatabaseClient:
    def __init__(self, dbPath):
        """
        Initialization

        Args:
            dbPath: path of database
        """
        self.conn = sqlite3.connect(dbPath)
        self.conn.row_factory = sqlite3.Row

    def init_db_papers(self):
        """初始化 DataBase papers table"""
        # 创建 papers table 用于记录 paper 处理状态
        # 状态枚举约定：
        # cr_metadata_fetched_status / publisher_page_fetched_status / ...
        #   'pending'    - 尚未处理
        #   'processing' - 正在处理（并发认领标记）
        #   'success'    - 处理成功
        #   'failed'     - 处理失败，需人工或定时重试
        #   'skipped'    - 因不满足条件跳过（如关键词不匹配）

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

            -- 处理状态（全部改为 TEXT + 统一枚举）
            cr_metadata_fetched_status TEXT DEFAULT 'pending',
            cr_metadata_fetched_error TEXT,
            cr_metadata_fetched_date TEXT,
            publisher_page_fetched_status TEXT DEFAULT 'pending',
            publisher_page_fetched_error TEXT,
            publisher_page_fetched_date TEXT,
            keywords_map TEXT, 
            -- keywords_filtered_status TEXT DEFAULT 'pending',
            -- keywords_filtered_date TEXT,
            -- keywords_filtered_matched_num INTEGER DEFAULT 0,
            -- llm_relevant_status TEXT DEFAULT 'pending',
            -- llm_relevant_result INTEGER,            -- 0/1
            -- llm_relevant_confidence TEXT,           -- high/medium/low
            -- llm_relevant_reason TEXT,
            -- llm_relevant_error TEXT,
            -- llm_relevant_date TEXT,
            -- llm_summarized_status TEXT DEFAULT 'pending',
            -- llm_summarized_error TEXT,
            -- llm_summarized_date TEXT,
            -- llm_summarized_result TEXT,

            -- 报告相关
            report_status TEXT DEFAULT 'pending',

            -- 调试
            created_date TEXT,
            updated_date TEXT
        )
        """)

        self.conn.commit()

    def paper_doi_exists(self, doi):

        cur = self.conn.execute("SELECT 1 FROM papers WHERE doi = ?", (doi,))

        return cur.fetchone() is not None

    def insert_rss_basicinfo(self, doi, title, link, journal, publisher, updated):
        """
        专为 rss 信息抓取后设计的存储方法，会先检查文献是否已经在数据库中；后期可能会被其他 API 获取的元数据覆盖。

        Args:
            doi
            title
            link
            journal
            publisher
            rss_updated_date: 从 RSS 中拿到的日期，避免 publisher 提供假 DOI 无法获取元数据
        ---
        """
        if self.paper_exists(doi):
            raise DataBaseDOINotExists
        
        self.conn.execute(
            """
            INSERT INTO papers (doi, title, page_url, journal, publisher, rss_updated_date)
            VALUES (?, ?)
            """,
            (doi, title, link, journal, publisher, rss_updated_date),
        )

        self.conn.commit()

    def get_pendings(self, status_field):
        """
        获取状态为 pending 的项

        Args:
            status_field: cr_metadata_fetched_status / publisher_page_fetched_status
        Returns:
            list[sqlite3.Row]
        ---
        """

        cur = self.conn.execute(f"""
        SELECT * FROM papers
        WHERE {status_field} = 'pending'
        ORDER BY created_date
        """)

        return cur.fetchall()


    def insert_paper_created_date(self, doi, created_date):
        """
        根据文献 doi 插入 created_date
        """
        if self.paper_exists(doi):
            return
        
        self.conn.execute(
            """
            UPDATE papers SET created_date = ? WHERE doi = ?
            """,
            (created_date, doi),
        )

        self.conn.commit()

    def update_crossref_metadata(self, doi, title, authors_json, published):
        """
        CrossRef 查询后更新部分元数据，根据 DOI 选择文献
        """
        if self.paper_exists(doi):
            raise DataBaseDOINotExists
        
        self.conn.execute(
            """
            UPDATE papers
            SET title = ?, authors_json = ?, paperdate_crossref = ?
            WHERE doi = ?;
            """,
            (title, authors_json, published, doi),
        )

        self.conn.commit()

    def update_process_status(self, doi, status_field, status_code, status_field_date, timestamp):
        """
        更新某个处理环境的处理状态

        Args:
            status_field: cr_metadata_fetched_status / publisher_page_fetched_status
            status_code: 'pending' / 'processing' / 'success' / 'failed' / 'skipped'
            status_field_date: cr_metadata_fetched_date / publisher_page_fetched_date
            timestamp
        """
        if self.paper_exists(doi):
            raise DataBaseDOINotExists

        self.conn.execute(f"""
            UPDATE papers
            SET {status_field} = ?, {status_field_date} = ?
            WHERE doi = ?;
            """,
            (status_code, timestamp, doi),
        )

        self.conn.commit()

    def update_error_message(self, doi, status_field, status_code, error_field, massage, error_field_date, timestamp):
        """
        更新错误信息

        Args:
            doi
            status_field: cr_metadata_fetched_status / publisher_page_fetched_status
            status_code: 'pending' / 'processing' / 'success' / 'failed' / 'skipped'
            error_field: cr_metadata_fetched_error / publisher_page_fetched_error
            massage:
            error_field_date: cr_metadata_fetched_date / publisher_page_fetched_date
            timestamp: 
        """
        if self.paper_exists(doi):
            raise DataBaseDOINotExists

        self.conn.execute(f"""
            UPDATE papers
            SET {status_field} = ?, {error_field} = ?, {error_field_date} = ?
            WHERE doi = ?;
            """,
            (status_code, massage, timestamp, doi),
        )

        self.conn.commit()
