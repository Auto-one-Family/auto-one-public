"""
God-Kaiser Server - Application Entry Point

FastAPI application with MQTT lifecycle management.

Features:
- MQTT client connection on startup
- Topic subscription and handler registration
- Database initialization
- Graceful shutdown
- Complete REST API with JWT authentication

Phase: 5 (Week 9-10) - API Layer
Status: IMPLEMENTED
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import sensor_processing
from .api.v1 import api_v1_router
from .api.v1.websocket import realtime as websocket_realtime
from .core.config import get_settings
from .core import constants
from .core.exception_handlers import (
    automation_one_exception_handler,
    general_exception_handler,
)
from .core.exceptions import GodKaiserException
from .core.logging_config import get_logger, setup_logging
from .core.resilience import ResilienceRegistry, get_health_status
from .core.task_registry import cancel_all_background_tasks
from .db.repositories import ActuatorRepository, LogicRepository
from .db.session import dispose_engine, get_engine, get_session, init_db, init_db_circuit_breaker
from .mqtt.client import MQTTClient
from .mqtt.topics import TopicBuilder
from .mqtt.handlers import (
    actuator_handler,
    actuator_latched_offline_handler,
    actuator_response_handler,
    actuator_alert_handler,
    calibration_response_handler,
    config_handler,
    diagnostics_handler,
    emergency_ack_handler,
    error_handler,
    heartbeat_handler,
    heartbeat_metrics_handler,
    intent_outcome_handler,
    intent_outcome_lifecycle_handler,
    lwt_handler,
    queue_pressure_handler,
    recovery_confirm_handler,
    sensor_batch_handler,  # AUT-715: offline spool replay
    sensor_handler,
    subzone_ack_handler,
    zone_ack_handler,
)
from .mqtt.publisher import Publisher
from .mqtt.subscriber import Subscriber
from .services.actuator_service import ActuatorService
from .services.logic.actions import (
    ActuatorActionExecutor,
    DelayActionExecutor,
    NotificationActionExecutor,
    SequenceActionExecutor,
)
from .services.logic.conditions import (
    CompoundConditionEvaluator,
    HysteresisConditionEvaluator,
    NotRunningConditionEvaluator,
    SensorConditionEvaluator,
    TimeConditionEvaluator,
)
from .services.logic_engine import LogicEngine
from .services.logic_scheduler import LogicScheduler
from .services.runtime_state_service import RuntimeMode, get_runtime_state_service
from .services.inbound_inbox_service import get_inbound_inbox_service
from .services.safety_service import SafetyService
from .websocket.manager import WebSocketManager

# Initialize logging BEFORE any logger usage
setup_logging()

logger = get_logger(__name__)
settings = get_settings()

# Global instances (for cleanup)
_subscriber_instance: Subscriber = None
_logic_engine: LogicEngine = None
_logic_scheduler: LogicScheduler = None
_websocket_manager: WebSocketManager = None
_sequence_executor: SequenceActionExecutor = None
_mqtt_command_bridge = None  # MQTTCommandBridge instance
_inbound_replay_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Handles startup and shutdown events:
    - Startup: Initialize database, connect MQTT, subscribe to topics
    - Shutdown: Disconnect MQTT, dispose database engine
    """
    logger.info("=" * 60)
    logger.info("God-Kaiser Server Starting...")
    logger.info("=" * 60)

    global _inbound_replay_task

    # ===== STARTUP =====
    try:
        runtime_state = get_runtime_state_service()
        await runtime_state.transition(RuntimeMode.WARMING_UP, "lifespan startup begin")

        # Step 0: Security Validation
        logger.info("Validating security configuration...")

        # Check JWT secret key
        if settings.security.jwt_secret_key == "change-this-secret-key-in-production":
            if settings.environment == "production":
                logger.critical(
                    "SECURITY CRITICAL: Using default JWT secret key in production! "
                    "This is a severe security risk. Set JWT_SECRET_KEY environment variable."
                )
                raise SystemExit(
                    "Cannot start server: Default JWT secret key detected in production. "
                    "Set JWT_SECRET_KEY environment variable to a secure random value."
                )
            else:
                logger.warning(
                    "SECURITY: Using default JWT secret key (OK for development only). "
                    "Change JWT_SECRET_KEY in production!"
                )

        # Check MQTT TLS if auth is enabled
        # Note: We can't check if auth is enabled yet (DB not initialized), but we can warn
        if not settings.mqtt.use_tls:
            logger.warning(
                "MQTT TLS is disabled. MQTT authentication credentials will be sent in plain text. "
                "Enable MQTT_USE_TLS for secure credential distribution."
            )

        # AUT-443: Validate Google Sheets export auth configuration (no-op when disabled).
        try:
            from .integrations.sheets import SheetsAuthError, validate_credentials_config

            sheets_metadata = validate_credentials_config(settings.sheets_export)
            if sheets_metadata:
                logger.info(
                    "Sheets export auth ready (project_id=%s, client_email=%s, "
                    "spreadsheet_configured=%s)",
                    sheets_metadata["project_id"],
                    sheets_metadata["client_email"],
                    sheets_metadata["spreadsheet_id_configured"],
                )
        except SheetsAuthError as exc:
            logger.critical(
                "Sheets export configuration invalid: %s (numeric_code=%s)",
                exc.message,
                exc.numeric_code,
            )
            raise SystemExit(
                "Cannot start server: Sheets export is enabled but configuration is "
                f"invalid. {exc.message}"
            ) from exc

        logger.info("Security validation complete")

        # Step 0.5: Initialize Resilience Patterns
        logger.info("Initializing resilience patterns...")

        # Initialize registry (singleton)
        resilience_registry = ResilienceRegistry.get_instance()

        # Database circuit breaker will be initialized in init_db_circuit_breaker()
        # MQTT circuit breaker is initialized in MQTTClient.__init__()

        # Initialize external API circuit breaker (optional)
        from .core.resilience import CircuitBreaker

        external_api_breaker = CircuitBreaker(
            name="external_api",
            failure_threshold=settings.resilience.circuit_breaker_api_failure_threshold,
            recovery_timeout=float(settings.resilience.circuit_breaker_api_recovery_timeout),
            half_open_timeout=float(settings.resilience.circuit_breaker_api_half_open_timeout),
        )
        resilience_registry.register_circuit_breaker("external_api", external_api_breaker)

        logger.info(
            f"[resilience] Resilience patterns initialized: "
            f"registry ready, external_api breaker registered"
        )

        # Step 1: Initialize database
        if settings.database.auto_init:
            logger.info("Initializing database...")
            await init_db()
            logger.info("Database initialized successfully")
        else:
            logger.info("Skipping database init (auto_init=False)")
            # Ensure engine is created even if not auto-initializing
            get_engine()

        # Reset persisted emergency_stop in actuator_states so dashboard does not
        # show stale Not-Aus after server restart (SafetyService state is in-memory only)
        try:
            from .db.session import get_session_maker

            session_maker = get_session_maker()
            async with session_maker() as session:
                actuator_repo = ActuatorRepository(session)
                n = await actuator_repo.clear_all_emergency_states_on_startup()
                if n:
                    await session.commit()
                    logger.info(
                        "Startup: cleared %d actuator_states from emergency_stop to idle", n
                    )
        except Exception as e:
            logger.warning("Startup clear emergency_states failed (non-fatal): %s", e)

        # Initialize database circuit breaker after DB is ready
        init_db_circuit_breaker()
        logger.info("[resilience] Database circuit breaker initialized")

        # Step 2: Connect to MQTT broker
        logger.info("Connecting to MQTT broker...")
        mqtt_client = MQTTClient.get_instance()
        connected = mqtt_client.connect()

        if not connected:
            logger.warning(
                "Failed to connect to MQTT broker during startup. "
                "Server will start anyway - auto-reconnect will attempt to restore connection."
            )
        else:
            logger.info("MQTT client connected successfully")
        await runtime_state.set_degraded_reason("mqtt_disconnected", not connected)

        # Step 2b: Clear stale retained emergency-stop message from broker.
        # Emergency-Stop is a one-shot command, not persistent state.
        # A retained message would replay on every reconnect/restart,
        # causing spurious CRITICAL logs and alert noise.
        if connected:
            try:
                mqtt_client.publish(
                    "kaiser/broadcast/emergency",
                    "",  # Empty payload clears retained message
                    qos=0,
                    retain=True,
                )
                logger.info("Cleared retained emergency-stop message from broker")
            except Exception as e:
                logger.debug("Failed to clear retained emergency message: %s", e)

        # Step 3: Register MQTT handlers (ALWAYS, even if not connected)
        # Handlers will be called when auto-reconnect succeeds
        logger.info("Registering MQTT handlers...")
        global _subscriber_instance
        _subscriber_instance = Subscriber(
            mqtt_client,
            max_workers=settings.mqtt.subscriber_max_workers,
        )
        await runtime_state.set_worker_health("mqtt_subscriber", True)

        # BUG O FIX (2026-01-05): Explicitly set main event loop for async handlers
        # This ensures SQLAlchemy AsyncEngine operations run in the correct event loop,
        # preventing "Queue bound to different event loop" errors in Python 3.12+.
        _subscriber_instance.set_main_loop(asyncio.get_running_loop())
        logger.info("Main event loop set for MQTT subscriber")

        # Register subscriber in MQTT client for auto re-subscription on reconnect
        mqtt_client.set_subscriber(_subscriber_instance)

        # Get KAISER_ID from config (default: "god")
        kaiser_id = settings.hierarchy.kaiser_id
        logger.info(f"Using KAISER_ID: {kaiser_id}")

        # WP6: Register handlers with wildcard kaiser_id (+) for multi-Kaiser support
        # Topic parsers already accept any kaiser_id via regex, subscriptions now match
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/sensor/+/data", sensor_handler.handle_sensor_data
        )
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/actuator/+/status", actuator_handler.handle_actuator_status
        )
        # Phase 8: Actuator Response Handler (command confirmations)
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/actuator/+/response", actuator_response_handler.handle_actuator_response
        )
        # Phase 8: Actuator Alert Handler (emergency/timeout alerts)
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/actuator/+/alert", actuator_alert_handler.handle_actuator_alert
        )
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/system/heartbeat", heartbeat_handler.handle_heartbeat
        )
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/session/announce",
            heartbeat_handler.get_heartbeat_handler().handle_session_announce,
        )
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/config_response", config_handler.handle_config_ack
        )
        # Phase 7: Zone ACK Handler (zone assignment confirmations)
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/zone/ack", zone_ack_handler.handle_zone_ack
        )
        # Phase 9: Subzone ACK Handler (subzone assignment confirmations)
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/subzone/ack", subzone_ack_handler.handle_subzone_ack
        )
        # LWT Handler (Instant Offline Detection)
        # Topic: kaiser/+/esp/+/system/will (WP6: wildcard kaiser_id)
        # ESP32 builds LWT topic from heartbeat: /system/heartbeat -> /system/will
        # QoS: 1 (broker publishes LWT with QoS from ESP32 config)
        # This provides INSTANT offline detection when ESP32 disconnects unexpectedly
        _subscriber_instance.register_handler("kaiser/+/esp/+/system/will", lwt_handler.handle_lwt)
        logger.info("LWT handler registered: kaiser/+/esp/+/system/will")
        # Error Event Handler (DS18B20/OneWire errors, GPIO conflicts, etc.)
        # Topic: kaiser/+/esp/+/system/error (WP6: wildcard kaiser_id)
        # ESP32 publishes hardware/config errors to this topic for server processing
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/system/error", error_handler.handle_error_event
        )
        logger.info("Error handler registered: kaiser/+/esp/+/system/error")
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/system/intent_outcome",
            intent_outcome_handler.handle_intent_outcome,
        )
        logger.info("Intent outcome handler registered: kaiser/+/esp/+/system/intent_outcome")
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/system/intent_outcome/lifecycle",
            intent_outcome_lifecycle_handler.handle_intent_outcome_lifecycle,
        )
        logger.info(
            "Intent outcome lifecycle handler registered: kaiser/+/esp/+/system/intent_outcome/lifecycle"
        )
        # System Diagnostics Handler (HealthMonitor snapshots)
        # Topic: kaiser/+/esp/+/system/diagnostics (WP6: wildcard kaiser_id)
        # ESP32 HealthMonitor publishes diagnostics every 60s (heap, RSSI, uptime, state)
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/system/diagnostics", diagnostics_handler.handle_diagnostics
        )
        logger.info("Diagnostics handler registered: kaiser/+/esp/+/system/diagnostics")
        # PKG-01b: Queue-Pressure Handler (pure observability, no DB/WS side effects)
        # Topic: kaiser/+/esp/+/system/queue_pressure
        # ESP32 publishes lifecycle events (entered_pressure / recovered) for the
        # outbound publish queue; server increments a Prometheus counter and logs.
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/system/queue_pressure",
            queue_pressure_handler.handle_queue_pressure,
        )
        logger.info("Queue pressure handler registered: kaiser/+/esp/+/system/queue_pressure")
        # AUT-118: Emergency application ACK + recovery_confirm (ESP → Server, QoS 1)
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/actuator/emergency/ack",
            emergency_ack_handler.handle_emergency_ack,
        )
        logger.info("Emergency ACK handler registered: kaiser/+/esp/+/actuator/emergency/ack")
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/actuator/recovery_confirm",
            recovery_confirm_handler.handle_recovery_confirm,
        )
        logger.info("Recovery confirm handler registered: kaiser/+/esp/+/actuator/recovery_confirm")
        # AUT-117: Actuator latched-offline telemetry (ESP → Server, QoS 0)
        # Pure observability: log + WS broadcast, no DB writes.
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/actuator/+/latched_offline",
            actuator_latched_offline_handler.handle_actuator_latched_offline,
        )
        logger.info(
            "Actuator latched-offline handler registered: "
            "kaiser/+/esp/+/actuator/+/latched_offline"
        )
        # AUT-121: Heartbeat Metrics Handler (pure ingest, no DB/WS)
        _subscriber_instance.register_handler(
            constants.get_topic_with_kaiser_id(constants.MQTT_SUBSCRIBE_ESP_HEARTBEAT_METRICS),
            heartbeat_metrics_handler.handle_heartbeat_metrics,
        )
        logger.info("Heartbeat metrics handler registered: kaiser/+/esp/+/system/heartbeat_metrics")
        # S-P5: Calibration Sensor Response Handler
        # Processes sensor command responses during active calibration sessions
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/sensor/+/response",
            calibration_response_handler.handle_sensor_response,
        )
        logger.info("Calibration response handler registered: kaiser/+/esp/+/sensor/+/response")
        # AUT-715: Sensor batch replay (offline spool flush from ESP32 SpoolManager)
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/sensor/batch",
            sensor_batch_handler.handle_sensor_batch,
        )
        logger.info("Batch handler registered: kaiser/+/esp/+/sensor/batch")

        logger.info(f"Registered {len(_subscriber_instance.handlers)} MQTT handlers")

        # Step 3.1: MQTTCommandBridge (ACK-gesteuert fuer Zone/Subzone-Operationen)
        from .services.mqtt_command_bridge import MQTTCommandBridge
        from .mqtt.handlers.zone_ack_handler import set_command_bridge as set_zone_bridge
        from .mqtt.handlers.subzone_ack_handler import set_command_bridge as set_subzone_bridge
        from .mqtt.handlers.heartbeat_handler import set_command_bridge as set_heartbeat_bridge

        global _mqtt_command_bridge
        _mqtt_command_bridge = MQTTCommandBridge(mqtt_client)
        set_zone_bridge(_mqtt_command_bridge)
        set_subzone_bridge(_mqtt_command_bridge)
        set_heartbeat_bridge(_mqtt_command_bridge)
        logger.info("MQTTCommandBridge registered with ACK handlers + heartbeat reconnect")

        # Step 3.4: Initialize Central Scheduler
        logger.info("Initializing Central Scheduler...")
        from .core.scheduler import init_central_scheduler

        _central_scheduler = init_central_scheduler()
        logger.info("Central Scheduler started")

        # Step 3.4.1: Initialize SimulationScheduler
        logger.info("Initializing SimulationScheduler...")
        from .services.simulation import init_simulation_scheduler
        import json

        def mqtt_publish_for_simulation(topic: str, payload: dict, qos: int = 1):
            if mqtt_client and mqtt_client.is_connected():
                mqtt_client.publish(topic, json.dumps(payload), qos=qos)

        _simulation_scheduler = init_simulation_scheduler(mqtt_publish_for_simulation)
        logger.info("SimulationScheduler initialized")

        # Paket G: Register handler for Mock-ESP actuator commands
        # This allows Mock-ESPs to receive commands sent by the server
        async def mock_actuator_command_handler(topic: str, payload: dict) -> bool | None:
            """Route actuator commands to Mock-ESP handler if target is an active mock.

            Returns True if handled by a mock, None if not applicable (real ESP or
            no active mock). None avoids a spurious subscriber warning for real ESPs.
            False is reserved for actual handler errors.
            """
            try:
                from .services.simulation import get_simulation_scheduler

                sim_scheduler = get_simulation_scheduler()
                # Convert payload back to JSON string for handler
                payload_str = json.dumps(payload)
                result = await sim_scheduler.handle_mqtt_message(topic, payload_str)
                return result if result else None  # None = not applicable, False = error
            except RuntimeError:
                # SimulationScheduler not initialized — not an error for real ESPs
                return None
            except Exception as e:
                logger.debug(f"Mock actuator command handler error: {e}")
                return None

        # WP6: Wildcard kaiser_id for Mock-ESP handlers
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/actuator/+/command", mock_actuator_command_handler
        )
        # Also handle emergency topics for mocks
        _subscriber_instance.register_handler(
            "kaiser/+/esp/+/actuator/emergency", mock_actuator_command_handler
        )
        # Broadcast pattern remains fixed (not kaiser-specific)
        _subscriber_instance.register_handler(
            "kaiser/broadcast/emergency", mock_actuator_command_handler
        )
        logger.info("Registered Mock-ESP actuator command handlers (Paket G)")

        # Step 3.4.2: Initialize MaintenanceService
        logger.info("Initializing MaintenanceService...")
        from .services.maintenance import init_maintenance_service

        _maintenance_service = init_maintenance_service(
            scheduler=_central_scheduler,
            session_factory=get_session,
            mqtt_client=mqtt_client,
            settings=settings,
        )
        _maintenance_service.start()  # Registriert alle Jobs
        logger.info("MaintenanceService initialized and started")

        # Step 3.4.2b: Initialize SheetsExportService (AUT-442 — gated by feature flag)
        # The service is constructed unconditionally so the dependency-injection
        # singleton is available, but ``start()`` only registers the scheduler
        # job when SHEETS_EXPORT_ENABLED=true AND SHEETS_SPREADSHEET_ID is set.
        try:
            from .services.sheets_export import init_sheets_export_service

            sheets_export_service = init_sheets_export_service(
                scheduler=_central_scheduler,
                session_factory=get_session,
                settings=settings.sheets_export,
            )
            registered = sheets_export_service.start()
            if registered:
                logger.info(
                    "SheetsExportService started — interval=%d min",
                    settings.sheets_export.export_interval_minutes,
                )
            else:
                logger.info(
                    "SheetsExportService initialised but inactive "
                    "(enabled=%s, spreadsheet_configured=%s)",
                    settings.sheets_export.enabled,
                    bool(settings.sheets_export.spreadsheet_id),
                )
        except Exception as exc:
            # Non-fatal: server must still come up if Sheets pipeline misconfigured.
            logger.warning(
                "SheetsExportService init failed (non-critical): %s",
                exc,
                exc_info=True,
            )

        # Step 3.4.3: Register Prometheus metrics update job
        # Updates custom Gauges (uptime, CPU, memory, MQTT, ESP counts) every 15s.
        # Gauges are in the default prometheus_client registry and automatically
        # exposed by the Instrumentator at /api/v1/health/metrics.
        logger.info("Registering Prometheus metrics update job...")
        from .core.metrics import init_metrics, set_server_start_time, update_all_metrics_async

        set_server_start_time(time.time())
        init_metrics()

        async def _metrics_update_job() -> None:
            await update_all_metrics_async(get_session)

        from .core.scheduler import JobCategory

        _central_scheduler.add_interval_job(
            job_id="monitor_prometheus_metrics",
            func=_metrics_update_job,
            seconds=15,
            category=JobCategory.MONITOR,
        )
        logger.info("Prometheus metrics job registered (15s interval)")

        # Step 3.4.4: Register Digest Service job (Phase 4A.1)
        # Batches warning notifications into periodic digest emails (ISA-18.2).
        # Default: every 60 minutes, sends digest when >= 3 pending warnings.
        logger.info("Registering Digest Service job...")
        from .services.digest_service import get_digest_service

        _digest_service = get_digest_service()

        async def _digest_job() -> None:
            await _digest_service.process_digests()

        _central_scheduler.add_interval_job(
            job_id="maintenance_digest_emails",
            func=_digest_job,
            seconds=3600,  # 60 minutes
            category=JobCategory.MAINTENANCE,
        )
        logger.info("Digest Service job registered (60min interval)")

        # Step 3.4.4b: Register Email Retry job (Phase C V1.2)
        # Retries failed emails (critical alerts, test) every 5 minutes.
        # Max 3 attempts total; then status=permanently_failed.
        logger.info("Registering Email Retry job...")
        from .services.email_retry_service import get_email_retry_service

        _email_retry_service = get_email_retry_service()

        async def _email_retry_job() -> None:
            await _email_retry_service.process_retries(limit=50)

        _central_scheduler.add_interval_job(
            job_id="maintenance_email_retry",
            func=_email_retry_job,
            seconds=300,  # 5 minutes
            category=JobCategory.MAINTENANCE,
        )
        logger.info("Email Retry job registered (5min interval)")

        # Step 3.4.5: Register Alert Suppression tasks (Phase 4A.7)
        # - Suppression expiry check: every 5 min (re-enables expired suppressions)
        # - Maintenance overdue check: daily at 08:00 (sends info notifications)
        logger.info("Registering Alert Suppression scheduler tasks...")
        try:
            from .services.alert_suppression_scheduler import register_suppression_tasks

            register_suppression_tasks(_central_scheduler)
            logger.info("Alert Suppression scheduler tasks registered")
        except Exception as e:
            logger.warning(f"Alert Suppression scheduler registration failed (non-critical): {e}")

        # Step 3.4.6: Initialize DatabaseBackupService (Phase A V5.1)
        # Backup runs at 02:00 — BEFORE cleanup at 03:00 (data safety guarantee)
        logger.info("Initializing DatabaseBackupService...")
        from .services.database_backup_service import init_database_backup_service

        _database_backup_service = init_database_backup_service(settings.backup)

        if settings.backup.enabled:

            async def _backup_job() -> None:
                try:
                    await _database_backup_service.create_backup()
                    await _database_backup_service.cleanup_old_backups()
                except Exception as e:
                    logger.error(f"Scheduled database backup failed: {e}", exc_info=True)

            _central_scheduler.add_cron_job(
                job_id="database_backup",
                func=_backup_job,
                cron_expression={
                    "hour": settings.backup.hour,
                    "minute": settings.backup.minute,
                },
                category=JobCategory.MAINTENANCE,
            )
            logger.info(
                f"Database backup job registered "
                f"(daily {settings.backup.hour:02d}:{settings.backup.minute:02d}, "
                f"retain {settings.backup.max_age_days}d, max {settings.backup.max_count})"
            )
        else:
            logger.info("Database backup job DISABLED (DB_BACKUP_ENABLED=False)")

        # Step 3.5: Recover running Mock-ESP simulations from database (Paket X)
        # After server restart, resume any simulations that were active before shutdown
        # Uses SimulationScheduler.recover_mocks() for DB-First architecture
        try:
            async for session in get_session():
                recovered_count = await _simulation_scheduler.recover_mocks(session)
                if recovered_count > 0:
                    logger.info(
                        f"Mock-ESP recovery complete: {recovered_count} simulations restored"
                    )
                else:
                    logger.info("No active Mock-ESP simulations to recover")

                # Cleanup orphaned runtimes (devices deleted from DB while server was down)
                orphaned = await _simulation_scheduler.cleanup_orphaned_runtimes(session)
                if orphaned > 0:
                    logger.info(f"Cleaned up {orphaned} orphaned mock runtimes")

                # Step 3.5.1: Rebuild simulation_configs from sensor_configs DB
                # Ensures cfg_{id} key format and consistency after restart (Fix B)
                from .db.repositories import ESPRepository, SensorRepository

                esp_repo = ESPRepository(session)
                sensor_repo = SensorRepository(session)
                mock_devices = await esp_repo.get_mock_devices()
                rebuilt = 0
                for mock_dev in mock_devices:
                    try:
                        sensor_cfgs = await sensor_repo.get_by_esp(mock_dev.id)
                        if sensor_cfgs:
                            await esp_repo.rebuild_simulation_config(mock_dev, sensor_cfgs)
                            rebuilt += 1
                    except Exception as rebuild_err:
                        logger.warning(
                            f"Failed to rebuild simulation_config for {mock_dev.device_id}: {rebuild_err}"
                        )
                if rebuilt > 0:
                    await session.commit()
                    logger.info(f"Rebuilt simulation_configs for {rebuilt} mock devices")

                break  # Exit after first session
        except Exception as e:
            logger.warning(f"Mock-ESP recovery failed (non-critical): {e}")

        # Step 3.5b: God-Kaiser Init (Phase 1)
        logger.info("Ensuring god-Kaiser exists...")
        try:
            from .services.kaiser_service import KaiserService

            async for session in get_session():
                kaiser_svc = KaiserService(session)
                await kaiser_svc.ensure_god_kaiser()
                orphan_count = await kaiser_svc.set_default_kaiser_for_orphans()
                zone_count = await kaiser_svc.sync_god_kaiser_zones()
                await session.commit()
                logger.info(
                    f"God-Kaiser init: {orphan_count} orphan ESPs assigned, "
                    f"{zone_count} zones synced"
                )
                break
        except Exception as e:
            logger.warning(f"God-Kaiser init failed (non-critical): {e}")

        # Step 3.6: Sensor Type Auto-Registration (Phase 2A)
        # Ensures all loaded sensor libraries have entries in sensor_type_defaults.
        # New libraries get defaults based on their RECOMMENDED_* class attributes.
        # Runs on every startup - idempotent (skips existing entries).
        logger.info("Running sensor type auto-registration...")
        try:
            from .services.sensor_type_registration import auto_register_sensor_types

            async for session in get_session():
                reg_results = await auto_register_sensor_types(session)
                logger.info(
                    f"Sensor type auto-registration: "
                    f"{reg_results['newly_registered']} new, "
                    f"{reg_results['already_registered']} existing, "
                    f"{reg_results['failed']} failed"
                )
                break  # Exit after first session
        except Exception as e:
            # Non-fatal: System can work with system-defaults fallback
            logger.warning(f"Sensor type auto-registration failed (non-critical): {e}")

        # Step 3.7: Recover Scheduled Sensor Jobs (Phase 2H)
        # Recreates APScheduler jobs for sensors with operating_mode='scheduled'.
        # Jobs are stored in sensor.schedule_config (cron expressions).
        # Missed jobs during server downtime are NOT caught up (only future runs).
        logger.info("Recovering scheduled sensor jobs...")
        try:
            from .db.repositories.esp_repo import ESPRepository
            from .db.repositories.sensor_repo import SensorRepository
            from .services.sensor_scheduler_service import SensorSchedulerService

            async for session in get_session():
                sensor_repo = SensorRepository(session)
                esp_repo = ESPRepository(session)
                publisher = Publisher()

                sensor_scheduler_service = SensorSchedulerService(
                    sensor_repo=sensor_repo,
                    esp_repo=esp_repo,
                    publisher=publisher,
                )

                recovered_count = await sensor_scheduler_service.recover_all_jobs(session)
                logger.info(f"Sensor schedule recovery complete: {recovered_count} jobs")
                break  # Exit after first session
        except Exception as e:
            # Non-fatal: Scheduled sensors won't auto-trigger, but manual trigger still works
            logger.warning(f"Sensor schedule recovery failed (non-critical): {e}")

        # Step 4: Subscribe to all topics (only if connected)
        if connected:
            logger.info("Subscribing to MQTT topics...")
            _subscriber_instance.subscribe_all()
            logger.info("MQTT subscriptions complete")
        else:
            logger.info(
                "Skipping initial subscription (not connected) - will subscribe on reconnect"
            )

        # Step 5: Initialize WebSocket Manager
        logger.info("Initializing WebSocket Manager...")
        global _websocket_manager
        _websocket_manager = await WebSocketManager.get_instance()
        await _websocket_manager.initialize()
        logger.info("WebSocket Manager initialized")
        await runtime_state.set_worker_health("websocket_manager", True)

        # Step 6: Initialize Safety Service, Actuator Service, and Logic Engine
        logger.info("Initializing services...")
        async for session in get_session():
            # Initialize repositories
            actuator_repo = ActuatorRepository(session)
            esp_repo = ESPRepository(session)
            logic_repo = LogicRepository(session)

            # Initialize Safety Service
            safety_service = SafetyService(actuator_repo, esp_repo)

            # Initialize Publisher
            publisher = Publisher()

            # Initialize Actuator Service
            actuator_service = ActuatorService(actuator_repo, safety_service, publisher)

            # Initialize Logic Engine with modular evaluators and executors
            global _logic_engine, _logic_scheduler

            # Setup action executors first — SequenceActionExecutor must exist before
            # NotRunningConditionEvaluator (AUT-1245/AUT-1333) so interlocks observe
            # the same in-memory running-sequence set used by sequence actions.
            actuator_executor = ActuatorActionExecutor(actuator_service)
            delay_executor = DelayActionExecutor()
            notification_executor = NotificationActionExecutor()

            global _sequence_executor
            _sequence_executor = SequenceActionExecutor(websocket_manager=_websocket_manager)

            # Phase 4C: Plugin Action Executor (session_factory pattern — fresh session per execution)
            from .services.logic.actions.plugin_executor import PluginActionExecutor

            plugin_executor = PluginActionExecutor(session_factory=get_session)

            # Phase 4D: Diagnostics Action Executor
            from .services.logic.actions.diagnostics_executor import (
                DiagnosticsActionExecutor,
            )

            diagnostics_executor = DiagnosticsActionExecutor(
                session_factory=get_session,
            )

            action_executors = [
                actuator_executor,
                delay_executor,
                notification_executor,
                _sequence_executor,
                plugin_executor,
                diagnostics_executor,
            ]

            # Setup condition evaluators (must include not_running — AUT-1333).
            # Previously main.py omitted NotRunningConditionEvaluator while LogicEngine's
            # default list had it; custom list → unknown type → legacy fail → Frischwasser /
            # PH MINUS permanently blocked.
            sensor_evaluator = SensorConditionEvaluator()
            time_evaluator = TimeConditionEvaluator()
            hysteresis_evaluator = HysteresisConditionEvaluator(
                session_factory=get_session,
            )
            await hysteresis_evaluator.load_states_from_db()

            from .services.logic.conditions.diagnostics_evaluator import (
                DiagnosticsConditionEvaluator,
            )

            diagnostics_condition_evaluator = DiagnosticsConditionEvaluator(
                session_factory=get_session,
            )
            not_running_evaluator = NotRunningConditionEvaluator(
                sequence_executor=_sequence_executor,
                session_factory=get_session,
            )

            compound_evaluator = CompoundConditionEvaluator(
                [
                    sensor_evaluator,
                    time_evaluator,
                    hysteresis_evaluator,
                    diagnostics_condition_evaluator,
                    not_running_evaluator,
                ]
            )
            condition_evaluators = [
                sensor_evaluator,
                time_evaluator,
                hysteresis_evaluator,
                diagnostics_condition_evaluator,
                not_running_evaluator,
                compound_evaluator,
            ]

            # KRITISCH: Circular-Dependency auflösen
            # SequenceExecutor braucht Zugriff auf andere Executors für Sub-Actions
            _sequence_executor.set_action_executors(action_executors)

            # Setup safety components
            from .services.logic.safety.conflict_manager import ConflictManager
            from .services.logic.safety.rate_limiter import RateLimiter

            conflict_manager = ConflictManager(websocket_manager=_websocket_manager)
            rate_limiter = RateLimiter(logic_repo=logic_repo)

            # Initialize Logic Engine
            _logic_engine = LogicEngine(
                logic_repo=logic_repo,
                actuator_service=actuator_service,
                websocket_manager=_websocket_manager,
                condition_evaluators=condition_evaluators,
                action_executors=action_executors,
                conflict_manager=conflict_manager,
                rate_limiter=rate_limiter,
            )
            await _logic_engine.start()
            await runtime_state.set_logic_liveness(True)

            # Initialize Logic Scheduler
            # AUT-115: pass websocket_manager so the scheduler can broadcast
            # rule.health snapshots for is_critical rules every interval.
            _logic_scheduler = LogicScheduler(
                _logic_engine,
                interval_seconds=settings.performance.logic_scheduler_interval_seconds,
                websocket_manager=_websocket_manager,
            )
            await _logic_scheduler.start()

            # Set global instance for handlers
            from .services.logic_engine import set_logic_engine

            set_logic_engine(_logic_engine)

            logger.info("Services initialized successfully")
            break  # Exit after first session

        # Step 6.0: Replay critical inbound inbox until stable (P0.3)
        await runtime_state.set_recovery_completed(False)
        await runtime_state.transition(RuntimeMode.RECOVERY_SYNC, "inbound replay bootstrap")
        inbox_service = get_inbound_inbox_service()
        replay_summary = await _subscriber_instance.replay_pending_events(limit=500)
        inbox_stats = await inbox_service.stats()
        logger.info(
            "Inbound replay bootstrap: replayed=%s failed=%s pending=%s",
            replay_summary.get("replayed", 0),
            replay_summary.get("failed", 0),
            inbox_stats.get("pending", 0),
        )

        async def _inbound_replay_worker() -> None:
            await runtime_state.set_worker_health("inbound_replay_worker", True)
            try:
                while True:
                    summary = await _subscriber_instance.replay_pending_events(limit=200)
                    stats = await inbox_service.stats()
                    await runtime_state.set_recovery_completed(stats.get("pending", 0) == 0)
                    if summary.get("failed", 0) > 0:
                        logger.warning(
                            "Inbound replay tick failures=%s pending=%s",
                            summary.get("failed", 0),
                            stats.get("pending", 0),
                        )
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                await runtime_state.set_worker_health("inbound_replay_worker", False)
                raise

        _inbound_replay_task = asyncio.create_task(_inbound_replay_worker())

        # Step 6.1: Sync Plugin Registry to DB (Phase 4C)
        logger.info("Syncing plugin registry to database...")
        try:
            async for session in get_session():
                from .autoops.core.plugin_registry import PluginRegistry
                from .services.plugin_service import PluginService

                plugin_registry = PluginRegistry()
                plugin_registry.discover_plugins()
                plugin_service = PluginService(session, plugin_registry)
                await plugin_service.sync_registry_to_db()
                logger.info(
                    f"Plugin registry synced: {len(plugin_registry.get_all())} plugins registered"
                )
                break
        except Exception as e:
            logger.warning(f"Plugin registry sync failed (non-critical): {e}")

        # Step 6.2: Daily Diagnostic Scheduler (Phase B V2.1)
        # Runs full system diagnostic daily + archives old reports (V2.2)
        if settings.maintenance.diagnostic_schedule_enabled:
            logger.info("Registering daily diagnostic scheduler...")
            from .services.diagnostics_service import DiagnosticsService

            async def _scheduled_daily_diagnostic():
                """Run full system diagnostic daily + cleanup old reports."""
                try:
                    async for session in get_session():
                        # Build with PluginService for complete plugins check
                        _diag_plugin_registry = PluginRegistry()
                        _diag_plugin_registry.discover_plugins()
                        _diag_ps = PluginService(session, _diag_plugin_registry)
                        diag_service = DiagnosticsService(session=session, plugin_service=_diag_ps)

                        # 1. Run diagnostic
                        report = await diag_service.run_full_diagnostic(triggered_by="scheduled")
                        logger.info(
                            f"Daily diagnostic: {report.overall_status.value} — "
                            f"{report.summary}"
                        )

                        # 2. Archive old reports (V2.2)
                        archived = await diag_service.cleanup_old_reports(
                            max_age_days=settings.maintenance.diagnostic_report_retention_days
                        )
                        if archived > 0:
                            logger.info(f"Archived {archived} old diagnostic reports")

                        break
                except Exception as e:
                    logger.error(f"Scheduled daily diagnostic FAILED: {e}")

            _central_scheduler.add_cron_job(
                job_id="daily_diagnostic",
                func=_scheduled_daily_diagnostic,
                cron_expression={
                    "hour": settings.maintenance.diagnostic_schedule_hour,
                    "minute": 0,
                },
                category=JobCategory.MAINTENANCE,
            )
            logger.info(
                f"Daily diagnostic scheduled at "
                f"{settings.maintenance.diagnostic_schedule_hour:02d}:00"
            )
        else:
            logger.info("Daily diagnostic scheduler DISABLED")

        # Step 6.2b: Daily Analysis Job (AUT-194)
        # 2x/day Claude stack-diagnostic at 06:00 + 18:00 UTC.
        # Reuses ai_service prompt-cache; idempotency via plugin_executions.
        # Runs even when ANTHROPIC_API_KEY is missing (writes empty report).
        try:
            from .autoops.core.reporter import AutoOpsReporter
            from .services.ai_service import ai_service as _ai_service_singleton
            from .services.daily_analysis_job import DailyAnalysisJob
            from .services.daily_snapshot_service import DailySnapshotService
            from .services.email_service import get_email_service
            from .core.scheduler import JobCategory as _JobCategory

            _daily_snapshot_service = DailySnapshotService(scheduler=_central_scheduler)
            _daily_reporter = AutoOpsReporter()
            _daily_email_service = get_email_service()
            _daily_analysis_job = DailyAnalysisJob(
                snapshot_service=_daily_snapshot_service,
                ai_service=_ai_service_singleton,
                reporter=_daily_reporter,
                email_service=_daily_email_service,
                session_factory=get_session,
            )

            _central_scheduler.add_cron_job(
                job_id="morning",
                func=_daily_analysis_job.run,
                cron_expression={"hour": 6, "minute": 0},
                kwargs={"slot": "morning"},
                category=_JobCategory.DAILY_ANALYSIS,
            )
            _central_scheduler.add_cron_job(
                job_id="evening",
                func=_daily_analysis_job.run,
                cron_expression={"hour": 18, "minute": 0},
                kwargs={"slot": "evening"},
                category=_JobCategory.DAILY_ANALYSIS,
            )
            logger.info(
                "DailyAnalysisJob (AUT-194) scheduled: morning=06:00 UTC, evening=18:00 UTC"
            )
        except Exception as _aut194_err:
            logger.warning(
                f"DailyAnalysisJob registration failed (non-critical): {_aut194_err}"
            )

        # Step 6.3: Plugin Schedule Registration (Phase B V3.1)
        # Load plugin schedules from DB and register as APScheduler cron jobs
        logger.info("Registering plugin schedules from DB...")
        try:
            from .core.scheduler import parse_cron_string
            from .autoops.core.base_plugin import PluginContext as _PluginContext
            from .db.models.plugin import PluginConfig as _PluginConfigModel

            async for session in get_session():
                _sched_plugin_registry = PluginRegistry()
                _sched_plugin_registry.discover_plugins()
                _sched_plugin_service = PluginService(session, _sched_plugin_registry)

                # Set default schedules for plugins that have none
                _DEFAULT_PLUGIN_SCHEDULES = {
                    "health_check": "0 5 * * *",  # Daily 05:00 (after cleanup + diagnostic)
                    "system_cleanup": "0 4 * * 0",  # Weekly Sunday 04:00
                }
                for _pid, _default_sched in _DEFAULT_PLUGIN_SCHEDULES.items():
                    _pconfig = await session.get(_PluginConfigModel, _pid)
                    if _pconfig and _pconfig.schedule is None:
                        try:
                            _pconfig.schedule = _default_sched
                            await session.commit()
                            logger.info(f"Set default schedule for '{_pid}': {_default_sched}")
                        except Exception as _e:
                            await session.rollback()
                            logger.debug(f"Plugin '{_pid}' default schedule failed: {_e}")

                # Register all scheduled plugins as APScheduler jobs
                scheduled_plugins = await _sched_plugin_service.get_scheduled_plugins()
                _registered_count = 0
                for _plugin_cfg in scheduled_plugins:
                    try:
                        cron_dict = parse_cron_string(_plugin_cfg.schedule)
                        _job_id = f"plugin_{_plugin_cfg.plugin_id}"

                        async def _execute_scheduled_plugin(
                            pid=_plugin_cfg.plugin_id,
                        ):
                            """Execute a scheduled plugin."""
                            try:
                                async for _sess in get_session():
                                    _reg = PluginRegistry()
                                    _reg.discover_plugins()
                                    _ps = PluginService(_sess, _reg)
                                    _ctx = _PluginContext(
                                        trigger_source="schedule",
                                    )
                                    await _ps.execute_plugin(
                                        plugin_id=pid,
                                        user_id=None,
                                        context=_ctx,
                                    )
                                    break
                            except Exception as _ex:
                                logger.error(f"Scheduled plugin {pid} FAILED: {_ex}")

                        _central_scheduler.add_cron_job(
                            job_id=_job_id,
                            func=_execute_scheduled_plugin,
                            cron_expression=cron_dict,
                            category=JobCategory.CUSTOM,
                        )
                        logger.info(
                            f"Plugin '{_plugin_cfg.plugin_id}' scheduled: "
                            f"{_plugin_cfg.schedule}"
                        )
                        _registered_count += 1
                    except Exception as _e:
                        logger.warning(
                            f"Failed to schedule plugin " f"'{_plugin_cfg.plugin_id}': {_e}"
                        )

                logger.info(f"Registered {_registered_count} plugin schedule(s)")
                break
        except Exception as e:
            logger.warning(f"Plugin schedule registration failed (non-critical): {e}")

        # Log resilience status
        resilience_status = get_health_status()
        logger.info(
            f"[resilience] Status: healthy={resilience_status['healthy']}, "
            f"breakers={resilience_status['summary']['total']} "
            f"(closed={resilience_status['summary']['closed']}, "
            f"open={resilience_status['summary']['open']})"
        )

        logger.info("=" * 60)
        logger.info("God-Kaiser Server Started Successfully")
        logger.info(f"Environment: {settings.environment}")
        logger.info(f"Log Level: {settings.log_level}")
        logger.info(f"MQTT Broker: {settings.mqtt.broker_host}:{settings.mqtt.broker_port}")
        logger.info(
            "API Endpoints: /api/v1/auth, /api/v1/esp, /api/v1/sensors, /api/v1/actuators, /api/v1/logic, /api/v1/health, /api/v1/notifications"
        )
        logger.info("Resilience: Circuit Breakers (mqtt, database, external_api) + Retry + Timeout")
        logger.info("=" * 60)

        final_runtime_mode = (
            RuntimeMode.NORMAL_OPERATION if connected else RuntimeMode.DEGRADED_OPERATION
        )
        await runtime_state.transition(final_runtime_mode, "startup completed")

        yield  # Server runs here

    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise

    # ===== SHUTDOWN =====
    logger.info("=" * 60)
    logger.info("God-Kaiser Server Shutting Down...")
    logger.info("=" * 60)
    runtime_state = get_runtime_state_service()
    await runtime_state.transition(RuntimeMode.SHUTDOWN_DRAIN, "lifespan shutdown begin")
    await runtime_state.set_logic_liveness(False)

    try:
        # Step 1: Stop Logic Scheduler
        if _logic_scheduler:
            logger.info("Stopping Logic Scheduler...")
            await _logic_scheduler.stop()
            logger.info("Logic Scheduler stopped")

        # Step 2: Stop Logic Engine
        if _logic_engine:
            logger.info("Stopping Logic Engine...")
            await _logic_engine.stop()
            logger.info("Logic Engine stopped")

        # Step 2.1: Stop SequenceActionExecutor cleanup task
        if _sequence_executor:
            logger.info("Stopping SequenceActionExecutor cleanup task...")
            await _sequence_executor.shutdown()
            logger.info("SequenceActionExecutor stopped")

        # Step 2.2: Shutdown MQTTCommandBridge (cancel pending Futures)
        if _mqtt_command_bridge:
            logger.info("Shutting down MQTTCommandBridge...")
            await _mqtt_command_bridge.shutdown()
            logger.info("MQTTCommandBridge shutdown complete")

        # Step 2.2b: Stop inbound replay worker
        if _inbound_replay_task:
            _inbound_replay_task.cancel()
            try:
                await _inbound_replay_task
            except asyncio.CancelledError:
                pass
            _inbound_replay_task = None

        # Step 2.3: Stop MaintenanceService FIRST (before scheduler shutdown)
        logger.info("Stopping MaintenanceService...")
        try:
            from .services.maintenance import get_maintenance_service

            maintenance_service = get_maintenance_service()
            maintenance_service.stop()  # Entfernt Maintenance-Jobs
            logger.info("  MaintenanceService stopped")
        except RuntimeError:
            logger.debug("  MaintenanceService not initialized, skipping")
        except Exception as e:
            logger.warning(f"  MaintenanceService shutdown warning: {e}")

        # Step 2.4: Stop SimulationScheduler simulations (Paket X - before scheduler shutdown)
        # This ensures Mock-ESPs can send final MQTT messages before scheduler jobs are removed
        logger.info("Stopping Mock-ESP simulations...")
        try:
            stopped_count = await _simulation_scheduler.stop_all_mocks()
            logger.info(f"  Mock-ESP shutdown: {stopped_count} simulations stopped")
        except Exception as e:
            logger.warning(f"  SimulationScheduler shutdown warning: {e}")

        # Step 2.5: Stop Central Scheduler AFTER Mocks (jobs can be removed safely now)
        logger.info("Stopping Central Scheduler...")
        try:
            from .core.scheduler import shutdown_central_scheduler

            scheduler_stats = await shutdown_central_scheduler()
            logger.info(
                f"  Central Scheduler: {scheduler_stats.get('jobs_removed', 0)} jobs removed"
            )
        except Exception as e:
            logger.warning(f"  Central Scheduler shutdown warning: {e}")

        # Step 2.6: Cancel all background tasks
        logger.info("Cancelling background tasks...")
        try:
            cancelled = await cancel_all_background_tasks(timeout=10.0)
            logger.info("Cancelled %d background tasks during shutdown", cancelled)
        except Exception as e:
            logger.warning(f"Background task cancellation warning: {e}")

        # Step 3: Shutdown WebSocket Manager
        if _websocket_manager:
            logger.info("Shutting down WebSocket Manager...")
            await _websocket_manager.shutdown()
            logger.info("WebSocket Manager shutdown complete")

        # Step 4: Shutdown MQTT subscriber (thread pool)
        if _subscriber_instance:
            logger.info("Shutting down MQTT subscriber thread pool...")
            _subscriber_instance.shutdown(wait=True, timeout=30.0)
            logger.info("MQTT subscriber shutdown complete")

        # Step 5: Disconnect MQTT client (always stop loop, even if not connected)
        logger.info("Disconnecting MQTT client...")
        mqtt_client = MQTTClient.get_instance()

        # SAFETY-P5: Publish offline status before disconnect (graceful shutdown)
        try:
            _server_status_topic = TopicBuilder.build_server_status_topic()
            mqtt_client.publish(
                _server_status_topic,
                json.dumps(
                    {
                        "status": "offline",
                        "timestamp": int(time.time()),
                        "reason": "graceful_shutdown",
                    }
                ),
                qos=1,
                retain=True,
            )
            logger.info("[SAFETY-P5] Server offline status published (graceful shutdown)")
        except Exception as _shutdown_err:
            logger.warning("[SAFETY-P5] Failed to publish shutdown status: %s", _shutdown_err)

        mqtt_client.disconnect()  # Always call - stops background thread even if not connected
        logger.info("MQTT client disconnected")

        # Step 6: Dispose database engine
        logger.info("Disposing database engine...")
        await dispose_engine()
        logger.info("Database engine disposed")

        logger.info("=" * 60)
        logger.info("God-Kaiser Server Shutdown Complete")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Shutdown failed: {e}", exc_info=True)


