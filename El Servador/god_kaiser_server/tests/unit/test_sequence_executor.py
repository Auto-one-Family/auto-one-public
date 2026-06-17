"""
Unit Tests für SequenceActionExecutor

Tests für Sequenz-Actions, Validierung, Execution und Error-Handling.

Phase: 3 - Sequence Action Executor
Status: IMPLEMENTED
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.error_codes import SequenceErrorCode
from src.services.logic.actions.base import ActionResult
from src.services.logic.actions.sequence_executor import (
    SequenceActionExecutor,
    SequenceProgress,
    SequenceStatus,
    StepResult,
)


@pytest.fixture
def websocket_manager():
    """Mock WebSocket Manager."""
    mock = AsyncMock()
    mock.broadcast = AsyncMock()
    return mock


@pytest.fixture
def mock_actuator_executor():
    """Mock Actuator Executor."""
    executor = Mock()
    executor.supports = Mock(side_effect=lambda t: t in ["actuator_command", "actuator"])
    executor.execute = AsyncMock(
        return_value=ActionResult(success=True, message="Actuator executed")
    )
    return executor


@pytest.fixture
def mock_delay_executor():
    """Mock Delay Executor."""
    executor = Mock()
    executor.supports = Mock(side_effect=lambda t: t == "delay")
    executor.execute = AsyncMock(return_value=ActionResult(success=True, message="Delay completed"))
    return executor


@pytest.fixture
def sequence_executor(websocket_manager, mock_actuator_executor, mock_delay_executor):
    """Initialisierter SequenceActionExecutor mit Mocks."""
    executor = SequenceActionExecutor(websocket_manager=websocket_manager)
    executor.set_action_executors([mock_actuator_executor, mock_delay_executor])
    return executor


class TestSequenceActionExecutor:
    """Test Suite für SequenceActionExecutor."""

    def test_supports_method(self, sequence_executor):
        """Test: supports() gibt True für 'sequence' zurück."""
        assert sequence_executor.supports("sequence") is True
        assert sequence_executor.supports("actuator") is False
        assert sequence_executor.supports("delay") is False

    def test_validate_empty_steps(self, sequence_executor):
        """Test: Validierung schlägt bei leeren Steps fehl."""
        action = {"type": "sequence", "steps": []}

        result = sequence_executor._validate_sequence(action)

        assert result is not None
        assert result.success is False
        assert result.data["error_code"] == SequenceErrorCode.SEQ_EMPTY_STEPS

    def test_validate_too_many_steps(self, sequence_executor):
        """Test: Validierung schlägt bei zu vielen Steps fehl."""
        action = {
            "type": "sequence",
            "steps": [{"action": {"type": "delay"}}] * 51,  # MAX = 50
        }

        result = sequence_executor._validate_sequence(action)

        assert result is not None
        assert result.success is False
        assert result.data["error_code"] == SequenceErrorCode.SEQ_TOO_MANY_STEPS

    def test_validate_invalid_action_type(self, sequence_executor):
        """Test: Validierung schlägt bei unbekanntem Action-Type fehl."""
        action = {
            "type": "sequence",
            "steps": [{"action": {"type": "unknown_type"}}],
        }

        result = sequence_executor._validate_sequence(action)

        assert result is not None
        assert result.success is False
        assert result.data["error_code"] == SequenceErrorCode.SEQ_INVALID_ACTION_TYPE

    def test_validate_nested_sequence_rejected(self, sequence_executor):
        """Test: Verschachtelte Sequenzen werden abgelehnt."""
        action = {
            "type": "sequence",
            "steps": [{"action": {"type": "sequence", "steps": []}}],
        }

        result = sequence_executor._validate_sequence(action)

        assert result is not None
        assert result.success is False
        assert result.data["error_code"] == SequenceErrorCode.SEQ_CIRCULAR_REFERENCE

    def test_validate_missing_action_and_delay(self, sequence_executor):
        """Test: Step ohne action und delay_seconds wird abgelehnt."""
        action = {
            "type": "sequence",
            "steps": [{"name": "Invalid step"}],  # Weder action noch delay_seconds
        }

        result = sequence_executor._validate_sequence(action)

        assert result is not None
        assert result.success is False
        assert result.data["error_code"] == SequenceErrorCode.SEQ_STEP_MISSING_ACTION

    def test_validate_invalid_delay_value(self, sequence_executor):
        """Test: Ungültiger Delay-Wert wird abgelehnt."""
        action = {
            "type": "sequence",
            "steps": [{"delay_seconds": 5000}],  # Über 3600 Sekunden
        }

        result = sequence_executor._validate_sequence(action)

        assert result is not None
        assert result.success is False
        assert result.data["error_code"] == SequenceErrorCode.SEQ_INVALID_DELAY

    @pytest.mark.asyncio
    async def test_execute_returns_immediately(self, sequence_executor):
        """Test: execute() gibt sofort ActionResult zurück (non-blocking)."""
        action = {
            "type": "sequence",
            "steps": [{"delay_seconds": 1}],
        }
        context = {"rule_id": "test-rule"}

        start = datetime.now()
        result = await sequence_executor.execute(action, context)
        end = datetime.now()

        # Sollte NICHT 1 Sekunde warten
        assert (end - start).total_seconds() < 0.5
        assert result.success is True
        assert "sequence_id" in result.data

    @pytest.mark.asyncio
    async def test_simple_sequence_execution(self, sequence_executor, mock_actuator_executor):
        """Test: Einfache Sequenz wird erfolgreich ausgeführt."""
        action = {
            "type": "sequence",
            "sequence_id": "test-seq",
            "steps": [
                {"action": {"type": "actuator_command", "esp_id": "ESP_TEST", "gpio": 10}},
            ],
        }
        context = {"rule_id": "test-rule"}

        result = await sequence_executor.execute(action, context)
        assert result.success is True

        # Warte kurz bis Sequenz läuft
        await asyncio.sleep(0.2)

        # Prüfe ob actuator execute aufgerufen wurde
        mock_actuator_executor.execute.assert_called_once()

        # Prüfe Status
        status = sequence_executor.get_sequence_status("test-seq")
        assert status is not None
        assert status["status"] in ["running", "completed"]

    @pytest.mark.asyncio
    async def test_delay_step(self, sequence_executor):
        """Test: Delay-Step wird korrekt ausgeführt."""
        action = {
            "type": "sequence",
            "sequence_id": "delay-seq",
            "steps": [{"delay_seconds": 0.1}],  # 100ms
        }
        context = {"rule_id": "test-rule"}

        result = await sequence_executor.execute(action, context)
        assert result.success is True

        # Warte bis Sequenz fertig ist
        await asyncio.sleep(0.3)

        status = sequence_executor.get_sequence_status("delay-seq")
        assert status is not None
        assert status["status"] == "completed"
        assert status["total_steps"] == 1

    @pytest.mark.asyncio
    async def test_abort_on_failure(self, sequence_executor, mock_actuator_executor):
        """Test: Sequenz bricht bei Fehler ab wenn abort_on_failure=True."""
        # Mocke fehlgeschlagene Aktion
        mock_actuator_executor.execute = AsyncMock(
            return_value=ActionResult(success=False, message="Actuator failed")
        )

        action = {
            "type": "sequence",
            "sequence_id": "abort-seq",
            "abort_on_failure": True,
            "steps": [
                {"action": {"type": "actuator_command"}},
                {"delay_seconds": 1},  # Sollte nicht erreicht werden
            ],
        }
        context = {"rule_id": "test-rule"}

        await sequence_executor.execute(action, context)
        await asyncio.sleep(0.3)

        status = sequence_executor.get_sequence_status("abort-seq")
        assert status is not None
        assert status["status"] == "failed"
        assert status["current_step"] == 0  # Bricht bei Step 0 ab
        assert len(status["step_results"]) == 1  # Nur 1 Step ausgeführt

    @pytest.mark.asyncio
    async def test_continue_on_failure(self, sequence_executor, mock_actuator_executor):
        """Test: Sequenz läuft weiter bei Fehler wenn on_failure=continue."""
        # Erster Call schlägt fehl, zweiter erfolgreich
        mock_actuator_executor.execute = AsyncMock(
            side_effect=[
                ActionResult(success=False, message="Failed"),
                ActionResult(success=True, message="Success"),
            ]
        )

        action = {
            "type": "sequence",
            "sequence_id": "continue-seq",
            "abort_on_failure": False,
            "steps": [
                {"action": {"type": "actuator_command"}, "on_failure": "continue"},
                {"action": {"type": "actuator_command"}},
            ],
        }
        context = {"rule_id": "test-rule"}

        await sequence_executor.execute(action, context)
        await asyncio.sleep(0.3)

        status = sequence_executor.get_sequence_status("continue-seq")
        assert status is not None
        assert len(status["step_results"]) == 2  # Beide Steps ausgeführt
        assert status["step_results"][0]["success"] is False
        assert status["step_results"][1]["success"] is True

    @pytest.mark.asyncio
    async def test_cancel_sequence(self, sequence_executor):
        """Test: Laufende Sequenz kann abgebrochen werden."""
        action = {
            "type": "sequence",
            "sequence_id": "cancel-seq",
            "steps": [{"delay_seconds": 2}],  # 2 Sekunden Delay
        }
        context = {"rule_id": "test-rule"}

        await sequence_executor.execute(action, context)
        await asyncio.sleep(0.1)  # Kurz warten bis Sequenz läuft

        # Cancel
        cancelled = await sequence_executor.cancel_sequence("cancel-seq", "Test cancel")
        assert cancelled is True

        await asyncio.sleep(0.2)

        status = sequence_executor.get_sequence_status("cancel-seq")
        assert status is not None
        assert status["status"] == "cancelled"
        assert "cancel" in status["error"].lower()

    @pytest.mark.asyncio
    async def test_concurrent_limit(self, sequence_executor):
        """Test: Concurrent-Limit wird eingehalten."""
        # Setze Limit auf 2
        sequence_executor.MAX_CONCURRENT_SEQUENCES = 2

        # Starte 2 Sequenzen mit langen Delays (damit sie noch laufen wenn 3. gestartet wird)
        for i in range(2):
            action = {
                "type": "sequence",
                "sequence_id": f"seq-{i}",
                "steps": [{"delay_seconds": 10}],  # 10 Sekunden damit sie nicht zu früh beenden
            }
            result = await sequence_executor.execute(action, {"rule_id": "test"})
            assert result.success is True

        # Kurz warten damit die Sequenzen in den RUNNING-Status wechseln
        await asyncio.sleep(0.1)

        # Verifizieren dass beide laufen
        running_count = sum(1 for s in sequence_executor._sequences.values() if s.is_running)
        assert running_count == 2, f"Expected 2 running sequences, got {running_count}"

        # 3. Sequenz sollte abgelehnt werden
        action = {
            "type": "sequence",
            "sequence_id": "seq-3",
            "steps": [{"delay_seconds": 1}],
        }
        result = await sequence_executor.execute(action, {"rule_id": "test"})
        assert result.success is False
        assert result.data["error_code"] == SequenceErrorCode.SEQ_ALREADY_RUNNING

        # Cleanup: Cancel laufende Sequenzen
        for i in range(2):
            await sequence_executor.cancel_sequence(f"seq-{i}")

    @pytest.mark.asyncio
    async def test_cleanup_old_sequences(self, sequence_executor):
        """Test: Alte abgeschlossene Sequenzen werden aufgeräumt."""
        # Setze kurze Retention-Zeit
        sequence_executor.PROGRESS_RETENTION_SECONDS = 0

        action = {
            "type": "sequence",
            "sequence_id": "cleanup-seq",
            "steps": [{"delay_seconds": 0.1}],
        }
        await sequence_executor.execute(action, {"rule_id": "test"})
        await asyncio.sleep(0.3)  # Warte bis Sequenz fertig

        # Sequenz sollte noch da sein
        assert sequence_executor.get_sequence_status("cleanup-seq") is not None

        # Cleanup durchführen
        await sequence_executor._cleanup_old_sequences()

        # Sequenz sollte entfernt sein
        assert sequence_executor.get_sequence_status("cleanup-seq") is None

    def test_get_all_sequences(self, sequence_executor):
        """Test: get_all_sequences() gibt Liste zurück."""
        # Erstelle Test-Progress
        progress = SequenceProgress(
            sequence_id="test",
            rule_id="rule1",
            rule_name="Test Rule",
            description="Test",
            total_steps=1,
            abort_on_failure=True,
            max_duration_seconds=60,
        )
        sequence_executor._sequences["test"] = progress

        all_seqs = sequence_executor.get_all_sequences()
        assert len(all_seqs) == 1
        assert all_seqs[0]["sequence_id"] == "test"

    def test_get_stats(self, sequence_executor):
        """Test: get_stats() gibt Statistiken zurück."""
        stats = sequence_executor.get_stats()

        assert "total_sequences" in stats
        assert "running" in stats
        assert "completed_last_hour" in stats
        assert "failed_last_hour" in stats
        assert "average_duration_seconds" in stats

    @pytest.mark.asyncio
    async def test_shutdown(self, sequence_executor):
        """Test: shutdown() stoppt Cleanup-Task."""
        # Starte Cleanup-Task
        sequence_executor._cleanup_task = asyncio.create_task(sequence_executor._cleanup_loop())
        await asyncio.sleep(0.1)

        assert not sequence_executor._cleanup_task.done()

        # Shutdown
        await sequence_executor.shutdown()

        # Task sollte beendet sein
        assert sequence_executor._cleanup_task.done()


class TestStepResult:
    """Tests für StepResult Dataclass."""

    def test_step_result_complete(self):
        """Test: StepResult.complete() setzt alle Felder."""
        # Setze started_at explizit in der Vergangenheit, um duration_ms > 0 zu garantieren
        from datetime import timedelta

        started = datetime.now(timezone.utc) - timedelta(milliseconds=50)
        result = StepResult(
            step_index=0,
            step_name="Test Step",
            success=False,
            message="Pending",
            started_at=started,
        )

        result.complete(True, "Step completed", None)

        assert result.success is True
        assert result.message == "Step completed"
        assert result.completed_at is not None
        assert result.duration_ms >= 50  # Mindestens 50ms


class TestSequenceProgress:
    """Tests für SequenceProgress Dataclass."""

    def test_progress_properties(self):
        """Test: SequenceProgress Properties funktionieren."""
        progress = SequenceProgress(
            sequence_id="test",
            rule_id="rule1",
            rule_name="Test",
            description="Test",
            total_steps=10,
            abort_on_failure=True,
            max_duration_seconds=60,
        )
        progress.status = SequenceStatus.RUNNING
        progress.current_step = 5

        assert progress.is_running is True
        assert progress.is_terminal is False
        assert progress.progress_percent == 50.0

    def test_to_dict(self):
        """Test: SequenceProgress.to_dict() serialisiert korrekt."""
        progress = SequenceProgress(
            sequence_id="test",
            rule_id="rule1",
            rule_name="Test",
            description="Test",
            total_steps=1,
            abort_on_failure=True,
            max_duration_seconds=60,
        )
        progress.started_at = datetime.now(timezone.utc)

        data = progress.to_dict()

        assert data["sequence_id"] == "test"
        assert data["rule_id"] == "rule1"
        assert "status" in data
        assert "progress_percent" in data
        assert "started_at" in data
