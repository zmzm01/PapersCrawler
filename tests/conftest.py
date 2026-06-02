"""
pytest 配置文件。
定义共享 fixtures 和全局配置。
"""
import os
import sys
import pytest

# 确保 src 在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def pytest_configure(config):
    """注册自定义标记。"""
    config.addinivalue_line(
        "markers", "network: 需要网络连接的测试 (默认跳过)"
    )
    config.addinivalue_line(
        "markers", "slow: 执行耗时较长的测试"
    )
    config.addinivalue_line(
        "markers", "browser: 需要 cloakbrowser 浏览器的测试 (默认跳过)"
    )
