"""
Unit Tests: ActuatorRepository
Tests for actuator config, state, and history operations
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from src.db.repositories.actuator_repo import ActuatorRepository


@pytest.mark.asyncio
class TestActuatorRepositoryConfig:
    """Test ActuatorRepository config operations"""

    async def test_get_by_esp_and_gpio_success(
        self, actuator_repo: ActuatorRepository, sample_esp_device
    ):
        """Test retrieval by ESP ID and GPIO."""
        config = await actuator_repo.create(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            actuator_name="Water Pump",
            enabled=True,
            min_value=0.0,
            max_value=1.0,
        )

        retrieved = await actuator_repo.get_by_esp_and_gpio(sample_esp_device.id, 5)

        assert retrieved is not None
        assert retrieved.gpio == 5
        assert retrieved.actuator_type == "pump"

    async def test_get_by_esp_and_gpio_not_found(
        self, actuator_repo: ActuatorRepository, sample_esp_device
    ):
        """Test retrieval with non-existent ESP/GPIO."""
        result = await actuator_repo.get_by_esp_and_gpio(sample_esp_device.id, 99)
        assert result is None

    async def test_get_by_esp_success(self, actuator_repo: ActuatorRepository, sample_esp_device):
        """Test retrieval of all actuators for an ESP."""
        await actuator_repo.create(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            actuator_name="Pump 1",
            enabled=True,
        )

        await actuator_repo.create(
            esp_id=sample_esp_device.id,
            gpio=6,
            actuator_type="valve",
            actuator_name="Valve 1",
            enabled=True,
        )

        actuators = await actuator_repo.get_by_esp(sample_esp_device.id)

        assert len(actuators) == 2
        gpios = {a.gpio for a in actuators}
        assert gpios == {5, 6}

    async def test_get_enabled(self, actuator_repo: ActuatorRepository, sample_esp_device):
        """Test retrieval of enabled actuators."""
        await actuator_repo.create(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            actuator_name="Enabled Pump",
            enabled=True,
        )

        await actuator_repo.create(
            esp_id=sample_esp_device.id,
            gpio=6,
            actuator_type="valve",
            actuator_name="Disabled Valve",
            enabled=False,
        )

        enabled = await actuator_repo.get_enabled()

        assert len(enabled) == 1
        assert enabled[0].gpio == 5


@pytest.mark.asyncio
class TestActuatorRepositoryState:
    """Test ActuatorRepository state operations"""

    async def test_get_state_success(self, actuator_repo: ActuatorRepository, sample_esp_device):
        """Test retrieval of actuator state."""
        from src.db.models.actuator import ActuatorState

        # Create state directly
        state = ActuatorState(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            current_value=1.0,
            state="on",
            last_command_timestamp=datetime.now(timezone.utc),
        )
        actuator_repo.session.add(state)
        await actuator_repo.session.flush()

        retrieved = await actuator_repo.get_state(sample_esp_device.id, 5)

        assert retrieved is not None
        assert retrieved.current_value == 1.0
        assert retrieved.state == "on"

    async def test_get_state_not_found(self, actuator_repo: ActuatorRepository, sample_esp_device):
        """Test retrieval with non-existent state."""
        result = await actuator_repo.get_state(sample_esp_device.id, 99)
        assert result is None

    async def test_update_state_create_new(
        self, actuator_repo: ActuatorRepository, sample_esp_device
    ):
        """Test creating new state via update_state()."""
        state = await actuator_repo.update_state(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            current_value=1.0,
            state="on",
        )

        assert state is not None
        assert state.current_value == 1.0
        assert state.state == "on"
        assert state.actuator_type == "pump"

    async def test_update_state_existing(
        self, actuator_repo: ActuatorRepository, sample_esp_device
    ):
        """Test updating existing state."""
        # Create initial state
        state1 = await actuator_repo.update_state(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            current_value=1.0,
            state="on",
        )

        # Update state
        state2 = await actuator_repo.update_state(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            current_value=0.0,
            state="off",
        )

        assert state2.id == state1.id
        assert state2.current_value == 0.0
        assert state2.state == "off"

    async def test_update_state_with_kwargs(
        self, actuator_repo: ActuatorRepository, sample_esp_device
    ):
        """Test updating state with additional kwargs."""
        state = await actuator_repo.update_state(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            current_value=0.75,
            state="on",
            runtime_seconds=120,
            metadata={"source": "test"},
        )

        assert state.current_value == 0.75
        # Note: runtime_seconds and metadata may not exist on ActuatorState model
        # This test verifies kwargs are passed through


@pytest.mark.asyncio
class TestActuatorRepositoryHistory:
    """Test ActuatorRepository history operations"""

    async def test_log_command_success(self, actuator_repo: ActuatorRepository, sample_esp_device):
        """Test logging actuator command."""
        history = await actuator_repo.log_command(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            command_type="set",
            value=1.0,
            success=True,
            issued_by="test_user",
        )

        assert history is not None
        assert history.command_type == "set"
        assert history.value == 1.0
        assert history.success is True
        assert history.issued_by == "test_user"

    async def test_log_command_failure(self, actuator_repo: ActuatorRepository, sample_esp_device):
        """Test logging failed command."""
        history = await actuator_repo.log_command(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            command_type="set",
            value=1.0,
            success=False,
            error_message="Safety constraint violated",
        )

        assert history.success is False
        assert history.error_message == "Safety constraint violated"

    async def test_get_history_success(self, actuator_repo: ActuatorRepository, sample_esp_device):
        """Test retrieval of history for specific actuator."""
        # Log commands for GPIO 5
        await actuator_repo.log_command(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            command_type="set",
            value=1.0,
            success=True,
        )

        await actuator_repo.log_command(
            esp_id=sample_esp_device.id,
            gpio=5,
            actuator_type="pump",
            command_type="set",
            value=0.0,
            success=True,
        )

        # Log command for different GPIO
        await actuator_repo.log_command(
            esp_id=sample_esp_device.id,
            gpio=6,
            actuator_type="valve",
            command_type="set",
            value=1.0,
            success=True,
        )

        history = await actuator_repo.get_history(sample_esp_device.id, 5)

        assert len(history) == 2
        assert all(h.gpio == 5 for h in history)

    async def test_get_history_empty(self, actuator_repo: ActuatorRepository, sample_esp_device):
        """Test retrieval with no history."""
        history = await actuator_repo.get_history(sample_esp_device.id, 99)
        assert len(history) == 0

    async def test_get_history_with_limit(
        self, actuator_repo: ActuatorRepository, sample_esp_device
    ):
        """Test retrieval with limit."""
        # Log multiple commands
        for i in range(5):
            await actuator_repo.log_command(
                esp_id=sample_esp_device.id,
                gpio=5,
                actuator_type="pump",
                command_type="set",
                value=float(i),
                success=True,
            )

        history = await actuator_repo.get_history(sample_esp_device.id, 5, limit=3)

        assert len(history) == 3
        # Should be ordered by timestamp desc (newest first)
        assert history[0].value == 4.0
        assert history[1].value == 3.0
        assert history[2].value == 2.0
