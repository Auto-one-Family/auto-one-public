"""
Hysteresis Condition Evaluator

Implementiert Hysterese-Logik für schwellwertbasierte Bedingungen.
Verhindert "Flattern" bei Werten nahe am Schwellwert.

PATTERN: Folgt BaseConditionEvaluator (siehe sensor_evaluator.py)
STATE: In-Memory Cache + DB-Persistenz (überlebt Server-Restart)

Phase: Logic Engine Phase 2 + L2 Hysterese-Härtung
Author: AutomationOne Development Team
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ....core.logging_config import get_logger
from ....db.models.logic import LogicHysteresisState
from .base import BaseConditionEvaluator

logger = get_logger(__name__)


@dataclass
class HysteresisState:
    """
    Zustand einer Hysterese-Condition.

    Attributes:
        is_active: Aktueller Aktivierungszustand
        last_activation: Zeitpunkt der letzten Aktivierung
        last_deactivation: Zeitpunkt der letzten Deaktivierung
        last_value: Letzter verarbeiteter Sensor-Wert
    """

    is_active: bool = False
    last_activation: Optional[datetime] = None
    last_deactivation: Optional[datetime] = None
    last_value: Optional[float] = None


class HysteresisConditionEvaluator(BaseConditionEvaluator):
    """
    Evaluator für Hysterese-Conditions.

    Zwei Modi:
    - Kühlung: activate_above + deactivate_below (z.B. Lüfter)
    - Heizung: activate_below + deactivate_above (z.B. Heizung)

    State-Key Format: "{rule_id}:{condition_index}"
    State is persisted to DB on every change and loaded on startup.

    Beispiel Kühlung:
        {
            "type": "hysteresis",
            "esp_id": "ESP_GREENHOUSE_1",
            "gpio": 4,
            "sensor_type": "DS18B20",
            "activate_above": 28.0,
            "deactivate_below": 24.0
        }

    Beispiel Heizung:
        {
            "type": "hysteresis",
            "esp_id": "ESP_GREENHOUSE_1",
            "gpio": 4,
            "activate_below": 18.0,
            "deactivate_above": 22.0
        }
    """

    def __init__(self, session_factory: Optional[Callable] = None):
        """
        Initialisiert den Hysterese-Evaluator.

        Args:
            session_factory: Async session factory for DB persistence.
                             If None, states are only kept in memory.
        """
        self._states: Dict[str, HysteresisState] = {}
        self._session_factory = session_factory
        logger.info(
            "HysteresisConditionEvaluator initialized (persistence=%s)", session_factory is not None
        )

    def supports(self, condition_type: str) -> bool:
        """
        Sagt der Engine dass wir 'hysteresis' Conditions handeln.

        Args:
            condition_type: Condition type string

        Returns:
            True wenn condition_type == "hysteresis"
        """
        return condition_type == "hysteresis"

    async def load_states_from_db(self) -> int:
        """
        Load all hysteresis states from DB into memory cache.

        Called once during server startup to restore state after restart.

        Returns:
            Number of states loaded
        """
        if not self._session_factory:
            return 0

        try:
            async for session in self._session_factory():
                result = await session.execute(select(LogicHysteresisState))
                rows = result.scalars().all()
                for row in rows:
                    key = f"{row.rule_id}:{row.condition_index}"
                    self._states[key] = HysteresisState(
                        is_active=row.is_active,
                        last_activation=row.last_activation,
                        last_deactivation=row.last_deactivation,
                        last_value=row.last_value,
                    )
                logger.info("Loaded %d hysteresis states from DB", len(rows))
                return len(rows)
        except Exception as e:
            logger.error("Failed to load hysteresis states from DB: %s", e, exc_info=True)
            return 0

    async def _persist_state(self, key: str, state: HysteresisState) -> None:
        """
        Persist a state change to DB (upsert).

        Called only when is_active actually changes, not on every evaluation.

        Args:
            key: State key in format "rule_id:condition_index"
            state: Current HysteresisState to persist
        """
        if not self._session_factory:
            return

        try:
            rule_id_str, condition_index_str = key.split(":", 1)
            async for session in self._session_factory():
                stmt = (
                    insert(LogicHysteresisState)
                    .values(
                        rule_id=rule_id_str,
                        condition_index=int(condition_index_str),
                        is_active=state.is_active,
                        last_value=state.last_value,
                        last_activation=state.last_activation,
                        last_deactivation=state.last_deactivation,
                    )
                    .on_conflict_do_update(
                        constraint="uq_hysteresis_state_rule_cond",
                        set_={
                            "is_active": state.is_active,
                            "last_value": state.last_value,
                            "last_activation": state.last_activation,
                            "last_deactivation": state.last_deactivation,
                        },
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error("Failed to persist hysteresis state for %s: %s", key, e, exc_info=True)

    async def evaluate(self, condition: Dict, context: Dict) -> bool:
        """
        Evaluiert eine Hysterese-Condition.

        Args:
            condition: Die Condition-Definition aus der Regel mit:
                - type: "hysteresis"
                - esp_id: ESP device ID
                - gpio: GPIO pin number
                - sensor_type: Optional sensor type filter
                - Kühlung-Modus: activate_above, deactivate_below
                - Heizung-Modus: activate_below, deactivate_above
            context: Enthält:
                - sensor_data: dict mit esp_id, gpio, value, sensor_type
                - rule_id: Regel-UUID
                - condition_index: Index der Condition in der Regel

        Returns:
            True wenn Bedingung erfüllt (Aktion soll ausgeführt werden)
        """
        sensor_data = context.get("sensor_data", {})

        # 1. Prüfe ob dieser Sensor zur Condition passt
        if not self._matches_sensor(condition, sensor_data):
            # Wenn der referenzierte Sensor-ESP als offline markiert ist,
            # darf ein alter aktiver Hysterese-State NICHT weiter zu True führen.
            # Sonst könnte eine Compound-Regel (hysteresis + time_window) trotz
            # fehlender Sensorquelle weiter Aktionen triggern.
            if self._is_condition_source_offline(condition, context):
                return False
            # Nicht unser Sensor - keine Änderung am State
            # WICHTIG: Gib aktuellen State zurück, nicht False!
            state = self._get_state(context)
            return state.is_active

        # 2. Hole den Wert
        value = sensor_data.get("value")
        if value is None:
            logger.warning(
                f"No value in sensor_data for {sensor_data.get('esp_id')}:{sensor_data.get('gpio')}"
            )
            return self._get_state(context).is_active

        try:
            value = float(value)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid numeric value for hysteresis condition: {e}")
            return self._get_state(context).is_active

        # 3. Hole/Erstelle State für diese Rule+Condition
        state = self._get_state(context)
        previous_active = state.is_active
        state.last_value = value

        # 4. Hysterese-Logik
        activate_above = condition.get("activate_above")
        deactivate_below = condition.get("deactivate_below")
        activate_below = condition.get("activate_below")
        deactivate_above = condition.get("deactivate_above")

        now = datetime.now(timezone.utc)

        # Mode A: Kühlung (activate_above / deactivate_below)
        if activate_above is not None and deactivate_below is not None:
            try:
                activate_above = float(activate_above)
                deactivate_below = float(deactivate_below)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid threshold values for cooling mode: {e}")
                return False

            # P0-Fix T9: Degenerate case — equal thresholds eliminate the deadband,
            # defeating the purpose of hysteresis and causing undefined behavior.
            if activate_above <= deactivate_below:
                logger.error(
                    "Hysteresis config error (cooling): activate_above (%.2f) must be "
                    "> deactivate_below (%.2f). Deadband requires activate > deactivate. "
                    "[rule=%s, condition=%s]",
                    activate_above,
                    deactivate_below,
                    context.get("rule_id"),
                    context.get("condition_index"),
                )
                return state.is_active  # Hold current state, don't corrupt

            if value > activate_above and not state.is_active:
                state.is_active = True
                state.last_activation = now
                logger.info(
                    f"Hysteresis ACTIVATED (cooling): value={value:.2f} > threshold={activate_above:.2f} "
                    f"[rule={context.get('rule_id')}, condition={context.get('condition_index')}]"
                )
            elif value < deactivate_below and state.is_active:
                state.is_active = False
                state.last_deactivation = now
                context["_hysteresis_just_deactivated"] = True  # T18-F2: Signal OFF to actuators
                logger.info(
                    f"Hysteresis DEACTIVATED (cooling): value={value:.2f} < threshold={deactivate_below:.2f} "
                    f"[rule={context.get('rule_id')}, condition={context.get('condition_index')}]"
                )
            # Zwischen den Schwellen: Zustand bleibt!

        # Mode B: Heizung (activate_below / deactivate_above)
        elif activate_below is not None and deactivate_above is not None:
            try:
                activate_below = float(activate_below)
                deactivate_above = float(deactivate_above)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid threshold values for heating mode: {e}")
                return False

            # P0-Fix T9: Degenerate case — equal thresholds eliminate the deadband.
            if deactivate_above <= activate_below:
                logger.error(
                    "Hysteresis config error (heating): deactivate_above (%.2f) must be "
                    "> activate_below (%.2f). Deadband requires deactivate > activate. "
                    "[rule=%s, condition=%s]",
                    deactivate_above,
                    activate_below,
                    context.get("rule_id"),
                    context.get("condition_index"),
                )
                return state.is_active  # Hold current state, don't corrupt

            if value < activate_below and not state.is_active:
                state.is_active = True
                state.last_activation = now
                logger.info(
                    f"Hysteresis ACTIVATED (heating): value={value:.2f} < threshold={activate_below:.2f} "
                    f"[rule={context.get('rule_id')}, condition={context.get('condition_index')}]"
                )
            elif value > deactivate_above and state.is_active:
                state.is_active = False
                state.last_deactivation = now
                context["_hysteresis_just_deactivated"] = True  # T18-F2: Signal OFF to actuators
                logger.info(
                    f"Hysteresis DEACTIVATED (heating): value={value:.2f} > threshold={deactivate_above:.2f} "
                    f"[rule={context.get('rule_id')}, condition={context.get('condition_index')}]"
                )

        else:
            logger.error(
                "Invalid hysteresis config: need activate_above+deactivate_below "
                "OR activate_below+deactivate_above"
            )
            return False

        # 5. Persist to DB only on state change
        if state.is_active != previous_active:
            key = self._get_state_key(context)
            await self._persist_state(key, state)

        return state.is_active

    def _get_state_key(self, context: Dict) -> str:
        """
        Generiert eindeutigen Key für State-Speicherung.

        Args:
            context: Evaluation context

        Returns:
            State key im Format "rule_id:condition_index"
        """
        rule_id = context.get("rule_id")
        if not rule_id:
            logger.warning(
                "HysteresisEvaluator called without rule_id in context — state not persisted correctly"
            )
            rule_id = "no_rule_id"
        condition_idx = context.get("condition_index", 0)
        return f"{rule_id}:{condition_idx}"

    def _get_state(self, context: Dict) -> HysteresisState:
        """
        Holt oder erstellt State für eine Rule+Condition.

        Args:
            context: Evaluation context

        Returns:
            HysteresisState für diese Rule+Condition
        """
        key = self._get_state_key(context)
        if key not in self._states:
            self._states[key] = HysteresisState()
            logger.debug(f"Created new hysteresis state for {key}")
        return self._states[key]

    def _matches_sensor(self, condition: Dict, sensor_data: Dict) -> bool:
        """
        Prüft ob der Sensor zur Condition passt.

        Args:
            condition: Condition definition
            sensor_data: Sensor data from context

        Returns:
            True wenn ESP-ID, GPIO und optional sensor_type matchen
        """
        # ESP-ID muss matchen
        if condition.get("esp_id") != sensor_data.get("esp_id"):
            return False

        # GPIO muss matchen (int coercion: JSON may deliver float or string)
        try:
            if int(condition.get("gpio", -1)) != int(sensor_data.get("gpio", -2)):
                return False
        except (ValueError, TypeError):
            return False

        # Sensor-Type ist optional (case-insensitive: ESP sends lowercase,
        # rules may store uppercase from UI input)
        cond_sensor_type = condition.get("sensor_type")
        if cond_sensor_type:
            data_sensor_type = sensor_data.get("sensor_type") or ""
            if cond_sensor_type.lower() != data_sensor_type.lower():
                return False

        return True

    def _is_condition_source_offline(self, condition: Dict, context: Dict) -> bool:
        """Check whether this condition's sensor reference is marked offline in context."""
        offline_refs = context.get("_offline_sensor_refs") or []
        if not isinstance(offline_refs, list):
            return False

        cond_esp = condition.get("esp_id")
        cond_gpio = condition.get("gpio")
        cond_sensor_type = condition.get("sensor_type")
        if cond_esp is None or cond_gpio is None:
            return False

        try:
            cond_gpio_int = int(cond_gpio)
        except (TypeError, ValueError):
            return False

        cond_sensor_type_norm = str(cond_sensor_type).lower() if cond_sensor_type else None

        for ref in offline_refs:
            if not isinstance(ref, dict):
                continue
            if ref.get("esp_id") != cond_esp:
                continue
            try:
                ref_gpio = int(ref.get("gpio"))
            except (TypeError, ValueError):
                continue
            if ref_gpio != cond_gpio_int:
                continue

            ref_sensor_type = ref.get("sensor_type")
            if cond_sensor_type_norm is None:
                return True
            if ref_sensor_type is None:
                continue
            if str(ref_sensor_type).lower() == cond_sensor_type_norm:
                return True

        return False

    def reset_state(self, rule_id: str, condition_index: int = 0) -> None:
        """
        Setzt State zurück (für Testing/Admin).

        Args:
            rule_id: Regel-UUID
            condition_index: Index der Condition in der Regel
        """
        key = f"{rule_id}:{condition_index}"
        if key in self._states:
            del self._states[key]
            logger.info(f"Hysteresis state reset for {key}")
        else:
            logger.debug(f"No state to reset for {key}")

    def reset_states_for_rule(self, rule_id: str) -> list[str]:
        """Reset all hysteresis states for a given rule.

        Called by LogicEngine.on_rule_updated() when a rule is changed via the API.
        Removes all in-memory states whose key starts with "{rule_id}:".

        Args:
            rule_id: Regel-UUID as string

        Returns:
            List of state keys that were active at the time of reset (for logging /
            deciding whether an OFF command must be sent to the actuator).
        """
        keys_to_reset = [k for k in self._states if k.startswith(f"{rule_id}:")]
        active_keys: list[str] = []
        for key in keys_to_reset:
            state = self._states.pop(key, None)
            if state and state.is_active:
                active_keys.append(key)
        if active_keys:
            logger.info(
                "Hysteresis states reset for rule %s: %d active state(s) cleared %s",
                rule_id,
                len(active_keys),
                active_keys,
            )
        elif keys_to_reset:
            logger.debug(
                "Hysteresis states reset for rule %s (%d inactive)", rule_id, len(keys_to_reset)
            )
        return active_keys

    def remove_state(self, key: str) -> bool:
        """Remove a single hysteresis state by its full key.

        Used by LogicEngine.on_rule_updated() for selective (bumpless transfer)
        resets: only states whose condition changed are removed; orthogonal
        states (e.g. a time_window was added/removed alongside an unchanged
        hysteresis) are kept.

        Args:
            key: State key in format "{rule_id}:{condition_index}"

        Returns:
            True if the removed state was active, False if inactive or not found
        """
        state = self._states.pop(key, None)
        if state is not None:
            if state.is_active:
                logger.info("Hysteresis state removed (active): %s", key)
            else:
                logger.debug("Hysteresis state removed (inactive): %s", key)
            return state.is_active
        logger.debug("No hysteresis state to remove for %s", key)
        return False

    def get_all_states(self) -> Dict[str, HysteresisState]:
        """
        Gibt alle States zurück (für Debugging/Monitoring).

        Returns:
            Copy der State-Dictionary
        """
        return self._states.copy()

    def get_state_for_rule(
        self, rule_id: str, condition_index: int = 0
    ) -> Optional[HysteresisState]:
        """
        Gibt State für eine spezifische Rule+Condition zurück.

        Args:
            rule_id: Regel-UUID
            condition_index: Index der Condition

        Returns:
            HysteresisState oder None wenn nicht vorhanden
        """
        key = f"{rule_id}:{condition_index}"
        return self._states.get(key)
