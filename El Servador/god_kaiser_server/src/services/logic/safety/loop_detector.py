"""
Loop Detector für Logic Engine

Erkennt potentielle Endlos-Loops BEVOR Rules ausgeführt werden.
Verwendet gerichteten Graphen: Nodes = Rules, Edges = Trigger-Beziehungen.

INTEGRATION: Wird von LogicValidator.validate() aufgerufen
PATTERN: Kein Singleton - wird als Instanz-Variable genutzt
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class LoopDetectionResult:
    """Ergebnis der Loop-Detection."""

    has_loop: bool
    cycle_path: List[str] = field(default_factory=list)  # Rule-IDs im Cycle
    depth: int = 0
    message: str = ""


class LoopDetector:
    """
    Erkennt Endlos-Loops in Rule-Chains.

    Beispiel:
        Rule A: Wenn Temp > 25 → Lüfter AN
        Rule B: Wenn Lüfter AN → Temp-Sensor erhöhen (hypothetisch)
        → LOOP: A → B → A

    Implementation:
        - Baut gerichteten Graphen aus Rules
        - DFS mit Cycle-Detection
        - Max-Depth-Limit (default: 10)

    Thread-Safety:
        - Graph wird bei jeder Prüfung neu gebaut (stateless)
        - Keine shared mutable state
    """

    MAX_CHAIN_DEPTH = 10  # Maximale Tiefe einer Rule-Chain

    def __init__(self):
        self._graph: Dict[str, Set[str]] = defaultdict(set)

    def build_dependency_graph(self, rules: List[dict]) -> None:
        """
        Baut den Abhängigkeits-Graphen aus allen aktiven Rules.

        Args:
            rules: Liste von Rule-Dictionaries mit:
                   - id: Rule-ID
                   - trigger_conditions: Was triggert die Rule
                   - actions: Was macht die Rule

        Graph-Logik:
            Wenn Rule A einen Actuator steuert und Rule B auf
            diesen Actuator reagiert → Edge A → B
        """
        self._graph.clear()

        # Schritt 1: Extrahiere alle Trigger und Actions
        rule_triggers = {}  # rule_id → Set of (esp_id, gpio, type)
        rule_actions = {}  # rule_id → Set of (esp_id, gpio)

        for rule in rules:
            rule_id = str(rule.get("id", ""))

            # Trigger extrahieren
            triggers = self._extract_triggers(rule.get("trigger_conditions", {}))
            rule_triggers[rule_id] = triggers

            # Actions extrahieren
            actions = self._extract_action_targets(rule.get("actions", []))
            rule_actions[rule_id] = actions

        # Schritt 2: Baue Edges
        # Wenn Rule A einen Actuator steuert, den Rule B als Trigger hat
        for rule_a_id, actions in rule_actions.items():
            for rule_b_id, triggers in rule_triggers.items():
                if rule_a_id == rule_b_id:
                    continue

                # Check: Hat Rule B einen Trigger der auf Actions von A reagiert?
                for action_target in actions:
                    # Action-Target ist (esp_id, gpio), Trigger ist (esp_id, gpio, type)
                    # Match wenn esp_id und gpio übereinstimmen
                    for trigger in triggers:
                        if action_target[0] == trigger[0] and action_target[1] == trigger[1]:
                            self._graph[rule_a_id].add(rule_b_id)
                            logger.debug(f"Loop edge: {rule_a_id} → {rule_b_id}")
                            break

    def _extract_triggers(self, conditions: dict) -> Set[Tuple[str, int, str]]:
        """
        Extrahiert (esp_id, gpio, type) Tupel aus Conditions.

        Args:
            conditions: Condition-Dictionary (kann compound sein)

        Returns:
            Set of (esp_id, gpio, condition_type) tuples
        """
        triggers = set()

        if not conditions:
            return triggers

        # Compound conditions (AND/OR)
        if "conditions" in conditions and isinstance(conditions.get("conditions"), list):
            for cond in conditions.get("conditions", []):
                triggers.update(self._extract_triggers(cond))
            return triggers

        # Single condition
        cond_type = conditions.get("type", "")
        if cond_type in ("sensor_threshold", "sensor", "actuator_state", "hysteresis"):
            esp_id = conditions.get("esp_id", "")
            gpio = conditions.get("gpio", -1)
            if esp_id and gpio != -1:
                triggers.add((esp_id, gpio, cond_type))

        return triggers

    def _extract_action_targets(self, actions: list) -> Set[Tuple[str, int]]:
        """
        Extrahiert (esp_id, gpio) Tupel aus Actions.

        Args:
            actions: Liste von Action-Dictionaries

        Returns:
            Set of (esp_id, gpio) tuples
        """
        targets = set()

        for action in actions:
            action_type = action.get("type", "")
            if action_type in ("actuator_command", "actuator"):
                esp_id = action.get("esp_id", "")
                gpio = action.get("gpio", -1)
                if esp_id and gpio != -1:
                    targets.add((esp_id, gpio))
            elif action_type == "sequence":
                # Sequenzen können verschachtelte Actions haben
                steps = action.get("steps", [])
                for step in steps:
                    step_action = step.get("action", {})
                    if step_action:
                        nested_targets = self._extract_action_targets([step_action])
                        targets.update(nested_targets)

        return targets

    def detect_loop(self, start_rule_id: str) -> LoopDetectionResult:
        """
        Prüft ob eine Rule-Chain einen Loop enthält.

        Args:
            start_rule_id: ID der startenden Rule

        Returns:
            LoopDetectionResult mit has_loop, cycle_path, depth

        Algorithm:
            DFS mit visited Set und recursion stack
        """
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str, depth: int) -> Optional[List[str]]:
            if depth > self.MAX_CHAIN_DEPTH:
                return None  # Max depth erreicht, aber kein Loop

            if node in rec_stack:
                # Loop gefunden!
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]

            if node in visited:
                return None

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._graph.get(node, set()):
                cycle = dfs(neighbor, depth + 1)
                if cycle:
                    return cycle

            path.pop()
            rec_stack.remove(node)
            return None

        cycle = dfs(start_rule_id, 0)

        if cycle:
            return LoopDetectionResult(
                has_loop=True,
                cycle_path=cycle,
                depth=len(cycle),
                message=f"Loop detected: {' → '.join(cycle)}",
            )

        return LoopDetectionResult(has_loop=False, depth=len(visited), message="No loop detected")

    def check_new_rule(self, new_rule: dict, existing_rules: List[dict]) -> LoopDetectionResult:
        """
        Prüft ob eine NEUE Rule einen Loop verursachen würde.

        Args:
            new_rule: Die zu prüfende neue Rule
            existing_rules: Alle existierenden aktiven Rules

        Returns:
            LoopDetectionResult

        USAGE:
            Aufrufen bei Rule-Create und Rule-Update!
        """
        # Baue Graph mit allen Rules + der neuen
        all_rules = existing_rules + [new_rule]
        self.build_dependency_graph(all_rules)

        # Prüfe ob die neue Rule in einem Loop ist
        new_rule_id = str(new_rule.get("id", ""))
        return self.detect_loop(new_rule_id)
