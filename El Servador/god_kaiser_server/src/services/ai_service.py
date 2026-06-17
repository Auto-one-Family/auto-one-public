"""AI Analysis Service — Claude API integration for error intelligence (AUT-168, AUT-194)."""

from __future__ import annotations

import os
from typing import Literal, Optional

try:
    from anthropic import AsyncAnthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None  # type: ignore[assignment,misc]
    _ANTHROPIC_AVAILABLE = False

from pydantic import BaseModel

from ..core.logging_config import get_logger
from ..core.server_error_mapping import get_all_server_error_codes

logger = get_logger(__name__)


class CodeRef(BaseModel):
    file: str
    line: int
    symbol: str


class ErrorAnalysisRequest(BaseModel):
    error_code: int
    context: dict
    recent_errors: list[int]
    system_state: dict


class ErrorAnalysisFinding(BaseModel):
    root_cause: str
    affected_components: list[str]
    code_references: list[CodeRef]
    recommended_actions: list[str]
    linear_title: str
    linear_description: str
    severity: Literal["critical", "high", "medium", "low"]
    related_error_codes: list[int]


# ---------------------------------------------------------------------------
# AUT-194: Daily snapshot models (DailyAnalysisJob)
# ---------------------------------------------------------------------------


class ErrorSourceSummary(BaseModel):
    """Aggregated error source for daily stack diagnostic."""

    error_code: int
    count: int
    esp_id: Optional[str] = None
    source_type: Literal["mqtt", "api"]
    first_seen: str
    last_seen: str


class HeartbeatHealthSummary(BaseModel):
    """ESP heartbeat health aggregation over the analysis period."""

    total_esps: int
    online_esps: int
    offline_esps: int
    avg_latency_ms: Optional[float] = None
    reconnect_events: int


class ConfigPushSummary(BaseModel):
    """Config-push activity over the period."""

    total_pushes: int
    failed_pushes: int
    chattering_events: int  # multiple pushes <45s same ESP


class NotificationSummary(BaseModel):
    """Notification system activity over the period."""

    total_sent: int
    dedup_hits: int
    failed_sends: int


class SchedulerHealthSummary(BaseModel):
    """CentralScheduler health snapshot."""

    total_jobs: int
    jobs_by_category: dict[str, int]
    total_executions: int
    total_errors: int


class FalseErrorPatternFlags(BaseModel):
    """Counters for the 9 known harmless patterns (false-positive prevention)."""

    heartbeat_ack_delays: int
    reconnect_storms: int
    config_push_chattering: int
    post_restart_races: int
    lwt_floods: int
    idle_actuator_states: int
    validation_errors_by_design: int
    discovery_ratelimit_by_design: int
    notification_dedup_hits: int


class SystemAnalysisRequest(BaseModel):
    """Aggregated system snapshot for daily Claude stack analysis (AUT-194)."""

    period_hours: int
    error_sources: list[ErrorSourceSummary]
    heartbeat_health: HeartbeatHealthSummary
    config_push: ConfigPushSummary
    notifications: NotificationSummary
    scheduler_health: SchedulerHealthSummary
    false_error_patterns: FalseErrorPatternFlags


_ESP32_ERROR_CONTEXT = """
ESP32 Firmware Error-Codes (El Trabajante — C++):
HARDWARE (1000-1999): GPIO 1001-1006, I2C 1007-1019, OneWire 1020-1029, PWM 1030-1032, Sensor 1040-1043, Actuator 1050-1053, DS18B20 1060-1063
SERVICE (2000-2999): NVS 2001-2005, Config 2010-2014, Logger 2020-2021, Storage 2030-2032, Subzone 2500-2506
COMMUNICATION (3000-3999): WiFi 3001-3005, MQTT 3010-3016, HTTP 3020-3023, Network 3030-3032
APPLICATION (4000-4999): State 4001-4003, Operation 4010-4012, Command 4020-4022, Payload 4030-4033, Memory 4040-4042, System 4050-4052, Task 4060-4062, Watchdog 4070-4072

Wichtige Code-Referenzen:
- Error Tracker: El Trabajante/src/error_handling/error_tracker.cpp
- Offline Mode Manager: El Trabajante/src/services/safety/offline_mode_manager.cpp
- MQTT Client: El Trabajante/src/services/communication/mqtt_client.cpp
- Config Manager: El Trabajante/src/services/config/config_manager.cpp
"""

