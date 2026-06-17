"""
Database Initialization Script

Creates all tables, seeds initial data, creates default admin user.
Run this script to initialize a fresh database.

Usage:
    poetry run python scripts/init_db.py
    or
    python -m scripts.init_db
"""

import asyncio
import os
import secrets
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


from src.core.config import get_settings
from src.core.logging_config import get_logger
from src.db.repositories.esp_repo import ESPRepository
from src.db.repositories.system_config_repo import SystemConfigRepository
from src.db.repositories.user_repo import UserRepository
from src.db.session import get_session

logger = get_logger(__name__)
settings = get_settings()


async def create_default_admin() -> tuple[str, str]:
    """
    Create default admin user if it doesn't exist.
    
    Returns:
        Tuple of (username, password) - password is generated if not in ENV
    """
    async for session in get_session():
        try:
            user_repo = UserRepository(session)
            
            # Check if admin already exists
            admin_user = await user_repo.get_by_username("admin")
            if admin_user:
                logger.info("Default admin user already exists")
                return ("admin", "[existing password]")
            
            # Get password from ENV or generate
            admin_password = os.getenv("ADMIN_PASSWORD")
            if not admin_password:
                # Generate secure random password
                admin_password = secrets.token_urlsafe(16)
                logger.warning(
                    f"\n{'='*60}\n"
                    f"DEFAULT ADMIN PASSWORD GENERATED:\n"
                    f"Username: admin\n"
                    f"Password: {admin_password}\n"
                    f"{'='*60}\n"
                    f"⚠️  SAVE THIS PASSWORD! It will not be shown again.\n"
                    f"To set a custom password, use ADMIN_PASSWORD environment variable.\n"
                )
            else:
                logger.info("Using ADMIN_PASSWORD from environment")
            
            # Create admin user
            admin_user = await user_repo.create_user(
                username="admin",
                email=os.getenv("ADMIN_EMAIL", "admin@example.com"),
                password=admin_password,
                role="admin",
                full_name="System Administrator",
            )
            
            await session.commit()
            logger.info(f"Default admin user created: {admin_user.username}")
            
            return ("admin", admin_password)
            
        except Exception as e:
            logger.error(f"Failed to create default admin: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            break


async def create_default_system_settings() -> None:
    """Create default system settings."""
    async for session in get_session():
        try:
            system_config_repo = SystemConfigRepository(session)

            # MQTT Auth settings
            await system_config_repo.set_mqtt_auth_config(
                enabled=False,
                username=None,
                password_hash=None,
            )

            await session.commit()
            logger.info("Default system settings created")

        except Exception as e:
            logger.error(f"Failed to create default system settings: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            break


async def create_wokwi_esp() -> bool:
    """
    Create Wokwi simulation ESP device if it doesn't exist.

    This ESP is pre-registered so Wokwi-simulated firmware can connect
    immediately without manual registration.

    ESP ID: ESP_WOKWI001 (matches WOKWI_ESP_ID in platformio.ini)

    Returns:
        True if created, False if already exists
    """
    from src.db.models.esp import ESPDevice

    WOKWI_ESP_ID = "ESP_WOKWI001"

    async for session in get_session():
        try:
            esp_repo = ESPRepository(session)

            # Check if Wokwi ESP already exists
            existing_esp = await esp_repo.get_by_device_id(WOKWI_ESP_ID)
            if existing_esp:
                logger.info(f"Wokwi ESP '{WOKWI_ESP_ID}' already exists")
                return False

            # Create Wokwi ESP device
            wokwi_esp = ESPDevice(
                device_id=WOKWI_ESP_ID,
                name="Wokwi Simulation ESP",
                hardware_type="ESP32_WROOM",
                status="offline",  # Will become online when Wokwi connects
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
                    "created_by": "init_db",
                    "description": "Pre-registered Wokwi ESP for firmware simulation testing",
                    "simulation_config": {
                        "sensors": {},
                        "actuators": {},
                        "auto_heartbeat": False,
                    },
                },
            )

            session.add(wokwi_esp)
            await session.commit()

            logger.info(
                f"\n{'='*60}\n"
                f"WOKWI ESP CREATED:\n"
                f"  Device ID: {WOKWI_ESP_ID}\n"
                f"  Name: Wokwi Simulation ESP\n"
                f"  Status: offline (waiting for Wokwi connection)\n"
                f"{'='*60}\n"
                f"To start Wokwi simulation:\n"
                f"  1. Start Mosquitto: mosquitto -v\n"
                f"  2. Start Server: poetry run uvicorn ...\n"
                f"  3. Build firmware: cd 'El Trabajante' && pio run -e wokwi_simulation\n"
                f"  4. Run Wokwi: wokwi-cli . --timeout 0\n"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to create Wokwi ESP: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            break

    return False


async def run_alembic_upgrade() -> None:
    """
    Run Alembic migrations to create/update database schema.
    
    Uses subprocess to run 'alembic upgrade head'.
    """
    import subprocess
    
    logger.info("Running Alembic migrations...")
    
    try:
        # Change to project root directory
        os.chdir(project_root)
        
        # Run alembic upgrade head
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True,
        )
        
        logger.info("Alembic migrations completed successfully")
        if result.stdout:
            logger.debug(f"Alembic output: {result.stdout}")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Alembic migration failed: {e}")
        if e.stdout:
            logger.error(f"stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"stderr: {e.stderr}")
        raise
    except FileNotFoundError:
        logger.error(
            "Alembic not found. Install it with: poetry add alembic"
        )
        raise


async def main() -> None:
    """
    Main initialization function.

    Steps:
    1. Run Alembic migrations (create tables)
    2. Create default admin user
    3. Create default system settings
    4. Create Wokwi ESP device (for simulation testing)
    """
    logger.info("=" * 60)
    logger.info("Database Initialization Script")
    logger.info("=" * 60)

    try:
        # Step 1: Run Alembic migrations
        logger.info("Step 1: Running database migrations...")
        await run_alembic_upgrade()

        # Step 2: Create default admin
        logger.info("Step 2: Creating default admin user...")
        username, password = await create_default_admin()

        # Step 3: Create default system settings
        logger.info("Step 3: Creating default system settings...")
        await create_default_system_settings()

        # Step 4: Create Wokwi ESP device
        logger.info("Step 4: Creating Wokwi ESP device...")
        wokwi_created = await create_wokwi_esp()

        logger.info("=" * 60)
        logger.info("Database initialization completed successfully!")
        logger.info("=" * 60)

        if password != "[existing password]":
            logger.info(f"\nAdmin credentials:")
            logger.info(f"  Username: {username}")
            logger.info(f"  Password: {password}")
            logger.info("\n⚠️  Save these credentials securely!")

        if wokwi_created:
            logger.info("\n🎮 Wokwi ESP 'ESP_WOKWI001' ready for simulation testing!")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
