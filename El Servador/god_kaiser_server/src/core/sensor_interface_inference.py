"""
Sensor interface_type inference and UART metadata helpers (AUT-527).

Shared by REST API and unit tests without importing the full sensors router.
"""

from __future__ import annotations

from typing import Optional

_UART_SENSOR_TYPE_FRAGMENTS = ("co2", "mhz19", "mhz19_co2", "sen0220", "sen0220_co2")
_DIGITAL_SENSOR_TYPE_FRAGMENTS = ("flow", "yfs201", "liquid_level")
DEFAULT_UART_BAUD = 9600


def infer_interface_type(sensor_type: str) -> str:
    """
    Infer interface_type from sensor_type naming convention.

    Rules:
    - sht31*, bmp280*, bme280*, bh1750*, veml7700* → I2C
    - ds18b20* → ONEWIRE
    - co2, mhz19*, sen0220* → UART
    - flow, yfs201, liquid_level → DIGITAL (pulse / reed-switch sensors)
    - Everything else → ANALOG (default)

    NOTE: ``adc_source`` (internal vs. ads1115) is ORTHOGONAL to interface_type.
    pH/EC stay ANALOG even when read via an external ADS1115 I2C ADC — the
    firmware keeps them on the analog-probe acquisition path and only swaps the
    RAW source internally (the ADS1115 read happens inside the analog sampler).
    Returning I2C here would mis-route them to the I2C multi-value handler.
    """
    sensor_lower = sensor_type.lower()

    if any(s in sensor_lower for s in ["sht31", "bmp280", "bme280", "bh1750", "veml7700"]):
        return "I2C"
    if "ds18b20" in sensor_lower:
        return "ONEWIRE"
    if any(t in sensor_lower for t in _UART_SENSOR_TYPE_FRAGMENTS):
        return "UART"
    if any(t in sensor_lower for t in _DIGITAL_SENSOR_TYPE_FRAGMENTS):
        return "DIGITAL"
    return "ANALOG"


def merge_uart_metadata(
    sensor_metadata: dict,
    *,
    logical_gpio: int,
    uart_rx_pin: Optional[int],
    uart_tx_pin: Optional[int],
    uart_baud: Optional[int],
) -> None:
    """Persist UART pins in sensor_metadata (Phase 1 — no DDL)."""
    rx = uart_rx_pin if uart_rx_pin is not None else logical_gpio
    tx = uart_tx_pin if uart_tx_pin is not None else 17
    baud = uart_baud if uart_baud is not None else DEFAULT_UART_BAUD
    sensor_metadata["uart_rx_pin"] = rx
    sensor_metadata["uart_tx_pin"] = tx
    sensor_metadata["uart_baud"] = baud


def uart_fields_from_metadata(sensor_metadata: Optional[dict]) -> dict[str, Optional[int]]:
    meta = sensor_metadata or {}
    return {
        "uart_rx_pin": meta.get("uart_rx_pin"),
        "uart_tx_pin": meta.get("uart_tx_pin"),
        "uart_baud": meta.get("uart_baud"),
    }
