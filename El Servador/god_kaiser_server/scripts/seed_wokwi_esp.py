"""
Wokwi ESP Seed Script

Creates the Wokwi simulation ESP device (ESP_00000001) in the database.
This allows Wokwi-simulated firmware to connect immediately.

Usage:
    poetry run python scripts/seed_wokwi_esp.py

Prerequisites:
    - Database must exist (run init_db.py first or alembic upgrade head)
    - PostgreSQL must be running

Note:
    ESP ID Format: ESP_00000001 (8 hex characters, matches Pydantic pattern)
    The firmware in El Trabajante uses this ID for Wokwi simulation.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone

from src.core.logging_config import get_logger
from src.core.config import get_settings
from src.db.models.esp import ESPDevice
from src.db.repositories.esp_repo import ESPRepository
from src.db.session import get_session

logger = get_logger(__name__)

# Wokwi ESP IDs - matches platformio.ini environments (wokwi_esp01, wokwi_esp02, wokwi_esp03)
WOKWI_ESP_IDS = [
    "ESP_00000001",
    "ESP_00000002",
    "ESP_00000003",
]


def create_wokwi_esp_device(device_id: str, index: int) -> ESPDevice:
    """
    Create a Wokwi ESP device object with consistent configuration.

    Args:
        device_id: ESP device ID (e.g., "ESP_00000001")
        index: Device index (1-based, for display purposes)

    Returns:
        ESPDevice object ready to be added to session
    """
    return ESPDevice(
        device_id=device_id,
        name=f"Wokwi Simulation ESP #{index}",
        hardware_type="ESP32_WROOM",
        status="approved",  # Pre-approved (Wokwi is controlled environment)
        discovered_at=datetime.now(timezone.utc),
        approved_at=datetime.now(timezone.utc),
        approved_by="seed_script",
        zone_id=None,
        zone_name=None,
        master_zone_id=None,
        is_zone_master=False,
        kaiser_id="god",
        capabilities={
            "max_sensors": 20,
            "max_actuators": 12,
            "features": ["heartbeat", "sensors", "actuators", "wokwi_simulation"],
            "wokwi": True,
        },
        device_metadata={
            "source": "wokwi_simulation",
            "created_by": "seed_wokwi_esp",
            "description": f"Pre-registered Wokwi ESP #{index} for firmware simulation testing",
            "simulation_config": {
                "sensors": {},
                "actuators": {},
                "auto_heartbeat": False,
            },
            "device_index": index,
        },
    )


def _is_soft_deleted(device: ESPDevice) -> bool:
    """Return True when device is marked as soft-deleted."""
    return device.deleted_at is not None or device.status == "deleted"


async def seed_wokwi_esp() -> dict[str, int]:
    """
    Create Wokwi simulation ESP devices if they don't exist.

    Returns:
        Dictionary with counts: {"created": N, "reactivated": M, "existing": K, "failed": X}
    """
    results = {"created": 0, "reactivated": 0, "existing": 0, "failed": 0}

    session_gen = get_session()
    session = await anext(session_gen)
    try:
        esp_repo = ESPRepository(session)

        for index, esp_id in enumerate(WOKWI_ESP_IDS, start=1):
            try:
                # Check if ESP already exists, including soft-deleted rows.
                existing_esp = await esp_repo.get_by_device_id(esp_id, include_deleted=True)
                if existing_esp:
                    if _is_soft_deleted(existing_esp):
                        # Reactivate previously deleted Wokwi devices.
                        existing_esp.deleted_at = None
                        existing_esp.deleted_by = None
                        existing_esp.status = "approved"
                        existing_esp.approved_at = datetime.now(timezone.utc)
                        existing_esp.approved_by = "seed_script"
                        existing_esp.rejection_reason = None
                        await session.commit()
                        logger.info(f"[OK] Reactivated Wokwi ESP '{esp_id}' (status=approved)")
                        results["reactivated"] += 1
                    else:
                        logger.info(
                            f"[OK] Wokwi ESP '{esp_id}' already exists (status: {existing_esp.status})"
                        )
                        results["existing"] += 1
                    continue

                # Create new Wokwi ESP device
                wokwi_esp = create_wokwi_esp_device(esp_id, index)
                session.add(wokwi_esp)
                await session.commit()

                logger.info(f"[OK] Created Wokwi ESP '{esp_id}'")
                results["created"] += 1

            except Exception as e:
                logger.error(f"Failed to upsert Wokwi ESP '{esp_id}': {e}", exc_info=True)
                await session.rollback()
                results["failed"] += 1
                # Continue with next device
    except Exception as e:
        logger.error(f"Failed to seed Wokwi ESPs: {e}", exc_info=True)
        raise
    finally:
        await session_gen.aclose()

    return results


async def main() -> None:
    """Main entry point."""
    print("=" * 60)
    print("Wokwi ESP Seed Script (Multi-Device)")
    print("=" * 60)
    print()

    db_url = get_settings().database.url
    print(f"Database URL: {db_url}")
    if db_url.startswith("sqlite"):
        print("WARNING: SQLite is active. This does NOT seed the Docker/PostgreSQL stack.")
        print("Set DATABASE_URL to PostgreSQL before running this script for Docker setup.")
        print()

    print(f"Creating {len(WOKWI_ESP_IDS)} Wokwi ESP devices:")
    for i, esp_id in enumerate(WOKWI_ESP_IDS, start=1):
        print(f"  {i}. {esp_id}")
    print()

    try:
        results = await seed_wokwi_esp()

        print()
        print("Results:")
        print(f"  Created: {results['created']}")
        print(f"  Reactivated: {results['reactivated']}")
        print(f"  Already exist: {results['existing']}")
        if results['failed'] > 0:
            print(f"  Failed: {results['failed']}")
        print()

        if results['created'] > 0 or results['reactivated'] > 0:
            print("Next steps:")
            print("  1. Mosquitto MQTT broker prüfen (läuft als Windows Service)")
            print("  2. God-Kaiser Server starten (poetry run uvicorn ...)")
            print("  3. Frontend starten (npm run dev)")
            print()
            print("  4. USER: Firmware bauen (choose one):")
            print("     - pio run -e wokwi_esp01  # ESP_00000001")
            print("     - pio run -e wokwi_esp02  # ESP_00000002")
            print("     - pio run -e wokwi_esp03  # ESP_00000003")
            print()
            print("  5. USER: Wokwi starten:")
            print("     - VS Code Extension: Select environment in PlatformIO panel")
            print("     - CLI: wokwi-cli . --timeout 0 --firmware .pio/build/wokwi_esp01/firmware.bin")
            print()
            print("Die ESPs erscheinen im Frontend sobald Wokwi verbindet.")
        else:
            print("[OK] All Wokwi ESPs already exist and are active - no action needed")

        print()
        print("=" * 60)

        if results['failed'] > 0:
            sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
