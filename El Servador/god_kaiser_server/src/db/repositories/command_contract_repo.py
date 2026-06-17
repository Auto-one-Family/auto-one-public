"""
Repository for intent/outcome contract persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.command_contract import CommandIntent, CommandOutcome
from ...core.logging_config import get_logger
from ...services.intent_outcome_contract import canonicalize_intent_outcome

logger = get_logger(__name__)

LEGACY_OUTCOMES = {"accepted", "applied", "rejected", "failed", "expired"}

# AUT-329: Outcomes that are considered terminal/final for ordering-race protection.
# Maps to FINAL_OUTCOMES in intent_outcome_contract.py plus "applied" which the firmware
# may emit after "accepted" (non-terminal → terminal progression is allowed; the reverse is not).
_TERMINAL_OUTCOMES = frozenset({"persisted", "rejected", "failed", "expired", "applied"})

# Inbound intent_outcome already advanced orchestration — never overwrite with "sent".
_INTENT_ORCH_ADVANCED_FROM_DEVICE = frozenset({"accepted", "ack_pending"})
_INTENT_ORCH_TERMINAL = frozenset({"terminal_success", "terminal_failed"})
_INTENT_ORCH_STATE_RANK = {
    "sent": 0,
    "accepted": 1,
    "ack_pending": 2,
    "terminal_success": 3,
    "terminal_failed": 3,
}


class CommandContractRepository:
    """Persistence facade for command_intents and command_outcomes."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_intent(self, payload: dict[str, Any], esp_id: str) -> CommandIntent:
        """Create/update ``command_intents`` from inbound ``intent_outcome`` (ESP → Server).

        State rule (orchestration_state):
        - ``outcome == "accepted"`` → ``accepted`` (ESP acknowledged admission)
        - any other canonical outcome in this event → ``ack_pending`` (awaiting further
          terminal progression tracked in ``command_outcomes``)

        This path does **not** set ``sent``; that is written only after the server
        successfully publishes MQTT when using ``record_intent_publish_sent`` (e.g. actuator
        commands with ``intent_id``/``correlation_id`` on the wire).
        """
        intent_id = str(payload["intent_id"])
        stmt = select(CommandIntent).where(CommandIntent.intent_id == intent_id).limit(1)
        result = await self.session.execute(stmt)
        intent = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        outcome = str(payload["outcome"]).lower()
        next_state = "accepted" if outcome == "accepted" else "ack_pending"

        if intent is None:
            insert_stmt = (
                pg_insert(CommandIntent)
                .values(
                    intent_id=intent_id,
                    correlation_id=str(payload["correlation_id"]),
                    esp_id=esp_id,
                    flow=str(payload["flow"]).lower(),
                    orchestration_state=next_state,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                .on_conflict_do_nothing(index_elements=["intent_id"])
            )
            await self.session.execute(insert_stmt)
            result = await self.session.execute(stmt)
            intent = result.scalar_one_or_none()
            if intent is None:
                raise RuntimeError(f"CommandIntent insert/select anomaly for intent_id={intent_id}")

        intent.correlation_id = str(payload["correlation_id"])
        intent.esp_id = esp_id
        intent.flow = str(payload["flow"]).lower()
        if self._can_advance_orchestration_state(intent.orchestration_state, next_state):
            intent.orchestration_state = next_state
        intent.last_seen_at = now
        await self.session.flush()
        await self.session.refresh(intent)
        return intent

    async def record_intent_publish_sent(
        self,
        *,
        intent_id: str,
        correlation_id: str,
        esp_id: str,
        flow: str,
    ) -> CommandIntent:
        """Persist ``orchestration_state='sent'`` after the broker accepted the publish.

        Preconditions: outbound JSON used the same ``intent_id`` the ESP will echo
        (actuator commands: ``intent_id`` mirrors ``correlation_id`` in ``Publisher``).

        If a row already exists with ``accepted`` or ``ack_pending`` from a fast
        ``intent_outcome``, the row is left unchanged (no downgrade).
        """
        iid = str(intent_id).strip()
        stmt = select(CommandIntent).where(CommandIntent.intent_id == iid).limit(1)
        result = await self.session.execute(stmt)
        intent = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        flow_norm = str(flow).lower()

        if intent is not None:
            if intent.orchestration_state in _INTENT_ORCH_ADVANCED_FROM_DEVICE:
                return intent
            if intent.orchestration_state in _INTENT_ORCH_TERMINAL:
                return intent
            intent.correlation_id = str(correlation_id)
            intent.esp_id = esp_id
            intent.flow = flow_norm
            intent.orchestration_state = "sent"
            intent.last_seen_at = now
            await self.session.flush()
            await self.session.refresh(intent)
            return intent

        insert_stmt = (
            pg_insert(CommandIntent)
            .values(
                intent_id=iid,
                correlation_id=str(correlation_id),
                esp_id=esp_id,
                flow=flow_norm,
                orchestration_state="sent",
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_nothing(index_elements=["intent_id"])
        )
        await self.session.execute(insert_stmt)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is None:
            raise RuntimeError(f"CommandIntent insert/select anomaly for intent_id={iid}")
        if existing.orchestration_state in _INTENT_ORCH_ADVANCED_FROM_DEVICE:
            return existing
        if existing.orchestration_state in _INTENT_ORCH_TERMINAL:
            return existing
        existing.correlation_id = str(correlation_id)
        existing.esp_id = esp_id
        existing.flow = flow_norm
        existing.orchestration_state = "sent"
        existing.last_seen_at = now
        await self.session.flush()
        await self.session.refresh(existing)
        return existing

    async def upsert_outcome(
        self, payload: dict[str, Any], esp_id: str
    ) -> tuple[CommandOutcome, bool]:
        """
        Upsert terminal outcome by intent_id.

        Returns:
            (outcome_row, was_stale)
        """
        intent_id = str(payload["intent_id"])
        stmt = select(CommandOutcome).where(CommandOutcome.intent_id == intent_id).limit(1)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        incoming_generation = self._to_int(payload.get("generation"), default=-1)
        incoming_seq = self._to_int(payload.get("seq"), default=-1)
        normalized = self._normalize_contract_fields(payload)
        now = datetime.now(timezone.utc)

        incoming_outcome_str = str(normalized["outcome"]).lower()
        incoming_is_terminal = bool(normalized["is_final"]) or (
            incoming_outcome_str in _TERMINAL_OUTCOMES
        )

        if existing is None:
            created = CommandOutcome(
                intent_id=intent_id,
                correlation_id=str(payload["correlation_id"]),
                esp_id=esp_id,
                flow=str(payload["flow"]).lower(),
                outcome=normalized["outcome"],
                contract_version=normalized["contract_version"],
                semantic_mode=normalized["semantic_mode"],
                legacy_status=normalized["legacy_status"],
                target_status=normalized["target_status"],
                is_final=normalized["is_final"],
                code=normalized["code"],
                reason=normalized["reason"],
                retryable=bool(normalized["retryable"]),
                generation=self._to_opt_int(payload.get("generation")),
                seq=self._to_opt_int(payload.get("seq")),
                epoch=self._to_opt_int(payload.get("epoch")),
                ttl_ms=self._to_opt_int(payload.get("ttl_ms")),
                ts=self._to_opt_int(payload.get("ts")),
                first_seen_at=now,
                terminal_at=now if incoming_is_terminal else None,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(created)
                    await self.session.flush()
                await self.session.refresh(created)
                await self._set_terminal_intent_state_if_needed(
                    intent_id=intent_id,
                    outcome=created.outcome,
                    is_terminal=incoming_is_terminal,
                    observed_at=now,
                )
                self._log_t6_terminal_stage_if_applicable(created)
                return created, False
            except IntegrityError:
                # Parallel insert won the race. Continue deterministic dedup flow.
                result = await self.session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is None:
                    raise

        existing_generation = existing.generation if existing.generation is not None else -1
        existing_seq = existing.seq if existing.seq is not None else -1

        # AUT-329: Terminal-beats-non-terminal guard.
        # MQTT OUTBOX pressure or reconnect bursts can deliver a non-terminal message
        # (e.g. "accepted") *after* a terminal one (e.g. "failed") due to QoS reordering.
        # If the stored outcome is already terminal and the incoming one is non-terminal,
        # the incoming message is a stale delivery and must be silently discarded.
        existing_outcome_str = str(existing.outcome).lower()
        canonical_outcome_str = incoming_outcome_str
        if (
            existing_outcome_str in _TERMINAL_OUTCOMES
            and canonical_outcome_str not in _TERMINAL_OUTCOMES
        ):
            await self._set_terminal_intent_state_if_needed(
                intent_id=intent_id,
                outcome=existing.outcome,
                is_terminal=True,
                observed_at=existing.terminal_at or now,
            )
            logger.debug(
                "[AUT-329] Skipping non-terminal '%s' delivery after terminal '%s': intent_id=%s",
                canonical_outcome_str,
                existing_outcome_str,
                intent_id,
            )
            return existing, True

        # Out-of-order protection: stale generations/sequences are ignored.
        if (incoming_generation < existing_generation) or (
            incoming_generation == existing_generation and incoming_seq < existing_seq
        ):
            if bool(existing.is_final) or existing_outcome_str in _TERMINAL_OUTCOMES:
                await self._set_terminal_intent_state_if_needed(
                    intent_id=intent_id,
                    outcome=existing.outcome,
                    is_terminal=True,
                    observed_at=existing.terminal_at or now,
                )
            return existing, True

        # Monotonic finality guard: a final outcome remains final.
        if bool(existing.is_final):
            incoming_is_final = bool(normalized["is_final"])
            if not incoming_is_final:
                await self._set_terminal_intent_state_if_needed(
                    intent_id=intent_id,
                    outcome=existing.outcome,
                    is_terminal=True,
                    observed_at=existing.terminal_at or now,
                )
                return existing, True
            if str(existing.outcome).lower() != str(normalized["outcome"]).lower():
                await self._set_terminal_intent_state_if_needed(
                    intent_id=intent_id,
                    outcome=existing.outcome,
                    is_terminal=True,
                    observed_at=existing.terminal_at or now,
                )
                return existing, True
            # Same final state replay -> idempotent duplicate.
            await self._set_terminal_intent_state_if_needed(
                intent_id=intent_id,
                outcome=existing.outcome,
                is_terminal=True,
                observed_at=existing.terminal_at or now,
            )
            return existing, True

        existing.correlation_id = str(payload["correlation_id"])
        existing.esp_id = esp_id
        existing.flow = str(payload["flow"]).lower()
        existing.outcome = normalized["outcome"]
        existing.contract_version = normalized["contract_version"]
        existing.semantic_mode = normalized["semantic_mode"]
        existing.legacy_status = normalized["legacy_status"]
        existing.target_status = normalized["target_status"]
        existing.is_final = normalized["is_final"]
        existing.code = normalized["code"]
        existing.reason = normalized["reason"]
        existing.retryable = bool(normalized["retryable"])
        existing.generation = self._to_opt_int(payload.get("generation"))
        existing.seq = self._to_opt_int(payload.get("seq"))
        existing.epoch = self._to_opt_int(payload.get("epoch"))
        existing.ttl_ms = self._to_opt_int(payload.get("ttl_ms"))
        existing.ts = self._to_opt_int(payload.get("ts"))
        if incoming_is_terminal and existing.terminal_at is None:
            existing.terminal_at = now
        await self._set_terminal_intent_state_if_needed(
            intent_id=intent_id,
            outcome=existing.outcome,
            is_terminal=incoming_is_terminal,
            observed_at=now,
        )
        await self.session.flush()
        await self.session.refresh(existing)
        self._log_t6_terminal_stage_if_applicable(existing)
        return existing, False

    async def list_open_intents_for_esp(
        self,
        *,
        esp_id: str,
        states: tuple[str, ...] = ("sent", "accepted", "ack_pending"),
    ) -> list[CommandIntent]:
        stmt = (
            select(CommandIntent)
            .where(CommandIntent.esp_id == esp_id)
            .where(CommandIntent.orchestration_state.in_(states))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_terminal_event_authority(
        self,
        *,
        event_class: str,
        dedup_key: str,
        esp_id: str,
        outcome: str,
        correlation_id: Optional[str] = None,
        is_final: bool = True,
        code: Optional[str] = None,
        reason: Optional[str] = None,
        retryable: bool = False,
        generation: Any = None,
        seq: Any = None,
        payload_ts: Any = None,
    ) -> tuple[CommandOutcome, bool]:
        """
        Persist write-once authority for non-intent terminal event classes.

        The row is stored in ``command_outcomes`` using a namespaced ``intent_id``
        so all terminal event classes share the same monotonic finality guards.
        """
        event_class_norm = str(event_class or "unknown").strip().lower()[:32]
        dedup_norm = str(dedup_key or "").strip().lower()
        intent_id = f"terminal:{event_class_norm}:{dedup_norm}"
        corr = str(correlation_id or dedup_norm or intent_id)[:128]
        outcome_norm = str(outcome or "unknown").strip().lower()[:32]

        stmt = select(CommandOutcome).where(CommandOutcome.intent_id == intent_id).limit(1)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        incoming_generation = self._to_int(generation, default=-1)
        incoming_seq = self._to_int(seq, default=-1)
        now = datetime.now(timezone.utc)

        if existing is None:
            insert_stmt = (
                pg_insert(CommandOutcome)
                .values(
                    intent_id=intent_id,
                    correlation_id=corr,
                    esp_id=esp_id,
                    flow=event_class_norm,
                    outcome=outcome_norm,
                    contract_version=2,
                    semantic_mode="target",
                    legacy_status=outcome_norm,
                    target_status=outcome_norm,
                    is_final=bool(is_final),
                    code=code,
                    reason=reason,
                    retryable=bool(retryable),
                    generation=self._to_opt_int(generation),
                    seq=self._to_opt_int(seq),
                    epoch=None,
                    ttl_ms=None,
                    ts=self._to_opt_int(payload_ts),
                    first_seen_at=now,
                    terminal_at=now,
                )
                .on_conflict_do_nothing(index_elements=["intent_id"])
                .returning(CommandOutcome.id)
            )
            inserted_id = (await self.session.execute(insert_stmt)).scalar_one_or_none()
            if inserted_id is not None:
                result = await self.session.execute(stmt)
                created = result.scalar_one_or_none()
                if created is None:
                    raise RuntimeError(
                        f"CommandOutcome inserted but not found afterward (intent_id={intent_id})"
                    )
                return created, False

            # Another concurrent worker inserted first. Treat as stale duplicate.
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is None:
                raise RuntimeError(
                    f"CommandOutcome conflict path missing existing row (intent_id={intent_id})"
                )
            return existing, True

        existing_generation = existing.generation if existing.generation is not None else -1
        existing_seq = existing.seq if existing.seq is not None else -1
        if (incoming_generation < existing_generation) or (
            incoming_generation == existing_generation and incoming_seq < existing_seq
        ):
            return existing, True

        if bool(existing.is_final):
            incoming_is_final = bool(is_final)
            if not incoming_is_final:
                return existing, True
            if str(existing.outcome).lower() != outcome_norm:
                return existing, True
            return existing, True

        existing.correlation_id = corr
        existing.esp_id = esp_id
        existing.flow = event_class_norm
        existing.outcome = outcome_norm
        existing.contract_version = 2
        existing.semantic_mode = "target"
        existing.legacy_status = outcome_norm
        existing.target_status = outcome_norm
        existing.is_final = bool(is_final)
        existing.code = code
        existing.reason = reason
        existing.retryable = bool(retryable)
        existing.generation = self._to_opt_int(generation)
        existing.seq = self._to_opt_int(seq)
        existing.ts = self._to_opt_int(payload_ts)
        existing.terminal_at = now
        await self.session.flush()
        await self.session.refresh(existing)
        return existing, False

    def _log_t6_terminal_stage_if_applicable(self, outcome_row: CommandOutcome) -> None:
        """Emit reproducible t6 stage marker for command-terminal outcomes."""
        if str(outcome_row.flow).lower() != "command":
            return
        # Keep instrumentation aligned with persisted terminal_at semantics.
        if outcome_row.terminal_at is None:
            return
        if not outcome_row.correlation_id:
            return
        terminal_at = outcome_row.terminal_at or datetime.now(timezone.utc)
        observed_at_ms = int(terminal_at.timestamp() * 1000)
        logger.warning(
            "latency_stage stage=t6_db_terminal_at correlation_id=%s intent_id=%s flow=%s observed_at_ms=%s outcome=%s",
            outcome_row.correlation_id,
            outcome_row.intent_id,
            outcome_row.flow,
            observed_at_ms,
            outcome_row.outcome,
        )

    async def get_by_intent_id(self, intent_id: str) -> Optional[CommandOutcome]:
        stmt = select(CommandOutcome).where(CommandOutcome.intent_id == intent_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(
        self,
        limit: int = 100,
        esp_id: Optional[str] = None,
        flow: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> list[CommandOutcome]:
        stmt = select(CommandOutcome)
        if esp_id:
            stmt = stmt.where(CommandOutcome.esp_id == esp_id)
        if flow:
            stmt = stmt.where(CommandOutcome.flow == flow.lower())
        if outcome:
            stmt = stmt.where(CommandOutcome.outcome == outcome.lower())

        stmt = stmt.order_by(desc(CommandOutcome.terminal_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _to_str(value: Any) -> Optional[str]:
        return None if value is None else str(value)

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _normalize_contract_fields(cls, payload: dict[str, Any]) -> dict[str, Any]:
        canonical = canonicalize_intent_outcome(payload)
        outcome = canonical.outcome

        contract_version = cls._to_int(payload.get("contract_version"), default=1)
        if contract_version not in (1, 2):
            contract_version = 1

        semantic_mode = str(payload.get("semantic_mode") or "").lower()
        if semantic_mode not in {"legacy", "dual", "target"}:
            semantic_mode = "legacy" if contract_version == 1 else "target"

        legacy_status = cls._to_str(payload.get("legacy_status"))
        target_status = cls._to_str(payload.get("target_status"))
        if not legacy_status and outcome in LEGACY_OUTCOMES:
            legacy_status = outcome
        if not target_status:
            target_status = "persisted" if outcome == "persisted" else outcome

        is_final = canonical.is_final
        return {
            "outcome": outcome,
            "contract_version": contract_version,
            "semantic_mode": semantic_mode,
            "legacy_status": legacy_status,
            "target_status": target_status,
            "is_final": is_final,
            "code": canonical.code,
            "reason": canonical.reason,
            "retryable": canonical.retryable,
        }

    @classmethod
    def _to_opt_int(cls, value: Any) -> Optional[int]:
        parsed = cls._to_int(value, default=-1)
        return None if parsed == -1 else parsed

    @classmethod
    def _can_advance_orchestration_state(cls, current: str, target: str) -> bool:
        current_norm = str(current or "").strip().lower()
        target_norm = str(target or "").strip().lower()
        if not current_norm:
            return True
        if current_norm in _INTENT_ORCH_TERMINAL and target_norm not in _INTENT_ORCH_TERMINAL:
            return False
        current_rank = _INTENT_ORCH_STATE_RANK.get(current_norm, -1)
        target_rank = _INTENT_ORCH_STATE_RANK.get(target_norm, -1)
        return target_rank >= current_rank

    @staticmethod
    def _terminal_state_for_outcome(outcome: str) -> str:
        normalized = str(outcome or "").strip().lower()
        if normalized in {"persisted", "applied"}:
            return "terminal_success"
        return "terminal_failed"

    async def _set_terminal_intent_state_if_needed(
        self,
        *,
        intent_id: str,
        outcome: str,
        is_terminal: bool,
        observed_at: datetime,
    ) -> None:
        if not is_terminal:
            return
        stmt = select(CommandIntent).where(CommandIntent.intent_id == intent_id).limit(1)
        intent = (await self.session.execute(stmt)).scalar_one_or_none()
        if intent is None:
            return
        target_state = self._terminal_state_for_outcome(outcome)
        if not self._can_advance_orchestration_state(intent.orchestration_state, target_state):
            return
        intent.orchestration_state = target_state
        intent.last_seen_at = observed_at
