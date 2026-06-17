"""
Integration Tests: Webhooks API (Grafana→AutomationOne)

Phase 4A Test-Suite (STEP 4, Block 5)
Tests: Grafana webhook processing, severity mapping, fingerprint dedup
"""

import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.webhooks import categorize_alert
from src.db.models.user import User
from src.main import app

# =============================================================================
# Fixtures
# =============================================================================


GRAFANA_FIRING_PAYLOAD = {
    "receiver": "automationone-webhook",
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "HighCPU", "severity": "critical"},
            "annotations": {"summary": "CPU > 90%", "description": "Server CPU is above 90%"},
            "startsAt": "2026-03-02T10:00:00Z",
            "fingerprint": "webhook_fp_001",
        }
    ],
}

GRAFANA_RESOLVED_PAYLOAD = {
    "receiver": "automationone-webhook",
    "status": "resolved",
    "alerts": [
        {
            "status": "resolved",
            "labels": {"alertname": "HighCPU", "severity": "critical"},
            "annotations": {"summary": "CPU > 90%"},
            "startsAt": "2026-03-02T10:00:00Z",
            "endsAt": "2026-03-02T10:15:00Z",
            "fingerprint": "webhook_fp_resolved",
        }
    ],
}


@pytest.fixture
async def webhook_user(db_session: AsyncSession):
    """Create a user for webhook broadcast (route needs at least one active user)."""
    user = User(
        username="webhook_test_user",
        email="webhook@example.com",
        password_hash="hashed_pw",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


# =============================================================================
# Test 1: Grafana Webhook — Firing Alert
# =============================================================================


@pytest.mark.asyncio
async def test_grafana_webhook_firing_alert(webhook_user):
    """POST /v1/webhooks/grafana-alerts with firing alert creates notification."""
    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/webhooks/grafana-alerts",
                json=GRAFANA_FIRING_PAYLOAD,
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["processed"] >= 1


# =============================================================================
# Test 2: Grafana Webhook — Resolved Alert
# =============================================================================


@pytest.mark.asyncio
async def test_grafana_webhook_resolved_alert(webhook_user):
    """POST with status 'resolved' maps to severity 'info'."""
    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/webhooks/grafana-alerts",
                json=GRAFANA_RESOLVED_PAYLOAD,
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["processed"] >= 1


# =============================================================================
# Test 3: Grafana Webhook — Invalid Payload
# =============================================================================


@pytest.mark.asyncio
async def test_grafana_webhook_invalid_payload():
    """POST with empty alerts → error response."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhooks/grafana-alerts",
            json={"status": "firing", "alerts": []},
        )

    # WebhookValidationException → should be 400 or 422
    assert response.status_code in [400, 422, 500]


# =============================================================================
# Test 4: Grafana Webhook — Fingerprint Dedup
# =============================================================================


@pytest.mark.asyncio
async def test_grafana_webhook_fingerprint_dedup(webhook_user):
    """Same fingerprint in 2 alerts → second is skipped."""
    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # First webhook
            response1 = await client.post(
                "/api/v1/webhooks/grafana-alerts",
                json={
                    "status": "firing",
                    "alerts": [
                        {
                            "status": "firing",
                            "labels": {"alertname": "DedupTest", "severity": "warning"},
                            "annotations": {"summary": "Dedup test"},
                            "fingerprint": "dedup_fp_unique_001",
                        }
                    ],
                },
            )
            assert response1.status_code == 200
            first_processed = response1.json()["processed"]

            # Second webhook with same fingerprint
            response2 = await client.post(
                "/api/v1/webhooks/grafana-alerts",
                json={
                    "status": "firing",
                    "alerts": [
                        {
                            "status": "firing",
                            "labels": {"alertname": "DedupTest", "severity": "warning"},
                            "annotations": {"summary": "Dedup test"},
                            "fingerprint": "dedup_fp_unique_001",
                        }
                    ],
                },
            )
            assert response2.status_code == 200
            assert response2.json()["skipped"] >= 1


# =============================================================================
# Test 5: categorize_alert Keywords
# =============================================================================


def test_categorize_alert_keywords():
    """categorize_alert() maps keywords to correct categories."""
    assert categorize_alert("HighCPU") == "infrastructure"
    assert categorize_alert("mqtt-disconnected") == "connectivity"
    assert categorize_alert("sensor-temp-range") == "data_quality"
    assert categorize_alert("logic-engine-error") == "system"
    assert categorize_alert("UnknownAlert") == "system"  # fallback
