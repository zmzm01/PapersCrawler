#!/usr/bin/env python
"""
tools/import_local_pdf.py — 手动导入本地 PDF 到 MinerU 解析队列

通过 --doi 和 --pdf 参数手动将本地 PDF 文件导入 MinerU 解析队列。
脚本会校验 PDF 文件合法性，将文件复制到 MinerU 输出目录，并将数据库中
该论文的 MinerU 解析状态重置为 pending，以便下次 daily 调度自动复用
该 PDF 进行 MinerU 解析，跳过下载步骤。

用法:
    python tools/import_local_pdf.py --doi <DOI> --pdf <PATH_TO_PDF>

示例:
    python tools/import_local_pdf.py \\
        --doi 10.1038/s41567-026-03184-9 \\
        --pdf /path/to/paper.pdf
"""

import argparse
import shutil
import sys
from pathlib import Path

# 项目根目录（脚本在 tools/ 下，上溯一级）
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import DB_PATH, MINERU_OUTPUT_DIR
from db.database import DatabaseClient


def validate_pdf(file_path: Path) -> None:
    """校验文件是否为合法的 PDF 文件。

    检查文件是否存在，并读取头部至少 5 字节确认以 ``b'%PDF-'`` 开头。

    Parameters
    ----------
    file_path : Path
        待校验的 PDF 文件路径。

    Raises
    ------
    SystemExit
        文件不存在时 exit code 1，头部校验失败时 exit code 2。
    """
    if not file_path.exists():
        print(f"错误: PDF 文件不存在: {file_path}", file=sys.stderr)
        sys.exit(1)

    with open(file_path, "rb") as f:
        header = f.read(5)
    if header != b'%PDF-':
        print(
            f"错误: 文件头部校验失败 (期望 b'%PDF-', 实际 {header!r}): {file_path}",
            file=sys.stderr,
        )
        sys.exit(2)


def compute_safe_doi(doi: str) -> str:
    """计算安全的目录名称。

    将 DOI 中的 ``/``、``\\`` 和 ``..`` 替换为 ``_``，
    与 ``src/pipeline/phase_e2.py`` 中的规则完全一致。

    Parameters
    ----------
    doi : str
        论文 DOI。

    Returns
    -------
    str
        安全的目录名，可用于文件系统路径。
    """
    return doi.replace("/", "_").replace("\\", "_").replace("..", "_")


def copy_pdf(source: Path, dest_dir: Path) -> Path:
    """将 PDF 文件复制到目标目录。

    创建目标目录（如不存在），使用 ``shutil.copy2`` 保留文件元数据。

    Parameters
    ----------
    source : Path
        源 PDF 文件路径。
    dest_dir : Path
        目标目录路径。

    Returns
    -------
    Path
        目标 PDF 文件的完整路径。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "paper.pdf"
    shutil.copy2(str(source), str(dest_path))
    return dest_path


def reset_mineru_status(doi: str) -> int:
    """重置数据库中指定 DOI 的 MinerU 解析状态为 pending。

    连接数据库，检查 DOI 是否存在。如果存在，将 ``mineru_parse_status``
    设为 ``'pending'``，清空 ``mineru_parse_error`` 和 ``mineru_parse_date``。
    不修改 ``mineru_output_dir``、``mineru_fulltext``、``pdf_url`` 等字段。

    Parameters
    ----------
    doi : str
        论文 DOI。

    Returns
    -------
    int
        UPDATE 影响的行数。

    Raises
    ------
    SystemExit
        DOI 在数据库中不存在时 exit code 3。
    """
    with DatabaseClient(DB_PATH) as db:
        if not db.paper_doi_exists(doi):
            print(
                f"警告: DOI '{doi}' 在数据库中不存在。\n"
                f" PDF 已落盘但无法更新数据库状态。\n"
                f" 请先运行 Phase A-E 让论文入库后再执行此脚本。",
                file=sys.stderr,
            )
            sys.exit(3)

        cur = db.conn.execute(
            "UPDATE papers SET mineru_parse_status = ?,"
            " mineru_parse_error = NULL,"
            " mineru_parse_date = NULL"
            " WHERE doi = ?",
            ('pending', doi),
        )
        db.conn.commit()
        return cur.rowcount


def main():
    """命令行入口函数。

    解析 ``--doi`` 和 ``--pdf`` 参数，按以下顺序执行：
    1. 校验 PDF 文件是否存在且合法
    2. 计算 safe_doi
    3. 创建目标目录并复制 PDF
    4. 连接数据库，重置 MinerU 解析状态
    """
    parser = argparse.ArgumentParser(
        description="手动导入本地 PDF 到 MinerU 解析队列",
    )
    parser.add_argument(
        "--doi",
        required=True,
        help="论文 DOI（原始形式，含 '/'，例如 10.1038/s41567-026-03184-9）",
    )
    parser.add_argument(
        "--pdf",
        required=True,
        help="本地 PDF 文件路径",
    )
    args = parser.parse_args()

    doi = args.doi
    pdf_path = Path(args.pdf)

    try:
        # 步骤 1-2: 校验 PDF 文件
        validate_pdf(pdf_path)

        # 步骤 3: 计算 safe_doi
        safe_doi = compute_safe_doi(doi)

        # 步骤 4-5: 创建目录并复制 PDF
        dest_dir = MINERU_OUTPUT_DIR / safe_doi
        dest_path = copy_pdf(pdf_path, dest_dir)
        print(f"PDF 已落盘: {dest_path}")

        # 步骤 7-9: 连接数据库并重置 MinerU 状态
        rowcount = reset_mineru_status(doi)
        print(f"数据库状态已更新: DOI={doi}, 影响行数={rowcount}")

    except SystemExit:
        raise
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
