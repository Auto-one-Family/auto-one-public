"""
Database cleanup script for real ESP32 fresh setup.
Removes all device/sensor/actuator data while preserving users and system essentials.
"""

import asyncpg
import asyncio


TABLES_TO_CLEAR = [
    # Children first (foreign key order)
    "logic_execution_history",
    "cross_esp_logic",
    "sensor_data",
    "sensor_configs",
    "actuator_history",
    "actuator_states",
    "actuator_configs",
    "esp_heartbeat_logs",
    "esp_ownership",
    "subzone_configs",
    "ai_predictions",
    "audit_logs",
    "kaiser_registry",
    "library_metadata",
    "system_config",
    # Parent last
    "esp_devices",
]

# Tables to KEEP:
# - user_accounts
# - token_blacklist
# - sensor_type_defaults (system config)
# - alembic_version (migration tracking)


async def main():
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="god_kaiser",
        password="password",
        database="god_kaiser_db",
    )

    print("=== Database Cleanup for Real ESP32 Setup ===\n")

    for table in TABLES_TO_CLEAR:
        try:
            result = await conn.execute(f"DELETE FROM {table}")
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                print(f"  Cleared: {table} ({count} rows deleted)")
            else:
                print(f"  Empty:   {table}")
        except Exception as e:
            print(f"  Error:   {table} - {e}")

    print("\n--- Preserved tables ---")
    for table in ["user_accounts", "token_blacklist", "sensor_type_defaults"]:
        count = await conn.fetchval(f"SELECT count(*) FROM {table}")
        print(f"  Kept:    {table} ({count} rows)")

    await conn.close()
    print("\nDatabase cleanup complete!")


if __name__ == "__main__":
    asyncio.run(main())
