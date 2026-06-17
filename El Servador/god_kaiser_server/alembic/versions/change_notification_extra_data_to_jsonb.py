"""Change notification extra_data column from JSON to JSONB

Revision ID: change_extra_data_jsonb
Revises: soft_delete_devices_preserve_sensor_data
Create Date: 2026-03-08 14:00:00.000000

BUG-07: The extra_data column was defined as JSON, but notification_repo.py
uses `.astext` (JSONB-only operator) for queries like
`Notification.extra_data["esp_id"].astext == esp_id`.
This caused AttributeError on device-delete (500 response).

JSONB provides:
- .astext / ->> operator support
- GIN indexing capability
- Faster query performance for JSON path lookups
"""

from typing import Union

from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON

revision: str = "change_extra_data_jsonb"
down_revision: Union[str, None] = "soft_delete_devices_preserve_sensor_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "notifications",
        "extra_data",
        type_=JSONB(),
        postgresql_using="extra_data::jsonb",
    )


def downgrade() -> None:
    op.alter_column(
        "notifications",
        "extra_data",
        type_=JSON(),
        postgresql_using="extra_data::text::json",
    )
