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

        工作流程:
          1. 构建 MIMEMultipart 邮件对象
          2. 添加邮件头 (From, To, Subject)
          3. 添加正文 (纯文本或 HTML)
          4. 逐个添加附件（文件以 base64 编码）
          5. 连接 SMTP 服务器，加密，登录，发送

        Args:
            subject:     邮件主题
            body:        邮件正文内容
            body_type:   "plain" 表示纯文本, "html" 表示 HTML 格式
            attachments: 附件路径列表，如 ["/path/to/file.pdf", "/path/to/photo.png"]
                         路径不存在则自动跳过该附件

        Returns:
            bool: 发送成功返回 True

        Raises:
            smtplib.SMTPException: SMTP 连接或认证失败
            socket.gaierror:      服务器地址解析失败
        """
        # ---- 1. 构建邮件对象 ----
        msg = MIMEMultipart()                   # 支持正文+附件的复合邮件
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)    # 多个收件人用逗号分隔
        msg["Subject"] = subject
        msg.attach(MIMEText(body, body_type, "utf-8"))  # 正文使用 UTF-8 编码

        # ---- 2. 添加附件 ----
        if attachments:
            for path in attachments:
                path = Path(path)
                if not path.exists():
                    continue                   # 附件不存在则静默跳过
                with open(path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)  # 附件 base64 编码
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{path.name}"'
                    )
                    msg.attach(part)

        # ---- 3. 连接 SMTP 服务器 ----
        # TLS 模式: 先建立普通连接, 再升级为加密连接 (STARTTLS)
        if self.use_tls:
            server = smtplib.SMTP(self.host, self.port, timeout=30)
            server.starttls()
        # SSL 模式: 直接建立加密连接
        else:
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=30)

        # ---- 4. 登录并发送 ----
        server.login(self.username, self.password)
        server.send_message(msg)
        server.quit()
        return True
