"""
Tests: Email sending (email_sender.py)

Coverage:
  - EmailSender instantiation
  - Recipient list handling (single / multiple)
  - TLS vs SSL mode
  - send() method with mocked SMTP (TLS, SSL, attachments)
"""

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from processors.email_sender import EmailSender


# ---- Instantiation ----

def test_email_sender_instantiation():
    """Verify EmailSender correctly initializes from config."""
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
    """Single recipient string should be converted to a list."""
    sender = EmailSender("h", 587, "u", "p", "f", "to@test.com")
    assert sender.to_addrs == ["to@test.com"]


def test_multiple_recipients():
    """Multiple recipients list should be preserved."""
    sender = EmailSender("h", 587, "u", "p", "f", ["a@t.com", "b@t.com"])
    assert len(sender.to_addrs) == 2
    assert "a@t.com" in sender.to_addrs


def test_ssl_mode():
    """SSL mode (port 465) should set use_tls=False."""
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


# ---- send() method (mocked SMTP) ----

def test_send_tls_calls_correct_methods():
    """Verify send() with TLS calls starttls, login, send_message, quit."""
    with patch('smtplib.SMTP') as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        sender = EmailSender(
            "smtp.test.com", 587, "user", "pass",
            "from@test.com", ["to@test.com"]
        )
        result = sender.send("Test Subject", "Test Body")

        mock_smtp.assert_called_once_with("smtp.test.com", 587, timeout=30)
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("user", "pass")
        mock_instance.send_message.assert_called_once()
        mock_instance.quit.assert_called_once()
        assert result is True


def test_send_ssl_calls_correct_methods():
    """Verify send() with SSL uses SMTP_SSL and skips starttls."""
    with patch('smtplib.SMTP_SSL') as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        sender = EmailSender(
            "smtp.test.com", 465, "user", "pass",
            "from@test.com", ["to@test.com"],
            use_tls=False,
        )
        result = sender.send("Test Subject", "Test Body")

        mock_smtp.assert_called_once_with("smtp.test.com", 465, timeout=30)
        mock_instance.login.assert_called_once_with("user", "pass")
        mock_instance.send_message.assert_called_once()
        mock_instance.quit.assert_called_once()
        assert result is True


def test_send_with_attachment():
    """Verify send() with a valid attachment."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("test attachment content")
        tmp_path = f.name

    try:
        with patch('smtplib.SMTP') as mock_smtp:
            mock_instance = MagicMock()
            mock_smtp.return_value = mock_instance

            sender = EmailSender(
                "smtp.test.com", 587, "user", "pass",
                "from@test.com", ["to@test.com"]
            )
            result = sender.send("Subject", "Body", attachments=[tmp_path])

            assert result is True
            mock_instance.send_message.assert_called_once()
            # Verify the sent message is multipart (has attachment)
            sent_msg = mock_instance.send_message.call_args[0][0]
            assert sent_msg.is_multipart()
    finally:
        os.unlink(tmp_path)


def test_send_with_missing_attachment():
    """Non-existent attachment should be silently skipped."""
    with patch('smtplib.SMTP') as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        sender = EmailSender(
            "smtp.test.com", 587, "user", "pass",
            "from@test.com", ["to@test.com"]
        )
        result = sender.send("Subject", "Body", attachments=["/nonexistent/file.pdf"])

        assert result is True
        mock_instance.send_message.assert_called_once()
        # MIMEMultipart is always multipart; verify no attachment payload
        sent_msg = mock_instance.send_message.call_args[0][0]
        assert len(sent_msg.get_payload()) == 1  # only text body, no attachment
