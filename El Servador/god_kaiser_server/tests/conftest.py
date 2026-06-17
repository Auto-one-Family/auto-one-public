"""
Pytest Configuration for God-Kaiser Server Tests.

FIX 2025-12-11: Test infrastructure overhaul
- Environment variables set BEFORE any src imports (prevents eager engine loading)
- In-memory SQLite with StaticPool for Windows compatibility
- override_get_db with autouse=True for proper DB isolation
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

# =============================================================================
# FIX 6: Set test environment variables BEFORE any src imports
# This prevents eager engine loading in session.py
# =============================================================================
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DATABASE_AUTO_INIT"] = "false"
os.environ["TESTING"] = "true"

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fastapi import Depends  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.api.deps import get_db  # noqa: E402
from src.db.base import Base  # noqa: E402
from src.db.models import (  # noqa: F401, E402 - imports needed for SQLAlchemy model registration
    actuator,
    ai,
    audit_log,
    auth,
    command_contract,
    dashboard,
    diagnostic,
    esp,
    esp_heartbeat,
    kaiser,
    library,
    logic,
    notification,
    plugin,
    sensor,
    sensor_type_defaults,
    subzone,
    system,
    user,
    zone,
)
from src.db.repositories.actuator_repo import ActuatorRepository  # noqa: E402
from src.db.repositories.esp_repo import ESPRepository  # noqa: E402
from src.db.repositories.sensor_repo import SensorRepository  # noqa: E402
from src.db.repositories.subzone_repo import SubzoneRepository  # noqa: E402
from src.db.repositories.user_repo import UserRepository  # noqa: E402

# =============================================================================
# FIX 3: In-memory SQLite with StaticPool for Windows compatibility
# StaticPool ensures all connections share the same in-memory database
# =============================================================================
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# =============================================================================
# Pytest Markers for Test Categorization (Phase 2 Core Services)
# =============================================================================
def pytest_configure(config):
    """Register custom markers for test categorization."""
    config.addinivalue_line("markers", "critical: Safety-critical tests (must never fail)")
    config.addinivalue_line("markers", "sensor: SensorManager tests")
    config.addinivalue_line("markers", "actuator: ActuatorManager tests")
    config.addinivalue_line("markers", "safety: SafetyController tests")
    config.addinivalue_line("markers", "edge_case: Edge case tests")
    config.addinivalue_line("markers", "ds18b20: DS18B20 specific tests")
    config.addinivalue_line("markers", "onewire: OneWire tests")
    config.addinivalue_line("markers", "flow_a: Sensor data flow tests (ESP→Server→DB)")
    config.addinivalue_line("markers", "flow_b: Actuator command flow tests (Server→ESP)")
    config.addinivalue_line("markers", "flow_c: Emergency stop flow tests")
    config.addinivalue_line("markers", "pwm: PWM actuator tests")
    config.addinivalue_line("markers", "gpio: GPIO conflict tests")
    config.addinivalue_line("markers", "hardware: Tests requiring real hardware (skipped in CI)")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Create a test database engine.

    Uses in-memory SQLite with StaticPool for Windows compatibility.
    All connections share the same in-memory database.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a test database session.

    Tests can use commit() freely - the in-memory database is
    recreated for each test function anyway via test_engine.
    """
    async_session_maker = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def test_session(db_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Alias for db_session - for backwards compatibility."""
    yield db_session


@pytest_asyncio.fixture
async def esp_repo(db_session: AsyncSession) -> ESPRepository:
    """Create ESPRepository instance."""
    return ESPRepository(db_session)


@pytest_asyncio.fixture
async def sensor_repo(db_session: AsyncSession) -> SensorRepository:
    """Create SensorRepository instance."""
    return SensorRepository(db_session)


@pytest_asyncio.fixture
async def actuator_repo(db_session: AsyncSession) -> ActuatorRepository:
    """Create ActuatorRepository instance."""
    return ActuatorRepository(db_session)


@pytest_asyncio.fixture
async def user_repo(db_session: AsyncSession) -> UserRepository:
    """Create UserRepository instance."""
    return UserRepository(db_session)


@pytest_asyncio.fixture
async def subzone_repo(db_session: AsyncSession) -> SubzoneRepository:
    """Create SubzoneRepository instance."""
    return SubzoneRepository(db_session)


@pytest_asyncio.fixture
async def sample_esp_device(db_session: AsyncSession):
    """Create a sample ESP device for testing."""
    from src.db.models.esp import ESPDevice  # noqa: E402

    device = ESPDevice(
        device_id="ESP_TEST_001",
        name="Test ESP32",
        ip_address="192.168.1.100",
        mac_address="AA:BB:CC:DD:EE:FF",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession):
    """Create a sample user for testing."""
    from src.db.models.user import User  # noqa: E402

    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_esp_with_zone(db_session: AsyncSession):
    """Create a sample ESP device with zone assigned for subzone testing."""
    from src.db.models.esp import ESPDevice  # noqa: E402

    device = ESPDevice(
        device_id="ESP_WITH_ZONE",
        name="Test ESP with Zone",
        ip_address="192.168.1.101",
        mac_address="AA:BB:CC:DD:EE:01",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id="test_zone",
        master_zone_id="master_test",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def sample_esp_no_zone(db_session: AsyncSession):
    """Create a sample ESP device without zone assigned."""
    from src.db.models.esp import ESPDevice  # noqa: E402

    device = ESPDevice(
        device_id="ESP_NO_ZONE",
        name="Test ESP No Zone",
        ip_address="192.168.1.102",
        mac_address="AA:BB:CC:DD:EE:02",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


# ==================== Hardware Validation Test Fixtures ====================


@pytest_asyncio.fixture
async def sample_esp_c3(db_session: AsyncSession):
    """Create a sample ESP32-C3 device for testing.

    ESP32-C3 (XIAO) has different hardware constraints than WROOM:
    - GPIO Range: 0-21 (not 0-39!)
    - I2C Pins: GPIO 4 (SDA), GPIO 5 (SCL) - not 21/22!
    - No Input-Only Pins (all bidirectional)
    """
    from src.db.models.esp import ESPDevice  # noqa: E402

    device = ESPDevice(
        device_id="ESP_C3_TEST_001",
        name="Test ESP32-C3",
        ip_address="192.168.1.101",
        mac_address="AA:BB:CC:DD:EE:C3",
        firmware_version="1.0.0",
        hardware_type="XIAO_ESP32_C3",  # ← CRITICAL!
        status="online",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def gpio_service(
    db_session: AsyncSession,
    sensor_repo: "SensorRepository",
    actuator_repo: "ActuatorRepository",
    esp_repo: "ESPRepository",
):
    """Create real GpioValidationService instance.

    This fixture creates a real service (not mocked) for testing
    hardware validation logic.
    """
    from src.services.gpio_validation_service import GpioValidationService  # noqa: E402

    service = GpioValidationService(
        session=db_session,
        sensor_repo=sensor_repo,
        actuator_repo=actuator_repo,
        esp_repo=esp_repo,
    )
    return service


@pytest.fixture
def mock_mqtt_publisher_for_subzone():
    """
    Create a mock MQTT publisher for subzone service tests.

    Provides mock client with publish method for testing.
    """
    from unittest.mock import MagicMock  # noqa: E402

    mock_publisher = MagicMock()
    mock_publisher.client = MagicMock()
    mock_publisher.client.publish = MagicMock(return_value=MagicMock(rc=0))
    mock_publisher.publish_raw = MagicMock(return_value=True)
    mock_publisher.publish_emergency_broadcast = MagicMock(return_value=True)
    mock_publisher.publish_actuator_emergency = MagicMock(return_value=True)
    return mock_publisher


# =============================================================================
# FIX 2: App Dependency Override with autouse=True
# This ensures ALL tests use the test database, not the production database
# =============================================================================


@pytest_asyncio.fixture(scope="function", autouse=True)
async def override_get_db(test_engine: AsyncEngine):
    """
    Override the app's get_db dependency with the test database.

    AUTOUSE=True: This fixture is automatically loaded for ALL tests.
    This ensures FastAPI always uses the test database.
    """
    from src.main import app  # noqa: E402
    from src.api.deps import get_db  # noqa: E402

    # Create session maker for test engine
    test_session_maker = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def override_get_db_func():
        async with test_session_maker() as session:
            try:
                yield session
            finally:
                pass

    # Apply override
    app.dependency_overrides[get_db] = override_get_db_func

    yield

    # Cleanup - remove override
    app.dependency_overrides.pop(get_db, None)


# =============================================================================
# Mock MQTT Publisher and ActuatorService for Tests
# This prevents tests from hanging on MQTT connection attempts
# =============================================================================


@pytest_asyncio.fixture(scope="function", autouse=True)
async def override_mqtt_publisher(test_engine: AsyncEngine):
    """
    Override the app's get_mqtt_publisher dependency with a mock.

    AUTOUSE=True: This fixture is automatically loaded for ALL tests.
    This prevents tests from hanging on MQTT connection attempts.
    """
    from unittest.mock import MagicMock  # noqa: E402

    from src.main import app  # noqa: E402
    from src.api.deps import get_mqtt_publisher  # noqa: E402

    # Create mock publisher with all methods used across services
    mock_publisher = MagicMock()
    mock_publisher.publish_actuator_command.return_value = True
    mock_publisher.publish_sensor_config.return_value = True
    mock_publisher.publish_actuator_config.return_value = True
    mock_publisher.publish_system_command.return_value = True
    mock_publisher.publish_pi_enhanced_response.return_value = True
    mock_publisher._publish_with_retry.return_value = True
    # SubzoneService uses publisher.publish_raw() (post-AUT-225)
    mock_publisher.client = MagicMock()
    mock_publisher.client.publish.return_value = True
    mock_publisher.publish_raw = MagicMock(return_value=True)

    def override_get_mqtt_publisher_func():
        return mock_publisher

    # Apply override
    app.dependency_overrides[get_mqtt_publisher] = override_get_mqtt_publisher_func

    yield mock_publisher

    # Cleanup - remove override
    app.dependency_overrides.pop(get_mqtt_publisher, None)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def override_actuator_service(test_engine: AsyncEngine):
    """
    Override the app's get_actuator_service dependency with a test instance.

    AUTOUSE=True: This fixture is automatically loaded for ALL tests.
    This ensures ActuatorService uses mocked Publisher in tests.
    """
    from unittest.mock import MagicMock  # noqa: E402

    from src.main import app  # noqa: E402
    from src.api.deps import get_actuator_service  # noqa: E402
    from src.db.repositories import ActuatorRepository, ESPRepository  # noqa: E402
    from src.services.actuator_service import ActuatorService  # noqa: E402
    from src.services.safety_service import SafetyService  # noqa: E402

    # Session factory that uses the test engine (not the global production engine)
    test_session_maker = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def test_session_factory():
        async with test_session_maker() as session:
            yield session

    def override_get_actuator_service_func(db: AsyncSession = Depends(get_db)):
        """
        Override function that receives db session from FastAPI dependency injection.

        Args:
            db: Database session (injected by FastAPI from override_get_db)
        """
        # Create repositories with the injected session
        actuator_repo = ActuatorRepository(db)
        esp_repo = ESPRepository(db)

        # Create safety service
        safety_service = SafetyService(actuator_repo, esp_repo)

        # Create mocked publisher
        mock_publisher = MagicMock()
        mock_publisher.publish_actuator_command.return_value = True
        mock_publisher._publish_with_retry.return_value = True

        # Create ActuatorService with mocked publisher and test session factory
        # to avoid using the global production engine in _command_transaction
        actuator_service = ActuatorService(
            actuator_repo=actuator_repo,
            safety_service=safety_service,
            publisher=mock_publisher,
            session_factory=test_session_factory,
        )

        return actuator_service

    # Apply override
    app.dependency_overrides[get_actuator_service] = override_get_actuator_service_func

    yield  # Cleanup - remove override
    app.dependency_overrides.pop(get_actuator_service, None)


# =============================================================================
# Notification Test Fixtures (Phase 4A)
# =============================================================================


@pytest_asyncio.fixture
async def sample_notification(db_session: AsyncSession, sample_user):
    """Create a test notification in the DB."""
    from src.db.models.notification import Notification  # noqa: E402

    notif = Notification(
        user_id=sample_user.id,
        title="Test Alert",
        body="Sensor XYZ hat Schwellwert ueberschritten",
        channel="websocket",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
    )
    db_session.add(notif)
    await db_session.flush()
    await db_session.refresh(notif)
    return notif


@pytest_asyncio.fixture
async def sample_preferences(db_session: AsyncSession, sample_user):
    """Create test NotificationPreferences."""
    from src.db.models.notification import NotificationPreferences  # noqa: E402

    prefs = NotificationPreferences(
        user_id=sample_user.id,
        websocket_enabled=True,
        email_enabled=False,
        email_severities=["critical"],
    )
    db_session.add(prefs)
    await db_session.flush()
    await db_session.refresh(prefs)
    return prefs


@pytest.fixture
def mock_email_service():
    """Mock for EmailService — no real email delivery in tests."""
    from unittest.mock import AsyncMock  # noqa: E402

    service = AsyncMock()
    service.is_available = True
    service.send_email = AsyncMock(return_value=True)
    service.send_critical_alert = AsyncMock(return_value=True)
    service.send_digest = AsyncMock(return_value=True)
    service.send_test_email = AsyncMock(return_value=True)
    service.provider_name = "Mock"
    return service


@pytest.fixture
def mock_ws_manager():
    """Mock for WebSocketManager — no real WS broadcast in tests."""
    from unittest.mock import AsyncMock, patch  # noqa: E402

    mock_instance = AsyncMock()
    mock_instance.broadcast = AsyncMock()
    mock_instance.connection_count = 0
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_instance,
    ):
        yield mock_instance
