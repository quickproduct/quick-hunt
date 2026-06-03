"""Email adapters — Mailtrap (REST) and SMTP, with factory."""
import asyncio
import base64
import hashlib
import re
import smtplib
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
import structlog

from services.api.core.config import get_settings

logger = structlog.get_logger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_adapter_lock = threading.Lock()
_adapter_instance: Optional["BaseEmailAdapter"] = None


@dataclass
class EmailPayload:
    to_email: str
    subject: str
    html_body: str
    plain_body: str
    to_name: str = ""
    from_email: str = ""
    from_name: str = ""
    attachment_bytes: Optional[bytes] = None
    attachment_filename: str = "resume.pdf"
    reply_to: str = ""


class BaseEmailAdapter(ABC):
    @abstractmethod
    async def send(self, payload: EmailPayload) -> str:
        """Send email and return provider message ID."""
        ...


class MailtrapAdapter(BaseEmailAdapter):
    """
    Mailtrap email adapter using their REST API directly (no SDK dependency).
    Sandbox:    POST https://sandbox.api.mailtrap.io/api/send/{inbox_id}
    Production: POST https://send.api.mailtrap.io/api/send
    """

    SANDBOX_URL = "https://sandbox.api.mailtrap.io/api/send/{inbox_id}"
    PRODUCTION_URL = "https://send.api.mailtrap.io/api/send"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.mailtrap_api_key
        if not self._api_key:
            raise ValueError(
                "MAILTRAP_API_KEY is not configured but email_provider=mailtrap. "
                "Set MAILTRAP_API_KEY in your environment."
            )
        self._sandbox = settings.mailtrap_sandbox
        self._inbox_id = settings.mailtrap_inbox_id
        self._from_email = settings.mailtrap_from_email
        self._from_name = settings.mailtrap_from_name
        if self._sandbox:
            self._url = self.SANDBOX_URL.format(inbox_id=self._inbox_id)
        else:
            self._url = self.PRODUCTION_URL
        logger.info(
            "email_adapter_init",
            provider="mailtrap",
            sandbox=self._sandbox,
            from_email=self._from_email,
            url=self._url,
        )

    async def send(self, payload: EmailPayload) -> str:
        from_email = payload.from_email or self._from_email
        from_name = payload.from_name or self._from_name

        body: dict = {
            "from": {"email": from_email, "name": from_name},
            "to": [{"email": payload.to_email}],
            "subject": payload.subject,
            "html": payload.html_body,
            "text": payload.plain_body,
        }

        if payload.attachment_bytes:
            body["attachments"] = [
                {
                    "content": base64.b64encode(payload.attachment_bytes).decode(),
                    "filename": payload.attachment_filename,
                    "type": "application/pdf",
                    "disposition": "attachment",
                }
            ]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._url, json=body, headers=headers)

        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Mailtrap error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        message_id = str(data.get("message_ids", [""])[0]) if "message_ids" in data else str(data)
        logger.info("email_sent", provider="mailtrap", to=payload.to_email, message_id=message_id)
        return message_id


