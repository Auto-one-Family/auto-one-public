"""
System Model: SystemConfig
"""

import uuid
from typing import Optional

from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class SystemConfig(Base, TimestampMixin):
    """
    System Configuration Model.

    Stores system-wide configuration that can be modified at runtime
    without restarting the server.

    Attributes:
        id: Primary key (UUID)
        config_key: Unique configuration key (e.g., mqtt.qos.sensor_data)
        config_value: JSON configuration value
        config_type: Configuration category (mqtt, database, api, pi_enhanced, security)
        description: Human-readable description
        is_secret: Whether this config contains sensitive data
        metadata: Additional config metadata
    """

    __tablename__ = "system_config"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Configuration Key
    config_key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique configuration key (e.g., mqtt.qos.sensor_data)",
    )

    # Configuration Value
    config_value: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        doc=(
            "Configuration value (can be any JSON type). "
            "Example: {'qos': 1, 'retain': false} or {'url': 'mqtt://broker'}"
        ),
    )

    # Configuration Type
    config_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Configuration category (mqtt, database, api, pi_enhanced, security)",
    )

    # Description
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable description of this configuration",
    )

    # Security
    is_secret: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether this config contains sensitive data (passwords, API keys)",
    )

    # Metadata
    system_metadata: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Additional config metadata (validation_schema, default_value, etc.)",
    )

    def __repr__(self) -> str:
        return f"<SystemConfig(config_key='{self.config_key}', config_type='{self.config_type}')>"