_CODE_REFERENCE_CONTEXT = """
Server-seitige Code-Referenzen:
- Logic Engine: El Servador/god_kaiser_server/src/services/logic_engine.py
- Logic Conditions: El Servador/god_kaiser_server/src/services/logic/conditions/
- MQTT Error Handler: El Servador/god_kaiser_server/src/mqtt/handlers/error_handler.py
- ESP Service: El Servador/god_kaiser_server/src/services/esp_service.py
- AI Notification Bridge: El Servador/god_kaiser_server/src/services/ai_notification_bridge.py
"""


def _build_server_error_context() -> str:
    codes = get_all_server_error_codes()
    lines = ["Server Error-Codes (5000-5999):"]
    for code, info in sorted(codes.items()):
        msg = info.get("message_user_de") or info.get("message_de", "")
        cat = info.get("category", "")
        lines.append(f"  {code} ({cat}): {msg}")
    return "\n".join(lines)


_SYSTEM_PROMPT = f"""Du bist ein AutomationOne IoT-Framework Debugging-Experte.

AutomationOne besteht aus:
- El Trabajante: ESP32 C++ Firmware (Sensoren, Aktoren, MQTT)
- El Servador: FastAPI Python Server (Logic Engine, MQTT-Broker-Bridge, REST API)
- El Frontend: Vue 3 Dashboard

{_ESP32_ERROR_CONTEXT}

{_build_server_error_context()}

{_CODE_REFERENCE_CONTEXT}

Deine Aufgabe: Analysiere Fehler-Events und gib strukturierte Befunde zurueck.
Benenne immer konkrete Datei-Pfade und Zeilennummern wenn moeglich.
"""


# ---------------------------------------------------------------------------
# AUT-194: Daily stack-diagnostic system prompt
# Reuses the same cached _SYSTEM_PROMPT block (Anthropic prompt-caching:
# identical text prefix => cache hit) and appends the 9 harmless-pattern
# guidance for false-positive suppression.
# ---------------------------------------------------------------------------

_DAILY_HARMLESS_PATTERNS = """

BEKANNTE HARMLOSE PATTERNS (KEIN Finding erzeugen, falls Evidenz innerhalb dieser Definitionen liegt):

1. Heartbeat-ACK-Delay: ACK-Latenzen <60s nach Heartbeat sind im Normalbereich (Mosquitto-Round-Trip + ESP-Verarbeitung).
2. Reconnect-Storm: Mehrere Heartbeats 0-120s nach einem Reconnect sind erwartet (clean_session=true => ESP republishes).
3. Config-Push-Chattering: Mehrere Config-Pushes <45s vom selben ESP sind harmlos (Idempotenz-Schutz, Server resendet bei fehlendem ACK).
4. F-V4-01 Post-Restart Race: Zone/Subzone-ACKs <30s nach Server-Restart koennen verloren gehen (clean_session=true) — KEIN Fehler.
5. LWT-Flood: Circuit-Breaker-Drops bei >3 simultanen LWTs sind das gewollte Schutzverhalten.
6. actuator_states "idle"-Werte sind kosmetisches Legacy aus AUT-118 — keine Aktion.
7. Validation-Fehler ohne ACK = by Design (Server verwirft invalide Payloads ohne ACK).
8. Discovery-Rate-Limit ohne ACK = by Design (Server droppt zu haeufige Discovery-Pings).
9. Notification-Dedup-Treffer = aktiver ISA-18.2-Schutz, keine Aktion.

WICHTIG: clean_session=true => Config-Push-Verlust nach Reconnect ist KEIN Error. Nur echte Auffaelligkeiten ausserhalb dieser Patterns als Findings melden.
"""

