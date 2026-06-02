# Phase E2: MinerU PDF 下载与输出持久化修复

## Fix 1: PDF 下载改用 Playwright

**现状** (`main.py:848-868`):
- 用 `requests.get(pdf_url)` + 静态 User-Agent 下载 PDF
- 出版商 PDF 链接经常需要 session cookie / referrer / Cloudflare 认证
- 容易被拦截

**修复**:
- 在 `phase_e2_mineru()` 中创建一个轻量的 Playwright 持久化浏览器上下文
- 复用 Phase C 的反检测 JS 注入模式和 viewport 设置
- 每次 `page.goto(pdf_url, wait_until="commit")` 后取 `response.body()` 写入临时文件
- 下载间加随机延迟（3-8 秒）
- finally 块中关闭浏览器

## Fix 2: MinerU 输出持久化

**现状** (`main.py:872, 887-889`):
- `parse_pdf()` 默认输出到 `/tmp/<random>_output/`
- 读完 `full.md` 后 `shutil.rmtree()` 全部删除

**修复**:
- 从 config 导入已有的 `MINERU_OUTPUT_DIR`（`data/mineru_output/`）
- DOI 中 `/` 替换为 `_` 作为子目录名
- `parse_pdf(pdf_path, output_dir=MINERU_OUTPUT_DIR / safe_doi)`
- 删除 `shutil.rmtree(mineru_output_dir)` 调用
- 仅保留临时 PDF 文件清理

## 修改文件

| 文件 | 变更 |
|------|------|
| `src/main.py` | 导入 `MINERU_OUTPUT_DIR`；重写 `phase_e2_mineru()` PDF 下载段；持久化 MinerU 输出 |
| （仅此 1 文件） | `mineru_paper_parser.py` 已支持 `output_dir` 参数 — 无需改动 |
