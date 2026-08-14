"""
Tests for tools/run_pipeline.py and tools/send_report.py.

覆盖:
  - run_pipeline --dry-run --all 不实际调用 run_pipeline
  - run_pipeline --phases A,B 解析为 ['A', 'B']
  - run_pipeline --phases "" 处理为无阶段
  - run_pipeline --daily 调用 run_daily
  - send_report --report missing.md 退出码 2 且日志含 "not found"
  - send_report 调用 phase_h_email 并传递正确的 to_addrs 和 report_path

测试策略:
  - 使用 subprocess 验证退出码和输出
  - 使用 unittest.mock.patch 验证函数调用
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
# 确保 tools/ 可导入（namespace package）
sys.path.insert(0, str(ROOT))


# ===================================================================
# Helpers
# ===================================================================

def _run_cli(script: str, args: list[str]) -> subprocess.CompletedProcess:
    """通过 subprocess 运行 CLI 脚本并返回结果。

    Parameters
    ----------
    script : str
        脚本路径（相对项目根目录）。
    args : list of str
        命令行参数。

    Returns
    -------
    subprocess.CompletedProcess
    """
    env = {**os.environ, "LOG_LEVEL": "DEBUG"}
    # 确保子进程能找到 src/ 下的模块
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{ROOT / 'src'}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = str(ROOT / "src")

    return subprocess.run(
        [sys.executable, str(ROOT / script)] + args,
        capture_output=True, text=True,
        cwd=str(ROOT),
        env=env,
        timeout=30,
    )


def _create_temp_report(filename: str, content: str = "# Test Report") -> Path:
    """在 AUTO_REPORT_DIR 下创建临时报告文件。

    Parameters
    ----------
    filename : str
        报告文件名。
    content : str, optional
        文件内容。

    Returns
    -------
    Path
        创建的文件的完整路径。
    """
    # 导入 config 前确保 src/ 在 sys.path 中
    sys.path.insert(0, str(ROOT / "src"))
    from config import AUTO_REPORT_DIR
    AUTO_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = AUTO_REPORT_DIR / filename
    report_path.write_text(content, encoding="utf-8")
    return report_path


# ===================================================================
# run_pipeline 测试
# ===================================================================

def test_run_pipeline_dry_run_all_prints_plan():
    """--dry-run --all 应打印执行计划而不实际调用 run_pipeline."""
    result = _run_cli("tools/run_pipeline.py", ["--all", "--dry-run"])
    assert result.returncode == 0
    # logging 输出到 stderr
    assert "Would run phases" in result.stderr
    assert "Dry-run mode" in result.stderr


def test_run_pipeline_phases_A_B_parsing():
    """--phases A,B 应解析为 ['A', 'B'] 并传递给 run_phases."""
    with patch("tools.run_pipeline.run_phases") as mock_run_phases:
        with patch("tools.run_pipeline._run_auto_reset"):
            # 需要重新导入，因为模块级代码在首次 import 时执行
            # 但 unittest.mock.patch 在 import 后修改引用，所以先 import
            import tools.run_pipeline  # noqa: F811
            # 清除模块级缓存以重新加载？不需要，patch 会替换引用
            tools.run_pipeline.main(["--phases", "A,B", "--no-reset-publisher", "--no-reset-mineru"])
            mock_run_phases.assert_called_once_with(phase_list=["A", "B"], force=False)


def test_run_pipeline_phases_empty_logs_warning():
    """--phases '' 应打印警告并安全返回."""
    result = _run_cli("tools/run_pipeline.py", ["--phases", ""])
    assert result.returncode == 0
    # 应包含空列表提示（logging 输出到 stderr）
    assert "空列表" in result.stderr


def test_run_pipeline_daily_calls_run_daily():
    """--daily 应调用 run_daily."""
    with patch("tools.run_pipeline.run_daily") as mock_run_daily:
        with patch("tools.run_pipeline._run_auto_reset"):
            import tools.run_pipeline
            tools.run_pipeline.main(["--daily", "--no-reset-publisher", "--no-reset-mineru"])
            mock_run_daily.assert_called_once()


def test_run_pipeline_dry_run_all_does_not_call_run_pipeline():
    """--dry-run --all 不应调用 run_pipeline 或 run_phases."""
    with patch("tools.run_pipeline.run_pipeline") as mock_run_pipeline:
        with patch("tools.run_pipeline.run_phases") as mock_run_phases:
            import tools.run_pipeline
            tools.run_pipeline.main(["--all", "--dry-run"])
            mock_run_pipeline.assert_not_called()
            mock_run_phases.assert_not_called()


def test_run_pipeline_reset_relevance_flagged_off():
    """--no-reset-relevance 应使 _run_auto_reset 收到 reset_relevance=False."""
    with patch("tools.run_pipeline.run_phases") as mock_run_phases:
        with patch("tools.run_pipeline._run_auto_reset") as mock_auto_reset:
            import tools.run_pipeline
            tools.run_pipeline.main(["--phases", "A", "--no-reset-relevance"])
            mock_auto_reset.assert_called_once_with(
                True, True, False, dry_run=False,
            )
            mock_run_phases.assert_called_once_with(phase_list=["A"], force=False)


def test_run_pipeline_reset_relevance_enabled_flag():
    """默认（未指定 --no-reset-relevance）时 _run_auto_reset 收到 reset_relevance=True."""
    with patch("tools.run_pipeline.run_phases") as mock_run_phases:
        with patch("tools.run_pipeline._run_auto_reset") as mock_auto_reset:
            import tools.run_pipeline
            tools.run_pipeline.main(["--phases", "A"])
            mock_auto_reset.assert_called_once_with(
                True, True, True, dry_run=False,
            )
            mock_run_phases.assert_called_once_with(phase_list=["A"], force=False)


# ===================================================================
# send_report 测试
# ===================================================================

def test_send_report_missing_file_exit_code_2():
    """不存在的报告文件应导致退出码 2 且日志含 'not found'."""
    result = _run_cli(
        "tools/send_report.py",
        ["--report", "nonexistent_report_xyz.md"],
    )
    assert result.returncode == 2
    combined = (result.stdout + result.stderr).lower()
    assert "not found" in combined


def test_send_report_calls_phase_h_email_with_correct_args():
    """发送命令应调用 phase_h_email，并传递正确的 report_path 和 to_addrs."""
    report_name = "test_send_report_dry_run.md"
    temp_path = _create_temp_report(report_name)

    try:
        with patch("tools.send_report.phase_h_email") as mock_email:
            import tools.send_report
            tools.send_report.main([
                "--report", report_name,
                "--recipients", "a@x.com,b@y.com",
                "--log-level", "DEBUG",
            ])

            # 验证 phase_h_email 被调用
            mock_email.assert_called_once()
            call_args, call_kwargs = mock_email.call_args

            # 验证 report_path 参数
            actual_report_path = call_kwargs.get("report_path")
            assert actual_report_path is not None
            assert actual_report_path.name == report_name

            # 验证 to_addrs 参数
            actual_to_addrs = call_kwargs.get("to_addrs")
            assert actual_to_addrs == ["a@x.com", "b@y.com"]
    finally:
        temp_path.unlink(missing_ok=True)


def test_send_report_default_recipients_fallback():
    """未指定 --recipients 时应使用默认收件人列表（load_email_recipients）。"""
    report_name = "test_send_report_default_recipients.md"
    temp_path = _create_temp_report(report_name)

    try:
        with patch("tools.send_report.phase_h_email") as mock_email:
            with patch("tools.send_report.load_email_recipients",
                       return_value=["default@x.com"]) as mock_load:
                import tools.send_report
                tools.send_report.main([
                    "--report", report_name,
                    "--log-level", "DEBUG",
                ])

                mock_email.assert_called_once()
                call_kwargs = mock_email.call_args[1]
                # to_addrs 应来自 load_email_recipients 的返回值
                assert call_kwargs.get("to_addrs") == ["default@x.com"]
                mock_load.assert_called_once()
    finally:
        temp_path.unlink(missing_ok=True)
