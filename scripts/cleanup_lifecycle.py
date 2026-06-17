"""
Database cleanup for Device/Sensor-Lifecycle fix (BLOCK 1).

Removes:
- Stale mock ESP: MOCK_7CE9A94D (202h offline)
- Wokwi ghosts: MOCK_E1BD1447, MOCK_25045525 (no mock flag)
- Failed sht31 sensor_config on ESP_472204

Preserves:
- ESP_472204 (Robin's real ESP)
- MOCK_0954B2B1 (active mock)
- MOCK_5D5ADA49 (stale but keepable mock)

Usage:
    .venv\\Scripts\\python.exe scripts/cleanup_lifecycle.py
"""

import asyncpg
import asyncio


DB_URL = "postgresql://god_kaiser:god_kaiser_password@localhost:5432/god_kaiser_db"

DEVICES_TO_DELETE = [
    "MOCK_7CE9A94D",   # Stale mock (202h offline, 371 heartbeats)
    "MOCK_E1BD1447",   # Wokwi-Ghost (no mock flag, no heartbeat_logs)
    "MOCK_25045525",   # Wokwi-Ghost (no mock flag, no heartbeat_logs)
]


async def main():
    conn = await asyncpg.connect(DB_URL)

    try:
        # Step 1: Show current state
        print("=== CURRENT STATE ===")
        rows = await conn.fetch(
            "SELECT device_id, status, hardware_type, "
            "(device_metadata->>'mock')::text as is_mock "
            "FROM esp_devices ORDER BY device_id"
        )
        for row in rows:
            print(f"  {row['device_id']:20s} status={row['status']:10s} "
                  f"hw={row['hardware_type'] or 'NULL':15s} mock={row['is_mock'] or 'N/A'}")

        print(f"\nTotal ESP devices: {len(rows)}")

        # Step 2: Delete stale/ghost devices (CASCADE handles child tables)
        print("\n=== DELETING STALE/GHOST DEVICES ===")
        for device_id in DEVICES_TO_DELETE:
            result = await conn.execute(
                "DELETE FROM esp_devices WHERE device_id = $1", device_id
            )
            count = int(result.split(" ")[-1])
            print(f"  {device_id}: {'DELETED' if count > 0 else 'NOT FOUND'}")

        # Step 3: Delete failed sht31 sensor_config on ESP_472204
        print("\n=== CLEANING FAILED SENSOR_CONFIG ===")
        result = await conn.execute("""
            DELETE FROM sensor_configs
            WHERE esp_id = (SELECT id FROM esp_devices WHERE device_id = 'ESP_472204')
            AND sensor_type = 'sht31'
            AND config_status = 'failed'
        """)
        count = int(result.split(" ")[-1])
        print(f"  Failed sht31 configs deleted: {count}")

        # Step 4: Verify final state
        print("\n=== FINAL STATE ===")
        rows = await conn.fetch(
            "SELECT device_id, status, hardware_type, "
            "(device_metadata->>'mock')::text as is_mock "
            "FROM esp_devices ORDER BY device_id"
        )
        for row in rows:
            print(f"  {row['device_id']:20s} status={row['status']:10s} "
                  f"hw={row['hardware_type'] or 'NULL':15s} mock={row['is_mock'] or 'N/A'}")

        print(f"\nTotal ESP devices: {len(rows)}")

        # Step 5: Check for orphaned records
        orphaned_configs = await conn.fetchval(
            "SELECT COUNT(*) FROM sensor_configs sc "
            "LEFT JOIN esp_devices ed ON sc.esp_id = ed.id WHERE ed.id IS NULL"
        )
        orphaned_logs = await conn.fetchval(
            "SELECT COUNT(*) FROM esp_heartbeat_logs ehl "
            "LEFT JOIN esp_devices ed ON ehl.esp_id = ed.id WHERE ed.id IS NULL"
        )
        print(f"\nOrphaned sensor_configs: {orphaned_configs}")
        print(f"Orphaned heartbeat_logs: {orphaned_logs}")

        # Step 6: Check sensor_configs for ESP_472204
        esp_configs = await conn.fetch("""
            SELECT sc.sensor_type, sc.config_status
            FROM sensor_configs sc
            JOIN esp_devices ed ON sc.esp_id = ed.id
            WHERE ed.device_id = 'ESP_472204'
        """)
        print(f"\nSensor configs for ESP_472204: {len(esp_configs)}")
        for cfg in esp_configs:
            print(f"  {cfg['sensor_type']:20s} status={cfg['config_status']}")

    finally:
        await conn.close()

    print("\n=== CLEANUP COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
