"""Logic Rule AI Assistant — Natural Language to Logic Rule JSON generation (AUT-172)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from .ai_service import ai_service as _ai_service
from ..core.logging_config import get_logger

logger = get_logger(__name__)


class SensorInfo(BaseModel):
    uuid: str
    name: str
    sensor_type: str
    esp_id: str
    unit: Optional[str] = None


class ActuatorInfo(BaseModel):
    uuid: str
    name: str
    actuator_type: str
    esp_id: str


class RuleGenerationRequest(BaseModel):
    description: str
    available_sensors: list[SensorInfo]
    available_actuators: list[ActuatorInfo]


class GeneratedRule(BaseModel):
    name: str
    description: str
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    safety_notes: list[str]
    validation_warnings: list[str]
    confidence: Literal["high", "medium", "low"]


_SYSTEM_PROMPT = """Du bist ein Experte für AutomationOne Logic Rules.

Deine Aufgabe: Konvertiere eine natürlichsprachliche Automatisierungs-Beschreibung in eine valide Logic Rule.

## Verfügbare Condition-Typen

### sensor
```json
{"type": "sensor", "sensor_uuid": "...", "operator": ">", "threshold": 7.5}
```
Operators: >, >=, <, <=, ==, !=

### sensor_diff
```json
{"type": "sensor_diff", "sensor_a_uuid": "...", "sensor_b_uuid": "...", "operator": ">", "threshold": 2.5, "consecutive_count": 3}
```

### time
```json
{"type": "time", "start": "08:00", "end": "20:00", "days": ["mon","tue","wed","thu","fri"]}
```

### diagnostics_status
```json
{"type": "diagnostics_status", "check_name": "sensor_freshness", "status": "warning", "operator": "=="}
```

### compound
```json
{"type": "compound", "operator": "AND", "conditions": [...]}
```

## Verfügbare Action-Typen

### actuator
```json
{"type": "actuator", "actuator_uuid": "...", "command": "on", "duration_seconds": 30}
```
Commands: on, off, set_value (für PWM)

### notification
```json
{"type": "notification", "channel": "websocket", "message": "...", "severity": "warning"}
```

### delay
```json
{"type": "delay", "seconds": 60}
```

### plugin
```json
{"type": "plugin", "plugin_id": "..."}
```

### run_diagnostic
```json
{"type": "run_diagnostic"}
```

## Sicherheits-Regeln
- Wenn Sensor und Aktor auf verschiedenen ESPs sind: safety_note hinzufügen "Cross-ESP Rule: Sensor ESP <esp_id> != Aktor ESP <esp_id>"
- Pumpen-Aktionen immer mit duration_seconds (max 3600s = 1h)
- Bei pH/EC Sensoren: threshold in realistischen Bereichen (pH 4-9, EC 0-5 mS/cm)
- Bei unklaren Beschreibungen: confidence auf "low" setzen und validation_warnings befüllen

Antworte NUR mit dem JSON-Objekt der GeneratedRule ohne zusätzlichen Text.
"""


class LogicAiAssistant:
    """AI-powered assistant to generate AutomationOne Logic Rules from natural language."""

    def __init__(self) -> None:
        self._client: Optional[AsyncAnthropic] = None

    def _get_client(self) -> AsyncAnthropic:
        if self._client is None:
            self._client = AsyncAnthropic()
        return self._client

    def is_available(self) -> bool:
        """Returns True if ANTHROPIC_API_KEY is configured."""
        return _ai_service.is_available()

    async def generate_rule(self, request: RuleGenerationRequest) -> GeneratedRule:
        """
        Generate a Logic Rule from a natural language description.

        Uses messages.parse() with output_format for structured output
        (requires anthropic>=0.49.0).
        """
        response = await self._get_client().messages.parse(
            model="claude-opus-4-7",
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_format=GeneratedRule,
            messages=[
                {
                    "role": "user",
                    "content": self._build_user_prompt(request),
                }
            ],
        )
        result = response.parsed_output  # SDK: parsed_output, not .parsed
        if result is None:
            raise ValueError("AI returned no parsable rule")
        return result

    def _build_user_prompt(self, request: RuleGenerationRequest) -> str:
        sensors = "\n".join(
            f"- {s.name} (UUID: {s.uuid}, Typ: {s.sensor_type}, ESP: {s.esp_id}, Einheit: {s.unit or '?'})"
            for s in request.available_sensors
        )
        actuators = "\n".join(
            f"- {a.name} (UUID: {a.uuid}, Typ: {a.actuator_type}, ESP: {a.esp_id})"
            for a in request.available_actuators
        )
        return (
            f"Aufgabe: {request.description}\n\n"
            f"Verfügbare Sensoren:\n{sensors}\n\n"
            f"Verfügbare Aktoren:\n{actuators}\n\n"
            "Erstelle eine Logic Rule die diese Aufgabe erfüllt."
        )

    async def validate_and_generate(
        self,
        request: RuleGenerationRequest,
        logic_service: Any,
    ) -> tuple[GeneratedRule, Any]:
        """
        Generate a rule and immediately validate it against the logic service.

        Returns:
            Tuple of (GeneratedRule, ValidationResult)
        """
        generated = await self.generate_rule(request)
        rule_data: dict[str, Any] = {
            "name": generated.name,
            "conditions": generated.conditions,
            "actions": generated.actions,
        }
        validation = await logic_service.validate_rule(rule_data)
        return generated, validation


logic_ai_assistant = LogicAiAssistant()
