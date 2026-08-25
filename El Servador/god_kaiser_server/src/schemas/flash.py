"""
Flash Workflow Pydantic Schemas — AUT-765/AUT-766/AUT-768

Schemas for USB device detection, NVS credential secrets, and flash execution.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class UsbDevice(BaseModel):
    port: str = Field(..., description="Serial port path, e.g. /dev/ttyUSB0 or COM3")
    description: str = Field(..., description="Human-readable device description from OS")
    hwid: str = Field(..., description="Raw hardware ID string from OS")
    chip_family: str = Field(
        ...,
        description="ESP chip family: ESP32, ESP32-S3, ESP32-C3, unknown",
    )
    board_type: str = Field(
        ...,
        description="Board variant: WROOM-32, WROOM-32-CP, S3-XIAO, S3-DevKit, C3-DevKit, unknown",
    )
    vid: int = Field(..., description="USB Vendor ID (decimal)")
    pid: int = Field(..., description="USB Product ID (decimal)")


class DeviceListResponse(BaseModel):
    success: bool = True
    devices: list[UsbDevice]
    scanning_available: bool = Field(
        ...,
        description="True when platform supports USB serial scanning",
    )
    count: int = Field(..., description="Number of detected USB serial devices")


# =============================================================================
# NVS Secrets Schemas — AUT-766
# =============================================================================


class NvsEnv(str, Enum):
    """Valid flash environments for NVS credential management."""

    dev_local = "dev-local"
    pi_home = "pi-home"
    pi_elbherb = "pi-elbherb"


class NvsSecretsCreate(BaseModel):
    """Payload for creating or overwriting NVS credential secrets.

    password and mqtt_password are optional: omit (or send null) to keep the
    existing value from the on-disk CSV.  An empty string is always rejected —
    use null/omit to preserve the current value.
    """

    ssid: str = Field(..., min_length=1, max_length=32, description="WiFi SSID")
    password: Optional[str] = Field(None, description="WiFi password — omit/null to keep existing")
    server_address: str = Field(..., min_length=1, description="MQTT broker host")
    mqtt_port: int = Field(..., ge=1, le=65535, description="MQTT broker port")
    mqtt_username: str = Field(..., min_length=1, description="MQTT username")
    mqtt_password: Optional[str] = Field(
        None, description="MQTT password — omit/null to keep existing"
    )
    configured: int = Field(
        default=1,
        ge=0,
        le=255,
        description="NVS configured flag (u8 — 1 = provisioned)",
    )

    @field_validator("password", "mqtt_password", mode="before")
    @classmethod
    def reject_empty_password(cls, v: object) -> object:
        if isinstance(v, str) and len(v) == 0:
            raise ValueError(
                "Password cannot be empty string — use null/omit to keep existing value"
            )
        return v


class NvsSecretsResponse(BaseModel):
    """Response for GET /flash/secrets/{env} — passwords always masked."""

    success: bool = True
    env: str
    ssid: str
    password: str = Field(default="***", description="Always masked")
    server_address: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str = Field(default="***", description="Always masked")
    configured: int


class SecretsWriteResponse(BaseModel):
    """Response for PUT /flash/secrets/{env}."""

    success: bool = True
    path: str = Field(..., description="Absolute path of the written CSV file")


class SecretsBuildResponse(BaseModel):
    """Response for POST /flash/secrets/{env}/build."""

    success: bool = True
    env: str
    binary_path: str = Field(..., description="Absolute path of the generated .bin file")
    size_bytes: int = Field(..., description="Size of the generated NVS binary in bytes")


class FlashEnvResponse(BaseModel):
    """Response for GET /flash/env — current server flash environment."""

    env: str = Field(..., description="Flash env name configured for this server instance")


# =============================================================================
# Flash Execute Schemas — AUT-768
# =============================================================================


class FlashExecuteRequest(BaseModel):
    """Request body for POST /flash/execute."""

    port: str = Field(..., description="Serial port, e.g. /dev/ttyUSB0 or COM3")
    env: NvsEnv = Field(..., description="Target flash environment")
    flash_type: Literal["nvs", "firmware", "full"] = Field(
        default="nvs",
        description=(
            "nvs=NVS credentials only (default, non-destructive) | "
            "firmware=bootloader+partitions+firmware+NVS (no erase) | "
            "full=erase-all+firmware+NVS (DESTRUCTIVE, requires erase_confirm=true)"
        ),
    )
    confirm: bool = Field(
        default=False,
        description="Must be True for env=pi-elbherb (STRICT environment)",
    )
    erase_confirm: bool = Field(
        default=False,
        description="Must be True for flash_type=full (destructive erase — silent erase is forbidden)",
    )


class FlashExecuteResponse(BaseModel):
    """Response for POST /flash/execute — synchronous, blocks until flash completes."""

    success: bool = True
    port: str = Field(..., description="Serial port that was flashed")
    env: str = Field(..., description="Flash environment used")
    flash_type: str = Field(default="nvs", description="Flash type that was executed")
    output: str = Field(..., description="Full esptool output")