# ===== CREATE FASTAPI APP =====

app = FastAPI(
    title="God-Kaiser Server",
    description="""
    Central control hub for ESP32 automation nodes with Pi-Enhanced sensor processing.
    
    ## Features
    - **ESP32 Device Management**: Register, configure, and monitor ESP32 nodes
    - **Sensor Processing**: Server-side Pi-Enhanced sensor data processing
    - **Actuator Control**: Safe command execution with safety validation
    - **Logic Automation**: Cross-ESP automation rules
    - **Real-time Updates**: WebSocket support for live data
    
    ## Authentication
    - JWT tokens for user authentication
    - API keys for ESP32 devices
    
    ## API Versions
    - v1: Current stable API
    """,
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "auth", "description": "Authentication & Authorization"},
        {"name": "esp", "description": "ESP32 Device Management"},
        {"name": "sensors", "description": "Sensor Configuration & Data"},
        {"name": "actuators", "description": "Actuator Control & Commands"},
        {"name": "logic", "description": "Logic Rules & Automation"},
        {"name": "zone", "description": "Zone Assignment & Management"},
        {"name": "subzone", "description": "Subzone Management & Safe-Mode Control"},
        {"name": "health", "description": "Health Checks & Metrics"},
        {"name": "websocket", "description": "WebSocket Real-time Updates"},
    ],
)

