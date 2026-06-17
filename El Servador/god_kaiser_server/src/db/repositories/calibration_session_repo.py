"""
Calibration Session Repository (S-P2)

CRUD + domain queries for calibration session management.
"""

import copy
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.calibration_session import CalibrationSession, CalibrationStatus
from .base_repo import BaseRepository


class CalibrationSessionRepository(BaseRepository[CalibrationSession]):
    """Repository for calibration session persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CalibrationSession, session)

    async def get_active_session(
        self, esp_id: str, gpio: int, sensor_type: str
    ) -> Optional[CalibrationSession]:
        """
        Get the currently active (non-terminal) session for a sensor.

        Only one active session should exist per sensor at any time.
        """
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.esp_id == esp_id,
                    self.model.gpio == gpio,
                    self.model.sensor_type == sensor_type,
                    self.model.status.notin_(
                        [
                            CalibrationStatus.APPLIED,
                            CalibrationStatus.REJECTED,
                            CalibrationStatus.EXPIRED,
                            CalibrationStatus.FAILED,
                        ]
                    ),
                )
            )
            .order_by(self.model.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, session_id: uuid.UUID) -> Optional[CalibrationSession]:
        """
        Get a session row-level locked for atomic mutations.

        Used by point add/update/delete/finalize flows to serialize concurrent
        writes on the same calibration session.
        """
        stmt = select(self.model).where(self.model.id == session_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_sessions_for_sensor(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[CalibrationSession]:
        """Get calibration history for a sensor, newest first."""
        conditions = [
            self.model.esp_id == esp_id,
            self.model.gpio == gpio,
        ]
        if sensor_type:
            conditions.append(self.model.sensor_type == sensor_type)

        stmt = (
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        session_id: uuid.UUID,
        new_status: CalibrationStatus,
        failure_reason: Optional[str] = None,
    ) -> Optional[CalibrationSession]:
        """
        Transition session to a new status.

        Sets completed_at for terminal states.
        """
        now = datetime.now(timezone.utc)

        values: dict = {"status": new_status, "updated_at": now}

        if new_status in (
            CalibrationStatus.APPLIED,
            CalibrationStatus.REJECTED,
            CalibrationStatus.EXPIRED,
            CalibrationStatus.FAILED,
        ):
            values["completed_at"] = now

        if failure_reason:
            values["failure_reason"] = failure_reason

        stmt = (
            update(self.model)
            .where(self.model.id == session_id)
            .values(**values)
            .returning(self.model)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        if row:
            await self.session.flush()

        return row

    async def add_calibration_point(
        self,
        session_id: uuid.UUID,
        point: dict,
    ) -> Optional[CalibrationSession]:
        """
        Append a calibration point to the session's points array.

        Args:
            session_id: The session to update
            point: Dict with {raw, reference, quality, timestamp, intent_id}
        """
        session = await self.get_by_id_for_update(session_id)
        if not session:
            return None

        # JSONB fields are not always reliably tracked for in-place nested mutations.
        # Build a fresh structure so SQLAlchemy marks the column as dirty on every add.
        current_points = (
            copy.deepcopy(session.calibration_points)
            if session.calibration_points
            else {"points": []}
        )
        existing_points = current_points.get("points", [])
        points_list = list(existing_points) if isinstance(existing_points, list) else []
        points_list.append(point)
        current_points["points"] = points_list

        session.calibration_points = current_points

        # Transition from PENDING to COLLECTING on first point
        if session.status == CalibrationStatus.PENDING:
            session.status = CalibrationStatus.COLLECTING

        await self.session.flush()
        await self.session.refresh(session)
        return session

    async def replace_calibration_points(
        self,
        session_id: uuid.UUID,
        points_payload: dict,
        *,
        force_collecting: bool = False,
        clear_result: bool = False,
    ) -> Optional[CalibrationSession]:
        """
        Replace the full calibration_points payload atomically.

        Used for role-based overwrite/delete workflows where we need deterministic
        in-memory manipulation before persisting JSONB.
        """
        session = await self.get_by_id_for_update(session_id)
        if not session:
            return None

        session.calibration_points = copy.deepcopy(points_payload)

        if force_collecting and session.status in (
            CalibrationStatus.PENDING,
            CalibrationStatus.COLLECTING,
            CalibrationStatus.FINALIZING,
        ):
            session.status = CalibrationStatus.COLLECTING

        if clear_result:
            session.calibration_result = None

        await self.session.flush()
        await self.session.refresh(session)
        return session

    async def set_result(
        self,
        session_id: uuid.UUID,
        result: dict,
    ) -> Optional[CalibrationSession]:
        """Set the calibration result and mark as finalizing."""
        session = await self.get_by_id_for_update(session_id)
        if not session:
            return None

        session.calibration_result = result
        session.status = CalibrationStatus.FINALIZING

        await self.session.flush()
        await self.session.refresh(session)
        return session

    async def expire_stale_sessions(self, max_age_hours: int = 24) -> int:
        """
        Expire sessions older than max_age_hours that are still active.

        Returns the number of expired sessions.
        """
        now = datetime.now(timezone.utc)
        from datetime import timedelta

        cutoff = now - timedelta(hours=max_age_hours)

        stmt = (
            update(self.model)
            .where(
                and_(
                    self.model.created_at < cutoff,
                    self.model.status.notin_(
                        [
                            CalibrationStatus.APPLIED,
                            CalibrationStatus.REJECTED,
                            CalibrationStatus.EXPIRED,
                            CalibrationStatus.FAILED,
                        ]
                    ),
                )
            )
            .values(
                status=CalibrationStatus.EXPIRED,
                completed_at=now,
                failure_reason="Session expired after 24h inactivity",
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount  # type: ignore[return-value]
