"""
T3 真实测试：发送一封真实测试邮件。

用法:
  python tests/real/real_email.py

前置条件:
  - .env 已配置真实的 SMTP 凭证

安全:
  - 只发送到配置的收件人地址
  - 正文不含敏感信息
  - 不会自动加入生产收件人列表（仅用第一个地址）
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


def main():
    from config import load_email_config

    cfg = load_email_config()
    if not cfg:
        print("[SKIP] SMTP not configured in .env (SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD)")
        return 0

    username = cfg.get("username", "")
    password = cfg.get("password", "")

    if not username or "@" not in username or not password:
        print("[SKIP] SMTP credentials not configured in .env")
        return 0

    to_addrs = cfg.get("to_addrs", [])
    if not to_addrs:
        print("[SKIP] .env has no SMTP_TO_ADDRS")
        return 0

    # 仅发送到第一个地址（通常是自己的地址）
    test_addr = to_addrs[0]

    from processors.email_sender import EmailSender

    sender = EmailSender(
        smtp_host=cfg["smtp_host"],
        smtp_port=cfg["smtp_port"],
        username=username,
        password=password,
        from_addr=cfg["from_addr"],
        to_addrs=test_addr,
        use_tls=cfg.get("use_tls", True),
    )

    subject = "[PapersCrawler T3 Test] SMTP 连接测试"
    body = (
        "这是一封来自 PapersCrawler T3 真实测试的自动邮件。\n\n"
        "如果收到此邮件，说明 SMTP 配置正确，邮件发送模块正常工作。\n\n"
        "--\nPapersCrawler T3 Test"
    )

    result = sender.send(subject, body, body_type="plain")
    assert result is True, "send() should return True"

    print(f"[OK] Test email sent to {test_addr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
