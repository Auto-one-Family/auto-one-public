"""
MQTT Handler: Device Heartbeat Messages

Processes heartbeat messages from ESP32 devices:
- Updates device status (online/offline)
- Tracks last_seen timestamp
- Logs device health metrics (with structured error codes)
- Detects stale connections
- AUTO-DISCOVERY: Automatically registers unknown ESP devices

Note: Heartbeat is the primary discovery mechanism.
ESP32 sends initial heartbeat on startup for registration.
Separate discovery topic (kaiser/god/discovery/esp32_nodes) is deprecated.

Error Codes:
- Uses ValidationErrorCode for payload validation errors
- Uses ConfigErrorCode for ESP device lookup errors
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncio
import json
import os
import time as time_module

from cachetools import TTLCache
from ...core.error_codes import ESP32ApplicationError, ValidationErrorCode
from ...core.config import get_settings
from ...core.logging_config import get_logger
from ...core.task_registry import create_tracked_task
from ...core.metrics import (
    increment_heartbeat_ack_valid,
    increment_heartbeat_contract_reject,
    increment_contract_unknown_code,
    increment_connect_attempt,
    observe_heartbeat_ack_latency_ms,
    observe_heartbeat_firmware_flags,
    observe_heartbeat_firmware_counters,
    observe_tls_handshake_latency_ms,
    update_esp_boot_count,
    update_esp_heartbeat_timestamp,
)
from ...core import constants
from ...db.models.audit_log import AuditEventType, AuditSeverity
from ...db.models.enums import DataSource
from sqlalchemy.orm.attributes import flag_modified

from ...db.models.esp import ESPDevice
from ...db.repositories import ESPRepository, ESPHeartbeatRepository
from ...db.repositories.esp_heartbeat_repo import extract_heartbeat_runtime_telemetry
from ...db.repositories.actuator_repo import ActuatorRepository
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...db.session import resilient_session
from ...services.event_contract_serializers import (
    extract_last_known_health_metrics,
    serialize_esp_health_event,
)
from ...services.system_event_contract import canonicalize_heartbeat
from ...services.state_adoption_service import get_state_adoption_service
from ...schemas.esp import SessionAnnouncePayload
from ..topics import TopicBuilder
from .heartbeat_metrics_handler import get_heartbeat_metrics_handler

logger = get_logger(__name__)

# Heartbeat timeout: device considered offline after configured threshold
HEARTBEAT_TIMEOUT_SECONDS = get_settings().maintenance.heartbeat_timeout_seconds

# Full-State-Push: Reconnect threshold (seconds offline before triggering)
# Must be > heartbeat interval (60s) to avoid false-positive reconnect detection
# when heartbeats arrive slightly late (e.g. 60.5s → offline_seconds=60.5 > 60).
RECONNECT_THRESHOLD_SECONDS = 150
# Full-State-Push: Cooldown between pushes (prevent rapid-fire on boot)
# Note: As of SAFETY-P5 Fix-3, the heartbeat ACK is sent early (before DB writes)
# and independently of config push. Config push is triggered via _has_pending_config().
STATE_PUSH_COOLDOWN_SECONDS = 120
ADOPTION_GRACE_SECONDS = 2.0
SESSION_STARTUP_REJECT_WINDOW_SECONDS = 1.0
# INC-EA5484 / AUT-346: After a long broker outage (e.g. server restart), the ESP
# reconnects with a full QoS OUTBOX backlog accumulated during the disconnect.
# Draining the outbox + completing 12 bootstrap subscription handshakes takes up to
# ~32s (observed). Pushing zone/assign before the outbox is drained causes TCP
# EAGAIN → MQTT client freeze → broker keepalive timeout (90s) → second disconnect.
# 30s gives the ESP enough margin to stabilize before any server-side state push.
STATE_PUSH_RECONNECT_DELAY_SECONDS = 30.0

# Config-Push: Cooldown between auto config pushes (prevent mismatch loop).
# Keep this below one heartbeat period (60s) so a lost first push can recover
# on the next heartbeat cycle instead of stalling for two full minutes.
CONFIG_PUSH_COOLDOWN_SECONDS = 45

# AUT-1029 / AUT-1026-S3 (E2): Dämpfung für Oversize-Operator-Sichtbarkeit.
# Muss das Heartbeat-Intervall (60 s, mqtt_client.h:265) überschreiten — der
# 45-s-Push-Cooldown allein dämpft Oversize nicht (AUT-1027 A2). Nutzt das
# bestehende Metadata-Feld config_push_oversize_blocked_at als Gate.
CONFIG_OVERSIZE_NOTIFY_COOLDOWN_SECONDS = 300

# Module-level MQTTCommandBridge reference (set via set_command_bridge())
_command_bridge = None


def set_command_bridge(bridge) -> None:
    """Set the MQTTCommandBridge for ACK-driven Full-State-Push on reconnect."""
    global _command_bridge
    _command_bridge = bridge


class HeartbeatHandler:
    """
    Handles incoming heartbeat messages from ESP32 devices.

    Flow:
    1. Parse topic → extract esp_id
    2. Validate payload structure
    3. Check if ESP exists in DB
    4. If NOT: Auto-register (Discovery via Heartbeat)
    5. Update ESP device status to "online"
    6. Update last_seen timestamp and metadata
    7. Log health metrics
    """

    def __init__(self) -> None:
        # Contract context for fail-closed ACK handover validation on ESP side.
        # Epoch increments only for reconnect cycles; steady-state ACKs still carry
        # a valid epoch >= 1 so strict devices never receive an incomplete contract.
        # 24h TTL covers realistic debug windows; maxsize prevents unbounded growth.
        self._handover_epoch_by_esp: TTLCache[str, int] = TTLCache(maxsize=10_000, ttl=86_400)
        self._session_id_by_esp: dict[str, str] = {}
        self._last_session_connected_ts_by_esp: TTLCache[str, float] = TTLCache(
            maxsize=10_000, ttl=86_400
        )
        # Companion to _handover_epoch_by_esp: records last epoch for which LWT was cleared.
        # Guard in _clear_retained_lwt prevents repeated publishes within the same session.
        self._lwt_cleared_epoch_by_esp: dict[str, int] = {}
        # Tracks ESPs for which a config push was triggered during heartbeat processing.
        # Used to gate the reconnect evaluation: if config is still being pushed,
        # the Logic Engine must not fire actuator commands before config arrives on ESP.
        self._config_push_pending_esps: set[str] = set()

    @staticmethod
    def _extract_correlation_id(payload: dict) -> Optional[str]:
        """
        Extract correlation_id from heartbeat payload for WS projection.

        Heartbeats may not carry correlation metadata in every path.
        Return None instead of raising to keep heartbeat processing non-fatal.
        """
        correlation_id = payload.get("correlation_id")
        if isinstance(correlation_id, str) and correlation_id.strip():
            return correlation_id
        return None

    def _build_ack_contract_context(
        self, esp_id: str, is_reconnect: bool, preferred_epoch: Optional[int] = None
    ) -> tuple[int, str]:
        """Return (handover_epoch, session_id) for the current ACK."""
        epoch_counter = self._handover_epoch_by_esp.get(esp_id, 0)
        preferred = (
            preferred_epoch if isinstance(preferred_epoch, int) and preferred_epoch > 0 else None
        )

        # If ESP reports its active handover epoch, use that as source of truth.
        if preferred is not None:
            if preferred != epoch_counter:
                self._handover_epoch_by_esp[esp_id] = preferred
                epoch_counter = preferred
                session_id = f"{esp_id}:handover:{epoch_counter}:{int(time_module.time())}"
                self._session_id_by_esp[esp_id] = session_id
            else:
                session_id = self._session_id_by_esp.get(
                    esp_id, f"{esp_id}:handover:{epoch_counter}:{int(time_module.time())}"
                )
                self._session_id_by_esp[esp_id] = session_id
            return max(1, epoch_counter), session_id

        if is_reconnect:
            epoch_counter += 1
            self._handover_epoch_by_esp[esp_id] = epoch_counter
            session_id = f"{esp_id}:handover:{epoch_counter}:{int(time_module.time())}"
            self._session_id_by_esp[esp_id] = session_id
        else:
            # Keep an existing reconnect session stable; if none exists use a
            # deterministic steady-state marker.
            session_id = self._session_id_by_esp.get(esp_id, f"{esp_id}:steady")

        handover_epoch = max(1, epoch_counter)
        return handover_epoch, session_id

    @staticmethod
    def _resolve_handover_epoch(payload: dict) -> Optional[int]:
        """Resolve canonical handover epoch with legacy alias support."""
        raw = payload.get("handover_epoch", payload.get("session_epoch"))
        if isinstance(raw, int) and raw > 0:
            return raw
        return None

    def _register_session_connected(
        self,
        esp_id: str,
        connected_ts: Optional[float] = None,
        announced_epoch: Optional[int] = None,
    ) -> None:
        """Store latest session-connect timestamp and optional epoch per ESP."""
        self._last_session_connected_ts_by_esp[esp_id] = (
            float(connected_ts) if connected_ts is not None else time_module.monotonic()
        )
        if isinstance(announced_epoch, int) and announced_epoch > 0:
            self._handover_epoch_by_esp[esp_id] = announced_epoch
            self._session_id_by_esp[esp_id] = (
                f"{esp_id}:handover:{announced_epoch}:{int(time_module.time())}"
            )

    def _is_startup_reject_window(self, esp_id: str) -> bool:
        """Return True for rejects within the first second after connect."""
        connected_ts = self._last_session_connected_ts_by_esp.get(esp_id)
        if connected_ts is None:
            return False
        return (time_module.monotonic() - connected_ts) <= SESSION_STARTUP_REJECT_WINDOW_SECONDS

    def _track_contract_reject_metrics(self, esp_id: str, payload: dict, metadata: dict) -> None:
        """Track monotonic ACK contract rejects reported by ESP telemetry."""
        if not isinstance(metadata, dict):
            return
        reported_count = payload.get("handover_contract_reject_count")
        if not isinstance(reported_count, int) or reported_count < 0:
            return
        previous_count = metadata.get("handover_contract_reject_count_last")
        try:
            previous_count_int = int(previous_count) if previous_count is not None else 0
        except (TypeError, ValueError):
            previous_count_int = 0
        delta = reported_count - max(previous_count_int, 0)
        if delta > 0:
            reason = payload.get("handover_contract_last_reject", "UNKNOWN")
            increment_heartbeat_contract_reject(str(reason), amount=delta)
            startup_count = int(metadata.get("handover_contract_reject_startup", 0) or 0)
            runtime_count = int(metadata.get("handover_contract_reject_runtime", 0) or 0)
            if self._is_startup_reject_window(esp_id):
                startup_count += delta
            else:
                runtime_count += delta
            metadata["handover_contract_reject_startup"] = startup_count
            metadata["handover_contract_reject_runtime"] = runtime_count
            metadata["handover_contract_reject"] = startup_count + runtime_count
        metadata["handover_contract_reject_count_last"] = reported_count

    @staticmethod
    def _merge_metrics_into_payload(esp_id: str, payload: dict) -> None:
        """Merge buffered heartbeat_metrics into heartbeat payload (idempotent).

        Adds ``runtime_telemetry`` fields from the latest metrics message and
        two freshness indicators:
        - ``metrics_delta_ts``: ESP timestamp of the latest metrics payload (unix seconds).
        - ``metrics_freshness_seconds``: server receive-age of the metrics message.

        Already-present heartbeat fields are NOT overwritten (heartbeat is authoritative).
        """
        entry = get_heartbeat_metrics_handler().get_latest(esp_id)
        if entry is None:
            return

        metrics_payload: dict = entry.get("payload", {})
        receive_ts: float = entry.get("receive_ts", 0.0)
        metrics_esp_ts: int = entry.get("esp_ts", 0)

        payload["metrics_delta_ts"] = (
            int(metrics_esp_ts) if isinstance(metrics_esp_ts, (int, float)) else 0
        )

        if receive_ts > 0:
            payload["metrics_freshness_seconds"] = round(time_module.time() - receive_ts, 1)
        else:
            payload["metrics_freshness_seconds"] = -1.0

        for key, value in metrics_payload.items():
            if key == "ts":
                continue
            if key not in payload:
                payload[key] = value

    async def handle_session_announce(self, topic: str, payload: dict) -> bool:
        """Register session/announce to classify startup reject telemetry."""
        parsed_topic = TopicBuilder.parse_session_announce_topic(topic)
        if not parsed_topic:
            logger.warning("Invalid session/announce topic: %s", topic)
            return False
        esp_id = parsed_topic["esp_id"]
        try:
            parsed = SessionAnnouncePayload.from_payload(payload)
        except ValueError as err:
            logger.warning("Invalid session/announce payload for %s: %s", esp_id, err)
            return False
        self._register_session_connected(
            esp_id=esp_id,
            announced_epoch=parsed.handover_epoch,
        )
        logger.debug(
            "Session announce registered for %s (epoch=%s, reason=%s)",
            esp_id,
            parsed.handover_epoch,
            parsed.reason,
        )
        return True

    async def handle_heartbeat(self, topic: str, payload: dict) -> bool:
        """
        Handle heartbeat message with auto-discovery.

        Expected topic: kaiser/god/esp/{esp_id}/system/heartbeat

        Expected payload (from ESP32):
        {
            "esp_id": "ESP_12AB34CD",
            "zone_id": "zone_main",
            "master_zone_id": "master",
            "zone_assigned": true,
            "ts": 1735818000,
            "uptime": 123456,
            "heap_free": 45000,
            "wifi_rssi": -45,
            "sensor_count": 3,
            "actuator_count": 2
        }

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully, False otherwise
        """
        # Default for Error-ACK scope (SAFETY-P5 Fix-4)
        esp_id_str: str = "unknown"
        handover_epoch: int = 1
        session_id: Optional[str] = None
        early_ack_sent: bool = False  # AUT-590 F6: guard against double-ACK on exception path

        try:
            payload = dict(payload)
            canonical = canonicalize_heartbeat(payload)
            payload = canonical.payload
            if canonical.is_contract_violation:
                increment_contract_unknown_code("heartbeat")
                logger.warning(
                    "Heartbeat contract violation normalized: %s (raw=%s)",
                    canonical.contract_reason,
                    canonical.raw_fields,
                )

            # Step 1: Parse topic
            parsed_topic = TopicBuilder.parse_heartbeat_topic(topic)
            if not parsed_topic:
                logger.error(
                    f"[{ValidationErrorCode.MISSING_REQUIRED_FIELD}] "
                    f"Failed to parse heartbeat topic: {topic}"
                )
                return False

            esp_id_str = parsed_topic["esp_id"]
            self._register_session_connected(esp_id=esp_id_str)
            # Default contract context for branches without reconnect detection.
            esp_reported_epoch = payload.get("active_handover_epoch")
            if not isinstance(esp_reported_epoch, int) or esp_reported_epoch <= 0:
                esp_reported_epoch = None
            handover_epoch, session_id = self._build_ack_contract_context(
                esp_id_str, is_reconnect=False, preferred_epoch=esp_reported_epoch
            )

            logger.debug(f"Processing heartbeat: esp_id={esp_id_str}")

            # Step 2: Validate payload
            validation_result = self._validate_payload(payload)
            if validation_result["valid"]:
                observe_heartbeat_firmware_flags(payload)
                observe_heartbeat_firmware_counters(esp_id_str, payload)

            if not validation_result["valid"]:
                error_code = validation_result.get(
                    "error_code", ValidationErrorCode.MISSING_REQUIRED_FIELD
                )
                logger.error(
                    f"[{error_code}] Invalid heartbeat payload from {esp_id_str}: "
                    f"{validation_result['error']}"
                )
                # SAFETY-P5 Fix-4: Error ACK — server alive, payload invalid
                await self._send_heartbeat_error_ack(
                    esp_id_str,
                    f"invalid_payload:{str(validation_result.get('error', ''))[:50]}",
                    handover_epoch=handover_epoch,
                    session_id=session_id,
                )
                return False

            # Step 2b: Merge buffered heartbeat_metrics (AUT-121)
            self._merge_metrics_into_payload(esp_id_str, payload)

            # Step 3: Get database session and repositories
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)

                # Step 4: Lookup ESP device
                esp_device = await esp_repo.get_by_device_id(esp_id_str)

                if not esp_device:
                    # ============================================
                    # Check for soft-deleted tombstone first
                    # ============================================
                    tombstone = await esp_repo.get_by_device_id(esp_id_str, include_deleted=True)
                    if tombstone is not None:
                        restore_policy = os.environ.get("ESP_SOFT_DELETE_RESTORE_POLICY", "allow")
                        if restore_policy == "deny":
                            logger.info(
                                f"Restore blocked by policy for soft-deleted device {esp_id_str}"
                            )
                            return True
                        # Restore: clear soft-delete fields
                        tombstone.deleted_at = None
                        tombstone.deleted_by = None
                        tombstone.status = "pending_approval"
                        await session.commit()
                        await self._send_heartbeat_ack(
                            esp_id=esp_id_str,
                            status="pending_approval",
                            config_available=False,
                            handover_epoch=handover_epoch,
                            session_id=session_id,
                        )
                        return True

                    # ============================================
                    # NEW DEVICE: Auto-Discovery
                    # ============================================
                    esp_device, status_msg = await self._discover_new_device(
                        session, esp_repo, esp_id_str, payload
                    )
                    if not esp_device:
                        # Rate limited - silently ignore
                        logger.debug(f"Discovery rate limited for {esp_id_str}: {status_msg}")
                        return True  # Don't log as error

                    # Broadcast discovery event (pass esp_device for hardware_type etc.)
                    await self._broadcast_device_discovered(esp_id_str, payload, esp_device)
                    await session.commit()

                    # Phase 2: ACK with pending_approval status
                    await self._send_heartbeat_ack(
                        esp_id=esp_id_str,
                        status="pending_approval",
                        config_available=False,
                        handover_epoch=handover_epoch,
                        session_id=session_id,
                    )
                    return True

                # ============================================
                # EXISTING DEVICE: Status-based processing
                # ============================================
                status = esp_device.status

                # T13-Phase3: Reconnect detection — BEFORE update_status() overwrites last_seen
                is_reconnect = False
                offline_seconds = 0.0
                if isinstance(esp_device.last_seen, datetime):
                    last_seen_for_reconnect = esp_device.last_seen
                    if last_seen_for_reconnect.tzinfo is None:
                        last_seen_for_reconnect = last_seen_for_reconnect.replace(
                            tzinfo=timezone.utc
                        )
                    offline_seconds = (
                        datetime.now(timezone.utc) - last_seen_for_reconnect
                    ).total_seconds()
                    is_reconnect = offline_seconds > RECONNECT_THRESHOLD_SECONDS
                handover_epoch, session_id = self._build_ack_contract_context(
                    esp_id_str,
                    is_reconnect=is_reconnect,
                    preferred_epoch=esp_reported_epoch,
                )

                # Reconnect handover starts with explicit adoption phase.
                if is_reconnect:
                    increment_connect_attempt()
                    adoption_service = get_state_adoption_service()
                    await adoption_service.start_reconnect_cycle(
                        esp_id=esp_id_str,
                        last_offline_seconds=offline_seconds,
                    )
                    await self._broadcast_reconnect_phase(
                        esp_id=esp_id_str,
                        phase="adopting",
                        details={"offline_seconds": offline_seconds},
                    )

                # SAFETY-P5 Fix-3: Send ACK early — before any DB writes (P1 timer reset)
                # config_available=False here; config push mechanism works independently.
                # ACK status: use target "online" when the device is not pending/rejected/deleted
                # so the ESP does not see stale "offline" from the pre-update DB row after LWT.
                if status not in ("rejected", "pending_approval"):
                    ack_status = (
                        "online"
                        if status not in ("rejected", "pending_approval", "deleted")
                        else status
                    )
                    await self._send_heartbeat_ack(
                        esp_id=esp_id_str,
                        status=ack_status,
                        config_available=False,
                        handover_epoch=handover_epoch,
                        session_id=session_id,
                    )
                    early_ack_sent = True  # AUT-590 F6: suppress error ACK if exception follows
                    # Log the early ACK for observability (boot-diagnosis in Loki)
                    # pending/rejected have their own downstream logs
                    logger.info(
                        "Early ACK sent for %s (status=%s, pre-db-write)",
                        esp_id_str,
                        ack_status,
                    )

                if status == "rejected":
                    # Check cooldown before rediscovery
                    if await self._check_rejection_cooldown(esp_device):
                        await self._rediscover_device(esp_device, payload, session)
                        await self._broadcast_device_rediscovered(esp_id_str, payload)
                        await session.commit()
                        return True
                    else:
                        # Still in cooldown - notify ESP of rejection
                        logger.debug(f"Rejected device {esp_id_str} in cooldown, ignoring")

                        # Phase 2: ACK - ESP knows it's rejected
                        await self._send_heartbeat_ack(
                            esp_id=esp_id_str,
                            status="rejected",
                            config_available=False,
                            handover_epoch=handover_epoch,
                            session_id=session_id,
                        )
                        return True

                if status == "pending_approval":
                    # Update heartbeat count but don't process normally
                    await self._update_pending_heartbeat(esp_device, payload)
                    await session.commit()
                    logger.debug(f"Pending device {esp_id_str} heartbeat recorded")

                    # AUT-339: Device is connected — clear retained LWT and append
                    # heartbeat history (previously only the online path did this).
                    self._clear_retained_lwt(esp_id_str, current_epoch=handover_epoch)
                    await self._log_heartbeat_entry(
                        esp_device=esp_device,
                        esp_id_str=esp_id_str,
                        payload=payload,
                    )

                    # Phase 2: ACK - ESP knows it's still pending
                    await self._send_heartbeat_ack(
                        esp_id=esp_id_str,
                        status="pending_approval",
                        config_available=False,
                        handover_epoch=handover_epoch,
                        session_id=session_id,
                    )
                    return True

                if status == "approved":
                    # First heartbeat after approval -> set to online
                    esp_device.status = "online"
                    logger.info(f"✅ Device {esp_id_str} now online after approval")

                    # Audit Logging: device_online (status change approved → online)
                    try:
                        audit_repo = AuditLogRepository(session)
                        await audit_repo.log_device_event(
                            esp_id=esp_id_str,
                            event_type=AuditEventType.DEVICE_ONLINE,
                            status="success",
                            message=f"Device came online after admin approval",
                            details={
                                "previous_status": "approved",
                                "heap_free": payload.get("heap_free", payload.get("free_heap")),
                                "wifi_rssi": payload.get("wifi_rssi"),
                                "uptime": payload.get("uptime"),
                            },
                            severity=AuditSeverity.INFO,
                        )
                    except Exception as audit_error:
                        logger.warning(f"Failed to audit log device_online: {audit_error}")

                # Step 5: Update device status + last_seen.
                # Keep server receive time authoritative for timeout freshness.
                # Payload ts is still parsed for diagnostics but does not drive DB
                # liveness anymore (prevents stale-ts reconnect flaps).
                server_received_at = datetime.now(timezone.utc)
                ts_raw = payload.get("ts")
                time_valid = payload.get("time_valid", True)  # Default True for old firmware

                payload_seen: Optional[datetime] = None
                if ts_raw is not None and ts_raw > 0 and time_valid:
                    ts_value = ts_raw / 1000 if ts_raw > 1e10 else ts_raw
                    payload_seen = datetime.fromtimestamp(ts_value, tz=timezone.utc)

                # Server-authoritative liveness: active heartbeat must never write a
                # stale payload ts that can immediately re-trigger timeout offline.
                last_seen = server_received_at
                existing_seen = esp_device.last_seen
                if existing_seen and existing_seen.tzinfo is None:
                    existing_seen = existing_seen.replace(tzinfo=timezone.utc)
                if existing_seen and last_seen < existing_seen:
                    logger.info(
                        "Ignoring regressive server heartbeat timestamp for %s: existing=%s incoming_server=%s",
                        esp_id_str,
                        existing_seen.isoformat(),
                        last_seen.isoformat(),
                    )
                    last_seen = existing_seen

                if payload_seen:
                    payload_drift_seconds = abs((server_received_at - payload_seen).total_seconds())
                    if payload_drift_seconds > HEARTBEAT_TIMEOUT_SECONDS:
                        logger.warning(
                            "Heartbeat payload timestamp drift too large for %s: payload=%s server=%s drift_s=%.1f (using server last_seen)",
                            esp_id_str,
                            payload_seen.isoformat(),
                            server_received_at.isoformat(),
                            payload_drift_seconds,
                        )

                await esp_repo.update_status(esp_id_str, "online", last_seen)

                # Log time_valid status — info only, no error (expected during boot)
                if not time_valid:
                    logger.info(
                        "ESP %s: time not synchronized (time_valid=false, using server timestamp)",
                        esp_id_str,
                    )

                # Step 5b: Clear stale retained LWT message from broker
                # After ESP reconnects, the broker still holds the retained
                # offline LWT message. Publishing empty payload with retain=True
                # clears it, preventing new subscribers from receiving stale
                # offline status.
                self._clear_retained_lwt(esp_id_str, current_epoch=handover_epoch)

                # Step 6: Update metadata with latest heartbeat info
                await self._update_esp_metadata(esp_device, payload, session, is_reconnect)
                self._normalize_last_disconnect_metadata_on_online(
                    esp_device=esp_device,
                    server_received_at=server_received_at,
                )

                # Step 7: Log health metrics
                self._log_health_metrics(esp_id_str, payload)

                # Commit transaction
                await session.commit()

                # Fix-1: Invalidate offline backoff cache after confirmed online commit.
                # Clears _offline_esp_skip so Logic Engine fires actuator actions
                # immediately after reconnect instead of waiting up to 30s TTL.
                from ...services.logic_engine import get_logic_engine

                logic_engine = get_logic_engine()
                if logic_engine is not None:
                    logic_engine.invalidate_offline_backoff(esp_id_str)
                    # Reconnect evaluation is gated until adoption is completed.
                    if is_reconnect:
                        create_tracked_task(
                            self._complete_adoption_and_trigger_reconnect_eval(esp_id_str),
                            name=f"reconnect_adoption_{esp_id_str}",
                        )

                # Update Prometheus metrics for Grafana alerting
                update_esp_heartbeat_timestamp(esp_id_str)
                boot_count = payload.get("boot_count")
                if boot_count is not None:
                    update_esp_boot_count(esp_id_str, int(boot_count))
                tls_handshake_latency_ms = payload.get(
                    "tls_handshake_latency_ms", payload.get("tls_handshake_latency")
                )
                if tls_handshake_latency_ms is not None:
                    try:
                        observe_tls_handshake_latency_ms(float(tls_handshake_latency_ms))
                    except (TypeError, ValueError):
                        pass

                # ============================================
                # HEARTBEAT HISTORY LOGGING (Time-Series)
                # ============================================
                # Non-blocking: Uses savepoint so a history-log failure
                # does not rollback the already-committed device update.
                # INV-1a/Fix3: Savepoint provides atomicity without risking
                # the main heartbeat transaction on history-log errors.
                device_source = await self._log_heartbeat_entry(
                    esp_device=esp_device,
                    esp_id_str=esp_id_str,
                    payload=payload,
                )

                source_indicator = (
                    f"[{device_source.upper()}]"
                    if device_source != DataSource.PRODUCTION.value
                    else ""
                )

                logger.debug(
                    f"Heartbeat processed{source_indicator}: esp_id={esp_id_str}, "
                    f"uptime={payload.get('uptime')}s, "
                    f"heap_free={payload.get('heap_free', payload.get('free_heap'))} bytes"
                )

                # WebSocket Broadcast
                try:
                    from ...websocket.manager import WebSocketManager

                    ws_manager = await WebSocketManager.get_instance()
                    heap_free = payload.get("heap_free", payload.get("free_heap", 0))
                    wifi_rssi = payload.get("wifi_rssi", 0)
                    uptime = payload.get("uptime", 0)
                    sensor_count = payload.get("sensor_count", payload.get("active_sensors", 0))
                    actuator_count = payload.get(
                        "actuator_count", payload.get("active_actuators", 0)
                    )

                    # Use server-authoritative timestamp (resolved last_seen) instead of raw
                    # payload ts. This keeps frontend online/offline badges stable even when
                    # ESP time is not synced yet (ts can be 0 during boot/NTP lag).
                    broadcast_payload = serialize_esp_health_event(
                        esp_id=esp_id_str,
                        status="online",
                        heap_free=heap_free,
                        wifi_rssi=wifi_rssi,
                        uptime=uptime,
                        sensor_count=sensor_count,
                        actuator_count=actuator_count,
                        timestamp=int(last_seen.timestamp()),
                        source="heartbeat",
                        gpio_status=payload.get("gpio_status", []),
                        gpio_reserved_count=payload.get("gpio_reserved_count", 0),
                        runtime_telemetry=extract_heartbeat_runtime_telemetry(payload),
                    )
                    broadcast_payload.update(
                        {
                            "contract_violation": canonical.is_contract_violation,
                            "contract_code": canonical.contract_code,
                            "contract_reason": canonical.contract_reason,
                            "raw_system_state": canonical.raw_fields.get("raw_system_state"),
                            "correlation_id": self._extract_correlation_id(payload),
                            "is_reconnect": is_reconnect,
                            "spool_pending_count": payload.get("spool_pending_count"),
                            "spool_dropped_count": payload.get("spool_dropped_count"),
                        }
                    )
                    last_disconnect = (esp_device.device_metadata or {}).get("last_disconnect")
                    if isinstance(last_disconnect, dict) and last_disconnect.get("is_flapping"):
                        broadcast_payload["reconnect_after_flapping"] = True
                        broadcast_payload["lwt_count_5m"] = last_disconnect.get("lwt_count_5m", 0)
                    await ws_manager.broadcast(
                        "esp_health",
                        broadcast_payload,
                    )
                except Exception as e:
                    logger.warning(f"Failed to broadcast ESP health via WebSocket: {e}")

                # ============================================
                # Phase 2: Config-Push Check (independent of ACK — SAFETY-P5 Fix-3)
                # ============================================
                # ACK was already sent early (before DB writes). Config push
                # runs independently to detect reboot-triggered config loss.
                esp_sensor_count = payload.get("sensor_count", payload.get("active_sensors", 0))
                esp_actuator_count = payload.get(
                    "actuator_count", payload.get("active_actuators", 0)
                )
                esp_offline_rule_count = payload.get("offline_rule_count", -1)
                esp_subzone_count = payload.get("subzone_count", -1)
                config_push_triggered = await self._has_pending_config(
                    esp_device,
                    session,
                    esp_sensor_count,
                    esp_actuator_count,
                    esp_offline_rule_count=esp_offline_rule_count,
                    is_reconnect=is_reconnect,
                    offline_seconds=offline_seconds,
                    reconnect_epoch=payload.get("handover_epoch"),
                    esp_subzone_count=esp_subzone_count,
                )
                # BUG-2 Fix: _has_pending_config sets config_push_sent_at on
                # esp_device.device_metadata but the session.commit() at line 288
                # runs BEFORE this call — so the cooldown timestamp is never
                # persisted. A second heartbeat (ESP still reports sensors=0 while
                # processing the first config push) reads no cooldown from DB and
                # fires a duplicate push. Committing here ensures the cooldown is
                # written before any concurrent heartbeat can read the metadata.
                if config_push_triggered:
                    await session.commit()

                # T13-Phase3: Full-State-Push runs only when no config resync is pending.
                # This prevents reconnect burst collisions (zone/subzone push vs. config push).
                if is_reconnect and esp_device.zone_id and _command_bridge:
                    if config_push_triggered:
                        logger.info(
                            "State push deferred for %s: config push pending",
                            esp_device.device_id,
                        )
                    else:
                        create_tracked_task(
                            self._handle_reconnect_state_push(esp_device.device_id),
                            name=f"reconnect_state_push_{esp_device.device_id}",
                        )

                return True

        except Exception as e:
            logger.error(
                f"Error handling heartbeat: {e}",
                exc_info=True,
            )
            # SAFETY-P5 Fix-4: Error ACK — server alive, internal error occurred.
            # AUT-590 F6: Only send if early ACK was not already sent (avoid double-ACK).
            if esp_id_str != "unknown" and not early_ack_sent:
                try:
                    await self._send_heartbeat_error_ack(
                        esp_id_str,
                        "internal_error",
                        handover_epoch=handover_epoch,
                        session_id=session_id,
                    )
                except Exception:
                    pass
            return False

        # If processing fell through without explicit return, treat as failure
        return False

    async def _auto_register_esp(
        self, session, esp_repo: ESPRepository, esp_id: str, payload: dict
    ) -> Optional[ESPDevice]:
        """
        Auto-register a new ESP device from heartbeat data with pending_approval status.

        This implements "Discovery via Heartbeat" - ESP32 sends initial
        heartbeat on startup, server auto-registers as pending_approval.

        The device must be approved by an administrator before it can
        operate normally. This ensures security in industrial environments.

        Args:
            session: Database session
            esp_repo: ESP repository
            esp_id: ESP device ID
            payload: Heartbeat payload

        Returns:
            Created ESPDevice or None on failure
        """
        try:
            # Extract available info from heartbeat
            zone_id = payload.get("zone_id", "")
            master_zone_id = payload.get("master_zone_id", "")
            zone_assigned = payload.get("zone_assigned", False)

            # Detect mock devices by ID prefix — mocks skip approval gate
            is_mock = esp_id.startswith("MOCK_") or esp_id.startswith("ESP_MOCK_")
            if is_mock:
                hardware_type = "MOCK_ESP32"
                device_status = "online"
            else:
                hardware_type = payload.get("hardware_type", "ESP32_WROOM")
                device_status = "pending_approval"

            # Create new ESP device
            new_esp = ESPDevice(
                device_id=esp_id,
                hardware_type=hardware_type,
                status=device_status,
                discovered_at=datetime.now(timezone.utc),  # Audit field
                kaiser_id=constants.get_kaiser_id(),  # WP2-Fix1: Default kaiser_id from config
                ip_address=payload.get("wifi_ip"),  # IP from heartbeat (if ESP sends it)
                capabilities={
                    "max_sensors": 20,  # Default for ESP32_WROOM
                    "max_actuators": 12,
                    "features": ["heartbeat", "sensors", "actuators"],
                },
                device_metadata={
                    "discovery_source": "heartbeat",
                    "initial_heartbeat": payload,
                    "heartbeat_count": 1,
                    "zone_id": zone_id,
                    "master_zone_id": master_zone_id,
                    "zone_assigned": zone_assigned,
                    "initial_heap_free": payload.get("heap_free", payload.get("free_heap")),
                    "initial_wifi_rssi": payload.get("wifi_rssi"),
                },
                last_seen=datetime.now(timezone.utc),
            )

            session.add(new_esp)
            await session.flush()  # Get ID without committing

            logger.info(
                f"🔔 New ESP discovered: {esp_id} "
                f"(hardware_type={hardware_type}, status={device_status}) "
                f"(Zone: {zone_id or 'unassigned'}, "
                f"Sensors: {payload.get('sensor_count', 0)}, "
                f"Actuators: {payload.get('actuator_count', 0)})"
            )

            return new_esp

        except Exception as e:
            logger.error(f"Error auto-registering ESP {esp_id}: {e}", exc_info=True)
            return None

    # =========================================================================
    # Discovery/Approval Helper Methods
    # =========================================================================

    async def _discover_new_device(
        self, session, esp_repo: ESPRepository, esp_id: str, payload: dict
    ) -> tuple[Optional[ESPDevice], str]:
        """
        Discover new device with rate limiting.

        Args:
            session: Database session
            esp_repo: ESP repository
            esp_id: ESP device ID
            payload: Heartbeat payload

        Returns:
            Tuple of (device, status_message)
        """
        from ...services.esp_service import _discovery_rate_limiter

        # Check rate limits
        allowed, reason = _discovery_rate_limiter.can_discover(esp_id)
        if not allowed:
            return None, reason

        # Create pending device
        new_esp = await self._auto_register_esp(session, esp_repo, esp_id, payload)
        if new_esp:
            _discovery_rate_limiter.record_discovery(esp_id)

            # Audit Logging: device_discovered
            try:
                audit_repo = AuditLogRepository(session)
                await audit_repo.log_device_event(
                    esp_id=esp_id,
                    event_type=AuditEventType.DEVICE_DISCOVERED,
                    status="success",
                    message=f"New ESP device discovered via heartbeat",
                    details={
                        "zone_id": payload.get("zone_id"),
                        "heap_free": payload.get("heap_free", payload.get("free_heap")),
                        "wifi_rssi": payload.get("wifi_rssi"),
                        "sensor_count": payload.get("sensor_count", 0),
                        "actuator_count": payload.get("actuator_count", 0),
                    },
                    severity=AuditSeverity.INFO,
                )
            except Exception as audit_error:
                logger.warning(f"Failed to audit log device_discovered: {audit_error}")

        return new_esp, "discovered"

    async def _check_rejection_cooldown(
        self, esp_device: ESPDevice, cooldown_seconds: int = 300
    ) -> bool:
        """
        Check if rejection cooldown has expired.

        Args:
            esp_device: ESP device model
            cooldown_seconds: Cooldown period in seconds (default 5 minutes)

        Returns:
            True if cooldown expired (can rediscover), False otherwise
        """
        if not esp_device.last_rejection_at:
            return True

        last_rejection = esp_device.last_rejection_at
        if last_rejection.tzinfo is None:
            last_rejection = last_rejection.replace(tzinfo=timezone.utc)

        cooldown = timedelta(seconds=cooldown_seconds)
        return (datetime.now(timezone.utc) - last_rejection) >= cooldown

    async def _rediscover_device(self, esp_device: ESPDevice, payload: dict, session) -> None:
        """
        Rediscover a previously rejected device.

        Args:
            esp_device: ESP device model
            payload: Heartbeat payload
            session: Database session
        """
        old_status = esp_device.status
        esp_device.status = "pending_approval"
        esp_device.rejection_reason = None

        metadata = esp_device.device_metadata or {}
        metadata["rediscovered_at"] = datetime.now(timezone.utc).isoformat()
        metadata["rediscovery_heartbeat"] = payload
        metadata["heartbeat_count"] = metadata.get("heartbeat_count", 0) + 1
        esp_device.device_metadata = metadata
        flag_modified(esp_device, "device_metadata")
        esp_device.last_seen = datetime.now(timezone.utc)
        # Update IP from rediscovery heartbeat (ESP may have new IP after WiFi reconnect)
        wifi_ip = payload.get("wifi_ip")
        if wifi_ip:
            esp_device.ip_address = wifi_ip

        logger.info(f"🔔 Device rediscovered: {esp_device.device_id} (pending_approval again)")

        # Audit Logging: device_rediscovered
        try:
            audit_repo = AuditLogRepository(session)
            await audit_repo.log_device_event(
                esp_id=esp_device.device_id,
                event_type=AuditEventType.DEVICE_REDISCOVERED,
                status="pending",
                message=f"Previously rejected device is sending heartbeats again",
                details={
                    "previous_status": old_status,
                    "zone_id": payload.get("zone_id"),
                    "heap_free": payload.get("heap_free", payload.get("free_heap")),
                    "wifi_rssi": payload.get("wifi_rssi"),
                },
                severity=AuditSeverity.WARNING,
            )
        except Exception as audit_error:
            logger.warning(f"Failed to audit log device_rediscovered: {audit_error}")

    async def _update_pending_heartbeat(self, esp_device: ESPDevice, payload: dict) -> None:
        """
        Update pending device heartbeat count and IP address.

        Args:
            esp_device: ESP device model
            payload: Heartbeat payload
        """
        metadata = esp_device.device_metadata or {}
        metadata["heartbeat_count"] = metadata.get("heartbeat_count", 0) + 1
        metadata["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        # Store latest metrics for REST /devices/pending (avoid stale initial_heartbeat)
        metadata["last_heap_free"] = payload.get("heap_free", payload.get("free_heap"))
        metadata["last_wifi_rssi"] = payload.get("wifi_rssi")
        metadata["last_sensor_count"] = payload.get("sensor_count", 0)
        metadata["last_actuator_count"] = payload.get("actuator_count", 0)
        esp_device.device_metadata = metadata
        flag_modified(esp_device, "device_metadata")
        esp_device.last_seen = datetime.now(timezone.utc)
        # Update IP address if provided (ESP sends wifi_ip in heartbeat)
        wifi_ip = payload.get("wifi_ip")
        if wifi_ip:
            esp_device.ip_address = wifi_ip

    async def _broadcast_device_discovered(
        self, esp_id: str, payload: dict, esp_device: Optional[ESPDevice] = None
    ) -> None:
        """
        Broadcast device_discovered WebSocket event.

        Args:
            esp_id: ESP device ID
            payload: Heartbeat payload
            esp_device: Newly created ESPDevice model (for hardware_type etc.)
        """
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            discovered_at = datetime.now(timezone.utc).isoformat()
            await ws_manager.broadcast(
                "device_discovered",
                {
                    "esp_id": esp_id,
                    "device_id": esp_id,  # Frontend expects device_id
                    "discovered_at": discovered_at,
                    "last_seen": discovered_at,  # Initially same as discovered_at
                    "zone_id": payload.get("zone_id"),
                    "heap_free": payload.get("heap_free", payload.get("free_heap")),
                    "wifi_rssi": payload.get("wifi_rssi"),
                    "sensor_count": payload.get("sensor_count", 0),
                    "actuator_count": payload.get("actuator_count", 0),
                    "hardware_type": (esp_device.hardware_type if esp_device else None)
                    or "ESP32_WROOM",
                    "ip_address": payload.get("wifi_ip"),  # ESP sends wifi_ip if available
                },
            )
            logger.info(f"📡 Broadcast device_discovered for {esp_id}")
        except Exception as e:
            logger.warning(f"Failed to broadcast device_discovered: {e}")

    async def _broadcast_device_rediscovered(self, esp_id: str, payload: dict) -> None:
        """
        Broadcast device_rediscovered WebSocket event.

        Args:
            esp_id: ESP device ID
            payload: Heartbeat payload
        """
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(
                "device_rediscovered",
                {
                    "esp_id": esp_id,
                    "device_id": esp_id,  # Frontend expects device_id
                    "rediscovered_at": datetime.now(timezone.utc).isoformat(),
                    "zone_id": payload.get("zone_id"),
                    "ip_address": payload.get("wifi_ip"),  # ESP sends wifi_ip in heartbeat
                },
            )
            logger.info(f"📡 Broadcast device_rediscovered for {esp_id}")
        except Exception as e:
            logger.warning(f"Failed to broadcast device_rediscovered: {e}")

    async def _update_esp_metadata(
        self,
        esp_device: ESPDevice,
        payload: dict,
        session,
        is_reconnect: bool = False,
    ) -> None:
        """
        Update ESP metadata with latest heartbeat information.

        Args:
            esp_device: ESP device model
            payload: Heartbeat payload
            session: Database session
            is_reconnect: True if ESP was offline >60s (Full-State-Push will handle resync)
        """
        try:
            # Update device_metadata with latest values
            current_metadata = esp_device.device_metadata or {}

            # Update zone info if provided
            if "zone_id" in payload:
                current_metadata["zone_id"] = payload["zone_id"]
            if "master_zone_id" in payload:
                current_metadata["master_zone_id"] = payload["master_zone_id"]
            if "zone_assigned" in payload:
                current_metadata["zone_assigned"] = payload["zone_assigned"]

            # WP7: Zone Mismatch Detection & Auto-Reassignment
            # Server is authoritative for zone assignment.
            # Two detection signals:
            #   1. zone_id string mismatch (ESP vs DB)
            #   2. zone_assigned: false flag in heartbeat (ESP lost NVS after reboot)
            heartbeat_zone_id = payload.get("zone_id", "")
            heartbeat_zone_assigned = payload.get("zone_assigned", True)
            db_zone_id = esp_device.zone_id or ""

            # Normalize: ESP sends "" for unassigned, DB uses None
            esp_has_zone = bool(heartbeat_zone_id)
            db_has_zone = bool(db_zone_id)

            # Detect zone loss: ESP explicitly reports zone_assigned=false
            # while server has a zone in DB (common after Wokwi/ESP reboot
            # where NVS is cleared)
            esp_lost_zone = not heartbeat_zone_assigned and db_has_zone

            if heartbeat_zone_id != db_zone_id or esp_lost_zone:
                # T13-Phase3: Reconnect detected — Full-State-Push handles resync
                if is_reconnect and db_has_zone:
                    logger.info(
                        "Zone mismatch for %s tolerated (reconnect state push pending)",
                        esp_device.device_id,
                    )
                # Check: Is a zone assignment currently pending? If so, tolerate mismatch.
                elif pending := current_metadata.get("pending_zone_assignment"):
                    pending_target = (
                        pending.get("zone_id", "?") if isinstance(pending, dict) else str(pending)
                    )
                    logger.info(
                        "Zone mismatch for %s tolerated (pending assignment to %s)",
                        esp_device.device_id,
                        pending_target,
                    )
                    # No warning, no resync — wait for ACK or timeout
                elif esp_has_zone and not db_has_zone:
                    # ESP has zone from NVS, Server has None
                    # This happens after: (1) Server restart, (2) failed zone removal
                    logger.info(
                        f"ZONE_MISMATCH [{esp_device.device_id}]: "
                        f"ESP reports zone_id='{heartbeat_zone_id}' but DB has zone_id=None. "
                        f"ESP may have stale zone from NVS. Consider re-sending zone removal."
                    )
                elif (not esp_has_zone and db_has_zone) or esp_lost_zone:
                    # Server has zone, ESP does not (or ESP explicitly reports zone_assigned=false)
                    # This happens after: (1) ESP reboot without persistent NVS (Wokwi),
                    # (2) ESP factory reset, (3) ESP NVS corruption
                    mismatch_reason = (
                        "zone_assigned=false"
                        if esp_lost_zone
                        else f"zone_id mismatch (ESP='{heartbeat_zone_id}', DB='{db_zone_id}')"
                    )
                    # Auto-resend zone/assign with rate-limiting
                    # Use 60s cooldown (not 300s) because zone loss after reboot
                    # should be resolved quickly for zone-based logic to work
                    zone_resync_cooldown_seconds = 60
                    last_resync = current_metadata.get("zone_resync_sent_at")
                    now_ts = int(time_module.time())
                    should_resync = True

                    if last_resync:
                        elapsed = now_ts - last_resync
                        if elapsed < zone_resync_cooldown_seconds:
                            should_resync = False
                            logger.debug(
                                "ZONE_MISMATCH [%s]: zone lost (%s), but resync cooldown active (%ds remaining)",
                                esp_device.device_id,
                                mismatch_reason,
                                zone_resync_cooldown_seconds - elapsed,
                            )

                    if should_resync and esp_device.status == "offline":
                        should_resync = False
                        logger.debug(
                            "Skipping zone resync for offline ESP %s",
                            esp_device.device_id,
                        )

                    # Do not emit an additional fire-and-forget resync while an
                    # ACK-driven zone operation is already in flight.
                    if (
                        should_resync
                        and _command_bridge
                        and _command_bridge.has_pending(esp_device.device_id, "zone")
                    ):
                        should_resync = False
                        logger.debug(
                            "Skipping zone resync for %s: pending zone command exists",
                            esp_device.device_id,
                        )

                    # During config resync windows, avoid extra zone resync bursts.
                    if should_resync and esp_device.device_id in self._config_push_pending_esps:
                        should_resync = False
                        logger.debug(
                            "Skipping zone resync for %s: config push pending",
                            esp_device.device_id,
                        )

                    if should_resync:
                        logger.warning(
                            f"ZONE_MISMATCH [{esp_device.device_id}]: "
                            f"ESP lost zone config ({mismatch_reason}). "
                            f"DB has zone_id='{db_zone_id}'. Auto-reassigning zone."
                        )
                        try:
                            from ..client import MQTTClient

                            resync_topic = TopicBuilder.build_zone_assign_topic(
                                esp_device.device_id
                            )
                            resync_payload = {
                                "zone_id": db_zone_id,
                                "master_zone_id": esp_device.master_zone_id or "",
                                "zone_name": esp_device.zone_name or "",
                                "kaiser_id": esp_device.kaiser_id or constants.get_kaiser_id(),
                                "timestamp": now_ts,
                            }
                            mqtt_client = MQTTClient.get_instance()
                            mqtt_client.publish(
                                resync_topic,
                                json.dumps(resync_payload),
                                qos=1,
                            )
                            current_metadata["zone_resync_sent_at"] = now_ts
                            current_metadata["zone_resync_reason"] = mismatch_reason
                            # Keep the same pending-marker semantics as ZoneService.
                            # This allows the next heartbeat cycles to tolerate the
                            # mismatch until zone/ack resolves or times out.
                            current_metadata["pending_zone_assignment"] = {
                                "zone_id": db_zone_id,
                                "master_zone_id": esp_device.master_zone_id,
                                "zone_name": esp_device.zone_name,
                                "sent_at": now_ts,
                                "source": "heartbeat_zone_resync",
                            }
                            logger.info(
                                f"Auto-reassigning zone '{db_zone_id}' to ESP {esp_device.device_id} "
                                f"(zone lost after reboot). Topic: {resync_topic}"
                            )

                            # For Mock-ESPs: also update the SimulationScheduler runtime
                            # so the next heartbeat sends zone_assigned=true, breaking
                            # the ZONE_MISMATCH loop (real ESPs handle this via NVS)
                            try:
                                from ...services.simulation import get_simulation_scheduler

                                sim_scheduler = get_simulation_scheduler()
                                if sim_scheduler.is_mock_active(esp_device.device_id):
                                    sim_scheduler.update_zone(
                                        esp_device.device_id,
                                        db_zone_id,
                                        esp_device.kaiser_id or constants.get_kaiser_id(),
                                    )
                                    logger.debug(
                                        f"Updated Mock-ESP runtime zone for {esp_device.device_id}"
                                    )
                            except Exception:
                                pass  # SimulationScheduler not initialized (no mock-ESP mode)
                        except Exception as resync_error:
                            logger.error(
                                f"Failed to resend zone assignment to "
                                f"{esp_device.device_id}: {resync_error}",
                                exc_info=True,
                            )
                else:
                    # Both have zone but different values
                    logger.info(
                        f"ZONE_MISMATCH [{esp_device.device_id}]: "
                        f"ESP reports zone_id='{heartbeat_zone_id}' but DB has zone_id='{db_zone_id}'. "
                        f"Zone assignment may be inconsistent."
                    )

            # AUT-283: Subzone Drift Detection & Auto-Reassignment
            # Analog to Zone Mismatch Detection (WP7) above.
            # Only fires on non-reconnect heartbeats; reconnects are handled by Full-State-Push.
            esp_subzone_count = payload.get("subzone_count", -1)
            if esp_subzone_count >= 0 and not is_reconnect:
                try:
                    from ...db.repositories.subzone_repo import SubzoneRepository as _SubzoneRepo

                    _subzone_repo = _SubzoneRepo(session)
                    db_subzone_count_meta = await _subzone_repo.count_by_esp(esp_device.device_id)

                    if esp_subzone_count == 0 and db_subzone_count_meta > 0:
                        subzone_resync_cooldown_seconds = 120
                        last_sz_resync = current_metadata.get("subzone_resync_sent_at")
                        now_ts_sz = int(time_module.time())
                        should_sz_resync = True

                        if last_sz_resync:
                            elapsed_sz = now_ts_sz - last_sz_resync
                            if elapsed_sz < subzone_resync_cooldown_seconds:
                                should_sz_resync = False
                                logger.debug(
                                    "SUBZONE_DRIFT [%s]: subzones lost but cooldown active (%ds remaining)",
                                    esp_device.device_id,
                                    subzone_resync_cooldown_seconds - elapsed_sz,
                                )

                        if should_sz_resync and esp_device.status == "offline":
                            should_sz_resync = False
                            logger.debug(
                                "Skipping subzone resync for offline ESP %s",
                                esp_device.device_id,
                            )

                        if (
                            should_sz_resync
                            and _command_bridge
                            and _command_bridge.has_pending(esp_device.device_id, "subzone")
                        ):
                            should_sz_resync = False
                            logger.debug(
                                "Skipping subzone resync for %s: pending subzone command exists",
                                esp_device.device_id,
                            )

                        if (
                            should_sz_resync
                            and esp_device.device_id in self._config_push_pending_esps
                        ):
                            should_sz_resync = False
                            logger.debug(
                                "Skipping subzone resync for %s: config push pending",
                                esp_device.device_id,
                            )

                        if should_sz_resync:
                            logger.warning(
                                "SUBZONE_DRIFT [%s]: ESP reports subzone_count=0 but DB has %d subzones. "
                                "Auto-resending subzone assignments.",
                                esp_device.device_id,
                                db_subzone_count_meta,
                            )
                            try:
                                from ..client import MQTTClient

                                active_subzones = await _subzone_repo.get_by_esp(
                                    esp_device.device_id
                                )
                                active_subzones = [sz for sz in active_subzones if sz.is_active][:8]
                                mqtt_client_instance = MQTTClient.get_instance()
                                resent = 0
                                for sz in active_subzones:
                                    sz_topic = TopicBuilder.build_subzone_assign_topic(
                                        esp_device.device_id
                                    )
                                    sz_payload_data = {
                                        "subzone_id": sz.subzone_id,
                                        "subzone_name": sz.subzone_name or "",
                                        "parent_zone_id": "",
                                        "assigned_gpios": [
                                            g for g in (sz.assigned_gpios or []) if g != 0
                                        ],
                                        "safe_mode_active": False,
                                        "timestamp": now_ts_sz,
                                    }
                                    mqtt_client_instance.publish(
                                        sz_topic,
                                        json.dumps(sz_payload_data),
                                        qos=1,
                                    )
                                    resent += 1
                                current_metadata["subzone_resync_sent_at"] = now_ts_sz
                                current_metadata["subzone_resync_count"] = db_subzone_count_meta
                                logger.info(
                                    "SUBZONE_DRIFT [%s]: Resent %d/%d subzone assignments.",
                                    esp_device.device_id,
                                    resent,
                                    len(active_subzones),
                                )
                            except Exception as sz_resync_err:
                                logger.error(
                                    "Failed to resend subzone assignments to %s: %s",
                                    esp_device.device_id,
                                    sz_resync_err,
                                    exc_info=True,
                                )
                except Exception as sz_drift_err:
                    logger.warning(
                        "Subzone drift check failed for %s: %s",
                        esp_device.device_id,
                        sz_drift_err,
                    )

            # Update health metrics
            current_metadata["last_heap_free"] = payload.get("heap_free", payload.get("free_heap"))
            current_metadata["last_wifi_rssi"] = payload.get("wifi_rssi")
            # Update IP address if provided (ESP may get new IP via DHCP lease renewal)
            wifi_ip = payload.get("wifi_ip")
            if wifi_ip:
                esp_device.ip_address = wifi_ip
            heartbeat_hardware_type = payload.get("hardware_type")
            if heartbeat_hardware_type and esp_device.hardware_type != "MOCK_ESP32":
                if heartbeat_hardware_type not in constants.HARDWARE_TYPES:
                    logger.warning(
                        "Unknown hardware_type '%s' from %s heartbeat — storing as reported",
                        heartbeat_hardware_type,
                        esp_device.device_id,
                    )
                if heartbeat_hardware_type != esp_device.hardware_type:
                    logger.info(
                        "Updating hardware_type for %s: %s -> %s",
                        esp_device.device_id,
                        esp_device.hardware_type,
                        heartbeat_hardware_type,
                    )
                    esp_device.hardware_type = heartbeat_hardware_type
                current_metadata["hardware_type"] = heartbeat_hardware_type
            current_metadata["last_uptime"] = payload.get("uptime")
            current_metadata["last_sensor_count"] = payload.get(
                "sensor_count", payload.get("active_sensors", 0)
            )
            current_metadata["last_actuator_count"] = payload.get(
                "actuator_count", payload.get("active_actuators", 0)
            )
            current_metadata["last_heartbeat"] = datetime.now(timezone.utc).isoformat()

            # AUT-60: Persist system_state for Logic Engine config_pending gate
            if "system_state" in payload:
                prev_state = current_metadata.get("system_state")
                current_metadata["system_state"] = payload["system_state"]

                # Clear Logic Engine config_pending backoff when leaving CONFIG_PENDING
                if (
                    prev_state == "CONFIG_PENDING_AFTER_RESET"
                    and payload["system_state"] != "CONFIG_PENDING_AFTER_RESET"
                ):
                    try:
                        from ...services.logic_engine import get_logic_engine

                        logic_engine = get_logic_engine()
                        if logic_engine is not None:
                            logic_engine.invalidate_config_pending_backoff(esp_device.device_id)
                            logger.info(
                                "Config pending backoff cleared for %s " "(system_state %s -> %s)",
                                esp_device.device_id,
                                prev_state,
                                payload["system_state"],
                            )
                    except Exception as cp_err:
                        logger.warning(
                            "Failed to clear config_pending backoff for %s: %s",
                            esp_device.device_id,
                            cp_err,
                        )

            if "boot_sequence_id" in payload:
                current_metadata["boot_sequence_id"] = payload.get("boot_sequence_id")
            if "reset_reason" in payload:
                current_metadata["reset_reason"] = payload.get("reset_reason")
            if "segment_start_ts" in payload:
                current_metadata["segment_start_ts"] = payload.get("segment_start_ts")
            if "metrics_schema_version" in payload:
                current_metadata["metrics_schema_version"] = payload.get("metrics_schema_version")
            self._track_contract_reject_metrics(esp_device.device_id, payload, current_metadata)

            # ============================================
            # GPIO STATUS (Phase 1) - With Pydantic Validation
            # ============================================
            if "gpio_status" in payload:
                validated_gpio_status = self._validate_gpio_status(
                    payload.get("gpio_status", []),
                    payload.get("gpio_reserved_count", 0),
                    esp_device.device_id,
                )
                if validated_gpio_status is not None:
                    current_metadata["gpio_status"] = validated_gpio_status["gpio_status"]
                    current_metadata["gpio_reserved_count"] = validated_gpio_status[
                        "gpio_reserved_count"
                    ]
                    current_metadata["gpio_status_updated_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    logger.debug(
                        f"GPIO status validated and updated for {esp_device.device_id}: "
                        f"{len(validated_gpio_status['gpio_status'])} reserved pins"
                    )
                else:
                    logger.warning(
                        f"GPIO status validation failed for {esp_device.device_id}, "
                        f"skipping GPIO metadata update"
                    )

            if "payload_degraded" in payload:
                current_metadata["payload_degraded"] = bool(payload.get("payload_degraded"))
            if "degraded_fields" in payload:
                raw_degraded_fields = payload.get("degraded_fields", [])
                if isinstance(raw_degraded_fields, list):
                    current_metadata["degraded_fields"] = [
                        str(field)
                        for field in raw_degraded_fields
                        if isinstance(field, str) and field
                    ]
            if "heartbeat_degraded_count" in payload:
                current_metadata["heartbeat_degraded_count"] = payload.get(
                    "heartbeat_degraded_count"
                )

            esp_device.device_metadata = current_metadata
            flag_modified(esp_device, "device_metadata")

        except (AttributeError, TypeError, KeyError) as e:
            # Structured data errors: log and roll back the in-progress metadata
            # changes so we never commit a partially-updated device_metadata blob.
            logger.error(
                f"Failed to update ESP metadata for {esp_device.device_id}: {e}",
                exc_info=True,
            )
            # Restore original metadata to avoid partial state commit
            esp_device.device_metadata = esp_device.device_metadata or {}
        except Exception as e:
            # Unexpected errors: same defensive rollback, re-raise so the caller
            # (handle_heartbeat) can decide whether the whole transaction should
            # be aborted.
            logger.error(
                f"Unexpected error updating ESP metadata for {esp_device.device_id}: {e}",
                exc_info=True,
            )
            esp_device.device_metadata = esp_device.device_metadata or {}
            raise

    def _validate_payload(self, payload: dict) -> dict:
        """
        Validate heartbeat payload structure.

        Required fields: ts, uptime, heap_free OR free_heap, wifi_rssi

        Args:
            payload: Payload dict to validate

        Returns:
            {"valid": bool, "error": str, "error_code": int}
        """
        # Check required fields (with alternatives for compatibility)
        if "ts" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: ts",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        if "uptime" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: uptime",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        # Accept both heap_free (ESP32) and free_heap (legacy)
        if "heap_free" not in payload and "free_heap" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: heap_free or free_heap",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        if "wifi_rssi" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: wifi_rssi",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        # Type validation
        if not isinstance(payload["ts"], int):
            return {
                "valid": False,
                "error": "Field 'ts' must be integer (Unix timestamp)",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        if not isinstance(payload["uptime"], int):
            return {
                "valid": False,
                "error": "Field 'uptime' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Validate heap field (whichever is present)
        heap_value = payload.get("heap_free", payload.get("free_heap"))
        if not isinstance(heap_value, int):
            return {
                "valid": False,
                "error": "Field 'heap_free/free_heap' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        if not isinstance(payload["wifi_rssi"], int):
            return {
                "valid": False,
                "error": "Field 'wifi_rssi' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Contract upgrade path:
        # - metrics_schema_version missing/1 => segment fields optional
        # - metrics_schema_version >=2 => segment fields mandatory (fail-closed)
        metrics_schema_version = payload.get("metrics_schema_version")
        if metrics_schema_version is not None and not isinstance(metrics_schema_version, int):
            return {
                "valid": False,
                "error": "Field 'metrics_schema_version' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        if isinstance(metrics_schema_version, int) and metrics_schema_version >= 2:
            required_segment_fields = ("boot_sequence_id", "reset_reason", "segment_start_ts")
            for field in required_segment_fields:
                if field not in payload:
                    return {
                        "valid": False,
                        "error": f"Missing required field for schema>=2: {field}",
                        "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    }

            if not isinstance(payload.get("boot_sequence_id"), str):
                return {
                    "valid": False,
                    "error": "Field 'boot_sequence_id' must be string for schema>=2",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

            if not isinstance(payload.get("reset_reason"), str):
                return {
                    "valid": False,
                    "error": "Field 'reset_reason' must be string for schema>=2",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

            if not isinstance(payload.get("segment_start_ts"), int):
                return {
                    "valid": False,
                    "error": "Field 'segment_start_ts' must be integer for schema>=2",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

        return {"valid": True, "error": "", "error_code": ValidationErrorCode.NONE}

    def _detect_device_source(self, esp_device: ESPDevice, payload: dict) -> str:
        """
        Detect the device source for logging purposes.

        Detection priority:
        1. Explicit _source field in payload → use value
        2. Device hardware_type == "MOCK_ESP32" → MOCK
        3. Device capabilities.mock == True → MOCK
        4. ESP ID starts with "MOCK_" or "ESP_MOCK" → MOCK
        5. ESP ID starts with "TEST_" → TEST
        6. ESP ID starts with "SIM_" → SIMULATION
        7. Default → PRODUCTION

        Args:
            esp_device: ESPDevice instance
            payload: MQTT payload dict

        Returns:
            Data source string value
        """
        esp_id = esp_device.device_id or "unknown"
        detection_reason = None

        # Priority 1: Explicit source field
        if "_source" in payload:
            source_value = payload["_source"].lower()
            try:
                result = DataSource(source_value).value
                detection_reason = f"payload._source='{source_value}'"
                logger.debug(
                    f"DeviceSource detection [{esp_id}]: {result} (reason: {detection_reason})"
                )
                return result
            except ValueError:
                return DataSource.PRODUCTION.value

        # Priority 2: Device hardware_type
        if esp_device.hardware_type == "MOCK_ESP32":
            detection_reason = "esp_device.hardware_type='MOCK_ESP32'"
            result = DataSource.MOCK.value
            logger.debug(
                f"DeviceSource detection [{esp_id}]: {result} (reason: {detection_reason})"
            )
            return result

        # Priority 3: Device capabilities flag
        if esp_device.capabilities and esp_device.capabilities.get("mock"):
            detection_reason = "esp_device.capabilities.mock=True"
            result = DataSource.MOCK.value
            logger.debug(
                f"DeviceSource detection [{esp_id}]: {result} (reason: {detection_reason})"
            )
            return result

        # Priority 4-6: ESP ID prefix detection
        if esp_id.startswith("MOCK_") or esp_id.startswith("ESP_MOCK"):
            detection_reason = f"esp_id prefix 'MOCK_' or 'ESP_MOCK'"
            result = DataSource.MOCK.value
            logger.debug(
                f"DeviceSource detection [{esp_id}]: {result} (reason: {detection_reason})"
            )
            return result
        if esp_id.startswith("TEST_"):
            detection_reason = f"esp_id prefix 'TEST_'"
            result = DataSource.TEST.value
            logger.debug(
                f"DeviceSource detection [{esp_id}]: {result} (reason: {detection_reason})"
            )
            return result
        if esp_id.startswith("SIM_"):
            detection_reason = f"esp_id prefix 'SIM_'"
            result = DataSource.SIMULATION.value
            logger.debug(
                f"DeviceSource detection [{esp_id}]: {result} (reason: {detection_reason})"
            )
            return result

        # Default
        detection_reason = "default (no matching criteria)"
        result = DataSource.PRODUCTION.value
        logger.debug(f"DeviceSource detection [{esp_id}]: {result} (reason: {detection_reason})")
        return result

    def _validate_gpio_status(
        self, gpio_status: list, gpio_reserved_count: int, device_id: str
    ) -> Optional[dict]:
        """
        Validate GPIO status data using Pydantic models.

        Ensures data integrity before storing in database.
        Returns validated data dict or None on validation failure.

        Args:
            gpio_status: Raw GPIO status list from payload
            gpio_reserved_count: Reported count from payload
            device_id: ESP device ID for logging

        Returns:
            Dict with validated gpio_status and gpio_reserved_count, or None on error
        """
        try:
            from ...schemas.esp import GpioStatusItem
            from pydantic import ValidationError

            # Validate each GPIO status item
            validated_items = []
            for idx, item in enumerate(gpio_status):
                try:
                    validated_item = GpioStatusItem(**item)
                    validated_items.append(validated_item.model_dump())
                except ValidationError as e:
                    logger.warning(f"GPIO status item {idx} validation failed for {device_id}: {e}")
                    # Skip invalid items but continue processing
                    continue

            # Log count mismatch but don't reject
            # Bus-GPIOs (I2C SDA/SCL, OneWire) may cause validation mismatches —
            # only warn if mismatch exceeds the number of bus-GPIOs in the raw input
            mismatch = abs(gpio_reserved_count - len(validated_items))
            if mismatch > 0:
                bus_gpio_count = sum(
                    1
                    for g in gpio_status
                    if isinstance(g, dict) and str(g.get("owner", "")).startswith("bus/")
                )
                if mismatch > bus_gpio_count:
                    logger.warning(
                        f"GPIO count mismatch for {device_id}: "
                        f"reported={gpio_reserved_count}, validated={len(validated_items)}, "
                        f"bus_gpios={bus_gpio_count}"
                    )
                else:
                    logger.debug(
                        f"GPIO count minor mismatch for {device_id}: "
                        f"reported={gpio_reserved_count}, validated={len(validated_items)}, "
                        f"bus_gpios={bus_gpio_count}"
                    )

            # Return validated items as dicts (already converted via model_dump)
            return {"gpio_status": validated_items, "gpio_reserved_count": len(validated_items)}

        except ImportError as e:
            logger.error(
                f"Failed to import GPIO schemas for {device_id}: {e}. "
                f"GPIO status will be skipped to avoid storing unvalidated data."
            )
            # Return None (not raw data) so the caller skips the metadata update
            # rather than persisting unvalidated GPIO status into the database.
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error validating GPIO status for {device_id}: {e}", exc_info=True
            )
            return None

    def _log_health_metrics(self, esp_id: str, payload: dict):
        """
        Log device health metrics.

        Args:
            esp_id: ESP device ID string
            payload: Heartbeat payload with metrics
        """
        uptime = payload.get("uptime", 0)
        # Accept both heap_free (ESP32) and free_heap (legacy)
        free_heap = payload.get("heap_free", payload.get("free_heap", 0))
        wifi_rssi = payload.get("wifi_rssi", 0)
        error_count = payload.get("error_count", 0)
        # Accept both sensor_count (ESP32) and active_sensors (legacy)
        active_sensors = payload.get("sensor_count", payload.get("active_sensors", 0))
        # Accept both actuator_count (ESP32) and active_actuators (legacy)
        active_actuators = payload.get("actuator_count", payload.get("active_actuators", 0))

        # Check for low memory
        if free_heap < 10000:  # Less than 10KB free
            logger.warning(f"Low memory on {esp_id}: heap_free={free_heap} bytes")

        # Check for weak WiFi signal
        if wifi_rssi < -70:  # Weak signal
            logger.warning(f"Weak WiFi signal on {esp_id}: rssi={wifi_rssi} dBm")

        # Check for errors
        if error_count > 0:
            logger.warning(f"Device {esp_id} reported {error_count} error(s)")

        logger.debug(
            f"Health metrics for {esp_id}: "
            f"uptime={uptime}s, free_heap={free_heap}B, rssi={wifi_rssi}dBm, "
            f"sensors={active_sensors}, actuators={active_actuators}, errors={error_count}"
        )

    def _normalize_last_disconnect_metadata_on_online(
        self,
        *,
        esp_device: ESPDevice,
        server_received_at: datetime,
    ) -> None:
        """
        Clear stale LWT disconnect metadata after a valid online heartbeat.

        Legacy LWT payloads may persist ``last_disconnect.timestamp=0``.
        Keeping that marker while the device is online creates an inconsistent
        state projection. We retain an audit trace in metadata and remove the
        stale marker from ``last_disconnect``.
        """
        metadata = esp_device.device_metadata
        if not isinstance(metadata, dict):
            return

        last_disconnect = metadata.get("last_disconnect")
        if not isinstance(last_disconnect, dict):
            return

        source = str(last_disconnect.get("source", "")).strip().lower()
        raw_timestamp = last_disconnect.get("timestamp")
        normalized_timestamp: Optional[int] = None
        try:
            parsed_timestamp = int(raw_timestamp)
            if parsed_timestamp > 0:
                normalized_timestamp = parsed_timestamp
        except (TypeError, ValueError):
            normalized_timestamp = None

        # Preserve valid disconnect records and non-LWT markers.
        if source != "lwt" or normalized_timestamp is not None:
            return

        metadata["last_disconnect_stale_cleared_at"] = int(server_received_at.timestamp())
        metadata["last_disconnect_stale_cleared_reason"] = "online_recovery_after_invalid_lwt"
        metadata.pop("last_disconnect", None)
        esp_device.device_metadata = metadata
        flag_modified(esp_device, "device_metadata")
        logger.info(
            "Cleared stale last_disconnect metadata after online recovery: esp_id=%s source=%s timestamp=%s",
            esp_device.device_id,
            source or "unknown",
            raw_timestamp,
        )

    def _clear_retained_lwt(self, esp_id: str, current_epoch: int = 0) -> None:
        """
        Publish empty retained message on the ESP LWT topic to clear stale offline.

        Step 5b (online path) and pending_approval (AUT-339): a connected ESP must
        not leave a retained LWT that makes subscribers think the device is offline.

        Guard: skip if LWT was already cleared for this handover_epoch (same session).
        One clear per reconnect session suffices — repeated clears are no-ops on the
        broker but waste QoS-1 publish slots and ESP inbound ACK capacity.
        """
        if current_epoch > 0 and self._lwt_cleared_epoch_by_esp.get(esp_id) == current_epoch:
            logger.debug(
                "LWT clear skipped for %s — already cleared for epoch %d", esp_id, current_epoch
            )
            return
        try:
            from ..client import MQTTClient

            lwt_topic = TopicBuilder.build_lwt_topic(esp_id)
            mqtt_client = MQTTClient.get_instance()
            mqtt_client.publish(lwt_topic, "", qos=1, retain=True)
            if current_epoch > 0:
                self._lwt_cleared_epoch_by_esp[esp_id] = current_epoch
            logger.debug("Cleared retained LWT message for %s (epoch=%d)", esp_id, current_epoch)
        except Exception as lwt_clear_error:
            logger.warning(
                "Failed to clear retained LWT for %s: %s",
                esp_id,
                lwt_clear_error,
            )

    async def _log_heartbeat_entry(
        self,
        esp_device: ESPDevice,
        esp_id_str: str,
        payload: dict,
    ) -> str:
        """
        Append one row to esp_heartbeat_logs in an isolated transaction.

        Shared by the online heartbeat path and pending_approval (AUT-339).
        Uses a dedicated session to keep history logging non-blocking for the
        caller's main heartbeat transaction.

        Returns:
            Resolved data_source (for downstream debug formatting).
        """
        device_source = self._detect_device_source(esp_device, payload)
        try:
            async with resilient_session() as heartbeat_session:
                heartbeat_repo = ESPHeartbeatRepository(heartbeat_session)
                await heartbeat_repo.log_heartbeat(
                    esp_uuid=esp_device.id,
                    device_id=esp_id_str,
                    payload=payload,
                    data_source=device_source,
                )
                await heartbeat_session.commit()
        except Exception as hb_log_error:
            logger.warning(
                "Failed to log heartbeat history for %s: %s",
                esp_id_str,
                hb_log_error,
            )
        return device_source

    async def _send_heartbeat_ack(
        self,
        esp_id: str,
        status: str,
        config_available: bool = False,
        handover_epoch: int = 1,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Send heartbeat ACK to ESP device (Phase 2: Bidirectional Approval).

        Sends device approval status back to ESP after each heartbeat.
        This allows ESP to transition from PENDING_APPROVAL → OPERATIONAL
        without requiring a reboot after admin approval.

        Fire-and-Forget Pattern:
        - ESP does NOT block waiting for this ACK
        - QoS 1 (at least once) — ensures reliable P1 timer reset
        - Next heartbeat will trigger another ACK

        Args:
            esp_id: ESP device ID (e.g., "ESP_12AB34CD")
            status: Current device status from DB
                    ("pending_approval", "approved", "online", "offline", "rejected")
            config_available: True if server has pending config for this device

        Returns:
            True if publish successful, False otherwise
        """
        try:
            ack_started = time_module.perf_counter()
            # Import MQTTClient only when needed (avoid circular imports)
            from ..client import MQTTClient

            # Build ACK topic
            topic = TopicBuilder.build_heartbeat_ack_topic(esp_id)

            # Build payload
            payload = {
                "status": status,
                "config_available": config_available,
                "server_time": int(time_module.time()),
                "handover_epoch": max(1, int(handover_epoch)),
                "ack_type": "heartbeat",
                "contract_version": 2,
            }
            if session_id:
                payload["session_id"] = session_id

            # Get MQTT client instance
            mqtt_client = MQTTClient.get_instance()

            # Publish with QoS 1 (at least once) — ensures reliable P1 timer reset
            success = mqtt_client.publish(topic, json.dumps(payload), qos=1)

            if success:
                observe_heartbeat_ack_latency_ms(
                    (time_module.perf_counter() - ack_started) * 1000.0
                )
                increment_heartbeat_ack_valid()
                # Use INFO for reconnect-relevant statuses to aid boot-diagnosis in Loki
                if status in ("online", "offline"):
                    logger.info(
                        "Heartbeat ACK sent to %s on topic %s (status=%s)",
                        esp_id,
                        topic,
                        status,
                    )
                else:
                    logger.debug(f"Heartbeat ACK sent to {esp_id}: status={status}")
            else:
                # Not critical - ESP will receive next ACK on next heartbeat
                logger.warning(f"Failed to send heartbeat ACK to {esp_id}")

            return success

        except Exception as e:
            # Not critical - don't fail the heartbeat handler
            logger.warning(f"Error sending heartbeat ACK to {esp_id}: {e}")
            return False

    async def _send_heartbeat_error_ack(
        self,
        esp_id: str,
        error: str,
        handover_epoch: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Send error ACK to prevent P1 false-positive (SAFETY-P5 Fix-4).

        Server is alive even if heartbeat processing failed.
        ESP resets P1 timer on ANY valid ACK, regardless of status.

        Args:
            esp_id: ESP device ID
            error: Short error description for ESP logging

        Returns:
            True if publish successful
        """
        try:
            from ..client import MQTTClient

            topic = TopicBuilder.build_heartbeat_ack_topic(esp_id)
            if handover_epoch is None:
                # Keep error ACKs on the same fail-closed contract as normal ACKs.
                handover_epoch, default_session_id = self._build_ack_contract_context(
                    esp_id, is_reconnect=False
                )
                if session_id is None:
                    session_id = default_session_id
            payload = {
                "status": "error",
                "error": error,
                "server_time": int(time_module.time()),
                "handover_epoch": max(1, int(handover_epoch)),
                "ack_type": "heartbeat",
                "contract_version": 2,
            }
            if session_id:
                payload["session_id"] = session_id
            mqtt_client = MQTTClient.get_instance()
            success = mqtt_client.publish(topic, json.dumps(payload), qos=1)
            if success:
                increment_heartbeat_ack_valid()
                logger.warning("[SAFETY-P5] Error ACK sent to %s: %s", esp_id, error)
            else:
                logger.error("[SAFETY-P5] Failed to send error ACK to %s", esp_id)
            return success
        except Exception as e:
            logger.error("[SAFETY-P5] Error ACK exception for %s: %s", esp_id, e)
            return False

    async def _broadcast_reconnect_phase(
        self, esp_id: str, phase: str, details: Optional[dict] = None
    ) -> None:
        """Expose reconnect handover phases for observability and UI."""
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            payload = {
                "esp_id": esp_id,
                "phase": phase,
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
            }
            if details:
                payload.update(details)
            await ws_manager.broadcast("esp_reconnect_phase", payload)
        except Exception as phase_error:
            logger.debug(
                "Reconnect phase broadcast failed for %s (%s): %s",
                esp_id,
                phase,
                phase_error,
            )

    async def _complete_adoption_and_trigger_reconnect_eval(self, esp_id: str) -> None:
        """Finalize adoption before reconnect delta evaluation is allowed.

        Config-Push Gate: If a config push was triggered during this heartbeat cycle
        (ESP reported 0 sensors/actuators but DB has configs), skip the reconnect
        evaluation. The ESP must receive and apply the config first — firing actuator
        commands before config arrives causes "No actuator configured on GPIO X" errors.
        The next heartbeat after the ESP applies the config will re-trigger evaluation.
        """
        try:
            await asyncio.sleep(ADOPTION_GRACE_SECONDS)

            # Config-Push Gate: skip reconnect eval if config push is pending.
            # _has_pending_config() marks the ESP in _config_push_pending_esps when
            # a push is triggered. The set is cleared after the check so subsequent
            # reconnects are not permanently gated.
            if esp_id in self._config_push_pending_esps:
                self._config_push_pending_esps.discard(esp_id)
                logger.info(
                    "Reconnect eval skipped for %s: config push pending, "
                    "waiting for ESP to apply config before firing actuator commands.",
                    esp_id,
                )
                adoption_service = get_state_adoption_service()
                await adoption_service.mark_adoption_completed(esp_id)
                await self._broadcast_reconnect_phase(
                    esp_id=esp_id,
                    phase="adopted",
                    details={"config_push_pending": True},
                )
                return

            adoption_service = get_state_adoption_service()
            await adoption_service.mark_adoption_completed(esp_id)
            await self._broadcast_reconnect_phase(esp_id=esp_id, phase="adopted")

            from ...services.logic_engine import get_logic_engine

            logic_engine = get_logic_engine()
            if logic_engine is not None:
                await logic_engine.trigger_reconnect_evaluation(esp_id)
                await self._broadcast_reconnect_phase(esp_id=esp_id, phase="delta_enforced")

            # Signal full convergence after successful reconnect evaluation
            await self._broadcast_reconnect_phase(esp_id=esp_id, phase="converged")
        except Exception as reconnect_eval_error:
            logger.error(
                "Reconnect adoption/evaluation failed for %s: %s",
                esp_id,
                reconnect_eval_error,
                exc_info=True,
            )

    async def _has_pending_config(
        self,
        esp_device: ESPDevice,
        session,
        esp_sensor_count: int = 0,
        esp_actuator_count: int = 0,
        esp_offline_rule_count: int = -1,
        esp_subzone_count: int = -1,
        is_reconnect: bool = False,
        offline_seconds: float = 0.0,
        reconnect_epoch: int | None = None,
    ) -> bool:
        """
        Check if server has unsent configuration for this ESP.

        Detects config loss after ESP reboot by comparing the sensor/actuator
        counts reported in the heartbeat against the DB. If the ESP reports 0
        but the DB has configs, triggers an automatic config push.

        Args:
            esp_device: ESPDevice instance
            session: Active DB session
            esp_sensor_count: sensor_count from heartbeat payload
            esp_actuator_count: actuator_count from heartbeat payload
            esp_subzone_count: subzone_count from heartbeat payload (-1 = old firmware, skip check)
            is_reconnect: True when this heartbeat is from reconnect (>60s offline)
            offline_seconds: Observed offline duration for reconnect telemetry

        Returns:
            True if there is pending configuration, False otherwise
        """
        try:
            # Skip config push to offline ESPs
            if esp_device.status == "offline":
                logger.debug("Skipping config push for offline ESP %s", esp_device.device_id)
                return False

            if esp_device.status == "virtual":
                logger.debug("Skipping config push for virtual ESP %s", esp_device.device_id)
                return False

            from ...db.repositories import SensorRepository, ActuatorRepository

            sensor_repo = SensorRepository(session)
            actuator_repo = ActuatorRepository(session)

            db_sensor_count = await sensor_repo.count_by_esp(esp_device.id)
            db_actuator_count = await actuator_repo.count_by_esp(esp_device.id)

            # AUT-134: count-drift detection.
            # Reboot-loss remains covered (ESP=0 while DB>0), but we now
            # also detect non-zero count drift to trigger targeted resync.
            needs_sensor_push = db_sensor_count > 0 and esp_sensor_count != db_sensor_count
            needs_actuator_push = db_actuator_count > 0 and esp_actuator_count != db_actuator_count

            # AUT-283: subzone count drift detection (esp_subzone_count=-1 means old firmware → skip)
            from ...db.repositories.subzone_repo import SubzoneRepository

            subzone_repo = SubzoneRepository(session)
            db_subzone_count = await subzone_repo.count_by_esp(esp_device.device_id)
            needs_subzone_push = (
                esp_subzone_count >= 0
                and db_subzone_count > 0
                and esp_subzone_count != db_subzone_count
            )
            db_offline_rule_count = -1
            needs_offline_rules_push = False
            try:
                esp_offline_rule_count = int(esp_offline_rule_count)
            except (TypeError, ValueError):
                esp_offline_rule_count = -1
            # Reconnect regression guard: if offline rules are missing on ESP after reconnect,
            # trigger the existing config push path to restore them.
            if esp_offline_rule_count == 0:
                db_offline_rule_count = await self._expected_offline_rule_count(
                    esp_device.device_id, session
                )
                needs_offline_rules_push = db_offline_rule_count > 0

            if (
                needs_sensor_push
                or needs_actuator_push
                or needs_subzone_push
                or needs_offline_rules_push
            ):
                if esp_device.device_id in self._config_push_pending_esps:
                    logger.debug(
                        "Config push for %s skipped (already pending). ESP sensors=%d/actuators=%d/"
                        "offline_rules=%d, DB sensors=%d/actuators=%d/offline_rules=%d",
                        esp_device.device_id,
                        esp_sensor_count,
                        esp_actuator_count,
                        esp_offline_rule_count,
                        db_sensor_count,
                        db_actuator_count,
                        db_offline_rule_count if db_offline_rule_count >= 0 else -1,
                    )
                    return False

                # R1 — AUT-590: Skip automated config push when ESP is under FreeRTOS
                # queue pressure. Resumes on next heartbeat after recovered is received.
                from .queue_pressure_handler import is_esp_under_pressure

                if is_esp_under_pressure(esp_device.device_id):
                    logger.info(
                        "Config push for %s skipped (queue pressure active)",
                        esp_device.device_id,
                    )
                    return False

                # Check cooldown (analog to zone_resync_sent_at pattern)
                metadata = esp_device.device_metadata or {}
                last_push = metadata.get("config_push_sent_at")
                last_push_epoch = metadata.get("config_push_epoch")
                now_ts = int(time_module.time())
                reconnect_epoch_int: int | None = None
                if reconnect_epoch is not None:
                    try:
                        reconnect_epoch_int = int(reconnect_epoch)
                    except (TypeError, ValueError):
                        reconnect_epoch_int = None

                # Reconnect-bypass is allowed once per reconnect epoch.
                # For missing epoch data, stay conservative and only bypass on first push.
                bypass_cooldown_for_reconnect = False
                if is_reconnect:
                    if reconnect_epoch_int is not None:
                        try:
                            last_push_epoch_int = (
                                int(last_push_epoch) if last_push_epoch is not None else None
                            )
                        except (TypeError, ValueError):
                            last_push_epoch_int = None
                        bypass_cooldown_for_reconnect = (
                            last_push_epoch_int is None
                            or reconnect_epoch_int != last_push_epoch_int
                        )
                    else:
                        bypass_cooldown_for_reconnect = last_push is None
                if needs_offline_rules_push:
                    reason_code = (
                        "reconnect_offline_rules_mismatch"
                        if bypass_cooldown_for_reconnect
                        else "heartbeat_offline_rules_mismatch"
                    )
                else:
                    reason_code = (
                        "reconnect_count_mismatch"
                        if bypass_cooldown_for_reconnect
                        else "heartbeat_count_mismatch"
                    )

                if last_push and not bypass_cooldown_for_reconnect:
                    elapsed = now_ts - last_push
                    if elapsed < CONFIG_PUSH_COOLDOWN_SECONDS:
                        logger.debug(
                            "Config push for %s skipped (cooldown: %ds remaining). "
                            "ESP: sensors=%d/actuators=%d/offline_rules=%d, "
                            "DB: sensors=%d/actuators=%d/offline_rules=%d",
                            esp_device.device_id,
                            int(CONFIG_PUSH_COOLDOWN_SECONDS - elapsed),
                            esp_sensor_count,
                            esp_actuator_count,
                            esp_offline_rule_count,
                            db_sensor_count,
                            db_actuator_count,
                            db_offline_rule_count if db_offline_rule_count >= 0 else -1,
                        )
                        return False
                elif last_push and bypass_cooldown_for_reconnect:
                    elapsed = now_ts - int(last_push)
                    logger.info(
                        "Config push cooldown bypass for reconnect %s "
                        "(offline=%.1fs, epoch=%s, elapsed_since_last_push=%ds, "
                        "ESP: sensors=%d/actuators=%d/offline_rules=%d, "
                        "DB: sensors=%d/actuators=%d/offline_rules=%d)",
                        esp_device.device_id,
                        float(offline_seconds),
                        str(reconnect_epoch_int) if reconnect_epoch_int is not None else "none",
                        int(elapsed),
                        esp_sensor_count,
                        esp_actuator_count,
                        esp_offline_rule_count,
                        db_sensor_count,
                        db_actuator_count,
                        db_offline_rule_count if db_offline_rule_count >= 0 else -1,
                    )

                # Cooldown expired or first push — update metadata and trigger
                metadata["config_push_sent_at"] = now_ts
                metadata["config_push_reason"] = reason_code
                if reconnect_epoch_int is not None:
                    metadata["config_push_epoch"] = reconnect_epoch_int
                metadata["config_push_snapshot"] = {
                    "esp_sensor_count": int(esp_sensor_count),
                    "esp_actuator_count": int(esp_actuator_count),
                    "esp_offline_rule_count": int(esp_offline_rule_count),
                    "db_sensor_count": int(db_sensor_count),
                    "db_actuator_count": int(db_actuator_count),
                    "db_offline_rule_count": (
                        int(db_offline_rule_count) if db_offline_rule_count >= 0 else None
                    ),
                    "is_reconnect": bool(is_reconnect),
                    "offline_seconds": float(offline_seconds),
                }
                esp_device.device_metadata = metadata
                flag_modified(esp_device, "device_metadata")

                logger.info(
                    "Config count mismatch detected for %s (reason=%s): "
                    "ESP sensors=%d/actuators=%d/offline_rules=%d, "
                    "DB sensors=%d/actuators=%d/offline_rules=%d. "
                    "Triggering auto config push.",
                    esp_device.device_id,
                    reason_code,
                    esp_sensor_count,
                    esp_actuator_count,
                    esp_offline_rule_count,
                    db_sensor_count,
                    db_actuator_count,
                    db_offline_rule_count if db_offline_rule_count >= 0 else -1,
                )
                # Mark ESP as config-push-pending so reconnect evaluation is gated
                # until the ESP applies the new config (prevents "No actuator on GPIO X").
                self._config_push_pending_esps.add(esp_device.device_id)

                create_tracked_task(
                    self._auto_push_config(
                        esp_device.device_id,
                        reason_code=reason_code,
                    ),
                    name=f"auto_push_config_{esp_device.device_id}",
                )
                return True

            return False

        except Exception as e:
            logger.warning(f"Failed to check pending config for {esp_device.device_id}: {e}")
            return False

    async def _expected_offline_rule_count(self, esp_device_id: str, session) -> int:
        """Return expected offline-rule count for an ESP using existing config builder logic."""
        try:
            from ...services.config_builder import ConfigPayloadBuilder

            config_builder = ConfigPayloadBuilder()
            combined_config = await config_builder.build_combined_config(esp_device_id, session)
            return len(combined_config.get("offline_rules", []))
        except Exception as e:
            logger.warning(
                "Failed to compute expected offline rule count for %s: %s",
                esp_device_id,
                e,
            )
            return -1

    async def _auto_push_config(self, esp_device_id: str, reason_code: str) -> None:
        """
        Auto-push configuration to ESP after reboot detection.

        Runs as a separate async task so it doesn't block heartbeat processing.
        Uses its own DB session to avoid conflicts with the heartbeat session.

        AUT-134 PKG-01: Pre-flight Budget-Gate. Wenn die geschätzte JSON-Wire-
        Größe der Combined-Config das ESP32-Ingress-Budget überschreitet, wird
        der Auto-Push terminiert (kein Publish), das ``config_push_pending``-
        Flag aufgelöst und Operator-Sichtbarkeit über Audit + WS hergestellt.
        Damit verhindern wir Retry-Bursts durch wiederkehrende Reject-Loops.
        """
        try:
            from ...services.config_builder import (
                ConfigPayloadBuilder,
                estimate_config_wire_size,
                resolve_autopush_budget_bytes,
            )
            from ...services.esp_service import ESPService

            async with resilient_session() as session:
                esp_repo = ESPRepository(session)
                esp_device = await esp_repo.get_by_device_id(esp_device_id)
                hardware_type = esp_device.hardware_type if esp_device else None
                budget_bytes = resolve_autopush_budget_bytes(hardware_type)

                config_builder = ConfigPayloadBuilder()
                combined_config = await config_builder.build_combined_config(esp_device_id, session)

                # AUT-134 PKG-01: Pre-flight Budget-Check — VOR dem Publish.
                estimated_wire_len = estimate_config_wire_size(combined_config)

                # AUT-1029: Recovery — Oversize-Block-State löschen sobald Config wieder passt.
                if estimated_wire_len <= budget_bytes and esp_device:
                    meta = dict(esp_device.device_metadata or {})
                    cleared = False
                    for key in (
                        "config_push_oversize_blocked_at",
                        "config_push_oversize_reason_code",
                        "config_push_oversize_snapshot",
                    ):
                        if key in meta:
                            meta.pop(key, None)
                            cleared = True
                    if cleared:
                        esp_device.device_metadata = meta
                        flag_modified(esp_device, "device_metadata")
                        await session.commit()
                        logger.info(
                            "AUT-1029: Oversize block cleared for %s "
                            "(estimated_wire_len=%d <= budget=%d) — auto-push resuming",
                            esp_device_id,
                            estimated_wire_len,
                            budget_bytes,
                        )

                if estimated_wire_len > budget_bytes:
                    await self._handle_oversize_auto_push(
                        session=session,
                        esp_device_id=esp_device_id,
                        reason_code=reason_code,
                        estimated_wire_len=estimated_wire_len,
                        budget_bytes=budget_bytes,
                        sensor_count=len(combined_config.get("sensors", [])),
                        actuator_count=len(combined_config.get("actuators", [])),
                        offline_rules_count=len(combined_config.get("offline_rules", [])),
                    )
                    return

                esp_service = ESPService(esp_repo)
                result = await esp_service.send_config(
                    esp_device_id,
                    combined_config,
                    reason_code=reason_code,
                )

                if result.get("success"):
                    logger.info(
                        f"Auto config push successful for {esp_device_id}: "
                        f"{len(combined_config.get('sensors', []))} sensors, "
                        f"{len(combined_config.get('actuators', []))} actuators"
                    )
                else:
                    logger.warning(
                        f"Auto config push failed for {esp_device_id}: "
                        f"{result.get('message', 'unknown error')}"
                    )
                    # AUT-134: Cooldown was written in _has_pending_config before this task
                    # runs; if the frame cannot fit the ESP ingress budget, clear the
                    # premature "push scheduled" metadata so a future resync is possible.
                    if result.get("error_code") == ESP32ApplicationError.PAYLOAD_TOO_LARGE:
                        dev = await esp_repo.get_by_device_id(esp_device_id)
                        if dev:
                            meta = dict(dev.device_metadata or {})
                            meta.pop("config_push_sent_at", None)
                            meta["config_push_oversize_blocked_at"] = int(time_module.time())
                            meta["config_push_oversize_reason_code"] = reason_code
                            dev.device_metadata = meta
                            flag_modified(dev, "device_metadata")
                        await session.commit()
                        # Unblock zone-resync / adoption gate: no config is in flight.
                        self._config_push_pending_esps.discard(esp_device_id)

        except Exception as e:
            logger.error(
                f"Auto config push error for {esp_device_id}: {e}",
                exc_info=True,
            )

    async def _handle_oversize_auto_push(
        self,
        session,
        esp_device_id: str,
        reason_code: str,
        estimated_wire_len: int,
        budget_bytes: int,
        sensor_count: int,
        actuator_count: int,
        offline_rules_count: int,
    ) -> None:
        """
        AUT-134 PKG-01: Sauberer Abbruchpfad bei Config-Oversize VOR dem Publish.

        AUT-1029: Operator-Sichtbarkeit (ERROR/Audit/WS) wird über
        ``config_push_oversize_blocked_at`` gedämpft (E2). Resync bleibt möglich:
        ``config_push_sent_at`` wird nicht mehr entfernt; bei Config unter Budget
        räumt ``_auto_push_config`` die Oversize-Metadata auf.

        - Räumt das ``config_push_pending``-Flag auf (kein hängendes Pending).
        - Setzt Metadata: ``config_push_oversize_blocked_at`` + Snapshot.
        - Schreibt ein strukturiertes Audit-Ereignis (``CONFIG_FAILED``).
        - Broadcastet ``config_failed`` mit ``intent_outcome="VALIDATION_FAIL"``
          und ``reason_code="config_oversize"`` an WebSocket-Clients.

        Das Pattern spiegelt den bestehenden Oversize-Pfad in
        ``ESPService.send_config`` (Wire-Schwelle 4352) — hier greift der
        Pre-flight Gate früher (4096) und verhindert den MQTT-Publish komplett.
        """
        from ...db.models.audit_log import AuditEventType, AuditSeverity, AuditSourceType

        now_ts = int(time_module.time())
        should_notify = True
        notify_remaining_seconds = CONFIG_OVERSIZE_NOTIFY_COOLDOWN_SECONDS

        # 1) Pending-Flag auflösen, damit Adoption-/Reconnect-Gate weiterläuft.
        self._config_push_pending_esps.discard(esp_device_id)

        # 2) Metadata: Snapshot immer aktualisieren; Operator-Events nur bei Bedarf.
        try:
            esp_repo = ESPRepository(session)
            dev = await esp_repo.get_by_device_id(esp_device_id)
            if dev:
                meta = dict(dev.device_metadata or {})
                blocked_at_raw = meta.get("config_push_oversize_blocked_at")
                if blocked_at_raw is not None:
                    try:
                        elapsed = now_ts - int(blocked_at_raw)
                        if elapsed < CONFIG_OVERSIZE_NOTIFY_COOLDOWN_SECONDS:
                            should_notify = False
                            notify_remaining_seconds = (
                                CONFIG_OVERSIZE_NOTIFY_COOLDOWN_SECONDS - elapsed
                            )
                    except (TypeError, ValueError):
                        should_notify = True

                meta["config_push_oversize_reason_code"] = reason_code
                meta["config_push_oversize_snapshot"] = {
                    "estimated_wire_len": int(estimated_wire_len),
                    "budget_bytes": int(budget_bytes),
                    "sensor_count": int(sensor_count),
                    "actuator_count": int(actuator_count),
                    "offline_rules_count": int(offline_rules_count),
                }
                if should_notify:
                    meta["config_push_oversize_blocked_at"] = now_ts
                dev.device_metadata = meta
                flag_modified(dev, "device_metadata")
            await session.commit()
        except Exception as meta_err:
            logger.warning(
                "AUT-134 PKG-01: Failed to persist oversize metadata for %s: %s",
                esp_device_id,
                meta_err,
            )

        if not should_notify:
            logger.debug(
                "AUT-1029: Oversize auto-push still blocked for %s "
                "(notify damped, %ds until next ERROR/audit/WS). "
                "estimated_wire_len=%d > budget=%d",
                esp_device_id,
                max(0, notify_remaining_seconds),
                estimated_wire_len,
                budget_bytes,
            )
            return

        # 3) Strukturiertes Log-Ereignis (Operator-sichtbar).
        logger.error(
            "AUT-134 PKG-01: Auto-push BLOCKED for %s (reason=%s, "
            "estimated_wire_len=%d > budget=%d, sensors=%d, actuators=%d, "
            "offline_rules=%d). Config too large for ESP ingress — Auto-Push terminated.",
            esp_device_id,
            reason_code,
            estimated_wire_len,
            budget_bytes,
            sensor_count,
            actuator_count,
            offline_rules_count,
        )

        # 4) Audit-Log: CONFIG_FAILED mit reason_code=config_oversize.
        try:
            audit_repo = AuditLogRepository(session)
            await audit_repo.create(
                event_type=AuditEventType.CONFIG_FAILED,
                severity=AuditSeverity.ERROR,
                source_type=AuditSourceType.MQTT,
                source_id=esp_device_id,
                status="failed",
                message=(
                    f"Auto-push blocked for {esp_device_id}: config oversize "
                    f"({estimated_wire_len} bytes > budget)"
                ),
                details={
                    "esp_id": esp_device_id,
                    "aut134": "auto_push_preflight_oversize",
                    "reason_code": "config_oversize",
                    "trigger_reason_code": reason_code,
                    "estimated_wire_len": int(estimated_wire_len),
                    "sensor_count": int(sensor_count),
                    "actuator_count": int(actuator_count),
                    "offline_rules_count": int(offline_rules_count),
                },
            )
            await session.commit()
        except Exception as audit_err:
            logger.warning(
                "AUT-134 PKG-01: Failed to write audit for oversize block (%s): %s",
                esp_device_id,
                audit_err,
            )

        # 5) WebSocket-Broadcast: Operator-UI signalisieren (intent_outcome).
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(
                "config_failed",
                {
                    "esp_id": esp_device_id,
                    "intent_outcome": "VALIDATION_FAIL",
                    "reason_code": "config_oversize",
                    "trigger_reason_code": reason_code,
                    "estimated_wire_len": int(estimated_wire_len),
                    "sensor_count": int(sensor_count),
                    "actuator_count": int(actuator_count),
                    "offline_rules_count": int(offline_rules_count),
                    "error": (
                        "Combined config exceeds ESP32 ingress budget — "
                        "Auto-Push blocked before publish."
                    ),
                    "timestamp": int(time_module.time()),
                },
            )
        except Exception as ws_err:
            logger.warning(
                "AUT-134 PKG-01: WebSocket broadcast for oversize block failed (%s): %s",
                esp_device_id,
                ws_err,
            )

    async def _handle_reconnect_state_push(self, device_id: str) -> None:
        """
        T13-Phase3: Full-State-Push after ESP reconnect (>60s offline).

        Sends zone/assign + all active subzone/assign via MQTTCommandBridge (ACK-driven).
        Runs as async task — does not block heartbeat processing.
        Uses its own DB session to avoid conflicts with the heartbeat session.
        """
        try:
            await asyncio.sleep(STATE_PUSH_RECONNECT_DELAY_SECONDS)
            if not _command_bridge:
                logger.warning("No command_bridge for state push to %s", device_id)
                return

            async with resilient_session() as session:
                esp_repo = ESPRepository(session)
                esp_device = await esp_repo.get_by_device_id(device_id)
                if not esp_device or not esp_device.zone_id:
                    return

                # Skip mock ESPs (no real reboot)
                if (
                    device_id.startswith("ESP_MOCK_")
                    or device_id.startswith("MOCK_")
                    or "MOCK" in device_id
                ):
                    logger.debug("Skipping state push for mock ESP %s", device_id)
                    return

                # Cooldown: prevent rapid-fire pushes
                metadata = dict(esp_device.device_metadata or {})
                last_push = metadata.get("full_state_push_sent_at", 0)
                now_ts = int(time_module.time())
                if now_ts - last_push < STATE_PUSH_COOLDOWN_SECONDS:
                    logger.debug(
                        "State push cooldown for %s (%ds remaining)",
                        device_id,
                        STATE_PUSH_COOLDOWN_SECONDS - (now_ts - last_push),
                    )
                    return

                # 1. Zone assign via command_bridge (ACK-driven)
                zone_topic = TopicBuilder.build_zone_assign_topic(device_id)
                zone_payload = {
                    "zone_id": esp_device.zone_id,
                    "master_zone_id": esp_device.master_zone_id or "",
                    "zone_name": esp_device.zone_name or "",
                    "kaiser_id": esp_device.kaiser_id or constants.get_kaiser_id(),
                    "timestamp": now_ts,
                }
                try:
                    await _command_bridge.send_and_wait_ack(
                        topic=zone_topic,
                        payload=zone_payload,
                        esp_id=device_id,
                        command_type="zone",
                        timeout=_command_bridge.DEFAULT_TIMEOUT,
                    )
                    # Set cooldown only after successful zone ACK. If send fails (timeout),
                    # cooldown is not persisted and next reconnect trigger retries immediately.
                    metadata["full_state_push_sent_at"] = now_ts
                    esp_device.device_metadata = metadata
                    flag_modified(esp_device, "device_metadata")
                    await session.commit()
                except Exception as e:
                    logger.warning("Zone ACK timeout during state push for %s: %s", device_id, e)
                    return

                # 2. Load and send active subzones sequentially
                from ...db.repositories.subzone_repo import SubzoneRepository

                subzone_repo = SubzoneRepository(session)
                subzones = await subzone_repo.get_by_esp(device_id)
                active_subzones = [sz for sz in subzones if sz.is_active][:8]  # Max 8

                subzone_count = 0
                for sz in active_subzones:
                    sz_topic = TopicBuilder.build_subzone_assign_topic(device_id)
                    sz_payload = {
                        "subzone_id": sz.subzone_id,
                        "subzone_name": sz.subzone_name or "",
                        "parent_zone_id": "",  # Firmware sets current zone automatically
                        "assigned_gpios": [g for g in (sz.assigned_gpios or []) if g != 0],
                        # Reconnect state push restores operational state — never
                        # activate safe-mode during resync (safe-mode is only for
                        # explicit user actions). Prevents GPIO conflict where
                        # safe-mode sets actuator pins to INPUT_PULLUP.
                        "safe_mode_active": False,
                        "timestamp": now_ts,
                    }
                    try:
                        await _command_bridge.send_and_wait_ack(
                            topic=sz_topic,
                            payload=sz_payload,
                            esp_id=device_id,
                            command_type="subzone",
                            timeout=_command_bridge.DEFAULT_TIMEOUT,
                        )
                        subzone_count += 1
                    except Exception as e:
                        logger.warning(
                            "Subzone ACK timeout for %s/%s: %s",
                            device_id,
                            sz.subzone_id,
                            e,
                        )

                logger.info(
                    "Full-State-Push completed for %s: zone=%s, subzones=%d/%d",
                    device_id,
                    esp_device.zone_id,
                    subzone_count,
                    len(active_subzones),
                )

        except Exception as e:
            logger.error("Full-State-Push failed for %s: %s", device_id, e, exc_info=True)

    async def check_device_timeouts(self) -> dict:
        """
        Check for devices that haven't sent heartbeat recently.

        Marks devices as offline if last_seen > HEARTBEAT_TIMEOUT_SECONDS.

        Returns:
            {
                "checked": int,
                "timed_out": int,
                "offline_devices": [str]
            }
        """
        try:
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)

                # Get all online devices
                online_devices = await esp_repo.get_by_status("online")

                offline_devices = []
                actuator_reset_counts: dict[str, int] = {}
                # AUT-884: last-known metrics per device for the offline broadcast below.
                offline_device_metrics: dict[str, dict] = {}
                now = datetime.now(timezone.utc)
                timeout_threshold = now - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)

                for device in online_devices:
                    if device.status == "virtual":
                        continue  # Virtual devices have no heartbeat, skip timeout check
                    last_seen = device.last_seen
                    if last_seen:
                        if last_seen.tzinfo is None:
                            last_seen = last_seen.replace(tzinfo=timezone.utc)
                        if last_seen < timeout_threshold:
                            # PKG-19: If LWT already handled this device recently,
                            # skip redundant timeout escalation to avoid double
                            # actuator resets and duplicate WS broadcasts.
                            last_disc = (device.device_metadata or {}).get("last_disconnect")
                            if isinstance(last_disc, dict) and last_disc.get("source") == "lwt":
                                lwt_ts = last_disc.get("timestamp")
                                normalized_lwt_ts: Optional[float] = None
                                if isinstance(lwt_ts, (int, float)):
                                    normalized_lwt_ts = float(lwt_ts)
                                elif isinstance(lwt_ts, str) and lwt_ts.strip().isdigit():
                                    normalized_lwt_ts = float(int(lwt_ts.strip()))
                                if normalized_lwt_ts is not None and normalized_lwt_ts > 0:
                                    lwt_age = now.timestamp() - normalized_lwt_ts
                                    if lwt_age < HEARTBEAT_TIMEOUT_SECONDS:
                                        logger.info(
                                            "Skipping heartbeat timeout for %s — "
                                            "LWT already processed %.0fs ago",
                                            device.device_id,
                                            lwt_age,
                                        )
                                        continue

                            await esp_repo.update_status(device.device_id, "offline")
                            offline_devices.append(device.device_id)
                            offline_device_metrics[device.device_id] = (
                                extract_last_known_health_metrics(device.device_metadata)
                            )

                            # Reset actuator states to idle for offline device
                            try:
                                actuator_repo = ActuatorRepository(session)
                                # Capture active actuators BEFORE reset for history logging (Fix L3)
                                active_actuators = (
                                    await actuator_repo.get_active_actuators_for_device(device.id)
                                )
                                reset_count = await actuator_repo.reset_states_for_device(
                                    esp_id=device.id,
                                    new_state="off",
                                    reason="heartbeat_timeout",
                                )
                                if reset_count > 0:
                                    actuator_reset_counts[device.device_id] = reset_count
                                    logger.info(
                                        f"[Heartbeat] Reset {reset_count} actuator state(s) to off "
                                        f"for offline device {device.device_id}"
                                    )
                                # Log history entry for each actuator that was reset (Fix L3)
                                now = datetime.now(timezone.utc)
                                for actuator_state in active_actuators:
                                    await actuator_repo.log_command(
                                        esp_id=device.id,
                                        gpio=actuator_state.gpio,
                                        actuator_type=actuator_state.actuator_type,
                                        command_type="OFF",
                                        value=0.0,
                                        success=True,
                                        issued_by="system:heartbeat_timeout",
                                        error_message=(
                                            f"Auto-reset: Heartbeat timeout "
                                            f"({HEARTBEAT_TIMEOUT_SECONDS}s). "
                                            f"Previous state: {actuator_state.state}"
                                        ),
                                        timestamp=now,
                                        metadata={
                                            "trigger": "heartbeat_timeout",
                                            "previous_state": actuator_state.state,
                                            "previous_value": actuator_state.current_value,
                                        },
                                    )
                                    logger.info(
                                        "Actuator history logged",
                                        extra={
                                            "esp_id": str(device.id),
                                            "gpio": actuator_state.gpio,
                                            "command_type": "OFF",
                                            "issued_by": "system:heartbeat_timeout",
                                            "trigger": "heartbeat_timeout",
                                        },
                                    )
                            except Exception as reset_err:
                                logger.warning(
                                    f"[Heartbeat] Failed to reset actuator states for "
                                    f"{device.device_id}: {reset_err}"
                                )

                            logger.warning(
                                f"Device {device.device_id} timed out. "
                                f"Last seen: {device.last_seen}"
                            )

                            # Audit Logging: device_offline (heartbeat timeout)
                            try:
                                audit_repo = AuditLogRepository(session)
                                await audit_repo.log_device_event(
                                    esp_id=device.device_id,
                                    event_type=AuditEventType.DEVICE_OFFLINE,
                                    status="success",
                                    message=f"Device timed out - no heartbeat for {HEARTBEAT_TIMEOUT_SECONDS}s",
                                    details={
                                        "last_seen": (
                                            device.last_seen.isoformat()
                                            if device.last_seen
                                            else None
                                        ),
                                        "timeout_threshold_seconds": HEARTBEAT_TIMEOUT_SECONDS,
                                        "reason": "heartbeat_timeout",
                                    },
                                    severity=AuditSeverity.WARNING,
                                )
                            except Exception as audit_error:
                                logger.warning(f"Failed to audit log device_offline: {audit_error}")

                # Commit transaction
                await session.commit()

                # Broadcast esp_health offline events via WebSocket
                if offline_devices:
                    try:
                        from ...websocket.manager import WebSocketManager

                        ws_manager = await WebSocketManager.get_instance()
                        for device_id in offline_devices:
                            broadcast_payload = serialize_esp_health_event(
                                esp_id=device_id,
                                status="offline",
                                timestamp=int(now.timestamp()),
                                reason="heartbeat_timeout",
                                source="heartbeat_timeout",
                                timeout_seconds=HEARTBEAT_TIMEOUT_SECONDS,
                                actuator_states_reset=actuator_reset_counts.get(device_id, 0),
                                **offline_device_metrics.get(device_id, {}),
                            )
                            await ws_manager.broadcast(
                                "esp_health",
                                broadcast_payload,
                            )
                            logger.info(f"📡 Broadcast esp_health offline event for {device_id}")
                    except Exception as e:
                        logger.warning(f"Failed to broadcast ESP offline events: {e}")

                return {
                    "checked": len(online_devices),
                    "timed_out": len(offline_devices),
                    "offline_devices": offline_devices,
                }

        except Exception as e:
            logger.error(f"Error checking device timeouts: {e}", exc_info=True)
            return {
                "checked": 0,
                "timed_out": 0,
                "offline_devices": [],
            }


# Global handler instance
_handler_instance: Optional[HeartbeatHandler] = None


def get_heartbeat_handler() -> HeartbeatHandler:
    """
    Get singleton heartbeat handler instance.

    Returns:
        HeartbeatHandler instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = HeartbeatHandler()
    return _handler_instance


async def handle_heartbeat(topic: str, payload: dict) -> bool:
    """
    Handle heartbeat message (convenience function).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if message processed successfully
    """
    handler = get_heartbeat_handler()
    return await handler.handle_heartbeat(topic, payload)
