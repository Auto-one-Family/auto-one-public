"""
Webhook API Endpoints

Phase 4A.3: Grafana Webhook Integration
Priority: HIGH
Status: IMPLEMENTED

Endpoints:
- POST /v1/webhooks/grafana-alerts  - Receive Grafana alert webhooks

Grafana sends alerts in a batch payload with status "firing" or "resolved".
Each alert is mapped to an AutomationOne notification and routed through
the NotificationRouter (DB persist → WS broadcast → optional email).
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from ...core.exceptions import WebhookValidationException
from ...core.logging_config import get_logger
from ...core.metrics import increment_alert_resolved, increment_webhook_received
from ...db.repositories.notification_repo import NotificationRepository
from ...schemas.notification import NotificationCreate
from ...services.notification_router import NotificationRouter
from ..deps import DBSession

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


# =============================================================================
# Grafana Webhook Schemas
# =============================================================================


class GrafanaAlert(BaseModel):
    """Single alert from Grafana webhook payload."""

    status: str = Field(..., description="Alert status: firing or resolved")
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    generatorURL: Optional[str] = None
    fingerprint: Optional[str] = None
    silenceURL: Optional[str] = None
    dashboardURL: Optional[str] = None
    panelURL: Optional[str] = None
    values: Optional[Dict[str, Any]] = None


class GrafanaWebhookPayload(BaseModel):
    """Grafana webhook payload (Alertmanager format)."""

    version: Optional[str] = None
    groupKey: Optional[str] = None
    truncatedAlerts: Optional[int] = 0
    status: str = Field(default="firing", description="Overall status")
    receiver: Optional[str] = None
    groupLabels: Dict[str, str] = Field(default_factory=dict)
    commonLabels: Dict[str, str] = Field(default_factory=dict)
    commonAnnotations: Dict[str, str] = Field(default_factory=dict)
    externalURL: Optional[str] = None
    alerts: List[GrafanaAlert] = Field(default_factory=list)
    orgId: Optional[int] = None
    title: Optional[str] = None
    state: Optional[str] = None
    message: Optional[str] = None


# =============================================================================
# Alert Categorization
# =============================================================================

# Map alertname keywords to AutomationOne categories
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "infrastructure": [
        "server",
        "database",
        "db",
        "loki",
        "alloy",
        "prometheus",
        "cadvisor",
        "container",
        "memory",
        "disk",
        "cpu",
    ],
    "connectivity": [
        "mqtt",
        "disconnected",
        "heartbeat",
        "offline",
        "ws",
        "websocket",
        "broker",
    ],
    "data_quality": [
        "sensor",
        "stale",
        "range",
        "temp",
        "humidity",
        "ph",
        "ec_",
        "ec-",
        "ecvalue",
        "electrical",
    ],
    "system": [
        "logic",
        "actuator",
        "safety",
        "boot",
        "error",
        "cascade",
        "safe-mode",
        "safemode",
    ],
}


def categorize_alert(alertname: str) -> str:
    """Categorize a Grafana alert based on alertname keywords."""
    name_lower = alertname.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return category
    return "system"


def map_grafana_severity(alert: GrafanaAlert) -> str:
    """Map Grafana alert status + labels to AutomationOne severity.

    FIX-02: 'resolved' is NOT a severity (only 3 levels: critical/warning/info).
    Resolved alerts map to 'info'; the resolved state is captured in
    metadata.grafana_status.
    """
    if alert.status == "resolved":
        return "info"

    # Check Grafana severity label (set in alert rules)
    severity_label = (
        alert.labels.get("severity") or alert.labels.get("grafana_severity") or ""
    ).lower()

    if severity_label in ("critical", "error"):
        return "critical"
    if severity_label in ("warning", "warn"):
        return "warning"

    # Check folder name as fallback
    folder = alert.labels.get("grafana_folder", "").lower()
    if "critical" in folder:
        return "critical"

    return "warning"


# =============================================================================
# POST /v1/webhooks/grafana-alerts
# =============================================================================


@router.post(
    "/grafana-alerts",
    status_code=status.HTTP_200_OK,
    summary="Grafana alert webhook",
    description="Receives Grafana alert webhooks and routes them as notifications.",
)
async def grafana_alerts_webhook(
    payload: GrafanaWebhookPayload,
    db: DBSession,
):
    """
    Process Grafana alert webhook payload.

    Iterates over payload.alerts, maps each to an AutomationOne notification,
    and routes through NotificationRouter.

    Deduplication is handled by NotificationRouter (60s window by fingerprint).
    """
    if not payload.alerts:
        raise WebhookValidationException("Grafana webhook payload contains no alerts")

    processed = 0
    skipped = 0
    auto_resolved = 0

    router_service = NotificationRouter(db)
    notification_repo = NotificationRepository(db)

    for alert in payload.alerts:
        alertname = alert.labels.get("alertname", "Unknown Alert")
        severity = map_grafana_severity(alert)
        category = categorize_alert(alertname)

        # Phase 4B: Build correlation_id from Grafana fingerprint
        correlation_id = f"grafana_{alert.fingerprint}" if alert.fingerprint else None

        # Phase 4B: Auto-resolve existing alerts when Grafana sends "resolved"
        if alert.status == "resolved" and correlation_id:
            try:
                resolved_count = await notification_repo.auto_resolve_by_correlation(correlation_id)
                if resolved_count > 0:
                    auto_resolved += resolved_count
                    await db.commit()
                    increment_alert_resolved(severity, resolution_type="auto")
                    logger.info(
                        f"Auto-resolved {resolved_count} alerts for "
                        f"correlation_id='{correlation_id}'"
                    )
                    # Resolution tracked on original alerts — skip creating
                    # a redundant info notification for the resolved event
                    continue
            except Exception as e:
                logger.error(f"Failed to auto-resolve alerts for '{alertname}': {e}")

        # Build title
        title = alert.annotations.get("summary", alertname)
        if len(title) > 255:
            title = title[:252] + "..."

        # Build body from annotations
        body_parts = []
        if alert.annotations.get("description"):
            body_parts.append(alert.annotations["description"])
        if alert.status == "resolved":
            body_parts.append("Alert wurde aufgelöst.")
        body = "\n".join(body_parts) if body_parts else None

        # Build metadata
        metadata: Dict[str, Any] = {
            "grafana_fingerprint": alert.fingerprint,
            "grafana_status": alert.status,
            "alertname": alertname,
            "labels": alert.labels,
        }
        if alert.generatorURL:
            metadata["grafana_url"] = alert.generatorURL
        if alert.dashboardURL:
            metadata["dashboard_url"] = alert.dashboardURL
        if alert.panelURL:
            metadata["panel_url"] = alert.panelURL
        if alert.values:
            metadata["values"] = alert.values

        # Extract ESP ID if present in labels
        esp_id = alert.labels.get("esp_id") or alert.labels.get("instance")
        if esp_id:
            metadata["esp_id"] = esp_id

        notification = NotificationCreate(
            user_id=None,  # Broadcast to all users
            channel="websocket",
            severity=severity,
            category=category,
            title=title,
            body=body,
            metadata=metadata,
            source="grafana",
            # FIX-07: Pass Grafana fingerprint for deduplication
            fingerprint=alert.fingerprint,
            # Phase 4B: Correlation ID for alert grouping + auto-resolve
            correlation_id=correlation_id,
        )

        try:
            result = await router_service.route(notification)
            if result:
                processed += 1
                increment_webhook_received("grafana", "processed")
            else:
                skipped += 1  # Deduplicated
                increment_webhook_received("grafana", "skipped")
        except IntegrityError as e:
            # Grafana may send the same alert multiple times concurrently.
            # The partial unique index on fingerprint raises IntegrityError
            # when a race condition bypasses the SELECT-before-INSERT dedup check.
            # Treat as deduplicated: rollback the failed transaction and continue.
            await db.rollback()
            skipped += 1
            increment_webhook_received("grafana", "skipped")
            logger.warning(
                f"Grafana alert '{alertname}' deduplicated via IntegrityError "
                f"(fingerprint='{alert.fingerprint}'): {e}"
            )
        except Exception as e:
            logger.error(f"Failed to route Grafana alert '{alertname}': {e}")
            await db.rollback()
            skipped += 1
            increment_webhook_received("grafana", "error")

    logger.info(
        f"Grafana webhook processed: {processed} routed, {skipped} skipped "
        f"(total: {len(payload.alerts)} alerts)"
    )

    return {
        "status": "ok",
        "processed": processed,
        "skipped": skipped,
        "auto_resolved": auto_resolved,
    }
