"""
Cleanup script: Delete all sensor configs and sensor data for ESP_472204.
Preserves ESP device registration, zones, user accounts.

Usage: Run from El Servador/god_kaiser_server/.venv/Scripts/python.exe
"""
import asyncio
import asyncpg


ESP_UUID = "3c4c4130-95a7-44c6-b0e7-9069bd4e9d31"
DB_URL = "postgresql://god_kaiser:password@localhost:5432/god_kaiser_db"


async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        # Step 1: Delete sensor_configs
        result1 = await conn.execute(
            "DELETE FROM sensor_configs WHERE esp_id = $1", ESP_UUID
        )
        print(f"[1/2] sensor_configs: {result1}")

        # Step 2: Delete sensor_data
        result2 = await conn.execute(
            "DELETE FROM sensor_data WHERE esp_id = $1", ESP_UUID
        )
        print(f"[2/2] sensor_data: {result2}")

        # Verify
        configs_left = await conn.fetchval(
            "SELECT COUNT(*) FROM sensor_configs WHERE esp_id = $1", ESP_UUID
        )
        data_left = await conn.fetchval(
            "SELECT COUNT(*) FROM sensor_data WHERE esp_id = $1", ESP_UUID
        )
        print(f"\nVerification: sensor_configs={configs_left}, sensor_data={data_left}")
        print("SUCCESS" if configs_left == 0 and data_left == 0 else "PARTIAL")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
