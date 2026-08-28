"""
Tests: Phase A 智能回溯逻辑（_compute_lookback_days / _load_last_run_date / _save_last_run_date）

覆盖场景：
  - 首次运行（无 last_run.json）→ 退化为 CROSSREF_LOOKBACK_DAYS
  - last_run.json 损坏 → 警告 + 退化为默认值
  - 正常每日运行（last_run 距今 0 天）→ CROSSREF_LOOKBACK_DAYS
  - 故障 1 天（last_run 距今 2 天）→ 扩展为 2 天
  - 故障多日（last_run 距今 10 天）→ 封顶 CROSSREF_LOOKBACK_DAYS_MAX
  - 写时间戳 → 文件可被读回
"""

import json
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ==================================================================
# Fixtures
# ==================================================================

@pytest.fixture
def tmp_last_run(tmp_path, monkeypatch):
    """重定向 LAST_RUN_PATH 和 STATE_DIR 到 tmp_path，并重置 CFG 字段。"""
    from config import CFG
    import pipeline.phase_a as phase_a_module

    monkeypatch.setattr(phase_a_module, "LAST_RUN_PATH", tmp_path / "last_run.json")
    monkeypatch.setattr(phase_a_module, "STATE_DIR", tmp_path)

    # 记录原值用于恢复
    original_default = CFG.CROSSREF_LOOKBACK_DAYS
    original_max = CFG.CROSSREF_LOOKBACK_DAYS_MAX
    yield tmp_path

    # 恢复
    CFG.CROSSREF_LOOKBACK_DAYS = original_default
    CFG.CROSSREF_LOOKBACK_DAYS_MAX = original_max


def _set_cfgs(default_days: int, max_days: int) -> None:
    from config import CFG
    CFG.CROSSREF_LOOKBACK_DAYS = default_days
    CFG.CROSSREF_LOOKBACK_DAYS_MAX = max_days


def _write_last_run(path, date_str: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"last_successful_run": date_str}, f)


# ==================================================================
# _load_last_run_date
# ==================================================================

def test_load_last_run_no_file(tmp_last_run):
    """无 last_run.json → 返回 None（首次运行）。"""
    from pipeline.phase_a import _load_last_run_date
    assert _load_last_run_date() is None


def test_load_last_run_valid(tmp_last_run):
    """正常 JSON → 返回日期字符串。"""
    from pipeline.phase_a import _load_last_run_date
    _write_last_run(tmp_last_run / "last_run.json", "2026-07-15")
    assert _load_last_run_date() == "2026-07-15"


def test_load_last_run_corrupted_json(tmp_last_run):
    """JSON 损坏 → 警告 + 返回 None（不抛异常）。"""
    from pipeline.phase_a import _load_last_run_date
    (tmp_last_run / "last_run.json").write_text("{invalid json", encoding="utf-8")
    assert _load_last_run_date() is None


# ==================================================================
# _save_last_run_date
# ==================================================================

def test_save_and_reload_roundtrip(tmp_last_run):
    """写入后读回，原子写入不损坏。"""
    from pipeline.phase_a import _save_last_run_date, _load_last_run_date
    _save_last_run_date("2026-07-20")
    assert _load_last_run_date() == "2026-07-20"


def test_save_creates_state_dir(tmp_last_run):
    """写入时自动创建 STATE_DIR。"""
    from pipeline.phase_a import _save_last_run_date
    nested = tmp_last_run / "deeper" / "nested"
    # 重新指向不存在的子目录
    import pipeline.phase_a as phase_a_module
    phase_a_module.LAST_RUN_PATH = nested / "last_run.json"
    phase_a_module.STATE_DIR = nested
    _save_last_run_date("2026-07-20")
    assert (nested / "last_run.json").exists()


# ==================================================================
# _compute_lookback_days
# ==================================================================

def test_lookback_first_run(tmp_last_run):
    """首次运行（无文件）→ 返回默认 CROSSREF_LOOKBACK_DAYS。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=1, max_days=7)
    assert _compute_lookback_days() == 1


def test_lookback_first_run_default_2(tmp_last_run):
    """首次运行（无文件）→ 尊重用户的 CROSSREF_LOOKBACK_DAYS 配置。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=3, max_days=7)
    assert _compute_lookback_days() == 3


def test_lookback_daily_normal(tmp_last_run):
    """今日已运行（last_run=今天）→ 返回默认（1 天）。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=1, max_days=7)
    _write_last_run(tmp_last_run / "last_run.json", date.today().isoformat())
    assert _compute_lookback_days() == 1


def test_lookback_yesterday(tmp_last_run):
    """昨天运行（last_run=今天-1）→ 返回默认（1 天）。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=1, max_days=7)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _write_last_run(tmp_last_run / "last_run.json", yesterday)
    assert _compute_lookback_days() == 1


def test_lookback_gap_2_days(tmp_last_run):
    """故障 1 天（last_run=今天-2，default=1）→ 扩展为 2 天。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=1, max_days=7)
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()
    _write_last_run(tmp_last_run / "last_run.json", two_days_ago)
    assert _compute_lookback_days() == 2


def test_lookback_gap_capped_at_max(tmp_last_run):
    """故障 10 天（远超 max=7）→ 封顶 7 天。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=1, max_days=7)
    ten_days_ago = (date.today() - timedelta(days=10)).isoformat()
    _write_last_run(tmp_last_run / "last_run.json", ten_days_ago)
    assert _compute_lookback_days() == 7


def test_lookback_max_configurable(tmp_last_run):
    """max=3 时故障 5 天 → 封顶 3 天。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=1, max_days=3)
    five_days_ago = (date.today() - timedelta(days=5)).isoformat()
    _write_last_run(tmp_last_run / "last_run.json", five_days_ago)
    assert _compute_lookback_days() == 3


def test_lookback_invalid_date_format(tmp_last_run):
    """last_run 格式异常 → 警告 + 退化为默认（不抛异常）。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=1, max_days=7)
    _write_last_run(tmp_last_run / "last_run.json", "not-a-date")
    assert _compute_lookback_days() == 1


def test_lookback_corrupted_json_file(tmp_last_run):
    """last_run.json 损坏 → 退化为默认（不抛异常）。"""
    from pipeline.phase_a import _compute_lookback_days
    _set_cfgs(default_days=1, max_days=7)
    (tmp_last_run / "last_run.json").write_text("{corrupted", encoding="utf-8")
    assert _compute_lookback_days() == 1
