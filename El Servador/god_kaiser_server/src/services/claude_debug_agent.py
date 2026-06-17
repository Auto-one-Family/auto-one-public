"""
ClaudeDebugAgent — Agentic LLM debug assistant for AutomationOne (AUT-270).

Provides 15 read-only tools that give Claude structured access to server state,
sensor history, audit logs, Loki logs and Prometheus metrics.

Supports two call styles:
- run_batch(): Blocking agentic loop, returns full text response.
- run():       Streaming SSE variant (yields data: ... lines).
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional

import httpx

try:
    from anthropic import AsyncAnthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None  # type: ignore[assignment,misc]
    _ANTHROPIC_AVAILABLE = False

from ..core.logging_config import get_logger
from ..core.server_error_mapping import get_all_server_error_codes

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..autoops.core.api_client import GodKaiserClient

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Allowed tables for the query_table tool (read-only whitelist)
# ---------------------------------------------------------------------------

_ALLOWED_TABLES: frozenset[str] = frozenset(
    [
        "esps",
        "sensor_configs",
        "actuator_configs",
        "sensor_data",
        "actuator_events",
        "audit_logs",
        "cross_esp_logic",
        "logic_hysteresis_states",
        "zones",
        "subzone_configs",
        "device_zone_changes",
        "notifications",
        "diagnostic_reports",
        "plugin_configs",
        "plugin_executions",
        "esp_heartbeat_logs",
        "device_active_context",
        "email_log",
    ]
)

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic tool-use schema)
# ---------------------------------------------------------------------------

_DEBUG_TOOLS_V2: list[dict[str, Any]] = [
    {
        "name": "get_esp_full_state",
        "description": (
            "Lese den vollstaendigen Zustand eines ESPs: Geraete-Details, alle Sensoren und alle Aktoren."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "esp_id": {"type": "string", "description": "ESP device ID (z.B. ESP_472204)"},
            },
            "required": ["esp_id"],
        },
    },
    {
        "name": "get_audit_logs",
        "description": "Lese die letzten N Audit-Log-Eintraege aus dem System.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Anzahl der zurueckgegebenen Eintraege (max 200)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "query_table",
        "description": (
            "Lese Zeilen direkt aus einer Datenbanktabelle. "
            f"Erlaubte Tabellen: {sorted(_ALLOWED_TABLES)}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name der Tabelle (nur aus der Whitelist)",
                },
                "limit": {"type": "integer", "default": 50, "description": "Max. Zeilen"},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "get_sensor_history",
        "description": "Lese die letzten N Sensormesswerte fuer einen ESP und GPIO.",
        "input_schema": {
            "type": "object",
            "properties": {
                "esp_id": {"type": "string"},
                "gpio": {"type": "integer", "description": "GPIO-Pin-Nummer"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["esp_id"],
        },
    },
    {
        "name": "get_health_metrics",
        "description": "Lese Server-Performance-Metriken (Prometheus-Format, geparst).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_logic_rules_full",
        "description": "Lese alle Automatisierungsregeln der Logic Engine.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_error_code_info",
        "description": "Lese alle bekannten Server-Error-Codes (5000-5999) mit Beschreibungen.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_diagnostic_reports",
        "description": "Lese die letzten Diagnose-Berichte aus der Datenbank.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_plugin_executions",
        "description": "Lese die letzten Plugin-Ausfuehrungs-Protokolle.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_heartbeat_logs",
        "description": "Lese Heartbeat-Logs, optional gefiltert nach ESP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "esp_id": {"type": "string", "description": "Optional: nur fuer diesen ESP"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "get_actuator_history",
        "description": "Lese Aktor-Events, optional gefiltert nach ESP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "esp_id": {"type": "string", "description": "Optional: nur fuer diesen ESP"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "query_loki",
        "description": "Lese Logs aus Loki mit einem LogQL-Query (z.B. '{container=\"el-servador\"}').",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "LogQL query string (z.B. '{job=\"el-servador\"}').",
                },
                "limit": {"type": "integer", "default": 100, "description": "Max. Log-Zeilen"},
                "start": {
                    "type": "string",
                    "description": "Start-Zeit (Unix ns oder RFC3339, default: jetzt-1h)",
                    "default": "now-1h",
                },
                "end": {
                    "type": "string",
                    "description": "End-Zeit (Unix ns oder RFC3339, default: now)",
                    "default": "now",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_prometheus",
        "description": "Fuehre eine PromQL-Anfrage gegen Prometheus aus.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PromQL-Ausdruck (z.B. 'up', 'rate(http_requests_total[5m])')",
                },
            },
            "required": ["query"],
        },
    },
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Du bist ein AutomationOne IoT-Framework Debugging-Experte.

AutomationOne besteht aus:
- El Trabajante: ESP32 C++ Firmware (Sensoren, Aktoren, MQTT)
- El Servador: FastAPI Python Server (Logic Engine, MQTT-Broker-Bridge, REST API)
- El Frontend: Vue 3 Dashboard

Deine Aufgabe: Analysiere Probleme mit den verfuegbaren Tools, sammle Evidenz
und gib einen strukturierten Befund mit konkreten Empfehlungen zurueck.
Benenne immer konkrete Ursachen und moegliche Loesungsschritte.
Antworte auf Deutsch, praezise und technisch korrekt.
"""


