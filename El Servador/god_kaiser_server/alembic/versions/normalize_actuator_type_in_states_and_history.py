"""Normalize actuator_type in actuator_states and actuator_history

S1 Consistency Fix: actuator_states and actuator_history stored raw ESP32 types
(relay, pump, valve) instead of server-normalized types (digital, pwm).
The MQTT handler now uses the config as source of truth, but existing rows
still contain ESP32 types. This migration backfills them.

Revision ID: normalize_actuator_type_in_states_and_history
Revises: add_logic_hysteresis_states
Create Date: 2026-03-30
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "normalize_actuator_type_in_states_and_history"
down_revision: Union[str, None] = "add_logic_hysteresis_states"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Normalize actuator_states: relay/pump/valve → digital
    op.execute("""
        UPDATE actuator_states
        SET actuator_type = CASE
            WHEN actuator_type IN ('relay', 'pump', 'valve') THEN 'digital'
            ELSE actuator_type
        END
        WHERE actuator_type IN ('relay', 'pump', 'valve')
    """)

    # Normalize actuator_history: relay/pump/valve → digital
    op.execute("""
        UPDATE actuator_history
        SET actuator_type = CASE
            WHEN actuator_type IN ('relay', 'pump', 'valve') THEN 'digital'
            ELSE actuator_type
        END
        WHERE actuator_type IN ('relay', 'pump', 'valve')
    """)


def downgrade() -> None:
    # Downgrade is intentionally a no-op.
    # The original ESP32 type is not recoverable after normalization.
    # hardware_type (added in a subsequent migration) preserves this information.
    pass
