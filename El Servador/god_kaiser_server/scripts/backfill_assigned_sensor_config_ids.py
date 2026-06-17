"""
One-time Backfill: Populate assigned_sensor_config_ids for all existing subzones.

R20-P5: The assigned_sensor_config_ids field on subzone_configs has never been
populated. This script computes the correct values from the current
assigned_gpios + sensor_configs state and writes them to the DB.

This is needed for correct I2C sensor differentiation: all I2C sensors share
gpio=0 as placeholder. Without assigned_sensor_config_ids, sync_subzone_counts()
falls back to pure GPIO matching which can't distinguish between sensors on
the same I2C bus.

This script is IDEMPOTENT - safe to run multiple times (no-op if already correct).

Usage:
    cd "El Servador/god_kaiser_server"
    python scripts/backfill_assigned_sensor_config_ids.py
    # or: python scripts/backfill_assigned_sensor_config_ids.py --dry-run
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path (same pattern as cleanup_orphaned_configs.py)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from src.core.logging_config import get_logger
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.db.models.subzone import SubzoneConfig
from src.db.session import get_session

logger = get_logger(__name__)


async def backfill_assigned_sensor_config_ids(dry_run: bool = False) -> dict:
    """
    Populate assigned_sensor_config_ids for all subzones based on GPIO match.

    For each subzone: find all sensor_configs of the same ESP whose GPIO is in
    assigned_gpios, then write their UUIDs to assigned_sensor_config_ids.

    Handles FK type mismatch: SubzoneConfig.esp_id = String (device_id),
    SensorConfig.esp_id = UUID (esp_devices.id).

    Args:
        dry_run: If True, only report what would change without writing.

    Returns:
        Dict with counts of inspected and updated subzones.
    """
    result = {
        "total_subzones": 0,
        "updated_subzones": 0,
        "already_correct": 0,
        "no_gpios": 0,
        "esp_not_found": 0,
    }

    async with get_session() as session:
        # Load all subzones
        subzone_result = await session.execute(select(SubzoneConfig))
        all_subzones = list(subzone_result.scalars().all())
        result["total_subzones"] = len(all_subzones)

        if not all_subzones:
            logger.info("No subzones found — nothing to backfill.")
            return result

        # Build ESP device_id → UUID lookup
        esp_result = await session.execute(select(ESPDevice))
        esp_map: dict[str, ESPDevice] = {
            esp.device_id: esp for esp in esp_result.scalars().all()
        }

        # Load all sensor configs, grouped by esp UUID
        sensor_result = await session.execute(select(SensorConfig))
        all_sensors = list(sensor_result.scalars().all())
        sensors_by_esp_uuid: dict[str, list[SensorConfig]] = {}
        for sensor in all_sensors:
            key = str(sensor.esp_id)
            sensors_by_esp_uuid.setdefault(key, []).append(sensor)

        for subzone in all_subzones:
            gpios = set(subzone.assigned_gpios or [])
            if not gpios:
                result["no_gpios"] += 1
                continue

            # Resolve device_id string → UUID for sensor lookup
            esp_device = esp_map.get(subzone.esp_id)
            if not esp_device:
                result["esp_not_found"] += 1
                logger.warning(
                    "Subzone %s: ESP device '%s' not found — skipping",
                    subzone.subzone_id,
                    subzone.esp_id,
                )
                continue

            # Find matching sensor configs
            esp_sensors = sensors_by_esp_uuid.get(str(esp_device.id), [])
            new_ids = sorted(str(s.id) for s in esp_sensors if s.gpio in gpios)
            old_ids = sorted(subzone.assigned_sensor_config_ids or [])

            if new_ids == old_ids:
                result["already_correct"] += 1
                continue

            logger.info(
                "Subzone '%s' (ESP %s): %s → %s (%d IDs)",
                subzone.subzone_name or subzone.subzone_id,
                subzone.esp_id,
                old_ids,
                new_ids,
                len(new_ids),
            )

            if not dry_run:
                subzone.assigned_sensor_config_ids = new_ids
                flag_modified(subzone, "assigned_sensor_config_ids")

            result["updated_subzones"] += 1

        if not dry_run and result["updated_subzones"] > 0:
            await session.commit()
            logger.info(
                "Committed %d subzone updates.", result["updated_subzones"]
            )

    return result


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    mode = "DRY-RUN" if dry_run else "LIVE"

    print(f"\n=== Backfill assigned_sensor_config_ids ({mode}) ===\n")

    result = await backfill_assigned_sensor_config_ids(dry_run=dry_run)

    print(f"Total subzones:    {result['total_subzones']}")
    print(f"Updated:           {result['updated_subzones']}")
    print(f"Already correct:   {result['already_correct']}")
    print(f"No GPIOs assigned: {result['no_gpios']}")
    print(f"ESP not found:     {result['esp_not_found']}")

    if dry_run and result["updated_subzones"] > 0:
        print(f"\nRun without --dry-run to apply {result['updated_subzones']} updates.")


if __name__ == "__main__":
    asyncio.run(main())
