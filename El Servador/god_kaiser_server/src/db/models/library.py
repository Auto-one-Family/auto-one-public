"""
Library Model: LibraryMetadata
"""

import uuid
from typing import Optional

from sqlalchemy import Boolean, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class LibraryMetadata(Base, TimestampMixin):
    """
    Library Metadata Model (OTA Updates).

    Stores metadata for sensor libraries, actuator libraries, and firmware
    that can be deployed to ESP32 devices via OTA updates.

    Attributes:
        id: Primary key (UUID)
        library_name: Unique library name
        library_type: Type (sensor_library, actuator_library, firmware)
        version: Semantic version (e.g., 1.2.3)
        description: Human-readable description
        file_path: Server file path to library/firmware binary
        file_hash: SHA256 hash for integrity verification
        file_size_bytes: File size in bytes
        compatible_hardware: JSON array of compatible hardware types
        dependencies: JSON dependencies (other libraries required)
        enabled: Whether library is available for deployment
        metadata: Additional library metadata
    """

    __tablename__ = "library_metadata"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Library Identity
    library_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique library name (e.g., DHT22_Sensor_v1.2.3)",
    )

    library_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Library type (sensor_library, actuator_library, firmware)",
    )

    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Semantic version (e.g., 1.2.3)",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable library description",
    )

    # File Information (CRITICAL for OTA!)
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Server file path to library/firmware binary",
    )

    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="SHA256 hash for integrity verification",
    )

    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="File size in bytes",
    )

    # Compatibility (CRITICAL!)
    compatible_hardware: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        doc="Compatible hardware types (e.g., ['ESP32_WROOM', 'XIAO_ESP32_C3'])",
    )

    dependencies: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Library dependencies (other libraries required)",
    )

    # Deployment Control
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        doc="Whether library is available for deployment",
    )

    # Metadata
    library_metadata: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Additional library metadata (author, changelog, etc.)",
    )

    def __repr__(self) -> str:
        return f"<LibraryMetadata(library_name='{self.library_name}', version='{self.version}', type='{self.library_type}')>"
