"""
Durable inbound inbox for critical MQTT classes (P0.3).

Storage is append-only JSONL with atomic rewrite-on-ack semantics.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

from ..core.logging_config import get_logger

logger = get_logger(__name__)

# Entries that exceed this attempt count are marked "dead" and excluded from replay.
# Prevents permanent retry loops for structurally invalid messages.
_MAX_REPLAY_ATTEMPTS = 20


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InboundPriority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2


class InboundInboxService:
    """File-backed durable inbox with simple replay/dedup support."""

    def __init__(self, file_path: Optional[str] = None, capacity: int = 20000) -> None:
        base_dir = Path(tempfile.gettempdir()) / "god-kaiser-inbox"
        base_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = Path(file_path) if file_path else base_dir / "critical-inbound.jsonl"
        self._capacity = capacity
        self._lock = asyncio.Lock()
        self._events: list[dict[str, Any]] = []
        self._loaded = False
        self._last_loaded_mtime: float = -1.0

    @staticmethod
    def _safe_stat_mtime(path: Path) -> float:
        """Best-effort stat to avoid TOCTOU FileNotFoundError."""
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            return -1.0

    def _ensure_parent_dir(self, context: str) -> bool:
        """Ensure parent directory exists; logs action for operations."""
        parent = self._file_path.parent
        if parent.exists():
            return True
        try:
            parent.mkdir(parents=True, exist_ok=True)
            logger.warning(
                "Inbound inbox parent directory missing path=%s action=created context=%s",
                parent,
                context,
            )
            return True
        except Exception as exc:
            logger.error(
                "Inbound inbox parent directory ensure failed path=%s action=failed context=%s error=%s",
                parent,
                context,
                exc,
            )
            return False

    async def append(
        self,
        topic: str,
        payload: dict[str, Any],
        correlation_id: Optional[str] = None,
        source: str = "live",
        priority: InboundPriority = InboundPriority.NORMAL,
    ) -> str:
        await self._ensure_loaded()
        event_id = str(uuid.uuid4())
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(f"{topic}|{payload_json}".encode("utf-8")).hexdigest()

        event = {
            "id": event_id,
            "topic": topic,
            "payload": payload,
            "payload_hash": content_hash,
            "correlation_id": correlation_id,
            "source": source,
            "status": "pending",
            "priority": int(priority),
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "attempts": 0,
        }

        async with self._lock:
            if len(self._events) >= self._capacity:
                created_space = self._evict_for_capacity_locked()
                if not created_space:
                    pending_by_prio = self._pending_by_priority_locked()
                    logger.error(
                        "inbound_inbox_capacity_critical topic=%s priority=%s pending=%s capacity=%s pending_critical=%s pending_high=%s pending_normal=%s",
                        topic,
                        priority.name,
                        len(self._events),
                        self._capacity,
                        pending_by_prio["critical"],
                        pending_by_prio["high"],
                        pending_by_prio["normal"],
                    )
                    return ""

            self._events.append(event)
            await self._persist_locked()
        return event_id

    def _priority_of(self, event: dict[str, Any]) -> InboundPriority:
        raw = event.get("priority")
        try:
            return InboundPriority(int(raw))
        except (TypeError, ValueError):
            return InboundPriority.NORMAL

    def _pending_by_priority_locked(self) -> dict[str, int]:
        pending = [event for event in self._events if event.get("status") != "acked"]
        return {
            "critical": sum(
                1 for event in pending if self._priority_of(event) == InboundPriority.CRITICAL
            ),
            "high": sum(
                1 for event in pending if self._priority_of(event) == InboundPriority.HIGH
            ),
            "normal": sum(
                1 for event in pending if self._priority_of(event) == InboundPriority.NORMAL
            ),
        }

    def _evict_for_capacity_locked(self) -> bool:
        """
        Create one free slot under capacity pressure.

        Order:
        1) Drop oldest acked event (always safe).
        2) Drop oldest pending NORMAL.
        3) Drop oldest pending HIGH.
        4) If only CRITICAL pending remain -> refuse drop and escalate.
        """
        acked_events = [event for event in self._events if event.get("status") == "acked"]
        if acked_events:
            oldest_acked = min(acked_events, key=lambda item: item.get("updated_at", ""))
            self._events.remove(oldest_acked)
            pending_by_prio = self._pending_by_priority_locked()
            logger.warning(
                "inbound_inbox_evict priority=ACKED topic=%s id=%s pending_critical=%s pending_high=%s pending_normal=%s",
                oldest_acked.get("topic"),
                oldest_acked.get("id"),
                pending_by_prio["critical"],
                pending_by_prio["high"],
                pending_by_prio["normal"],
            )
            return True

        for priority in (InboundPriority.NORMAL, InboundPriority.HIGH):
            candidates = [
                event
                for event in self._events
                if event.get("status") != "acked" and self._priority_of(event) == priority
            ]
            if not candidates:
                continue
            oldest = min(candidates, key=lambda item: item.get("created_at", ""))
            self._events.remove(oldest)
            pending_by_prio = self._pending_by_priority_locked()
            logger.warning(
                "inbound_inbox_evict priority=%s topic=%s id=%s pending_critical=%s pending_high=%s pending_normal=%s",
                priority.name,
                oldest.get("topic"),
                oldest.get("id"),
                pending_by_prio["critical"],
                pending_by_prio["high"],
                pending_by_prio["normal"],
            )
            return True

        pending_by_prio = self._pending_by_priority_locked()
        logger.error(
            "inbound_inbox_evict_blocked reason=only_critical_pending pending_critical=%s pending_high=%s pending_normal=%s",
            pending_by_prio["critical"],
            pending_by_prio["high"],
            pending_by_prio["normal"],
        )
        return False

    async def mark_delivered(self, event_id: str) -> None:
        await self._ensure_loaded()
        async with self._lock:
            for event in self._events:
                if event["id"] == event_id:
                    event["status"] = "acked"
                    event["updated_at"] = _utc_now_iso()
                    await self._persist_locked()
                    return

    async def mark_attempt(self, event_id: str) -> None:
        await self._ensure_loaded()
        async with self._lock:
            for event in self._events:
                if event["id"] == event_id:
                    new_attempts = int(event.get("attempts", 0)) + 1
                    event["attempts"] = new_attempts
                    event["updated_at"] = _utc_now_iso()
                    if new_attempts >= _MAX_REPLAY_ATTEMPTS:
                        event["status"] = "dead"
                        logger.warning(
                            "Inbound inbox event %s exceeded max attempts (%d), "
                            "marking as dead. topic=%s",
                            event_id,
                            _MAX_REPLAY_ATTEMPTS,
                            event.get("topic"),
                        )
                    await self._persist_locked()
                    return

    async def list_pending(self, limit: int = 200) -> list[dict[str, Any]]:
        await self._ensure_loaded()
        async with self._lock:
            pending = [event for event in self._events if event.get("status") == "pending"]
            return [dict(item) for item in pending[:limit]]

    async def stats(self) -> dict[str, int]:
        await self._ensure_loaded()
        async with self._lock:
            total = len(self._events)
            dead = sum(1 for event in self._events if event.get("status") == "dead")
            pending = sum(1 for event in self._events if event.get("status") == "pending")
            acked = total - pending - dead
            return {"total": total, "pending": pending, "acked": acked, "dead": dead}

    async def _ensure_loaded(self) -> None:
        async with self._lock:
            current_mtime = self._safe_stat_mtime(self._file_path)
            if self._loaded and current_mtime != -1.0 and current_mtime <= self._last_loaded_mtime:
                return
            if self._loaded and current_mtime == -1.0 and self._last_loaded_mtime == -1.0:
                return

            self._events = []
            self._ensure_parent_dir(context="load")
            if current_mtime == -1.0:
                if not self._loaded:
                    logger.warning(
                        "Inbound inbox file missing path=%s action=skipped context=load reason=file_missing",
                        self._file_path,
                    )
                self._loaded = True
                self._last_loaded_mtime = -1.0
                return

            try:
                content = self._file_path.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if not line.strip():
                        continue
                    parsed = json.loads(line)
                    if isinstance(parsed, dict) and "id" in parsed:
                        self._events.append(parsed)
            except FileNotFoundError:
                # TOCTOU race (another process cleaned/replaced file between stat/read)
                logger.warning(
                    "Inbound inbox file missing path=%s action=skipped context=load reason=file_disappeared",
                    self._file_path,
                )
                self._events = []
            except Exception as exc:
                logger.error(
                    "Failed loading inbound inbox file path=%s action=failed context=load error=%s",
                    self._file_path,
                    exc,
                )
                self._events = []

            self._loaded = True
            self._last_loaded_mtime = self._safe_stat_mtime(self._file_path)

    async def _persist_locked(self) -> None:
        if not self._ensure_parent_dir(context="persist"):
            return
        lines = [
            json.dumps(event, separators=(",", ":"), ensure_ascii=True) for event in self._events
        ]
        # Unique temp file reduces cross-process collisions on the same inbox path.
        tmp_path = self._file_path.with_name(
            f"{self._file_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        payload = "\n".join(lines) + ("\n" if lines else "")
        try:
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, self._file_path)
            self._last_loaded_mtime = self._safe_stat_mtime(self._file_path)
        except FileNotFoundError:
            # Parent could vanish between mkdir and write/replace; retry once.
            if not self._ensure_parent_dir(context="persist-retry"):
                return
            try:
                tmp_path.write_text(payload, encoding="utf-8")
                os.replace(tmp_path, self._file_path)
                self._last_loaded_mtime = self._safe_stat_mtime(self._file_path)
                logger.warning(
                    "Inbound inbox persist recovered path=%s action=created context=persist-retry",
                    self._file_path,
                )
            except Exception as exc:
                logger.error(
                    "Inbound inbox persist failed path=%s action=failed context=persist-retry error=%s",
                    self._file_path,
                    exc,
                )
        except Exception as exc:
            logger.error(
                "Inbound inbox persist failed path=%s action=failed context=persist error=%s",
                self._file_path,
                exc,
            )
        finally:
            # Best-effort cleanup when replace path changed or failed.
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


_inbox_service: Optional[InboundInboxService] = None


def get_inbound_inbox_service() -> InboundInboxService:
    global _inbox_service
    if _inbox_service is None:
        _inbox_service = InboundInboxService()
    return _inbox_service
