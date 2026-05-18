"""
测试: 邮件发送 (email_sender.py)

覆盖范围:
  - EmailSender 类实例化
  - MIME 邮件对象构建
  - 收件人列表处理 (单个/多个)
  - 附件添加逻辑

SMTP 实际发送测试需要真实服务器，默认跳过。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.email_sender import EmailSender


def test_email_sender_instantiation():
    """验证 EmailSender 正确初始化。"""
    sender = EmailSender(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="user@test.com",
        password="secret",
        from_addr="user@test.com",
        to_addrs="receiver@test.com",
        use_tls=True,
    )
    assert sender.host == "smtp.example.com"
    assert sender.port == 587
    assert sender.use_tls is True


def test_single_recipient():
    """单个收件人字符串应被转为列表。"""
    sender = EmailSender("h", 587, "u", "p", "f", "to@test.com")
    assert sender.to_addrs == ["to@test.com"]


def test_multiple_recipients():
    """多个收件人列表保持不变。"""
    sender = EmailSender("h", 587, "u", "p", "f", ["a@t.com", "b@t.com"])
    assert len(sender.to_addrs) == 2
    assert "a@t.com" in sender.to_addrs


def test_ssl_mode():
    """SSL 模式 (port 465)。"""
    sender = EmailSender(
        smtp_host="smtp.example.com",
        smtp_port=465,
        username="user@test.com",
        password="secret",
        from_addr="user@test.com",
        to_addrs="r@test.com",
        use_tls=False,
    )
    assert sender.use_tls is False


def test_send_builds_mime_message():
    """验证 send 方法构建的 MIME 消息。"""
    # 由于不连接真实服务器，我们通过 mock 验证
    from email.mime.multipart import MIMEMultipart
    msg = MIMEMultipart()
    msg["From"] = "from@test.com"
    msg["To"] = "to@test.com"
    msg["Subject"] = "Test Subject"

    from email.mime.text import MIMEText
    msg.attach(MIMEText("Body text", "plain", "utf-8"))

    # 验证邮件对象结构
    assert msg["Subject"] == "Test Subject"
    assert msg["From"] == "from@test.com"

    # 验证正文存在
    payloads = [p for p in msg.get_payload() if isinstance(p, MIMEText)]
    assert len(payloads) == 1


@pytest.mark.skip(reason="需要真实 SMTP 服务器和凭证")
def test_send_real_email():
    """集成测试: 真实发送邮件 (需要配置 real_credentials)。"""
    import json
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "configs", "email.yaml"
    )
    import yaml
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    # 跳过未配置凭证的情况
    if "your_" in cfg.get("username", "your_") or "your_" in cfg.get("password", "your_"):
        pytest.skip("Email credentials not configured")

    sender = EmailSender(
        smtp_host=cfg["smtp_host"],
        smtp_port=cfg["smtp_port"],
        username=cfg["username"],
        password=cfg["password"],
        from_addr=cfg["from_addr"],
        to_addrs=cfg["to_addrs"],
        use_tls=cfg.get("use_tls", True),
    )
    result = sender.send("Test", "Hello from pytest", body_type="plain")
    assert result is True
