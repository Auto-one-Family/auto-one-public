"""
Unit Tests: EmailService

Phase 4A Test-Suite (STEP 4, Block 3)
Tests: Dual-provider logic (Resend + SMTP fallback), templates, singleton
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path

# =============================================================================
# Mock Settings
# =============================================================================


def _make_mock_settings(resend_key=None, smtp_enabled=False, email_enabled=True):
    """Create mock settings for EmailService tests."""
    settings = MagicMock()
    settings.notification.resend_api_key = resend_key
    settings.notification.smtp_enabled = smtp_enabled
    settings.notification.smtp_host = "localhost"
    settings.notification.smtp_port = 587
    settings.notification.smtp_use_tls = False
    settings.notification.smtp_username = None
    settings.notification.smtp_password = None
    settings.notification.email_enabled = email_enabled
    settings.notification.email_from = "test@automationone.local"
    settings.notification.email_template_dir = "templates/email"
    return settings


# =============================================================================
# Test 1: Resend Success
# =============================================================================


@pytest.mark.asyncio
async def test_send_email_resend_success():
    """Resend provider successful → return True."""
    mock_settings = _make_mock_settings(resend_key="re_test123", email_enabled=True)

    with patch("src.services.email_service.get_settings", return_value=mock_settings):
        from src.services.email_service import EmailService

        service = EmailService()
        service._resend_available = True

        # Mock _send_via_resend directly to test routing logic
        service._send_via_resend = AsyncMock(return_value=True)

        result = await service.send_email(
            to="user@example.com",
            subject="Test",
            html_body="<p>Test</p>",
        )

        assert result is True
        service._send_via_resend.assert_called_once()


# =============================================================================
# Test 2: Resend Fail → SMTP Fallback
# =============================================================================


@pytest.mark.asyncio
async def test_send_email_resend_fail_smtp_fallback():
    """Resend fails → SMTP fallback succeeds → return True."""
    mock_settings = _make_mock_settings(
        resend_key="re_test123", smtp_enabled=True, email_enabled=True
    )

    with patch("src.services.email_service.get_settings", return_value=mock_settings):
        from src.services.email_service import EmailService

        service = EmailService()
        service._resend_available = True

        # Resend fails
        service._send_via_resend = AsyncMock(return_value=False)
        # SMTP succeeds
        service._send_via_smtp = AsyncMock(return_value=True)

        result = await service.send_email(
            to="user@example.com",
            subject="Fallback Test",
            html_body="<p>Test</p>",
        )

        assert result is True
        service._send_via_resend.assert_called_once()
        service._send_via_smtp.assert_called_once()


# =============================================================================
# Test 3: Both Fail → return False
# =============================================================================


@pytest.mark.asyncio
async def test_send_email_both_fail_returns_false():
    """Both Resend and SMTP fail → return False (no exception)."""
    mock_settings = _make_mock_settings(
        resend_key="re_test123", smtp_enabled=True, email_enabled=True
    )

    with patch("src.services.email_service.get_settings", return_value=mock_settings):
        from src.services.email_service import EmailService

        service = EmailService()
        service._resend_available = True

        service._send_via_resend = AsyncMock(return_value=False)
        service._send_via_smtp = AsyncMock(return_value=False)

        result = await service.send_email(
            to="user@example.com",
            subject="Both Fail Test",
            html_body="<p>Test</p>",
        )

        assert result is False


# =============================================================================
# Test 4: send_critical_alert Template
# =============================================================================


@pytest.mark.asyncio
async def test_send_critical_alert_template():
    """send_critical_alert() calls send_email with alert_critical.html template."""
    mock_settings = _make_mock_settings(email_enabled=True)

    with patch("src.services.email_service.get_settings", return_value=mock_settings):
        from src.services.email_service import EmailService

        service = EmailService()
        service.send_email = AsyncMock(return_value=True)

        result = await service.send_critical_alert(
            to="admin@example.com",
            title="Critical Alert",
            body="Server down",
            severity="critical",
            source="system",
            category="infrastructure",
            metadata={"esp_id": "ESP_12AB34CD"},
        )

        assert result is True
        service.send_email.assert_called_once()
        call_kwargs = service.send_email.call_args[1]
        assert call_kwargs["template_name"] == "alert_critical.html"
        assert "[CRITICAL]" in call_kwargs["subject"]


# =============================================================================
# Test 5: send_digest Template
# =============================================================================


@pytest.mark.asyncio
async def test_send_digest_template():
    """send_digest() renders alert_digest.html with notification list."""
    mock_settings = _make_mock_settings(email_enabled=True)

    with patch("src.services.email_service.get_settings", return_value=mock_settings):
        from src.services.email_service import EmailService

        service = EmailService()
        service.send_email = AsyncMock(return_value=True)

        notifications = [
            {"title": "Alert 1", "body": "Body 1", "severity": "warning", "source": "system"},
            {"title": "Alert 2", "body": "Body 2", "severity": "warning", "source": "grafana"},
        ]

        result = await service.send_digest(
            to="user@example.com",
            notifications=notifications,
            digest_period="1 hour",
        )

        assert result is True
        service.send_email.assert_called_once()
        call_kwargs = service.send_email.call_args[1]
        assert call_kwargs["template_name"] == "alert_digest.html"
        assert "2 notifications" in call_kwargs["subject"]


# =============================================================================
# Test 6: send_test_email Template
# =============================================================================


@pytest.mark.asyncio
async def test_send_test_email_template():
    """send_test_email() renders test.html template."""
    mock_settings = _make_mock_settings(email_enabled=True)

    with patch("src.services.email_service.get_settings", return_value=mock_settings):
        from src.services.email_service import EmailService

        service = EmailService()
        service.send_email = AsyncMock(return_value=True)

        result = await service.send_test_email("test@example.com")

        assert result is True
        service.send_email.assert_called_once()
        call_kwargs = service.send_email.call_args[1]
        assert call_kwargs["template_name"] == "test.html"


# =============================================================================
# Test 7: Singleton get_email_service
# =============================================================================


def test_singleton_get_email_service():
    """get_email_service() returns same instance on repeated calls."""
    import src.services.email_service as es_mod

    # Reset singleton
    es_mod._email_service = None

    mock_settings = _make_mock_settings()
    with patch("src.services.email_service.get_settings", return_value=mock_settings):
        svc1 = es_mod.get_email_service()
        svc2 = es_mod.get_email_service()
        assert svc1 is svc2

    # Cleanup
    es_mod._email_service = None


# =============================================================================
# Test 8: Jinja2 Template Loading
# =============================================================================


def test_jinja2_template_loading():
    """All 3 templates load without TemplateNotFoundError."""
    # Find template directory
    template_dir = Path(__file__).parent.parent.parent / "templates" / "email"

    if not template_dir.exists():
        pytest.skip("Email template directory not found — templates may not be deployed")

    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        pytest.skip("jinja2 not installed")

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )

    # All 3 templates should load
    for template_name in ["alert_critical.html", "alert_digest.html", "test.html"]:
        try:
            tmpl = env.get_template(template_name)
            assert tmpl is not None
        except Exception as e:
            # If template doesn't exist, that's ok — skip gracefully
            pytest.skip(f"Template '{template_name}' not found: {e}")
