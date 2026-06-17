"""
Email Service: Dual-Provider Email Delivery (Resend + SMTP Fallback)

Phase 4A.1: Notification-Stack Backend
Priority: HIGH
Status: IMPLEMENTED

Providers:
- Resend (Primary): API-based, better deliverability, free tier 3,000/month
- SMTP (Fallback): Traditional SMTP when Resend is unavailable

IMPORTANT: Email failures MUST NOT block alert processing (try/except, return False).
"""

import asyncio
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, Optional

from ..core.config import get_settings
from ..core.logging_config import get_logger
from ..core.metrics import increment_email_error, increment_email_sent, observe_email_latency

logger = get_logger(__name__)


class EmailService:
    """
    Dual-provider email delivery service.

    Tries Resend first (if API key configured), falls back to SMTP.
    All methods are non-blocking and return bool (never raise).
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._jinja_env: Optional[object] = None
        self._resend_available: bool = False
        self._init_providers()
        self._init_templates()

    def _init_providers(self) -> None:
        """Initialize email providers based on configuration."""
        # Check Resend availability
        if self._settings.notification.resend_api_key:
            try:
                import resend

                resend.api_key = self._settings.notification.resend_api_key
                self._resend_available = True
                logger.info("Email provider initialized: Resend (primary)")
            except ImportError:
                logger.warning(
                    "resend package not installed, falling back to SMTP. "
                    "Install with: pip install resend"
                )
                self._resend_available = False
        else:
            logger.info("No RESEND_API_KEY configured, using SMTP only")

        if self._settings.notification.smtp_enabled:
            logger.info(
                f"Email provider available: SMTP ({self._settings.notification.smtp_host}:"
                f"{self._settings.notification.smtp_port})"
            )

    def _init_templates(self) -> None:
        """Initialize Jinja2 template engine."""
        try:
            from jinja2 import Environment, FileSystemLoader

            template_dir = self._settings.notification.email_template_dir

            # Resolve relative paths from the server root directory
            template_path = Path(__file__).parent.parent.parent / template_dir
            if not template_path.exists():
                logger.warning(f"Email template directory not found: {template_path}")
                return

            self._jinja_env = Environment(
                loader=FileSystemLoader(str(template_path)),
                autoescape=True,
            )
            logger.info(f"Email templates loaded from: {template_path}")
        except ImportError:
            logger.warning("jinja2 not installed, email templates disabled")
        except Exception as e:
            logger.error(f"Failed to initialize email templates: {e}")

    def _render_template(self, template_name: str, context: Dict) -> Optional[str]:
        """Render a Jinja2 email template."""
        if not self._jinja_env:
            return None

        try:
            template = self._jinja_env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Failed to render email template '{template_name}': {e}")
            return None

    @property
    def is_available(self) -> bool:
        """Check if any email provider is available."""
        return self._settings.notification.email_enabled and (
            self._resend_available or self._settings.notification.smtp_enabled
        )

    @property
    def provider_name(self) -> str:
        """Return the name of the active email provider."""
        if self._resend_available:
            return "Resend"
        if self._settings.notification.smtp_enabled:
            return "SMTP"
        return "None"

    async def send_email(
        self,
        to: str,
        subject: str,
        html_body: Optional[str] = None,
        text_body: Optional[str] = None,
        template_name: Optional[str] = None,
        template_context: Optional[Dict] = None,
    ) -> bool:
        """
        Send an email via Resend (primary) or SMTP (fallback).

        IMPORTANT: Never raises exceptions. Returns False on failure.

        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML email body (used if template_name is None)
            text_body: Plain text fallback
            template_name: Jinja2 template filename (e.g., "alert_critical.html")
            template_context: Template context variables

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._settings.notification.email_enabled:
            logger.debug("Email delivery disabled (EMAIL_ENABLED=false)")
            return False

        # Render template if provided
        if template_name and template_context:
            rendered = self._render_template(template_name, template_context)
            if rendered:
                html_body = rendered

        if not html_body and not text_body:
            logger.warning("Email send called with no body content")
            return False

        sender = self._settings.notification.email_from

        # Try Resend first
        if self._resend_available:
            success = await self._send_via_resend(sender, to, subject, html_body, text_body)
            if success:
                return True
            logger.warning("Resend delivery failed, attempting SMTP fallback")

        # Fallback to SMTP
        if self._settings.notification.smtp_enabled:
            return await self._send_via_smtp(sender, to, subject, html_body, text_body)

        logger.warning("No email provider available for delivery")
        return False

    async def _send_via_resend(
        self,
        sender: str,
        to: str,
        subject: str,
        html_body: Optional[str],
        text_body: Optional[str],
    ) -> bool:
        """Send email via Resend API."""
        import time as _time

        start = _time.monotonic()
        try:
            import resend

            params = {
                "from": sender,
                "to": [to],
                "subject": subject,
            }
            if html_body:
                params["html"] = html_body
            if text_body:
                params["text"] = text_body

            # Resend SDK is sync — run in thread pool
            result = await asyncio.to_thread(resend.Emails.send, params)
            duration = _time.monotonic() - start
            increment_email_sent("resend", True)
            observe_email_latency("resend", duration)
            logger.info(f"Email sent via Resend to {to} (id={result.get('id', 'unknown')})")
            return True
        except Exception as e:
            duration = _time.monotonic() - start
            increment_email_sent("resend", False)
            observe_email_latency("resend", duration)
            increment_email_error("resend", type(e).__name__)
            logger.error(f"Resend email delivery failed: {e}")
            return False

    async def _send_via_smtp(
        self,
        sender: str,
        to: str,
        subject: str,
        html_body: Optional[str],
        text_body: Optional[str],
    ) -> bool:
        """Send email via SMTP (blocking call in thread pool)."""
        cfg = self._settings.notification

        def _send_sync() -> None:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:
                if cfg.smtp_use_tls:
                    server.starttls()
                if cfg.smtp_username and cfg.smtp_password:
                    server.login(cfg.smtp_username, cfg.smtp_password)

                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = sender
                msg["To"] = to

                if html_body:
                    msg.set_content(text_body or "Please view this email in an HTML client.")
                    msg.add_alternative(html_body, subtype="html")
                else:
                    msg.set_content(text_body or "")

                server.send_message(msg)

        import time as _time

        start = _time.monotonic()
        try:
            await asyncio.to_thread(_send_sync)
            duration = _time.monotonic() - start
            increment_email_sent("smtp", True)
            observe_email_latency("smtp", duration)
            logger.info(f"Email sent via SMTP to {to}")
            return True
        except Exception as e:
            duration = _time.monotonic() - start
            increment_email_sent("smtp", False)
            observe_email_latency("smtp", duration)
            increment_email_error("smtp", type(e).__name__)
            logger.error(f"SMTP email delivery failed: {e}")
            return False

    async def send_test_email(self, to: str) -> bool:
        """
        Send a test email to verify configuration.

        Args:
            to: Recipient email address

        Returns:
            True if sent successfully
        """
        provider = "Resend" if self._resend_available else "SMTP"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        return await self.send_email(
            to=to,
            subject="AutomationOne — Email Test",
            template_name="test.html",
            template_context={
                "provider": provider,
                "timestamp": now,
                "recipient": to,
            },
            text_body=f"AutomationOne email test successful. Provider: {provider}, Time: {now}",
        )

    async def send_critical_alert(
        self,
        to: str,
        title: str,
        body: str,
        severity: str,
        source: str,
        category: str,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """
        Send a critical alert email immediately.

        Args:
            to: Recipient email address
            title: Alert title
            body: Alert body
            severity: Alert severity
            source: Alert source
            category: Alert category
            metadata: Additional context

        Returns:
            True if sent successfully
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        context = {
            "title": title,
            "body": body,
            "severity": severity,
            "source": source,
            "category": category,
            "timestamp": now,
            "esp_id": (metadata or {}).get("esp_id"),
            "sensor_type": (metadata or {}).get("sensor_type"),
        }

        return await self.send_email(
            to=to,
            subject=f"[CRITICAL] {title} — AutomationOne",
            template_name="alert_critical.html",
            template_context=context,
            text_body=f"CRITICAL ALERT: {title}\n\n{body}\n\nSource: {source}\nCategory: {category}\nTime: {now}",
        )

    async def send_digest(
        self,
        to: str,
        notifications: list,
        digest_period: str = "1 hour",
    ) -> bool:
        """
        Send a digest email with batched notifications.

        Args:
            to: Recipient email address
            notifications: List of notification dicts with title, body, severity, source, timestamp
            digest_period: Human-readable digest period string

        Returns:
            True if sent successfully
        """
        if not notifications:
            return False

        context = {
            "notifications": notifications,
            "notification_count": len(notifications),
            "digest_period": digest_period,
        }

        return await self.send_email(
            to=to,
            subject=f"Alert Digest ({len(notifications)} notifications) — AutomationOne",
            template_name="alert_digest.html",
            template_context=context,
            text_body="\n\n".join(
                f"[{n.get('severity', 'INFO').upper()}] {n.get('title', 'Notification')}: {n.get('body', '')}"
                for n in notifications
            ),
        )


# Module-level singleton
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create the EmailService singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
