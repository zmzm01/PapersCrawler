"""
pdf_converter.py
================
使用 pandoc + xelatex 将 Markdown 报告转换为 PDF。

依赖:
  - pandoc: Markdown 转换引擎 (需系统安装)
  - xelatex: LaTeX 排版引擎 (含中文支持，需系统安装)
  - Noto Sans CJK SC: 中文字体 (用于渲染中文内容)

安装依赖 (Ubuntu/Debian):
  sudo apt install pandoc texlive-xetex texlive-latex-extra \
                   fonts-noto-cjk

工作原理:
  1. 将 Markdown 文本写入临时文件
  2. 将自定义 LaTeX 模板写入临时文件
  3. 调用 pandoc 进行 Markdown → PDF 转换
  4. 如果 xelatex + CJK 字体方式失败，回退到无字体的纯 LaTeX 方式
  5. 清理临时文件

注意事项:
  - 本模块生成的 PDF 适合包含 LaTeX 数学公式的学术文章
  - 中文渲染需要系统安装中文字体（如 Noto Sans CJK SC）
  - 如果 pandoc 或 xelatex 未安装，函数返回 None（不抛异常）
"""

import subprocess
import tempfile
from pathlib import Path


# ------------------------------------------------------------------
# LaTeX 模板: 基于 xelatex + XeCJK, 支持中文和数学公式
# ------------------------------------------------------------------
LATEX_TEMPLATE = r"""
\documentclass[12pt,a4paper]{article}

% ---- 中文支持 ----
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{Noto Sans CJK SC}       % 设置中文正文字体（需系统安装）

% ---- 数学公式支持 ----
\usepackage{amsmath,amssymb}

% ---- 其他功能 ----
\usepackage{hyperref}                   % 超链接支持
\usepackage{graphicx}                   % 图片支持
\usepackage[margin=2.5cm]{geometry}     % 页边距

\hypersetup{
    colorlinks=true,
    linkcolor=blue,                     % 内部链接颜色
    urlcolor=cyan,                      % URL 链接颜色
}

\begin{document}
$body$                                  % pandoc 会将 Markdown 内容注入此处
\end{document}
"""


def markdown_to_pdf(md_text, output_path, template=None):
    """
    将 Markdown 文本转换为 PDF 文件。

    双重回退策略:
      策略 A: 使用自定义模板（含 CJK 中文字体）的 xelatex 转换
      策略 B: 回退到无字体配置的 xelatex 转换（中文可能显示为空白）
      策略 C: pandoc 未安装 → 返回 None

    Args:
        md_text:     Markdown 格式的文本内容
        output_path: 输出的 PDF 文件路径 (Path 对象或字符串)
        template:    自定义 LaTeX 模板字符串，默认使用内置模板（支持中文）

    Returns:
        Path 或 None: 成功返回 PDF 路径的 Path 对象，失败返回 None

    使用示例:
        md = "# 标题\n\n这是正文内容，包含行内公式 $E=mc^2$。"
        result = markdown_to_pdf(md, "/tmp/report.pdf")
        if result:
            print(f"PDF 已生成: {result}")
        else:
            print("PDF 生成失败，请检查 pandoc/xelatex 是否已安装")
    """
    # ---- 1. 准备模板 ----
    if template is None:
        template = LATEX_TEMPLATE

    # ---- 2. 确保输出目录存在 ----
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- 3. 写入 Markdown 临时文件 ----
    # NamedTemporaryFile 创建后即删除，我们手动管理生命周期
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(md_text)
        md_path = f.name                      # 临时 .md 文件路径

    # ---- 4. 写入 LaTeX 模板临时文件 ----
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tex", delete=False, encoding="utf-8"
    ) as f:
        f.write(template)
        template_path = f.name                # 临时 .tex 模板路径

    try:
        # ---- 5. 策略 A: xelatex + CJK 字体 ----
        # pandoc 参数说明:
        #   --pdf-engine=xelatex     使用 xelatex 引擎
        #   --template=...           使用自定义 LaTeX 模板
        #   -V mainfont=...          设置正文字体变量
        #   --from markdown+...      启用 raw_tex (原始 LaTeX 透传) 和 tex_math_dollars ($公式$) 扩展
        cmd = [
            "pandoc",
            md_path,
            "-o", str(output_path),
            "--pdf-engine=xelatex",
            "--template", template_path,
            "-V", "mainfont=Noto Sans CJK SC",
            "--from", "markdown+raw_tex+tex_math_dollars",
            "--mathjax",
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path

    except subprocess.CalledProcessError:
        # ---- 6. 策略 B: 回退到无模板 xelatex ----
        # 不使用自定义模板（因此也没有中文字体），适用于纯英文或 LaTeX 数学公式场景
        try:
            cmd2 = [
                "pandoc",
                md_path,
                "-o", str(output_path),
                "--pdf-engine=xelatex",
                "--from", "markdown+raw_tex+tex_math_dollars",
            ]
            subprocess.run(cmd2, check=True, capture_output=True, text=True)
            return output_path
        except subprocess.CalledProcessError:
            return None

    except FileNotFoundError:
        # pandoc 命令不存在 → 返回 None
        return None

    finally:
        # ---- 7. 清理临时文件 ----
        # 无论成功或失败，都要清理临时文件以免磁盘空间浪费
        Path(md_path).unlink(missing_ok=True)
        Path(template_path).unlink(missing_ok=True)
