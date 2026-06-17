"""Add hardware_type to actuator_configs

S2 Hardware-Type Preservation: Adds a hardware_type column to actuator_configs
to store the original ESP32 logical type (relay, pump, valve, pwm) alongside
the server-normalized type (digital, pwm). This allows the frontend to display
correct icons and analytics to differentiate pumps from valves from relays.

Backfill strategy: existing 'digital' records default to hardware_type='relay'
(most common digital type). Records will be corrected on next MQTT status
message from the ESP32.

Revision ID: add_hardware_type_to_actuator_configs
Revises: normalize_actuator_type_in_states_and_history
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "add_hardware_type_to_actuator_configs"
down_revision: Union[str, None] = "normalize_actuator_type_in_states_and_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "actuator_configs",
        sa.Column("hardware_type", sa.String(50), nullable=True),
    )
    # Backfill: digital → relay (safe default), pwm → pwm, servo → servo
    op.execute("""
        UPDATE actuator_configs
        SET hardware_type = CASE
            WHEN actuator_type = 'digital' THEN 'relay'
            WHEN actuator_type = 'pwm'     THEN 'pwm'
            WHEN actuator_type = 'servo'   THEN 'servo'
            ELSE actuator_type
        END
        WHERE hardware_type IS NULL
    """)


def downgrade() -> None:
    op.drop_column("actuator_configs", "hardware_type")
