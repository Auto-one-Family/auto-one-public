#!/usr/bin/env python3
"""
One-off: fix CO₂ sensor on ESP_AEAE64 from ANALOG → UART (AUT-527).

Usage (from god_kaiser_server, with DATABASE_URL set):
  poetry run python scripts/fix_esp_aeae64_co2_uart.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Allow running as script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.models.esp import ESPDevice  # noqa: E402
from src.db.models.sensor import SensorConfig  # noqa: E402

ESP_DEVICE_ID = "ESP_AEAE64"
UART_META = {
    "uart_rx_pin": 18,
    "uart_tx_pin": 17,
    "uart_baud": 9600,
    "sensor_model": "SEN0220",
}


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        esp_result = await session.execute(
            select(ESPDevice.id).where(ESPDevice.esp_id == ESP_DEVICE_ID)
        )
        esp_row = esp_result.scalar_one_or_none()
        if esp_row is None:
            print(f"ESP {ESP_DEVICE_ID} not found")
            return

        sensors = await session.execute(
            select(SensorConfig).where(
                SensorConfig.esp_id == esp_row,
                SensorConfig.sensor_type.ilike("%co2%"),
            )
        )
        rows = list(sensors.scalars().all())
        if not rows:
            print(f"No CO₂ sensor on {ESP_DEVICE_ID}")
            return

        for sensor in rows:
            merged_meta = dict(sensor.sensor_metadata or {})
            merged_meta.update(UART_META)
            await session.execute(
                update(SensorConfig)
                .where(SensorConfig.id == sensor.id)
                .values(
                    interface_type="UART",
                    gpio=18,
                    i2c_address=None,
                    sensor_metadata=merged_meta,
                )
            )
            print(
                f"Updated sensor {sensor.id} ({sensor.sensor_type}): "
                f"UART rx=18 tx=17 baud=9600"
            )

        await session.commit()
    await engine.dispose()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
