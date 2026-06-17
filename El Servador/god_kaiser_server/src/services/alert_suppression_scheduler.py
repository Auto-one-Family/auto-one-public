"""
Alert Suppression Expiry Scheduler Task

Phase 4A.7: Periodically checks suppression_until fields and re-enables
alerts that have expired. Runs every 5 minutes via CentralScheduler.

Also checks maintenance overdue and sends maintenance reminder notifications.
"""

from datetime import datetime, timezone

from sqlalchemy.orm.attributes import flag_modified

from ..core.logging_config import get_logger
from ..core.metrics import (
    increment_alert_suppression_expired,
    update_alert_suppression_active,
)
from ..db.session import get_session_maker

logger = get_logger(__name__)


async def check_suppression_expiry() -> None:
    """
    Check all sensor_configs, actuator_configs, and esp_devices for
    expired suppression_until dates and re-enable alerts.

    Called every 5 minutes by CentralScheduler (MAINTENANCE category).
    """
    from sqlalchemy import select

    from ..db.models.actuator import ActuatorConfig
    from ..db.models.sensor import SensorConfig
    from ..db.models.esp import ESPDevice

    now = datetime.now(timezone.utc)
    total_re_enabled = 0

    try:
        async with get_session_maker()() as session:
            # Check sensor_configs
            result = await session.execute(
                select(SensorConfig).where(SensorConfig.alert_config.isnot(None))
            )
            for sensor in result.scalars():
                cfg = dict(
                    sensor.alert_config or {}
                )  # Copy to avoid in-place mutation of SA committed state
                if not cfg.get("alerts_enabled", True) and cfg.get("suppression_until"):
                    try:
                        until_dt = datetime.fromisoformat(cfg["suppression_until"])
                        if until_dt.tzinfo is None:
                            until_dt = until_dt.replace(tzinfo=timezone.utc)
                        if now > until_dt:
                            cfg["alerts_enabled"] = True
                            cfg.pop("suppression_until", None)
                            cfg.pop("suppression_reason", None)
                            cfg.pop("suppression_note", None)
                            sensor.alert_config = cfg
                            flag_modified(sensor, "alert_config")
                            total_re_enabled += 1
                            logger.info(
                                f"Alert re-enabled (expired): sensor_config "
                                f"esp_id={sensor.esp_id}, gpio={sensor.gpio}"
                            )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid suppression_until on sensor {sensor.id}: {e}")

            # Check actuator_configs
            result = await session.execute(
                select(ActuatorConfig).where(ActuatorConfig.alert_config.isnot(None))
            )
            for actuator in result.scalars():
                cfg = dict(actuator.alert_config or {})  # Copy to avoid in-place mutation
                if not cfg.get("alerts_enabled", True) and cfg.get("suppression_until"):
                    try:
                        until_dt = datetime.fromisoformat(cfg["suppression_until"])
                        if until_dt.tzinfo is None:
                            until_dt = until_dt.replace(tzinfo=timezone.utc)
                        if now > until_dt:
                            cfg["alerts_enabled"] = True
                            cfg.pop("suppression_until", None)
                            cfg.pop("suppression_reason", None)
                            cfg.pop("suppression_note", None)
                            actuator.alert_config = cfg
                            flag_modified(actuator, "alert_config")
                            total_re_enabled += 1
                            logger.info(
                                f"Alert re-enabled (expired): actuator_config "
                                f"esp_id={actuator.esp_id}, gpio={actuator.gpio}"
                            )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid suppression_until on actuator {actuator.id}: {e}")

            # Check esp_devices
            result = await session.execute(
                select(ESPDevice).where(ESPDevice.alert_config.isnot(None))
            )
            for device in result.scalars():
                cfg = dict(device.alert_config or {})  # Copy to avoid in-place mutation
                if not cfg.get("alerts_enabled", True) and cfg.get("suppression_until"):
                    try:
                        until_dt = datetime.fromisoformat(cfg["suppression_until"])
                        if until_dt.tzinfo is None:
                            until_dt = until_dt.replace(tzinfo=timezone.utc)
                        if now > until_dt:
                            cfg["alerts_enabled"] = True
                            cfg.pop("suppression_until", None)
                            cfg.pop("suppression_reason", None)
                            cfg.pop("suppression_note", None)
                            device.alert_config = cfg
                            flag_modified(device, "alert_config")
                            total_re_enabled += 1
                            logger.info(f"Alert re-enabled (expired): device {device.device_id}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid suppression_until on device {device.id}: {e}")

            # Count currently suppressed entities for gauge
            sensor_suppressed = sum(
                1
                for s in (
                    await session.execute(
                        select(SensorConfig).where(SensorConfig.alert_config.isnot(None))
                    )
                ).scalars()
                if not (s.alert_config or {}).get("alerts_enabled", True)
            )
            actuator_suppressed = sum(
                1
                for a in (
                    await session.execute(
                        select(ActuatorConfig).where(ActuatorConfig.alert_config.isnot(None))
                    )
                ).scalars()
                if not (a.alert_config or {}).get("alerts_enabled", True)
            )
            device_suppressed = sum(
                1
                for d in (
                    await session.execute(
                        select(ESPDevice).where(ESPDevice.alert_config.isnot(None))
                    )
                ).scalars()
                if not (d.alert_config or {}).get("alerts_enabled", True)
            )
            update_alert_suppression_active("sensor", sensor_suppressed)
            update_alert_suppression_active("actuator", actuator_suppressed)
            update_alert_suppression_active("device", device_suppressed)

            if total_re_enabled > 0:
                await session.commit()
                for _ in range(total_re_enabled):
                    increment_alert_suppression_expired()
                logger.info(f"Suppression expiry check: {total_re_enabled} alerts re-enabled")

    except Exception as e:
        logger.error(f"Suppression expiry check failed: {e}", exc_info=True)


