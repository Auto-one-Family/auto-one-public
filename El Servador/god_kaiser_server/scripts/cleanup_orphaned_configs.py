"""
One-time Cleanup: Delete sensor_configs and actuator_configs
whose esp_device has been soft-deleted (deleted_at IS NOT NULL).

These orphans were created BEFORE T09-Fix-B which correctly
implemented CASCADE delete for sensor_configs on device deletion.
Since that fix, new device deletes properly cascade to configs.

This script is IDEMPOTENT - safe to run multiple times (0 deletes on repeat).

Usage:
    cd "El Servador/god_kaiser_server"
    python scripts/cleanup_orphaned_configs.py
    # or: python scripts/cleanup_orphaned_configs.py --dry-run
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path (same pattern as init_db.py)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import delete, func, select

from src.core.logging_config import get_logger
from src.db.models.actuator import ActuatorConfig
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig, SensorData
from src.db.session import get_session

logger = get_logger(__name__)


async def cleanup_orphaned_configs(dry_run: bool = False) -> dict:
    """
    Delete sensor_configs and actuator_configs belonging to soft-deleted devices.

    Args:
        dry_run: If True, only report counts without deleting.

    Returns:
        Dict with counts of found and deleted orphans.
    """
    result = {
        "deleted_devices": 0,
        "orphaned_sensor_configs": 0,
        "orphaned_actuator_configs": 0,
        "deleted_sensor_configs": 0,
        "deleted_actuator_configs": 0,
        "sensor_data_count": 0,
        "active_sensor_configs": 0,
    }

    async for session in get_session():
        try:
            # 1. Find all soft-deleted devices
            deleted_devices = await session.execute(
                select(ESPDevice.id, ESPDevice.device_id).where(
                    ESPDevice.deleted_at.isnot(None)
                )
            )
            deleted_rows = deleted_devices.all()
            deleted_ids = [row[0] for row in deleted_rows]
            result["deleted_devices"] = len(deleted_ids)

            if not deleted_ids:
                print("No soft-deleted devices found. Nothing to do.")
                return result

            device_names = [row[1] for row in deleted_rows]
            print(f"Found {len(deleted_ids)} soft-deleted device(s): {device_names}")

            # 2. Count orphaned sensor_configs
            orphan_sensor_count = await session.execute(
                select(func.count())
                .select_from(SensorConfig)
                .where(SensorConfig.esp_id.in_(deleted_ids))
            )
            result["orphaned_sensor_configs"] = orphan_sensor_count.scalar()

            # 3. Count orphaned actuator_configs
            orphan_actuator_count = await session.execute(
                select(func.count())
                .select_from(ActuatorConfig)
                .where(ActuatorConfig.esp_id.in_(deleted_ids))
            )
            result["orphaned_actuator_configs"] = orphan_actuator_count.scalar()

            # 4. Baseline: count sensor_data and active sensor_configs
            sensor_data_count = await session.execute(
                select(func.count()).select_from(SensorData)
            )
            result["sensor_data_count"] = sensor_data_count.scalar()

            active_config_count = await session.execute(
                select(func.count())
                .select_from(SensorConfig)
                .where(SensorConfig.esp_id.notin_(deleted_ids))
            )
            result["active_sensor_configs"] = active_config_count.scalar()

            # Report
            print(f"\n--- Orphan Report ---")
            print(f"Orphaned sensor_configs:   {result['orphaned_sensor_configs']}")
            print(f"Orphaned actuator_configs: {result['orphaned_actuator_configs']}")
            print(f"Active sensor_configs:     {result['active_sensor_configs']}")
            print(f"Total sensor_data rows:    {result['sensor_data_count']}")

            if (
                result["orphaned_sensor_configs"] == 0
                and result["orphaned_actuator_configs"] == 0
            ):
                print("\nNo orphans found. Cleanup not needed.")
                return result

            if dry_run:
                print("\n[DRY RUN] No changes made.")
                return result

            # 5. Delete orphaned sensor_configs
            if result["orphaned_sensor_configs"] > 0:
                del_sensors = await session.execute(
                    delete(SensorConfig).where(
                        SensorConfig.esp_id.in_(deleted_ids)
                    )
                )
                result["deleted_sensor_configs"] = del_sensors.rowcount
                print(
                    f"\nDeleted: {del_sensors.rowcount} orphaned sensor_configs"
                )

            # 6. Delete orphaned actuator_configs
            if result["orphaned_actuator_configs"] > 0:
                del_actuators = await session.execute(
                    delete(ActuatorConfig).where(
                        ActuatorConfig.esp_id.in_(deleted_ids)
                    )
                )
                result["deleted_actuator_configs"] = del_actuators.rowcount
                print(
                    f"Deleted: {del_actuators.rowcount} orphaned actuator_configs"
                )

            await session.commit()

            # 7. Verify: sensor_data unchanged
            post_data_count = await session.execute(
                select(func.count()).select_from(SensorData)
            )
            post_count = post_data_count.scalar()
            if post_count == result["sensor_data_count"]:
                print(f"\nVerified: sensor_data unchanged ({post_count} rows)")
            else:
                logger.warning(
                    "sensor_data count changed: %d -> %d",
                    result["sensor_data_count"],
                    post_count,
                )

            print("\nCleanup completed successfully.")

        except Exception as e:
            logger.error("Cleanup failed: %s", e, exc_info=True)
            await session.rollback()
            raise
        finally:
            break

    return result


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN MODE ===\n")
    asyncio.run(cleanup_orphaned_configs(dry_run=dry_run))