# ===== MIDDLEWARE =====

# Request-ID middleware (must be added before CORS so it wraps the full request)
from .middleware.request_id import RequestIdMiddleware

app.add_middleware(RequestIdMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# ===== PROMETHEUS INSTRUMENTATOR =====
# Must be after CORS middleware, before router includes.
# Exposes HTTP request metrics (duration, count, size) + custom gauges
# at /api/v1/health/metrics in Prometheus text format.
# Skip under pytest: prometheus-fastapi-instrumentator 7.x assumes every
# app.routes entry has .path. FastAPI's _IncludedRouter does not, so every
# ASGI request 500s (AttributeError) before reaching the endpoint.
if os.environ.get("TESTING") != "true":
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(
            app,
            endpoint="/api/v1/health/metrics",
            include_in_schema=False,
        )
    except ImportError:
        logger.warning(
            "prometheus_fastapi_instrumentator not installed — metrics endpoint disabled"
        )

# ===== ROUTES =====


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Health check endpoint."""
    mqtt_client = MQTTClient.get_instance()
    return {
        "service": "God-Kaiser Server",
        "version": "2.0.0",
        "status": "online",
        "mqtt_connected": mqtt_client.is_connected(),
        "environment": settings.environment,
        "docs": "/docs",
        "api_prefix": "/api/v1",
    }


# Health endpoint (standard path for E2E tests and monitoring)
@app.get("/health", tags=["health"])
async def health():
    """Simple health check endpoint for monitoring and E2E tests."""
    mqtt_client = MQTTClient.get_instance()
    return {
        "status": "healthy" if mqtt_client.is_connected() else "degraded",
        "mqtt_connected": mqtt_client.is_connected(),
    }


# ===== API v1 ROUTERS =====

# Include all v1 API endpoints
app.include_router(
    api_v1_router,
    prefix="/api",
)

# Sensor Processing API (Real-Time HTTP) - keep at root for backward compatibility
app.include_router(
    sensor_processing.router,
    tags=["sensors", "processing"],
)

# WebSocket API
app.include_router(
    websocket_realtime.router,
    prefix="/api/v1",
    tags=["websocket"],
)

# Register global exception handlers (Paket X)
app.add_exception_handler(GodKaiserException, automation_one_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "god_kaiser_server.src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
        access_log=False,  # Redundant with RequestIdMiddleware request logging
    )
# Reload trigger Fr, 30. Jan 2026 04:31:31
