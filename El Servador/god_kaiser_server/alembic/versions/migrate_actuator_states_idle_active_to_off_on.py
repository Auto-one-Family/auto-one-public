"""migrate actuator states idle/active to off/on

Aligns DB values with MQTT payload states (INV-1c).
Old states: idle, active → New states: off, on

Revision ID: 78002fde47ca
Revises: add_sensor_data_dedup
Create Date: 2026-03-25 09:42:52.075969

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "78002fde47ca"
down_revision: Union[str, None] = "add_sensor_data_dedup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Migrate legacy actuator state values to match MQTT payload convention
    op.execute("UPDATE actuator_states SET state = 'off' WHERE state = 'idle'")
    op.execute("UPDATE actuator_states SET state = 'on' WHERE state = 'active'")


def downgrade() -> None:
    # Revert to legacy state names
    op.execute("UPDATE actuator_states SET state = 'idle' WHERE state = 'off'")
    op.execute("UPDATE actuator_states SET state = 'active' WHERE state = 'on'")
