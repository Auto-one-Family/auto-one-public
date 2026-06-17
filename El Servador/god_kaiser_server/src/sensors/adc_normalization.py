"""
ADC Normalization - Single Source of Truth for RAW -> Voltage conversion.

Sensor calibration (slope/offset) is identical regardless of which ADC produced
the RAW value. The ONLY thing that differs per acquisition source is how a RAW
count maps to a voltage:

- ``internal`` : ESP32 built-in 12-bit ADC, 0..4095 over 0..3.3V
                 -> voltage = raw / 4095 * 3.3
- ``ads1115``  : external 16-bit I2C ADC, single-ended 0..32767, PGA-selectable
                 full-scale range. LSB = FSR / 32768 -> voltage = raw * LSB(pga)

Having exactly one place for this normalization keeps measurement and
calibration consistent (no drift when the PGA / source changes). pH and EC
sensor libraries, the calibration service and the live-preview handler all call
into this module instead of hardcoding ``/ 4095 * 3.3``.

NOTE on the legacy EC ``adc_type`` discriminator: older EC calibrations stored
``adc_type = "16bit"`` and used an approximate ``raw / 32767 * 5.0V`` mapping
(see ``ECSensorProcessor`` backward-compat branch). That path is preserved for
existing data; the new, PGA-exact path is keyed on ``adc_source = "ads1115"``
plus ``pga_gain`` and is the one all new ADS1115 sensors use.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# ── Acquisition sources ──────────────────────────────────────────────────────
ADC_SOURCE_INTERNAL = "internal"
ADC_SOURCE_ADS1115 = "ads1115"

# ── Internal ESP32 ADC (12-bit) ──────────────────────────────────────────────
INTERNAL_ADC_MAX = 4095
INTERNAL_ADC_VOLTAGE = 3.3

# ── ADS1115 external ADC (16-bit, single-ended positive) ─────────────────────
# Single-ended positive readings span codes 0..32767. The LSB step is defined
# against the full +-FSR range which is 2^16 = 65536 codes, i.e. FSR / 32768
# for the positive half.
ADS1115_FULL_SCALE_COUNTS = 32768
ADS1115_MAX_COUNT = 32767

# PGA gain identifier -> full-scale range in volts (FSR). Strings keep the value
# DB/JSON friendly and avoid float-key lookups.
PGA_FULL_SCALE_VOLTS: Dict[str, float] = {
    "6.144": 6.144,
    "4.096": 4.096,
    "2.048": 2.048,
    "1.024": 1.024,
    "0.512": 0.512,
    "0.256": 0.256,
}

DEFAULT_PGA_GAIN = "4.096"


def normalize_pga_gain(pga_gain: Optional[Any]) -> str:
    """
    Normalize a PGA gain value to a canonical key in ``PGA_FULL_SCALE_VOLTS``.

    Accepts strings ("4.096"), floats (4.096) or ``None`` and falls back to the
    default gain (+-4.096V) for unknown / missing values.
    """
    if pga_gain is None:
        return DEFAULT_PGA_GAIN
    key = str(pga_gain).strip()
    if key in PGA_FULL_SCALE_VOLTS:
        return key
    # Tolerate numeric input like 4.096 or "4.096000"
    try:
        as_float = float(key)
    except (TypeError, ValueError):
        return DEFAULT_PGA_GAIN
    for candidate, fsr in PGA_FULL_SCALE_VOLTS.items():
        if abs(fsr - as_float) < 1e-6:
            return candidate
    return DEFAULT_PGA_GAIN


def pga_full_scale_volts(pga_gain: Optional[Any]) -> float:
    """Return the full-scale range (volts) for a PGA gain."""
    return PGA_FULL_SCALE_VOLTS[normalize_pga_gain(pga_gain)]


def pga_lsb_volts(pga_gain: Optional[Any]) -> float:
    """Return the LSB step (volts per count) for a PGA gain: FSR / 32768."""
    return pga_full_scale_volts(pga_gain) / ADS1115_FULL_SCALE_COUNTS


def adc_max_for_source(adc_source: Optional[str]) -> int:
    """Return the maximum RAW count for an acquisition source (for validation)."""
    if _is_ads1115(adc_source):
        return ADS1115_MAX_COUNT
    return INTERNAL_ADC_MAX


def _is_ads1115(adc_source: Optional[str]) -> bool:
    return bool(adc_source) and str(adc_source).strip().lower() == ADC_SOURCE_ADS1115


def raw_to_voltage(
    raw_value: float,
    adc_source: Optional[str] = ADC_SOURCE_INTERNAL,
    pga_gain: Optional[Any] = None,
) -> float:
    """
    Convert a RAW ADC count to voltage — the single normalization used by both
    measurement and calibration.

    Args:
        raw_value: RAW ADC count (0..4095 internal, 0..32767 ads1115).
        adc_source: ``"internal"`` (default) or ``"ads1115"``.
        pga_gain: ADS1115 PGA gain (only used for ``ads1115``); defaults to
            +-4.096V when missing.

    Returns:
        Voltage in volts.
    """
    if _is_ads1115(adc_source):
        return float(raw_value) * pga_lsb_volts(pga_gain)
    return (float(raw_value) / INTERNAL_ADC_MAX) * INTERNAL_ADC_VOLTAGE


def resolve_adc_descriptor(
    source: Optional[Dict[str, Any]],
) -> Tuple[str, Optional[str]]:
    """
    Extract ``(adc_source, pga_gain)`` from a calibration/config dict.

    Returns the canonical ADS1115 descriptor when ``adc_source == "ads1115"``,
    otherwise ``("internal", None)``. Unknown / missing keys default to internal.
    The legacy EC ``adc_type`` discriminator is intentionally NOT mapped here —
    it is handled inside ``ECSensorProcessor`` for backward compatibility.
    """
    if not isinstance(source, dict):
        return ADC_SOURCE_INTERNAL, None
    adc_source = source.get("adc_source")
    if _is_ads1115(adc_source):
        return ADC_SOURCE_ADS1115, normalize_pga_gain(source.get("pga_gain"))
    return ADC_SOURCE_INTERNAL, None