class SMTPAdapter(BaseEmailAdapter):
    """SMTP adapter using asyncio.to_thread for non-blocking sends."""

    def __init__(self) -> None:
        settings = get_settings()
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._use_tls = settings.smtp_use_tls
        if not self._host or not self._user:
            raise ValueError(
                "SMTP_HOST and SMTP_USER are required but not configured "
                "for email_provider=smtp. Set them in your environment."
            )
        self._from_email = getattr(settings, 'smtp_from_email', None) or settings.smtp_user
        self._from_name = getattr(settings, 'smtp_from_name', None) or "Job Application Bot"
        logger.info("email_adapter_init", provider="smtp", host=self._host, port=self._port)

    def _send_sync(self, payload: EmailPayload) -> str:
        from_email = payload.from_email or self._from_email
        from_name = payload.from_name or self._from_name

        if payload.attachment_bytes:
            # RFC 2046: outer must be "mixed" when attachments are present.
            # Text alternatives go inside a nested "alternative" sub-part.
            msg = MIMEMultipart("mixed")
            msg["Subject"] = payload.subject
            msg["From"] = f"{from_name} <{from_email}>"
            msg["To"] = payload.to_email
            if payload.reply_to:
                msg["Reply-To"] = payload.reply_to
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(payload.plain_body, "plain"))
            alt.attach(MIMEText(payload.html_body, "html"))
            msg.attach(alt)
            part = MIMEBase("application", "octet-stream")
            part.set_payload(payload.attachment_bytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{payload.attachment_filename}"')
            msg.attach(part)
        else:
            # No attachment — "alternative" is correct.
            msg = MIMEMultipart("alternative")
            msg["Subject"] = payload.subject
            msg["From"] = f"{from_name} <{from_email}>"
            msg["To"] = payload.to_email
            if payload.reply_to:
                msg["Reply-To"] = payload.reply_to
            msg.attach(MIMEText(payload.plain_body, "plain"))
            msg.attach(MIMEText(payload.html_body, "html"))

        if self._use_tls:
            server = smtplib.SMTP(self._host, self._port)
            server.ehlo()
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(self._host, self._port)

        server.login(self._user, self._password)
        server.sendmail(from_email, [payload.to_email], msg.as_string())
        server.quit()

        import uuid
        message_id = uuid.uuid4().hex
        logger.info("email_sent", provider="smtp", to=payload.to_email, message_id=message_id)
        return message_id

    async def send(self, payload: EmailPayload) -> str:
        return await asyncio.to_thread(self._send_sync, payload)


class BrevoAdapter(BaseEmailAdapter):
    """
    Brevo (ex-Sendinblue) transactional email adapter using their REST API.
    Endpoint: POST https://api.brevo.com/v3/smtp/email
    Supports attachments as base64-encoded content.
    """

    API_URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.brevo_api_key
        if not self._api_key:
            raise ValueError(
                "BREVO_API_KEY is not configured but email_provider=brevo. "
                "Set BREVO_API_KEY in your environment."
            )
        self._from_email = settings.brevo_from_email
        self._from_name = settings.brevo_from_name
        logger.info(
            "email_adapter_init",
            provider="brevo",
            from_email=self._from_email,
        )

    async def send(self, payload: EmailPayload) -> str:
        if not payload.to_email or not _EMAIL_RE.match(payload.to_email):
            raise ValueError(f"Invalid destination email: {payload.to_email!r}")

        from_email = payload.from_email or self._from_email
        from_name = payload.from_name or self._from_name

        if not from_email or not _EMAIL_RE.match(from_email):
            raise ValueError(f"Invalid sender email: {from_email!r}")

        body: dict = {
            "sender": {"name": from_name, "email": from_email},
            "to": [{"email": payload.to_email, "name": payload.to_name or "Hiring Manager"}],
            "subject": payload.subject,
            "htmlContent": payload.html_body,
            "textContent": payload.plain_body,
        }

        if payload.attachment_bytes:
            body["attachment"] = [
                {
                    "content": base64.b64encode(payload.attachment_bytes).decode(),
                    "name": payload.attachment_filename,
                }
            ]

        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json",
            "X-Mailin-Client": "ai-job-hunter",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.API_URL, json=body, headers=headers)

        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Brevo error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        message_id = data.get("messageId", str(data))
        logger.info("email_sent", provider="brevo", to=payload.to_email, message_id=message_id)
        return message_id


def get_email_adapter() -> BaseEmailAdapter:
    """Singleton factory — returns adapter based on EMAIL_PROVIDER env var."""
    global _adapter_instance
    if _adapter_instance is None:
        with _adapter_lock:
            if _adapter_instance is None:
                settings = get_settings()
                if settings.email_provider == "brevo":
                    _adapter_instance = BrevoAdapter()
                elif settings.email_provider == "mailtrap":
                    _adapter_instance = MailtrapAdapter()
                else:
                    _adapter_instance = SMTPAdapter()
    return _adapter_instance
