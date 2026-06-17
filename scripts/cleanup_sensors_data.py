"""
Cleanup script: Delete remaining sensor_data for ESP_472204.
"""
import asyncio
import asyncpg

ESP_UUID = "3c4c4130-95a7-44c6-b0e7-9069bd4e9d31"
DB_URL = "postgresql://god_kaiser:password@localhost:5432/god_kaiser_db"


async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        result = await conn.execute(
            "DELETE FROM sensor_data WHERE esp_id = $1", ESP_UUID
        )
        print(f"sensor_data: {result}")
        remaining = await conn.fetchval(
            "SELECT COUNT(*) FROM sensor_data WHERE esp_id = $1", ESP_UUID
        )
        print(f"Remaining: {remaining}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