# ---------------------------------------------------------------------------
# ClaudeDebugAgent
# ---------------------------------------------------------------------------


class ClaudeDebugAgent:
    """
    Agentic debug assistant backed by Claude with 15 read-only tools.

    Usage:
        client = GodKaiserClient(base_url=settings.server.internal_url)
        agent = ClaudeDebugAgent(client=client, db_session=db)
        text = await agent.run_batch("Was ist falsch mit ESP_123?", session_id="s1")
    """

    _MODEL = "claude-opus-4-7"
    _MAX_TOKENS = 4096

    def __init__(
        self,
        client: "GodKaiserClient",
        db_session: Optional["AsyncSession"] = None,
    ) -> None:
        self._client = client
        self._db_session = db_session
        self._anthropic: Optional[Any] = None

    # ------------------------------------------------------------------
    # Anthropic client resolution
    # ------------------------------------------------------------------

    async def _get_anthropic_client(self) -> Any:
        """Resolve API key (DB-first, env fallback) and return AsyncAnthropic."""
        if self._anthropic is not None:
            return self._anthropic

        if not _ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic package is not installed")

        from .ai_service import AiService

        ai_svc = AiService()
        api_key = await ai_svc.get_configured_api_key(db_session=self._db_session)
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("No Anthropic API key configured (DB plugin 'claude' or ANTHROPIC_API_KEY env var)")

        self._anthropic = AsyncAnthropic(api_key=api_key)
        return self._anthropic

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Dispatch a tool call and return the result as a JSON string."""
        try:
            result = await self._dispatch_tool(tool_name, tool_input)
            return json.dumps(result, default=str)
        except Exception as exc:
            logger.warning("Tool %s failed: %s", tool_name, exc)
            return json.dumps({"error": str(exc), "tool": tool_name})

    async def _dispatch_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:  # noqa: PLR0911,PLR0912
        """Execute the named tool and return the raw result."""
        client = self._client

        if tool_name == "get_esp_full_state":
            esp_id: str = tool_input["esp_id"]
            device, sensors, actuators = await _gather_esp_state(client, esp_id)
            return {"device": device, "sensors": sensors, "actuators": actuators}

        if tool_name == "get_audit_logs":
            limit = int(tool_input.get("limit", 50))
            return await client.list_audit_logs(limit=min(limit, 200))

        if tool_name == "query_table":
            table = tool_input["table_name"]
            if table not in _ALLOWED_TABLES:
                return {"error": f"Table '{table}' not in allowed whitelist"}
            limit = int(tool_input.get("limit", 50))
            return await client.query_table(table, limit=limit)

        if tool_name == "get_sensor_history":
            esp_id = tool_input["esp_id"]
            gpio = tool_input.get("gpio")
            limit = int(tool_input.get("limit", 20))
            return await client.list_sensor_data(esp_id=esp_id, gpio=gpio, limit=limit)

        if tool_name == "get_health_metrics":
            return await client.get_health_metrics()

        if tool_name == "get_logic_rules_full":
            return await client.list_logic_rules()

        if tool_name == "get_error_code_info":
            codes = get_all_server_error_codes()
            return {str(k): v for k, v in codes.items()}

        if tool_name == "get_diagnostic_reports":
            limit = int(tool_input.get("limit", 10))
            return await client.query_table("diagnostic_reports", limit=limit)

        if tool_name == "get_plugin_executions":
            limit = int(tool_input.get("limit", 20))
            return await client.query_table("plugin_executions", limit=limit)

        if tool_name == "get_heartbeat_logs":
            limit = int(tool_input.get("limit", 50))
            data = await client.query_table("esp_heartbeat_logs", limit=limit)
            if "esp_id" in tool_input and tool_input["esp_id"]:
                esp_filter = tool_input["esp_id"]
                rows = data.get("rows") or data.get("data") or []
                if isinstance(rows, list):
                    rows = [r for r in rows if r.get("esp_id") == esp_filter]
                    return {"rows": rows}
            return data

        if tool_name == "get_actuator_history":
            limit = int(tool_input.get("limit", 50))
            data = await client.query_table("actuator_events", limit=limit)
            if "esp_id" in tool_input and tool_input["esp_id"]:
                esp_filter = tool_input["esp_id"]
                rows = data.get("rows") or data.get("data") or []
                if isinstance(rows, list):
                    rows = [r for r in rows if r.get("esp_id") == esp_filter]
                    return {"rows": rows}
            return data

        if tool_name == "query_loki":
            return await _query_loki(tool_input)

        if tool_name == "query_prometheus":
            return await _query_prometheus(tool_input)

        return {"error": f"Unknown tool: {tool_name}"}

    # ------------------------------------------------------------------
    # Agentic loop helpers
    # ------------------------------------------------------------------

    def _build_tool_result_block(self, tool_use_id: str, content: str) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }

    async def _run_agentic_loop(
        self,
        messages: list[dict[str, Any]],
        max_iterations: int,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Execute the agentic tool-use loop.

        Returns (final_messages, final_text).
        """
        anthropic = await self._get_anthropic_client()
        final_text = ""

        for iteration in range(max_iterations):
            response = await anthropic.messages.create(
                model=self._MODEL,
                max_tokens=self._MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=_DEBUG_TOOLS_V2,  # type: ignore[arg-type]
                messages=messages,
            )

            logger.debug(
                "ClaudeDebugAgent iteration %d: stop_reason=%s blocks=%d",
                iteration + 1,
                response.stop_reason,
                len(response.content),
            )

            if response.stop_reason == "end_turn":
                for block in reversed(response.content):
                    if hasattr(block, "text") and block.text:
                        final_text = block.text
                        break
                messages.append({"role": "assistant", "content": response.content})
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        result_content = await self._execute_tool(block.name, block.input)
                        tool_results.append(
                            self._build_tool_result_block(block.id, result_content)
                        )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                # Unexpected stop reason — extract text and break
                for block in response.content:
                    if hasattr(block, "text") and block.text:
                        final_text = block.text
                        break
                break

        return messages, final_text

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run_batch(
        self,
        user_message: str,
        session_id: str,
        esp_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        max_iterations: int = 10,
    ) -> str:
        """
        Run the agentic debug loop and return the complete text response.

        Args:
            user_message: The user's question or debug request.
            session_id:   Identifier for this conversation (used for logging).
            esp_id:       Optional ESP device ID to focus analysis on.
            context:      Optional extra context dict passed to the first message.
            max_iterations: Maximum tool-use iterations before stopping.

        Returns:
            The final text response from Claude.
        """
        content = user_message
        if esp_id:
            content = f"[ESP: {esp_id}] {content}"
        if context:
            content = f"{content}\n\nZusaetzlicher Kontext: {json.dumps(context, default=str)}"

        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]

        logger.info(
            "ClaudeDebugAgent.run_batch started session=%s esp_id=%s",
            session_id,
            esp_id,
        )

        try:
            _, final_text = await self._run_agentic_loop(messages, max_iterations)
        except Exception as exc:
            logger.error(
                "ClaudeDebugAgent.run_batch failed session=%s: %s",
                session_id,
                exc,
                exc_info=True,
            )
            return f"Fehler bei der Analyse: {exc}"

        logger.info(
            "ClaudeDebugAgent.run_batch completed session=%s chars=%d",
            session_id,
            len(final_text),
        )
        return final_text

    async def run(
        self,
        user_message: str,
        session_id: str,
        esp_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        max_iterations: int = 10,
    ) -> AsyncIterator[str]:
        """
        Streaming SSE variant — yields 'data: {chunk}\\n\\n' strings.

        Runs the same agentic loop as run_batch but streams the final
        text response token by token via the Anthropic streaming API.
        Tool-use iterations are performed without streaming (blocking per
        iteration); only the final end_turn response is streamed.
        """
        content = user_message
        if esp_id:
            content = f"[ESP: {esp_id}] {content}"
        if context:
            content = f"{content}\n\nZusaetzlicher Kontext: {json.dumps(context, default=str)}"

        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        anthropic = await self._get_anthropic_client()

        logger.info(
            "ClaudeDebugAgent.run (streaming) started session=%s esp_id=%s",
            session_id,
            esp_id,
        )

        # Tool-use iterations (non-streaming)
        for iteration in range(max_iterations - 1):
            response = await anthropic.messages.create(
                model=self._MODEL,
                max_tokens=self._MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=_DEBUG_TOOLS_V2,  # type: ignore[arg-type]
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                # Yield the final text as a single chunk
                for block in reversed(response.content):
                    if hasattr(block, "text") and block.text:
                        yield f"data: {block.text}\n\n"
                return

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        result_content = await self._execute_tool(block.name, block.input)
                        tool_results.append(
                            self._build_tool_result_block(block.id, result_content)
                        )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                for block in response.content:
                    if hasattr(block, "text") and block.text:
                        yield f"data: {block.text}\n\n"
                return

        # Final streaming turn
        async with anthropic.messages.stream(
            model=self._MODEL,
            max_tokens=self._MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            tools=_DEBUG_TOOLS_V2,  # type: ignore[arg-type]
            messages=messages,
        ) as stream:
            async for text_chunk in stream.text_stream:
                yield f"data: {text_chunk}\n\n"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _gather_esp_state(
    client: "GodKaiserClient",
    esp_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Fetch device, sensors and actuators concurrently."""
    import asyncio

    device_task = asyncio.create_task(client.get_device(esp_id))
    sensors_task = asyncio.create_task(client.list_sensors(esp_id=esp_id))
    actuators_task = asyncio.create_task(client.list_actuators(esp_id=esp_id))

    results = await asyncio.gather(device_task, sensors_task, actuators_task, return_exceptions=True)

    device: dict[str, Any] = results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])}
    sensors: dict[str, Any] = results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])}
    actuators: dict[str, Any] = results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])}
    return device, sensors, actuators


async def _query_loki(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Query Loki log aggregation via HTTP."""
    from ..core.config import get_settings

    settings = get_settings()
    loki_url = settings.external_services.loki_url
    query = tool_input.get("query", "")
    limit = int(tool_input.get("limit", 100))
    start = tool_input.get("start", "now-1h")
    end = tool_input.get("end", "now")

    params: dict[str, Any] = {
        "query": query,
        "limit": limit,
        "start": start,
        "end": end,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                f"{loki_url}/loki/api/v1/query_range",
                params=params,
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        return {"error": "Loki request timed out after 10s", "url": loki_url}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Loki HTTP {exc.response.status_code}", "url": loki_url}
    except Exception as exc:
        return {"error": str(exc), "url": loki_url}


async def _query_prometheus(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Query Prometheus via HTTP instant query."""
    from ..core.config import get_settings

    settings = get_settings()
    prometheus_url = settings.external_services.prometheus_url
    query = tool_input.get("query", "")

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                f"{prometheus_url}/api/v1/query",
                params={"query": query},
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        return {"error": "Prometheus request timed out after 10s", "url": prometheus_url}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Prometheus HTTP {exc.response.status_code}", "url": prometheus_url}
    except Exception as exc:
        return {"error": str(exc), "url": prometheus_url}
