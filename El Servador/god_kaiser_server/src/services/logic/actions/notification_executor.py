"""
Notification Action Executor

Executes notification actions by delegating to the NotificationRouter.

Phase 4A.1 Refactoring: Channel methods now route through the central
NotificationRouter which handles DB persistence, WebSocket broadcast,
and email delivery (severity-based). Webhook remains a direct HTTP POST.
"""

import httpx
from typing import Dict, Optional

from ....core.config import get_settings
from ....core.logging_config import get_logger
from ....db.session import resilient_session
from ....schemas.notification import NotificationCreate
from ...notification_router import NotificationRouter
from .base import ActionResult, BaseActionExecutor

logger = get_logger(__name__)


class NotificationActionExecutor(BaseActionExecutor):
    """
    Executes notification actions via NotificationRouter.

    Channels:
    - websocket / email → delegated to NotificationRouter (DB + WS + Email)
    - webhook → direct HTTP POST (not part of notification stack)
    """

    def __init__(self, notification_router: Optional[NotificationRouter] = None):
        """
        Initialize notification executor.

        Args:
            notification_router: Optional NotificationRouter instance.
                If None, a new one is created per invocation using resilient_session.
        """
        self._notification_router = notification_router

    def supports(self, action_type: str) -> bool:
        """Check if this executor supports notification actions."""
        return action_type == "notification"

    async def execute(self, action: Dict, context: Dict) -> ActionResult:
        """
        Execute notification action.

        Args:
            action: Action dictionary with:
                - type: "notification"
                - channel: Notification channel ("email", "webhook", "websocket")
                - target: Target (email address, webhook URL, etc.)
                - message_template: Message template with placeholders
            context: Execution context with:
                - trigger_data: Sensor data that triggered the rule
                - rule_name: Rule name
                - rule_id: Rule ID

        Returns:
            ActionResult with execution status
        """
        channel = action.get("channel")
        target = action.get("target")
        message_template = action.get("message_template", "")

        # Validate required fields
        if not channel:
            return ActionResult(
                success=False,
                message="Missing 'channel' field in notification action",
            )

        if not target:
            return ActionResult(
                success=False,
                message="Missing 'target' field in notification action",
            )

        # Get context data for template
        trigger_data = context.get("trigger_data", {})
        rule_name = context.get("rule_name", "Unknown Rule")
        rule_id = context.get("rule_id")

        # Format message template
        try:
            message = message_template.format(
                sensor_value=trigger_data.get("value", "N/A"),
                esp_id=trigger_data.get("esp_id", "N/A"),
                gpio=trigger_data.get("gpio", "N/A"),
                sensor_type=trigger_data.get("sensor_type", "N/A"),
                timestamp=trigger_data.get("timestamp", "N/A"),
                rule_name=rule_name,
                rule_id=str(rule_id) if rule_id else "N/A",
            )
        except KeyError as e:
            logger.warning(f"Error formatting notification template: {e}")
            message = message_template  # Use template as-is if formatting fails

        # Webhook remains a direct HTTP POST (not part of notification stack)
        if channel == "webhook":
            return await self._send_webhook_notification(target, message, context)

        # WebSocket and email go through NotificationRouter
        if channel in ("websocket", "email"):
            return await self._route_via_notification_router(
                channel=channel,
                target=target,
                message=message,
                context=context,
            )

        return ActionResult(
            success=False,
            message=f"Unsupported notification channel: {channel}",
        )

    async def _route_via_notification_router(
        self,
        channel: str,
        target: str,
        message: str,
        context: Dict,
    ) -> ActionResult:
        """
        Route notification through the central NotificationRouter.

        Creates a NotificationCreate schema and delegates to the router
        which handles DB persistence, WebSocket broadcast, and email delivery.
        """
        trigger_data = context.get("trigger_data", {})
        rule_name = context.get("rule_name", "Unknown Rule")
        rule_id = context.get("rule_id")

        # Determine severity from action context
        severity = context.get("severity", "info")

        # Build metadata from trigger context
        metadata = {
            "rule_name": rule_name,
            "rule_id": str(rule_id) if rule_id else None,
            "esp_id": trigger_data.get("esp_id"),
            "sensor_type": trigger_data.get("sensor_type"),
            "gpio": trigger_data.get("gpio"),
            "target": target,
        }
        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        notification = NotificationCreate(
            user_id=None,  # Broadcast to all users (system notification)
            channel=channel,
            severity=severity,
            category="system",
            title=f"Logic Rule: {rule_name}",
            body=message,
            metadata=metadata,
            source="logic_engine",
        )

        try:
            if self._notification_router:
                result = await self._notification_router.route(notification)
            else:
                # Create a transient router with a fresh session
                async with resilient_session() as session:
                    router = NotificationRouter(session)
                    result = await router.route(notification)

            if result:
                return ActionResult(
                    success=True,
                    message=f"Notification routed via {channel} for rule '{rule_name}'",
                    data={
                        "channel": channel,
                        "target": target,
                        "notification_id": str(result.id),
                    },
                )
            else:
                # result is None → deduplicated
                return ActionResult(
                    success=True,
                    message=f"Notification deduplicated for rule '{rule_name}'",
                    data={"channel": channel, "target": target, "deduplicated": True},
                )

        except Exception as e:
            logger.error(
                f"Error routing notification via NotificationRouter: {e}",
                exc_info=True,
            )
            return ActionResult(
                success=False,
                message=f"Error routing notification: {str(e)}",
            )

    async def _send_webhook_notification(
        self, target: str, message: str, context: Dict
    ) -> ActionResult:
        """Send webhook notification via HTTP POST."""
        settings = get_settings()
        timeout = settings.notification.webhook_timeout_seconds

        payload = {
            "message": message,
            "rule_name": context.get("rule_name"),
            "rule_id": str(context.get("rule_id")) if context.get("rule_id") else None,
            "trigger": context.get("trigger_data", {}),
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(target, json=payload)
                response.raise_for_status()

            return ActionResult(
                success=True,
                message=f"Webhook sent to {target}",
                data={"channel": "webhook", "target": target, "status": response.status_code},
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Webhook returned HTTP error {e.response.status_code} for {target}",
                exc_info=True,
            )
            return ActionResult(
                success=False,
                message=f"Webhook HTTP error: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            logger.error(f"Webhook request failed for {target}: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=f"Webhook request failed: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=f"Error sending webhook notification: {str(e)}",
            )