_DAILY_SYSTEM_PROMPT = (
    _SYSTEM_PROMPT
    + _DAILY_HARMLESS_PATTERNS
    + """
Aufgabe: Analysiere diesen aggregierten 12h-Stack-Snapshot des Servers und gib eine
sortierte Liste strukturierter ErrorAnalysisFinding-Eintraege zurueck (Severity-Reihenfolge:
critical -> high -> medium -> low). Nur Auffaelligkeiten OUTSIDE der bekannten harmlosen
Patterns oben werden zu Findings. Filtere by-design-Verhalten konsequent heraus.
Jedes Finding MUSS belastbare code_references mit Datei:Zeile haben.
"""
)


class _DailyAnalysisFindings(BaseModel):
    """Wrapper schema for messages.parse() — Claude returns structured list."""

    findings: list[ErrorAnalysisFinding]


class AiService:
    def __init__(self) -> None:
        self._client: Optional[AsyncAnthropic] = None
        self._system_prompt = _SYSTEM_PROMPT

    def _get_client(self) -> AsyncAnthropic:
        if self._client is None:
            self._client = AsyncAnthropic()
        return self._client

    def is_available(self) -> bool:
        """Returns True if anthropic is installed and ANTHROPIC_API_KEY is configured."""
        return _ANTHROPIC_AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY"))

    async def get_configured_api_key(self, db_session=None) -> Optional[str]:
        """
        Resolve the Anthropic API key using a two-step priority chain.

        Priority order:
        1. DB plugin config (PluginConfig for "claude") — requires db_session
        2. Environment variable ANTHROPIC_API_KEY — always checked as fallback

        This method is intended for use in ClaudeDebugAgent (AUT-270) and
        other services that have a DB session available.

        Args:
            db_session: Optional AsyncSession. When provided, the DB is queried
                        first for a non-empty api_key in the "claude" plugin config.

        Returns:
            The resolved API key string, or None if no key is configured.
        """
        if db_session is not None:
            try:
                from ..db.models.plugin import PluginConfig

                plugin_config = await db_session.get(PluginConfig, "claude")
                if plugin_config is not None:
                    db_key: Optional[str] = (plugin_config.config or {}).get("api_key")
                    if db_key:
                        return db_key
            except Exception:
                # Non-fatal: fall through to env-based resolution
                logger.debug("Claude plugin config DB lookup failed — falling back to env")

        return os.environ.get("ANTHROPIC_API_KEY")

    async def analyze_error(self, request: ErrorAnalysisRequest) -> ErrorAnalysisFinding:
        """
        Analyze an error event using Claude and return a structured finding.

        Uses messages.parse() with output_format for structured output
        (requires anthropic>=0.49.0).
        """
        response = await self._get_client().messages.parse(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": self._system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_format=ErrorAnalysisFinding,
            messages=[
                {
                    "role": "user",
                    "content": request.model_dump_json(),
                }
            ],
        )
        result = response.parsed_output
        if result is None:
            raise ValueError("Claude returned no parsed output for error analysis request")
        return result

    async def analyze_daily_snapshot(
        self, request: SystemAnalysisRequest
    ) -> list[ErrorAnalysisFinding]:
        """
        Run a 2x/day stack-diagnostic on aggregated server telemetry (AUT-194).

        Reuses the same cached system-prompt prefix as ``analyze_error`` (Anthropic
        prompt-caching ``cache_control={"type": "ephemeral"}``) and appends the
        9 known-harmless-pattern guidance. Claude returns a list of
        ErrorAnalysisFinding sorted by severity (critical -> low).

        Args:
            request: Aggregated SystemAnalysisRequest from DailySnapshotService

        Returns:
            list[ErrorAnalysisFinding] sorted by severity, empty list if no
            findings outside the harmless patterns.
        """
        response = await self._get_client().messages.parse(
            model="claude-opus-4-7",
            max_tokens=8192,
            system=[
                {
                    "type": "text",
                    "text": _DAILY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_format=_DailyAnalysisFindings,
            messages=[
                {
                    "role": "user",
                    "content": request.model_dump_json(),
                }
            ],
        )
        result = response.parsed_output
        if result is None:
            logger.warning("Claude returned no parsed output for daily snapshot request")
            return []

        # Stable severity sort (critical -> high -> medium -> low)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            result.findings,
            key=lambda f: severity_order.get(f.severity, 99),
        )


ai_service = AiService()
