"""
email_sender.py
==============
通过 SMTP 协议发送邮件报告。

功能：
  - 支持 TLS (STARTTLS, 端口 587) 和 SSL (端口 465) 两种加密方式
  - 支持纯文本 (plain) 和 HTML 两种正文格式
  - 支持添加多个附件
  - 适用于 QQ邮箱、163邮箱、Gmail 等主流邮件服务商

使用前提：
  需要邮箱开启 IMAP/SMTP 服务并获取"授权码"（非邮箱登录密码）。
  以 QQ邮箱为例：设置 → 账户 → POP3/IMAP/SMTP服务 → 生成授权码。
"""

import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


class EmailSender:
    """
    SMTP 邮件发送器。

    使用示例:
        sender = EmailSender(
            smtp_host="smtp.qq.com",
            smtp_port=587,
            username="your_email@qq.com",
            password="your_auth_code",     # 授权码，不是邮箱密码
            from_addr="your_email@qq.com",
            to_addrs=["receiver@example.com"],
            use_tls=True,                  # 端口 587 用 TLS
        )
        sender.send(
            subject="测试邮件",
            body="<h1>你好</h1>",
            body_type="html",
            attachments=["/path/to/report.pdf"],
        )
    """

    def __init__(self, smtp_host, smtp_port, username, password,
                 from_addr, to_addrs, use_tls=True):
        """
        初始化邮件发送器。

        Args:
            smtp_host: SMTP 服务器地址
                       常用服务器: QQ邮箱 → smtp.qq.com
                                  163邮箱 → smtp.163.com
                                  Gmail  → smtp.gmail.com
            smtp_port: SMTP 端口
                       TLS (STARTTLS) → 587
                       SSL           → 465
            username:  登录用户名 (通常就是邮箱地址)
            password:  授权码 (非邮箱登录密码！)
            from_addr: 发件人邮箱地址
            to_addrs:  收件人列表，可以是单个字符串或字符串列表
            use_tls:   是否使用 STARTTLS 加密 (端口 587 时为 True，465 时为 False)
        """
        self.host = smtp_host
        self.port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        # 统一转为列表，方便后续处理
        self.to_addrs = to_addrs if isinstance(to_addrs, list) else [to_addrs]
        self.use_tls = use_tls

    def send(self, subject, body, body_type="plain", attachments=None):
        """
        发送邮件。

        含 1 次自动重试（共 2 次尝试），应对 SMTP 瞬态故障。
        TLS 模式下在 STARTTLS 后主动发送 EHLO 重新协商能力（部分
        国内 SMTP 服务器需要）。

        Args:
            subject:     邮件主题
            body:        邮件正文内容
            body_type:   "plain" 表示纯文本, "html" 表示 HTML 格式
            attachments: 附件路径列表，路径不存在则自动跳过

        Returns:
            bool: 发送成功返回 True

        Raises:
            smtplib.SMTPException: 所有尝试均失败时抛出最后一次异常
            OSError:               网络不可达 / DNS 解析失败
        """
        # ---- 1. 构建邮件对象 ----
        msg = MIMEMultipart()
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, body_type, "utf-8"))

        # ---- 2. 添加附件 ----
        if attachments:
            for path in attachments:
                path = Path(path)
                if not path.exists():
                    continue
                with open(path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{path.name}"'
                    )
                    msg.attach(part)

        # ---- 3. 连接并发送（含 1 次重试） ----
        for attempt in range(2):
            server = None
            try:
                if self.use_tls:
                    # TLS (STARTTLS): 先明文连接，再升级为 TLS
                    server = smtplib.SMTP(self.host, self.port, timeout=30)
                    server.starttls()
                    # RFC 3207: TLS 协商后须重新 EHLO 以获取加密通道内能力
                    server.ehlo()
                else:
                    # SSL: 直接建立加密连接
                    server = smtplib.SMTP_SSL(self.host, self.port, timeout=30)

                server.login(self.username, self.password)
                server.send_message(msg)
                return True

            except (smtplib.SMTPException, OSError) as e:
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise

            finally:
                if server is not None:
                    try:
                        server.quit()
                    except Exception:
                        pass
