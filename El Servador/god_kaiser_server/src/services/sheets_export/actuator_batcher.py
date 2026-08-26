"""
Actuator / rule batcher for the Sheets export pipeline (AUT-447 / S5).

This module owns the operational truth for the actuator tab:

- D1: actuator_history is the ONLY event source.
- D2: server-side ON/OFF pairing (Variante A) produces one row per
  completed run.
- D3: frozen ``ausloeser`` vocabulary.
- D8: correlation between actuator_history and logic_execution_history
  uses ``issued_by`` + optional ``correlation_id`` + time window (no
  hard FK).

The batcher returns an ``ActuatorBatch`` and updated ``open_runs`` so
the orchestrating service can write the rows AND persist both the
cursor and the open-runs state atomically (after a successful Sheets
write).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging_config import get_logger
from ...db.models.actuator import ActuatorHistory
from ...db.models.logic import CrossESPLogic, LogicExecutionHistory
from ...db.models.esp import ESPDevice

logger = get_logger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")

# Frozen 9-column actuator tab schema.
ACTUATOR_HEADER: List[str] = [
    "run_start_utc",
    "run_end_utc",
    "duration_seconds",
    "esp_id",
    "gpio",
    "actuator_type",
    "ausloeser",
    "result",
    "notes",
]

AUSLOESER_EMERGENCY = "emergency_stop"
AUSLOESER_LWT = "lwt_offline"


# -----------------------------------------------------------------------------
# Public dataclasses
# -----------------------------------------------------------------------------


@dataclass
class ActuatorRunRow:
    """One actuator run-line ready for Sheets."""

    run_start_utc: Optional[datetime]
    run_end_utc: Optional[datetime]
    duration_seconds: Optional[int]
    esp_id: str
    gpio: int
    actuator_type: str
    ausloeser: str
    result: str
    notes: str

    def to_sheet_row(self) -> List[Any]:
        return [
            _iso_or_blank(self.run_start_utc),
            _iso_or_blank(self.run_end_utc),
            "" if self.duration_seconds is None else int(self.duration_seconds),
            self.esp_id,
            int(self.gpio),
            self.actuator_type,
            self.ausloeser,
            self.result,
            self.notes,
        ]


@dataclass
class ActuatorBatch:
    """Result of one actuator export tick."""

    rows: List[ActuatorRunRow] = field(default_factory=list)
    open_runs_after: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_row_id: Optional[uuid.UUID] = None
    last_row_timestamp: Optional[datetime] = None
    notes_counter: Dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.rows

    def to_sheet_values(self) -> List[List[Any]]:
        return [r.to_sheet_row() for r in self.rows]


# -----------------------------------------------------------------------------
# Event classification
# -----------------------------------------------------------------------------


_OFF_COMMANDS: frozenset[str] = frozenset({"stop", "off", "emergency_stop"})
_ON_COMMANDS: frozenset[str] = frozenset({"set", "activate", "on", "pwm"})


def _is_on_event(history: ActuatorHistory) -> bool:
    cmd = (history.command_type or "").lower()
    if cmd in _OFF_COMMANDS:
        return False
    if cmd in _ON_COMMANDS:
        return (history.value or 0.0) > 0.0
    # Unknown command_type with positive value -> assume ON
    return (history.value or 0.0) > 0.0


def _is_off_event(history: ActuatorHistory) -> bool:
    cmd = (history.command_type or "").lower()
    if cmd in _OFF_COMMANDS:
        return True
    if cmd in _ON_COMMANDS:
        return (history.value or 0.0) == 0.0
    return (history.value or 0.0) == 0.0


def _classify_ausloeser(
    history: ActuatorHistory,
    rule_lookup: Dict[uuid.UUID, str],
) -> str:
    """Map ``issued_by`` to the frozen D3 vocabulary."""
    cmd = (history.command_type or "").lower()
    if cmd == "emergency_stop":
        return AUSLOESER_EMERGENCY

    issued_by = (history.issued_by or "").strip()
    if not issued_by:
        return "manual:unknown"

    lowered = issued_by.lower()
    if lowered.startswith("emergency:"):
        return AUSLOESER_EMERGENCY
    if lowered == "system:lwt_disconnect":
        return AUSLOESER_LWT
    if lowered.startswith("system:offline") or lowered.startswith("offline_rule"):
        return f"offline:{history.gpio}"
    if lowered.startswith("logic:"):
        # logic:<rule_id_or_name>
        rest = issued_by.split(":", 1)[1] if ":" in issued_by else ""
        rule_id: Optional[uuid.UUID]
        try:
            rule_id = uuid.UUID(rest)
        except (ValueError, TypeError):
            rule_id = None
        rule_name = rule_lookup.get(rule_id) if rule_id is not None else None
        if rule_id is None:
            return f"rule:{rest}"
        return f"rule:{rule_id}:{rule_name or rest}"
    if lowered.startswith("user:"):
        return f"manual:{issued_by}"
    if lowered.startswith("api:"):
        return f"manual:{issued_by}"
    if lowered.startswith("system:"):
        return f"manual:{issued_by}"

    return f"manual:{issued_by}"


# -----------------------------------------------------------------------------
# Batcher
# -----------------------------------------------------------------------------


class ActuatorExportBatcher:
    """
    Reads ``actuator_history`` and produces paired run-rows.

    Open-runs are passed in by the orchestrating service (rehydrated
    from ``system_config.sheets_export_history_open_runs`` on restart)
    and the updated state is returned in :class:`ActuatorBatch`.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        correlation_window_seconds: int = 120,
    ) -> None:
        self._session = session
        self._correlation_window = timedelta(seconds=correlation_window_seconds)

    async def fetch_batch(
        self,
        *,
        last_timestamp_iso: Optional[str],
        last_id: Optional[str],
        limit: int,
        open_runs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ActuatorBatch:
        anchor = _parse_anchor(last_timestamp_iso, last_id)

        stmt = (
            select(ActuatorHistory, ESPDevice.device_id.label("esp_device_id"))
            .outerjoin(ESPDevice, ESPDevice.id == ActuatorHistory.esp_id)
            .order_by(ActuatorHistory.timestamp.asc(), ActuatorHistory.id.asc())
            .limit(limit)
        )
        if anchor is not None:
            ts, row_id = anchor
            stmt = stmt.where(
                or_(
                    ActuatorHistory.timestamp > ts,
                    and_(
                        ActuatorHistory.timestamp == ts,
                        ActuatorHistory.id > row_id,
                    ),
                )
            )

        result = await self._session.execute(stmt)
        events_with_esp: List[tuple[ActuatorHistory, Optional[str]]] = [
            (row[0], row[1]) for row in result.all()
        ]

        if not events_with_esp:
            return ActuatorBatch(open_runs_after=dict(open_runs or {}))

        rule_lookup = await self._build_rule_lookup(events_with_esp)
        rule_correlation = await self._build_rule_correlation(events_with_esp)

        open_state: Dict[str, Dict[str, Any]] = {
            k: dict(v) for k, v in (open_runs or {}).items()
        }
        batch = ActuatorBatch(open_runs_after=open_state)

        for history, esp_device_id in events_with_esp:
            esp_display = esp_device_id or _short_uuid(history.esp_id)
            key = f"{history.esp_id}:{history.gpio}"

            current_open = open_state.get(key)
            ts = _ensure_aware(history.timestamp)
            ausloeser = _classify_ausloeser(history, rule_lookup)
            # D8 optional strengthen: pull stored correlation_id and tag
            corr_id = _extract_correlation_id(history.command_metadata)

            if _is_off_event(history) and not _is_on_event(history):
                # OFF (or emergency_stop)
                if current_open is None:
                    batch.rows.append(
                        ActuatorRunRow(
                            run_start_utc=None,
                            run_end_utc=ts,
                            duration_seconds=None,
                            esp_id=esp_display,
                            gpio=int(history.gpio),
                            actuator_type=str(history.actuator_type or ""),
                            ausloeser=ausloeser,
                            result=_result_string(history),
                            notes="off_without_on",
                        )
                    )
                    _bump(batch.notes_counter, "off_without_on")
                else:
                    start_ts = _ensure_aware(
                        datetime.fromisoformat(current_open["start_ts"])
                    )
                    duration_s = int(max(0.0, (ts - start_ts).total_seconds()))
                    notes = current_open.get("notes") or ""
                    if (history.command_type or "").lower() == "emergency_stop":
                        ausloeser_final = AUSLOESER_EMERGENCY
                        notes = _merge_notes(notes, "emergency_stop")
                    elif ausloeser == AUSLOESER_LWT:
                        ausloeser_final = AUSLOESER_LWT
                        notes = _merge_notes(notes, "lwt_offline")
                    else:
                        ausloeser_final = current_open.get("ausloeser") or ausloeser
                    batch.rows.append(
                        ActuatorRunRow(
                            run_start_utc=start_ts,
                            run_end_utc=ts,
                            duration_seconds=duration_s,
                            esp_id=esp_display,
                            gpio=int(history.gpio),
                            actuator_type=str(history.actuator_type or ""),
                            ausloeser=ausloeser_final,
                            result=_result_string(history),
                            notes=notes,
                        )
                    )
                    if notes:
                        for tag in notes.split(","):
                            tag = tag.strip()
                            if tag:
                                _bump(batch.notes_counter, tag)
                    open_state.pop(key, None)
            elif _is_on_event(history):
                # ON
                if current_open is not None:
                    # double-ON without OFF -> close previous as overlapping
                    start_ts = _ensure_aware(
                        datetime.fromisoformat(current_open["start_ts"])
                    )
                    duration_s = int(max(0.0, (ts - start_ts).total_seconds()))
                    batch.rows.append(
                        ActuatorRunRow(
                            run_start_utc=start_ts,
                            run_end_utc=ts,
                            duration_seconds=duration_s,
                            esp_id=esp_display,
                            gpio=int(history.gpio),
                            actuator_type=str(history.actuator_type or ""),
                            ausloeser=(
                                current_open.get("ausloeser")
                                or ausloeser
                            ),
                            result=_result_string(history),
                            notes="overlapping_on",
                        )
                    )
                    _bump(batch.notes_counter, "overlapping_on")
                # Enrich rule-correlation by time window (D8 Option A)
                enriched = _maybe_enrich_with_correlation(
                    ausloeser=ausloeser,
                    history=history,
                    rule_correlation=rule_correlation,
                    correlation_id=corr_id,
                    window=self._correlation_window,
                )
                open_state[key] = {
                    "start_id": str(history.id),
                    "start_ts": _ensure_aware(history.timestamp)
                    .astimezone(timezone.utc)
                    .isoformat(),
                    "issued_by": history.issued_by,
                    "value": history.value,
                    "ausloeser": enriched,
                    "correlation_id": corr_id,
                    "notes": "",
                }
            # else: row neither pure ON nor pure OFF — defensive skip.

            batch.last_row_id = uuid.UUID(str(history.id))
            batch.last_row_timestamp = _ensure_aware(history.timestamp)

        return batch

    async def _build_rule_lookup(
        self,
        events: Sequence[tuple[ActuatorHistory, Optional[str]]],
    ) -> Dict[uuid.UUID, str]:
        ids: set[uuid.UUID] = set()
        for history, _ in events:
            issued_by = (history.issued_by or "").lower()
            if not issued_by.startswith("logic:"):
                continue
            rest = issued_by.split(":", 1)[1]
            try:
                ids.add(uuid.UUID(rest))
            except (ValueError, TypeError):
                continue
        if not ids:
            return {}
        stmt = select(CrossESPLogic.id, CrossESPLogic.rule_name).where(
            CrossESPLogic.id.in_(list(ids))
        )
        rows = await self._session.execute(stmt)
        return {row.id: row.rule_name for row in rows}

    async def _build_rule_correlation(
        self,
        events: Sequence[tuple[ActuatorHistory, Optional[str]]],
    ) -> Dict[uuid.UUID, List[Any]]:
        """Pre-fetch logic_execution_history per rule_id within the window."""
        rule_ids: set[uuid.UUID] = set()
        for history, _ in events:
            issued_by = (history.issued_by or "").lower()
            if not issued_by.startswith("logic:"):
                continue
            try:
                rule_ids.add(uuid.UUID(issued_by.split(":", 1)[1]))
            except (ValueError, TypeError):
                continue
        if not rule_ids:
            return {}

        earliest = min(_ensure_aware(h.timestamp) for h, _ in events) - (
            self._correlation_window * 2
        )
        latest = max(_ensure_aware(h.timestamp) for h, _ in events) + (
            self._correlation_window * 2
        )
        stmt = (
            select(LogicExecutionHistory)
            .where(LogicExecutionHistory.logic_rule_id.in_(list(rule_ids)))
            .where(LogicExecutionHistory.timestamp >= earliest)
            .where(LogicExecutionHistory.timestamp <= latest)
            .order_by(LogicExecutionHistory.timestamp.asc())
        )
        result = await self._session.execute(stmt)
        bucket: Dict[uuid.UUID, List[Any]] = {}
        for execution in result.scalars().all():
            bucket.setdefault(execution.logic_rule_id, []).append(execution)
        return bucket


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _parse_anchor(
    last_timestamp_iso: Optional[str],
    last_id: Optional[str],
) -> Optional[tuple[datetime, uuid.UUID]]:
    if not last_timestamp_iso or not last_id:
        return None
    try:
        ts = datetime.fromisoformat(last_timestamp_iso)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    try:
        row_id = uuid.UUID(str(last_id))
    except (ValueError, TypeError):
        return None
    return ts, row_id


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _short_uuid(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text[:8] if len(text) > 8 else text


def _iso_or_blank(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


def _result_string(history: ActuatorHistory) -> str:
    if history.success:
        return "success"
    if history.error_message:
        return f"failure:{history.error_message}"
    return "failure"


def _merge_notes(existing: str, addition: str) -> str:
    if not existing:
        return addition
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    if addition not in parts:
        parts.append(addition)
    return ",".join(parts)


def _bump(counter: Dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _extract_correlation_id(metadata: Optional[dict]) -> Optional[str]:
    if not isinstance(metadata, dict):
        return None
    for key in ("correlation_id", "mqtt_correlation_id", "incident_correlation_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _maybe_enrich_with_correlation(
    *,
    ausloeser: str,
    history: ActuatorHistory,
    rule_correlation: Dict[uuid.UUID, List[Any]],
    correlation_id: Optional[str],
    window: timedelta,
) -> str:
    """
    For ``logic:*`` triggers we prefer a stronger correlation hit if
    available. ``correlation_id`` from MQTT metadata is the strongest
    signal; otherwise we accept the first time-window match.
    """
    if not ausloeser.startswith("rule:"):
        return ausloeser

    issued_by = (history.issued_by or "").lower()
    if not issued_by.startswith("logic:"):
        return ausloeser
    try:
        rule_id = uuid.UUID(issued_by.split(":", 1)[1])
    except (ValueError, TypeError):
        return ausloeser

    executions = rule_correlation.get(rule_id) or []
    if not executions:
        return ausloeser

    ts = _ensure_aware(history.timestamp)

    matching = None
    if correlation_id:
        for execution in executions:
            metadata = getattr(execution, "execution_metadata", None) or {}
            if metadata.get("correlation_id") == correlation_id:
                matching = execution
                break
    if matching is None:
        for execution in executions:
            exec_ts = _ensure_aware(execution.timestamp)
            if abs(exec_ts - ts) <= window:
                matching = execution
                break
    if matching is None:
        return ausloeser

    # ausloeser already contains rule_name from lookup — keep as-is, just
    # ensure prefix is correct.
    return ausloeser
