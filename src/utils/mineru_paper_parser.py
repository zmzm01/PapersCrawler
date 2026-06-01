"""
MinerU PDF 论文解析模块
======================
利用 MinerU Precision Extract API (batch file upload) 完成论文 PDF 解析，
将结果 zip 包完整解压到指定目录，方便获取 markdown 全文以及文中提取出的图片。

依赖: pip install requests

用法:
    from mineru_paper_parser import MinerUParser

    token = "your_mineru_token"
    parser = MinerUParser(token)
    parser.parse_pdf("qdgp-tydj.pdf")
    # => 解压到 ./qdgp-tydj_output/ 目录，内含 full.md + images/

    # 也可指定解压目录
    parser.parse_pdf("paper.pdf", output_dir="./my_result/")
"""

import os
import sys
import time
import zipfile
import tempfile
from pathlib import Path

import requests

# ---------- 常量 ----------
BASE_URL = "https://mineru.net/api/v4"     # MinerU API 基础地址
POLL_INTERVAL = 3                           # 轮询间隔（秒）
POLL_TIMEOUT = 600                          # 轮询超时（秒），10 分钟


class MinerUParser:
    """
    MinerU 论文解析器。
    封装了 batch file upload 全流程：申请上传地址 -> 上传文件 -> 轮询结果 -> 下载 zip 并完整解压。
    """

    def __init__(self, token):
        """
        初始化解析器。

        Args:
            token: MinerU API token，从 https://mineru.net 个人中心获取。
        """
        self.token = token
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        })

    # ---------- 公开接口 ----------

    def parse_pdf(self, pdf_path, output_dir=None):
        """
        解析单个 PDF 论文文件，下载结果 zip 并完整解压到指定目录。

        解压后的目录结构:
            output_dir/
            ├── full.md                  # 完整 markdown（全文）
            ├── images/                  # 文中提取的图片
            │   ├── xxx_0.jpg
            │   └── ...
            ├── layout.json              # 版面布局
            ├── *_model.json             # 模型识别结果
            └── *_content_list.json      # 内容列表

        Parameters
        ----------
        pdf_path:   待解析的 PDF 文件路径（str 或 Path）。
        output_dir: 解压目标目录，不传则默认在与 PDF 同目录下创建
                    名为 "{PDF名}_output" 的目录。

        Returns:
        --------
        Path: 解压后的目录路径。

        Raises:
        -------
        FileNotFoundError: PDF 文件不存在。
        RuntimeError:      API 返回错误或解析失败。
        TimeoutError:      轮询等待超时。
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        # 默认输出目录：PDF 同目录下，名为 "{PDF名}_output"
        if output_dir is None:
            output_dir = pdf_path.parent / f"{pdf_path.stem}_output"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # ---- 步骤 1: 申请批量上传地址 ----
        print(f"[1/4] 请求上传地址: {pdf_path.name}")
        batch_id, file_urls = self._create_batch(pdf_path.name)

        # ---- 步骤 2: 上传 PDF 文件 ----
        file_size = pdf_path.stat().st_size
        print(f"[2/4] 上传文件 ({file_size} 字节)...")
        self._upload_file(file_urls[0], pdf_path)

        # ---- 步骤 3: 轮询等待解析完成 ----
        print(f"[3/4] 等待解析完成 (batch_id={batch_id})...")
        zip_url = self._poll_batch(batch_id, pdf_path.name)

        # ---- 步骤 4: 下载结果 zip 并完整解压 ----
        print(f"[4/4] 下载结果并解压到 {output_dir} ...")
        self._download_and_extract(zip_url, output_dir)

        markdown_path = output_dir / "full.md"
        print(f"完成! Markdown: {markdown_path}")
        print(f"       图片目录: {output_dir / 'images'}")
        return output_dir

    # ---------- 内部方法 ----------

    def _create_batch(self, filename):
        """
        向 MinerU 申请批量文件上传地址。

        POST /api/v4/file-urls/batch

        Args:
            filename: 文件名（含扩展名）。

        Returns:
            (batch_id, file_urls): batch_id 用于后续轮询, file_urls 是上传 URL 列表。

        请求体:
            {
                "files": [{"name": "xxx.pdf"}],   # 可批量，这里只传 1 个
                "model_version": "vlm",           # 使用 vlm 模型，精度最高
                "enable_formula": true,           # 启用公式识别
                "enable_table": true,             # 启用表格识别
                "language": "en"                  # 论文语言为英文
            }
        """
        payload = {
            "files": [{"name": filename}],
            "model_version": "vlm",
            "enable_formula": True,
            "enable_table": True,
            "language": "en",
        }
        resp = self._session.post(f"{BASE_URL}/file-urls/batch", json=payload)
        resp.raise_for_status()
        result = resp.json()

        if result["code"] != 0:
            raise RuntimeError(f"获取上传地址失败: {result.get('msg', '未知错误')}")

        data = result["data"]
        return data["batch_id"], data["file_urls"]

    def _upload_file(self, upload_url, file_path):
        """
        将本地 PDF 文件 PUT 上传到 OSS 预签名 URL。

        Args:
            upload_url: OSS 预签名上传地址（来自 _create_batch 的响应）。
            file_path:  本地 PDF 文件路径。
        """
        with open(file_path, "rb") as f:
            resp = requests.put(upload_url, data=f)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"文件上传失败: HTTP {resp.status_code}")

    def _poll_batch(self, batch_id, filename):
        """
        轮询批量解析任务状态，直到完成或失败。

        GET /api/v4/extract-results/batch/{batch_id}

        响应示例:
            {
                "code": 0,
                "data": {
                    "batch_id": "...",
                    "extract_result": [
                        {
                            "file_name": "demo.pdf",
                            "state": "done",        # pending/running/done/failed
                            "full_zip_url": "https://..."  # 结果 zip 包地址
                        }
                    ]
                }
            }

        Args:
            batch_id: 批量任务 ID。
            filename: 要匹配的文件名。

        Returns:
            str: 结果 zip 包的 URL。
        """
        url = f"{BASE_URL}/extract-results/batch/{batch_id}"
        start = time.time()

        while time.time() - start < POLL_TIMEOUT:
            resp = self._session.get(url)
            resp.raise_for_status()
            result = resp.json()

            if result["code"] != 0:
                raise RuntimeError(f"查询任务状态失败: {result.get('msg')}")

            extract_results = result["data"].get("extract_result", [])
            for item in extract_results:
                if item.get("file_name") == filename:
                    state = item["state"]
                    elapsed = int(time.time() - start)

                    if state == "done":
                        print(f"  [{elapsed}s] 解析完成")
                        return item["full_zip_url"]

                    if state == "failed":
                        err_code = item.get("err_code", "")
                        err_msg = item.get("err_msg", "未知错误")
                        raise RuntimeError(f"解析失败 (code={err_code}): {err_msg}")

                    # 打印进度信息
                    progress = item.get("extract_progress", {})
                    pages_info = ""
                    if progress:
                        pages_info = f" (已解析 {progress.get('extracted_pages', 0)}/{progress.get('total_pages', 0)} 页)"
                    print(f"  [{elapsed}s] 状态: {state}{pages_info}")
                    break

            time.sleep(POLL_INTERVAL)

        raise TimeoutError(f"轮询超时 ({POLL_TIMEOUT}s)，请手动查询 batch_id={batch_id}")

    def _download_and_extract(self, zip_url, output_dir):
        """
        下载结果 zip 包，将全部内容解压到 output_dir。

        MinerU 结果 zip 内文件说明:
            full.md             - 完整 markdown 全文
            images/             - 文中提取的图片
            layout.json         - 版面布局信息
            *_model.json        - 模型识别结果
            *_content_list.json - 内容列表

        Args:
            zip_url:    结果 zip 包的下载 URL。
            output_dir: 解压目标目录（Path 对象）。
        """
        resp = requests.get(zip_url)
        resp.raise_for_status()

        # 将 zip 内容写入临时文件
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                zf.extractall(output_dir)  # 完整解压到 output_dir
        finally:
            os.unlink(tmp_path)  # 删除临时 zip 文件


# ---------- 快捷函数 ----------

def parse_paper(pdf_path, token, output_dir=None):
    """
    一行调用解析论文 PDF，结果完整解压到目录。

    Args:
        pdf_path:   PDF 文件路径。
        token:      MinerU API token。
        output_dir: (可选) 解压目标目录。

    Returns:
        Path: 解压后的目录路径。

    用法:
        parse_paper("paper.pdf", "your_token")
    """
    return MinerUParser(token).parse_pdf(pdf_path, output_dir)


if __name__ == "__main__":
    token = os.getenv("MINERU_TOKEN", "your-token-placeholder")
    parser = MinerUParser(token)
    dir_path = Path(__file__).parent
    parser.parse_pdf(dir_path / "qdgp-tydj.pdf", dir_path / "qdgp-tydj")