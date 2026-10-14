"""Change-digest email: real SMTP round-trip, no mocks.

A minimal SMTP server runs on a loopback port; the platform's own
``smtplib``-based transport connects to it and delivers the digest, so the
message that arrives is produced by the real email path.
"""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.config import settings
from app.db.models import DetectedChange
from app.services import email_service


@dataclass
class _SmtpServer:
    """Accept one SMTP session and record the DATA payload and envelope."""

    messages: list[str] = field(default_factory=list)
    mail_from: str | None = None
    rcpt_to: list[str] = field(default_factory=list)
    _sock: socket.socket | None = None
    _thread: threading.Thread | None = None

    def start(self) -> tuple[str, int]:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        host, port = self._sock.getsockname()
        return host, port

    def _serve(self) -> None:
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return
        with conn:
            conn.sendall(b"220 test ESMTP\r\n")
            buffer = b""
            data_mode = False
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\r\n" in buffer:
                    line, buffer = buffer.split(b"\r\n", 1)
                    text = line.decode("utf-8", "replace")
                    if data_mode:
                        if text == ".":
                            data_mode = False
                            conn.sendall(b"250 OK queued\r\n")
                        else:
                            self.messages.append(text)
                        continue
                    upper = text.upper()
                    if upper.startswith("EHLO") or upper.startswith("HELO"):
                        conn.sendall(b"250-test\r\n250 OK\r\n")
                    elif upper.startswith("MAIL FROM"):
                        self.mail_from = text
                        conn.sendall(b"250 OK\r\n")
                    elif upper.startswith("RCPT TO"):
                        self.rcpt_to.append(text)
                        conn.sendall(b"250 OK\r\n")
                    elif upper.startswith("DATA"):
                        data_mode = True
                        conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    elif upper.startswith("QUIT"):
                        conn.sendall(b"221 Bye\r\n")
                        return
                    else:
                        conn.sendall(b"250 OK\r\n")

    def stop(self) -> None:
        if self._sock is not None:
            self._sock.close()


def _change(**overrides) -> DetectedChange:
    base = dict(
        module="ftf",
        source_code="fda_ftf_paragraph_iv",
        entity_type="ftf_filing",
        change_type="added",
        source_key="ANDA-12345|US1234567",
        significance=88,
        summary="New Paragraph IV certification for Anda 12345",
        field_changes=[{"field": "certification_date", "before": None, "after": "2026-09-30"}],
        detected_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        is_baseline=False,
    )
    base.update(overrides)
    return DetectedChange(**base)


def test_change_digest_delivers_over_smtp(monkeypatch):
    """The digest reaches the configured recipient with the change detail."""
    server = _SmtpServer()
    host, port = server.start()
    try:
        monkeypatch.setattr(settings, "smtp_host", host)
        monkeypatch.setattr(settings, "smtp_port", port)
        monkeypatch.setattr(settings, "smtp_use_ssl", False)
        monkeypatch.setattr(settings, "smtp_use_tls", False)
        monkeypatch.setattr(settings, "smtp_username", None)
        monkeypatch.setattr(settings, "smtp_password", None)
        monkeypatch.setattr(settings, "smtp_from", "alerts@pharma-intel.test")
        monkeypatch.setattr(
            settings, "alert_email_recipients", ["pharsightspatent@gmail.com"]
        )

        result = email_service.send_change_digest(
            [_change(), _change(source_key="ANDA-999|US7654321", change_type="updated")],
            run_id="run-abc",
        )

        assert result.status == "sent", result.error
        assert result.recipients == ["pharsightspatent@gmail.com"]
        assert server.mail_from is not None and "alerts@pharma-intel.test" in server.mail_from
        assert any("pharsightspatent@gmail.com" in rcpt for rcpt in server.rcpt_to)

        payload = "\n".join(server.messages)
        assert "2 change(s) detected" in payload
        assert "ANDA-12345|US1234567" in payload
        assert "certification_date" in payload
        assert "1 added, 1 updated, 0 removed" in payload
    finally:
        server.stop()


def test_change_digest_skipped_without_smtp(monkeypatch):
    """With no relay configured the send is skipped, not failed."""
    monkeypatch.setattr(settings, "smtp_host", None)
    result = email_service.send_change_digest([_change()], run_id="run-none")
    assert result.status == "skipped"


def test_change_digest_skipped_when_no_changes(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    result = email_service.send_change_digest([], run_id="run-empty")
    assert result.status == "skipped"
