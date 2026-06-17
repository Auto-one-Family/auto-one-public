"""
Sequence Action Schemas

Pydantic Schemas für Sequenz-Validierung und API-Responses.

Phase: 3 - Sequence Action Executor
Status: IMPLEMENTED
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SequenceStatus(str, Enum):
    """Status einer Sequenz."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class StepFailureAction(str, Enum):
    """Verhalten bei Step-Fehler."""

    ABORT = "abort"
    CONTINUE = "continue"
    RETRY = "retry"


class SequenceStepBase(BaseModel):
    """Basis für einen Sequenz-Step."""

    name: Optional[str] = None
    delay_before_seconds: Optional[float] = Field(None, ge=0, le=3600)
    delay_after_seconds: Optional[float] = Field(None, ge=0, le=3600)
    delay_seconds: Optional[float] = Field(None, ge=0, le=3600)  # Pure delay step
    timeout_seconds: Optional[float] = Field(30, ge=1, le=300)
    on_failure: StepFailureAction = StepFailureAction.ABORT
    retry_count: Optional[int] = Field(0, ge=0, le=3)
    retry_delay_seconds: Optional[float] = Field(1.0, ge=0, le=60)


class SequenceStepWithAction(SequenceStepBase):
    """Step mit einer Action."""

    action: Dict[str, Any]


class SequenceStepDelayOnly(SequenceStepBase):
    """Reiner Delay-Step ohne Action."""

    delay_seconds: float = Field(..., ge=0.1, le=3600)


SequenceStep = Union[SequenceStepWithAction, SequenceStepDelayOnly]


class SequenceActionSchema(BaseModel):
    """Schema für eine Sequenz-Action in Logic Rules."""

    type: str = "sequence"
    sequence_id: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    abort_on_failure: bool = True
    max_duration_seconds: int = Field(3600, ge=1, le=86400)
    steps: List[Dict[str, Any]] = Field(..., min_length=1, max_length=50)

    @field_validator("sequence_id")
    @classmethod
    def generate_sequence_id(cls, v, info):
        """Generiert sequence_id wenn nicht angegeben."""
        if v is None:
            import uuid

            return f"seq-{uuid.uuid4().hex[:8]}"
        return v

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, v):
        """Validiert dass mindestens ein Step vorhanden ist."""
        if not v:
            raise ValueError("Sequence must have at least one step")
        for i, step in enumerate(v):
            if "action" not in step and "delay_seconds" not in step:
                raise ValueError(f"Step {i} must have either 'action' or 'delay_seconds'")
        return v


class StepResult(BaseModel):
    """Ergebnis eines ausgeführten Steps."""

    step_index: int
    step_name: Optional[str]
    success: bool
    message: str
    error_code: Optional[int] = None
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    retries: int = 0


class SequenceProgressSchema(BaseModel):
    """Schema für Sequenz-Progress (API Response)."""

    sequence_id: str
    rule_id: str
    rule_name: Optional[str]
    status: SequenceStatus
    description: Optional[str]
    current_step: int
    total_steps: int
    progress_percent: float
    started_at: datetime
    completed_at: Optional[datetime]
    estimated_completion: Optional[datetime] = None
    step_results: List[StepResult]
    current_step_name: Optional[str]
    error: Optional[str]
    error_code: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class SequenceListResponse(BaseModel):
    """Response für Sequenz-Liste."""

    success: bool = True
    sequences: List[SequenceProgressSchema]
    total: int
    running: int
    completed: int
    failed: int


class SequenceStatsResponse(BaseModel):
    """Statistiken über Sequenzen."""

    success: bool = True
    total_sequences: int
    running: int
    completed_last_hour: int
    failed_last_hour: int
    average_duration_seconds: float
    longest_sequence_id: Optional[str] = None
    most_common_failure_step: Optional[str] = None