async def check_maintenance_overdue() -> None:
    """
    Check all sensors/actuators for overdue maintenance and send
    notifications via NotificationRouter.

    Called daily by CentralScheduler (MAINTENANCE category).
    """
    from sqlalchemy import select

    from ..db.models.sensor import SensorConfig
    from ..services.notification_router import NotificationRouter
    from ..schemas.notification import NotificationCreate

    now = datetime.now(timezone.utc)

    try:
        async with get_session_maker()() as session:
            # Check sensors with metadata containing maintenance info
            result = await session.execute(
                select(SensorConfig).where(SensorConfig.sensor_metadata.isnot(None))
            )
            for sensor in result.scalars():
                meta = sensor.sensor_metadata or {}
                last_maintenance = meta.get("last_maintenance")
                interval_days = meta.get("maintenance_interval_days")

                if not last_maintenance or not interval_days:
                    continue

                try:
                    last_dt = datetime.fromisoformat(last_maintenance)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    from datetime import timedelta

                    next_dt = last_dt + timedelta(days=interval_days)

                    if now > next_dt:
                        notification = NotificationCreate(
                            severity="info",
                            category="maintenance",
                            title=f"Wartung fällig: {sensor.sensor_name}",
                            body=(
                                f"Sensor '{sensor.sensor_name}' ({sensor.sensor_type}) "
                                f"hat den Wartungstermin überschritten. "
                                f"Letzte Wartung: {last_maintenance}, "
                                f"Intervall: {interval_days} Tage."
                            ),
                            source="system",
                            metadata={
                                "esp_id": str(sensor.esp_id),
                                "gpio": sensor.gpio,
                                "sensor_type": sensor.sensor_type,
                                "last_maintenance": last_maintenance,
                                "interval_days": interval_days,
                            },
                        )
                        router = NotificationRouter(session)
                        await router.route(notification)
                except (ValueError, TypeError):
                    pass

            await session.commit()

    except Exception as e:
        logger.error(f"Maintenance overdue check failed: {e}", exc_info=True)


def register_suppression_tasks(scheduler) -> None:
    """
    Register suppression expiry and maintenance tasks with the CentralScheduler.

    Call this during server startup (in main.py or startup hooks).
    """
    from ..core.scheduler import JobCategory

    # Every 5 minutes: check suppression expiry
    scheduler.add_interval_job(
        job_id="suppression_expiry_check",
        func=check_suppression_expiry,
        seconds=300,  # 5 minutes
        category=JobCategory.MAINTENANCE,
        start_immediately=False,
    )

    # Daily at 08:00: check maintenance overdue
    scheduler.add_cron_job(
        job_id="maintenance_overdue_check",
        func=check_maintenance_overdue,
        cron_expression={"hour": 8, "minute": 0},
        category=JobCategory.MAINTENANCE,
    )

    logger.info("Alert suppression scheduler tasks registered")
