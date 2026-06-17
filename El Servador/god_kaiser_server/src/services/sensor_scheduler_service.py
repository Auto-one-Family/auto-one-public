"""
Sensor Scheduler Service (Phase 2H)

Manages scheduled sensor measurements using APScheduler.
Jobs are persisted in sensor.schedule_config and recreated on server restart.

Architecture:
- Uses CentralScheduler (APScheduler singleton) for job management
- Jobs are identified by: sensor_schedule_{esp_id}_{gpio}
- Cron expressions are parsed and validated before job creation
- Server restart recovery loads all scheduled sensors from DB
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..core.scheduler import CentralScheduler, JobCategory, get_central_scheduler
from ..db.models.esp import ESPDevice
from ..db.models.sensor import SensorConfig
from ..db.repositories.esp_repo import ESPRepository
from ..db.repositories.sensor_repo import SensorRepository
from ..mqtt.publisher import Publisher

logger = get_logger(__name__)


class SensorSchedulerService:
    """
    Service for managing scheduled sensor measurement jobs.

    Responsibilities:
    - Parse cron expressions from schedule_config
    - Create/update/remove APScheduler jobs
    - Recover jobs on server restart
    - Trigger measurements via MQTT Publisher

    Usage:
        service = SensorSchedulerService(sensor_repo, esp_repo, publisher)

        # Create a scheduled job
        await service.create_or_update_job(
            esp_id="ESP_12AB34CD",
            gpio=34,
            schedule_config={"type": "cron", "expression": "0 8,20 * * *"}
        )

        # Remove a job
        await service.remove_job("ESP_12AB34CD", 34)

        # Recover all jobs on startup
        await service.recover_all_jobs(session)
    """

    def __init__(
        self,
        sensor_repo: SensorRepository,
        esp_repo: ESPRepository,
        publisher: Publisher,
        scheduler: Optional[CentralScheduler] = None,
    ):
        """
        Initialize SensorSchedulerService.

        Args:
            sensor_repo: Sensor repository for DB queries
            esp_repo: ESP repository for device lookups
            publisher: MQTT publisher for triggering measurements
            scheduler: Central scheduler (uses singleton if not provided)
        """
        self.sensor_repo = sensor_repo
        self.esp_repo = esp_repo
        self.publisher = publisher
        self._scheduler = scheduler
        self._active_jobs: Dict[str, str] = {}  # full_job_id -> esp_id:gpio

    @property
    def scheduler(self) -> CentralScheduler:
        """Get scheduler instance (lazy initialization)."""
        if self._scheduler is None:
            self._scheduler = get_central_scheduler()
        return self._scheduler

    # =========================================================================
    # CRON PARSING
    # =========================================================================

    @staticmethod
    def parse_cron_expression(expression: str) -> Optional[Dict[str, Any]]:
        """
        Parse a cron expression into APScheduler CronTrigger parameters.

        Cron format: "minute hour day month day_of_week"
        Example: "0 8,20 * * *" → {"minute": "0", "hour": "8,20"}

        Args:
            expression: Cron expression string (5 parts)

        Returns:
            Dict with APScheduler cron parameters, or None if invalid.
            Parameters use string values to support ranges/lists (e.g., "8,20").
        """
        if not expression or not isinstance(expression, str):
            return None

        expression = expression.strip()
        parts = expression.split()

        if len(parts) != 5:
            logger.warning(f"Invalid cron expression (expected 5 parts): {expression}")
            return None

        minute, hour, day, month, day_of_week = parts

        try:
            cron_params: Dict[str, Any] = {}

            # Minute (0-59 or */n or n,m)
            if minute != "*":
                cron_params["minute"] = minute

            # Hour (0-23 or */n or n,m)
            if hour != "*":
                cron_params["hour"] = hour

            # Day of month (1-31 or */n or n,m)
            if day != "*":
                cron_params["day"] = day

            # Month (1-12 or */n or n,m)
            if month != "*":
                cron_params["month"] = month

            # Day of week (0-6, 0=Sunday in cron standard)
            # APScheduler uses 0=Monday by default, but accepts string values
            if day_of_week != "*":
                cron_params["day_of_week"] = day_of_week

            # Default: if no params, run every hour at minute 0
            return cron_params if cron_params else {"minute": "0"}

        except Exception as e:
            logger.error(f"Failed to parse cron expression '{expression}': {e}")
            return None

    @staticmethod
    def validate_schedule_config(config: Optional[Dict[str, Any]]) -> bool:
        """
        Validate schedule_config structure.

        Expected format:
        {
            "type": "cron",
            "expression": "0 8,20 * * *"
        }

        Args:
            config: Schedule configuration dict

        Returns:
            True if valid, False otherwise
        """
        if not config:
            return False

        if not isinstance(config, dict):
            return False

        config_type = config.get("type")
        expression = config.get("expression")

        if config_type != "cron":
            logger.warning(f"Unsupported schedule type: {config_type}")
            return False

        if not expression or not isinstance(expression, str):
            return False

        # Validate cron expression can be parsed
        return SensorSchedulerService.parse_cron_expression(expression) is not None

    # =========================================================================
    # JOB ID MANAGEMENT
    # =========================================================================

    @staticmethod
    def build_job_id(esp_id: str, gpio: int) -> str:
        """
        Build job ID for a sensor (without category prefix).

        The CentralScheduler will add the category prefix automatically.

        Args:
            esp_id: ESP device ID (e.g., "ESP_12AB34CD")
            gpio: Sensor GPIO pin

        Returns:
            Job ID string (e.g., "ESP_12AB34CD_34")
        """
        return f"{esp_id}_{gpio}"

    @staticmethod
    def build_full_job_id(esp_id: str, gpio: int) -> str:
        """
        Build full job ID including category prefix.

        Used for tracking and lookup in _active_jobs.

        Args:
            esp_id: ESP device ID
            gpio: Sensor GPIO pin

        Returns:
            Full job ID (e.g., "sensor_schedule_ESP_12AB34CD_34")
        """
        return f"{JobCategory.SENSOR_SCHEDULE.value}_{esp_id}_{gpio}"

    @staticmethod
    def parse_job_id(job_id: str) -> Optional[Tuple[str, int]]:
        """
        Parse job ID back to esp_id and gpio.

        Handles both with and without category prefix.

        Args:
            job_id: Job ID string

        Returns:
            Tuple of (esp_id, gpio) or None if invalid
        """
        # Remove category prefix if present
        prefix = f"{JobCategory.SENSOR_SCHEDULE.value}_"
        if job_id.startswith(prefix):
            job_id = job_id[len(prefix) :]

        # Pattern: ESP_XXXXXX_NN (ESP ID with 6-8 hex chars, underscore, GPIO)
        # ESP ID format: ESP_ followed by 6-8 uppercase hex characters
        match = re.match(r"(ESP_[A-F0-9]{6,8})_(\d+)$", job_id)
        if match:
            return match.group(1), int(match.group(2))
        return None

    # =========================================================================
    # JOB LIFECYCLE
    # =========================================================================

    async def create_or_update_job(
        self,
        esp_id: str,
        gpio: int,
        schedule_config: Dict[str, Any],
    ) -> bool:
        """
        Create or update a scheduled measurement job.

        Args:
            esp_id: ESP device ID (e.g., "ESP_12AB34CD")
            gpio: Sensor GPIO pin
            schedule_config: Schedule configuration with cron expression

        Returns:
            True if job was created/updated successfully
        """
        job_id = self.build_job_id(esp_id, gpio)
        full_job_id = self.build_full_job_id(esp_id, gpio)

        # Validate config
        if not self.validate_schedule_config(schedule_config):
            logger.error(f"Invalid schedule_config for {full_job_id}: {schedule_config}")
            return False

        # Parse cron expression
        expression = schedule_config.get("expression", "")
        cron_params = self.parse_cron_expression(expression)
        if not cron_params:
            logger.error(f"Failed to parse cron for {full_job_id}: {expression}")
            return False

        # Remove existing job if any
        await self.remove_job(esp_id, gpio)

        try:
            # Create measurement callback
            # IMPORTANT: Store esp_id and gpio in closure for callback
            captured_esp_id = esp_id
            captured_gpio = gpio

            async def trigger_scheduled_measurement():
                """Callback executed by scheduler at scheduled time."""
                await self._execute_scheduled_measurement(captured_esp_id, captured_gpio)

            # Add job to scheduler
            # Note: CentralScheduler.add_cron_job expects cron_expression as dict param
            success = self.scheduler.add_cron_job(
                job_id=job_id,
                func=trigger_scheduled_measurement,
                cron_expression=cron_params,
                category=JobCategory.SENSOR_SCHEDULE,
            )

            if success:
                self._active_jobs[full_job_id] = f"{esp_id}:{gpio}"
                logger.info(
                    f"Scheduled measurement job created: {full_job_id} " f"(cron: {expression})"
                )
                return True
            else:
                logger.error(f"Failed to add job to scheduler: {full_job_id}")
                return False

        except Exception as e:
            logger.exception(f"Failed to create job {full_job_id}: {e}")
            return False

    async def remove_job(self, esp_id: str, gpio: int) -> bool:
        """
        Remove a scheduled measurement job.

        Args:
            esp_id: ESP device ID
            gpio: Sensor GPIO pin

        Returns:
            True if job was removed (or didn't exist)
        """
        job_id = self.build_job_id(esp_id, gpio)
        full_job_id = self.build_full_job_id(esp_id, gpio)

        try:
            # Remove from scheduler (with category prefix)
            removed = self.scheduler.remove_job(job_id, category=JobCategory.SENSOR_SCHEDULE)

            # Clean up tracking
            self._active_jobs.pop(full_job_id, None)

            if removed:
                logger.info(f"Scheduled measurement job removed: {full_job_id}")

            return True

        except Exception as e:
            logger.warning(f"Failed to remove job {full_job_id}: {e}")
            return False

    async def _execute_scheduled_measurement(self, esp_id: str, gpio: int) -> None:
        """
        Execute a scheduled measurement.

        Called by APScheduler at the scheduled time.

        Args:
            esp_id: ESP device ID
            gpio: Sensor GPIO pin
        """
        full_job_id = self.build_full_job_id(esp_id, gpio)

        logger.info(f"Executing scheduled measurement: {esp_id}/GPIO {gpio}")

        try:
            # Check if ESP is online
            esp = await self.esp_repo.get_by_device_id(esp_id)
            if not esp:
                logger.warning(f"Scheduled measurement skipped - ESP not found: {esp_id}")
                return

            if esp.status != "online":
                logger.warning(
                    f"Scheduled measurement skipped - ESP offline: {esp_id} "
                    f"(status: {esp.status})"
                )
                return

            # R1 — AUT-590: Skip measurement command when ESP is under FreeRTOS
            # queue pressure to avoid compounding the queue fill level.
            from ..mqtt.handlers.queue_pressure_handler import is_esp_under_pressure
            if is_esp_under_pressure(esp_id):
                logger.warning(
                    f"Scheduled measurement skipped - ESP under queue pressure: {esp_id}/GPIO {gpio}"
                )
                return

            # Check if sensor still exists and is scheduled
            # Use get_all to handle multi-value sensors on shared GPIO
            all_sensors = await self.sensor_repo.get_all_by_esp_and_gpio(esp.id, gpio)
            # Find the scheduled sensor(s) on this GPIO
            scheduled_sensors = [
                s for s in all_sensors if s.operating_mode == "scheduled" and s.enabled
            ]

            if not all_sensors:
                logger.warning(
                    f"Scheduled measurement skipped - Sensor not found: {esp_id}/GPIO {gpio}"
                )
                # Remove orphaned job
                await self.remove_job(esp_id, gpio)
                return

            if not scheduled_sensors:
                logger.info(
                    f"Scheduled measurement skipped - No scheduled+enabled sensor: "
                    f"{esp_id}/GPIO {gpio}"
                )
                # Remove job since no sensor is scheduled anymore
                await self.remove_job(esp_id, gpio)
                return

            # Trigger measurement via MQTT
            success, request_id = self.publisher.publish_sensor_command(
                esp_id=esp_id,
                gpio=gpio,
                command="measure",
            )

            if success:
                logger.info(
                    f"Scheduled measurement triggered: {esp_id}/GPIO {gpio} "
                    f"(sensor_type: {scheduled_sensors[0].sensor_type}, "
                    f"request_id: {request_id})"
                )
            else:
                logger.error(f"Failed to trigger scheduled measurement: {esp_id}/GPIO {gpio}")

        except Exception as e:
            logger.exception(f"Error executing scheduled measurement {full_job_id}: {e}")

    # =========================================================================
    # RECOVERY & INITIALIZATION
    # =========================================================================

    async def recover_all_jobs(self, session: AsyncSession) -> int:
        """
        Recover all scheduled sensor jobs from database.

        Called during server startup to recreate jobs.
        Only future jobs are scheduled - missed jobs are NOT caught up.

        Args:
            session: Database session

        Returns:
            Number of jobs recovered
        """
        logger.info("Recovering scheduled sensor jobs...")

        recovered = 0

        try:
            # Query all sensors with operating_mode='scheduled' and valid schedule_config
            stmt = (
                select(SensorConfig, ESPDevice)
                .join(ESPDevice, SensorConfig.esp_id == ESPDevice.id)
                .where(
                    and_(
                        SensorConfig.operating_mode == "scheduled",
                        SensorConfig.enabled == True,
                        SensorConfig.schedule_config.isnot(None),
                    )
                )
            )

            result = await session.execute(stmt)
            rows = result.all()

            for sensor, esp in rows:
                if not self.validate_schedule_config(sensor.schedule_config):
                    logger.warning(
                        f"Skipping invalid schedule_config: {esp.device_id}/GPIO {sensor.gpio}"
                    )
                    continue

                success = await self.create_or_update_job(
                    esp_id=esp.device_id,
                    gpio=sensor.gpio,
                    schedule_config=sensor.schedule_config,
                )

                if success:
                    recovered += 1

            logger.info(f"Recovered {recovered} scheduled sensor jobs")
            return recovered

        except Exception as e:
            logger.exception(f"Failed to recover scheduled jobs: {e}")
            return recovered

    # =========================================================================
    # STATUS & MONITORING
    # =========================================================================

    def get_active_jobs(self) -> List[Dict[str, Any]]:
        """
        Get list of active scheduled measurement jobs.

        Returns:
            List of job info dicts with job_id, esp_id, gpio, next_run, status
        """
        jobs = []

        for full_job_id, sensor_ref in self._active_jobs.items():
            esp_id, gpio_str = sensor_ref.split(":")
            gpio = int(gpio_str)

            # Get next run time from scheduler
            job = self.scheduler._scheduler.get_job(full_job_id)
            next_run = job.next_run_time if job else None

            jobs.append(
                {
                    "job_id": full_job_id,
                    "esp_id": esp_id,
                    "gpio": gpio,
                    "next_run": next_run.isoformat() if next_run else None,
                    "status": "active" if job else "missing",
                }
            )

        return jobs

    def get_job_count(self) -> int:
        """Get count of active scheduled jobs."""
        return len(self._active_jobs)

    def get_job_info(self, esp_id: str, gpio: int) -> Optional[Dict[str, Any]]:
        """
        Get info for a specific job.

        Args:
            esp_id: ESP device ID
            gpio: Sensor GPIO pin

        Returns:
            Job info dict or None if not found
        """
        full_job_id = self.build_full_job_id(esp_id, gpio)

        if full_job_id not in self._active_jobs:
            return None

        job = self.scheduler._scheduler.get_job(full_job_id)
        next_run = job.next_run_time if job else None

        return {
            "job_id": full_job_id,
            "esp_id": esp_id,
            "gpio": gpio,
            "next_run": next_run.isoformat() if next_run else None,
            "status": "active" if job else "missing",
            "trigger": str(job.trigger) if job else None,
        }
