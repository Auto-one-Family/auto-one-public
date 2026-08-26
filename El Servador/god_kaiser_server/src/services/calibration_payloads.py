"""
Canonical calibration payload adapters.

Provides a single canonical shape for ``sensor_configs.calibration_data`` while
keeping backward compatibility for legacy payloads and stored rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonicalize_calibration_data(
    payload: Any,
    *,
    default_method: str = "unknown",
    source: str = "legacy",
) -> dict | None:
    """
    Normalize calibration payloads into canonical schema.

    Canonical schema (all methods):
    {
      "method": str,  # linear_2point, moisture_2point, offset, ph_2point, ec_1point, ec_2point
      "points": list[dict],  # Original measurement points with point_role, raw, reference
      "derived": dict,  # Computed parameters (slope, offset, cell_factor, calibrated_at, valid_until?)
      "metadata": dict  # {schema_version, source, normalized_at}
    }

    Event fields (existing Cal place, AUT-1576):
    - Zeit-SSOT: derived.calibrated_at (read_calibrated_at)
    - Gültigkeit: derived.valid_until nullable — never invent a default interval
    - Referenz: points[].reference + point_role (wizard already stores these)
    - Wer: calibration_sessions.initiated_by — do not copy into this blob
    """
    if payload is None:
        return None
    if not isinstance(payload, dict):
        return None

    # Already canonical
    if {
        "method",
        "points",
        "derived",
        "metadata",
    }.issubset(payload.keys()):
        method = str(payload.get("method") or default_method)
        points = payload.get("points")
        derived = payload.get("derived")
        metadata = payload.get("metadata")
        return {
            "method": method,
            "points": points if isinstance(points, list) else [],
            "derived": derived if isinstance(derived, dict) else {},
            "metadata": metadata if isinstance(metadata, dict) else {},
        }

    method = str(payload.get("method") or payload.get("type") or default_method)
    metadata = {
        "schema_version": 1,
        "source": source,
        "normalized_at": _utc_iso_now(),
    }

    # Session points payload: {"points":[...], "history":[...]}
    if isinstance(payload.get("points"), list):
        return {
            "method": method,
            "points": payload.get("points", []),
            "derived": {},
            "metadata": metadata,
        }

    # Legacy computed calibration objects -> move all keys to derived.
    return {
        "method": method,
        "points": [],
        "derived": dict(payload),
        "metadata": metadata,
    }


def build_canonical_calibration_result(
    *,
    method: str,
    points: list[dict] | None,
    derived: dict,
    source: str = "calibration_session",
) -> dict:
    """
    Build canonical payload for newly computed calibration results.

    Supports all calibration methods:
    - moisture_2point: {slope, offset, ...}
    - linear_2point: {slope, offset, ...}
    - offset: {offset, ...}
    - ph_2point: {slope, offset, slope_deviation_pct, measured_response_mv_per_ph, ...}
    - ec_1point: {cell_factor, ...}
    - ec_2point: {slope, offset, ...}
    """
    return {
        "method": method,
        "points": points if isinstance(points, list) else [],
        "derived": dict(derived),
        "metadata": {
            "schema_version": 1,
            "source": source,
            "normalized_at": _utc_iso_now(),
        },
    }


# Keys present on canonical rows written via ``canonicalize_calibration_data`` /
# ``build_canonical_calibration_result``.
_CANONICAL_WRAPPER_KEYS = frozenset({"method", "points", "derived", "metadata"})


def resolve_calibration_for_processor(payload: Any) -> dict | None:
    """
    Extract a flat calibration dict for ``BaseSensorProcessor.process()``.

    Session apply and API normalization store physics parameters (``dry_value`` /
    ``wet_value``, ``slope`` / ``offset``, …) inside ``derived``. Processors
    expect those keys at the top level of the ``calibration`` argument.

    Returns:
        Flat dict usable by sensor libraries, or ``None`` if no usable data.
    """
    if payload is None or not isinstance(payload, dict):
        return None

    derived = payload.get("derived")
    if isinstance(derived, dict) and derived:
        return dict(derived)

    # Canonical wrapper with empty derived — processors cannot use this.
    if _CANONICAL_WRAPPER_KEYS.issubset(payload.keys()):
        return None

    # Legacy flat row (pre-canonical schema): the whole object is calibration.
    return dict(payload)


def read_calibrated_at(payload: Any) -> Any:
    """
    Read ``calibrated_at`` for the sensor_health reminder interval.

    Session apply stores the timestamp on ``derived`` (SSOT). Legacy rows
    may still have a top-level value. Derived wins when both exist.
    This function does not write or copy the field.
    """
    if payload is None or not isinstance(payload, dict):
        return None

    derived = payload.get("derived")
    if isinstance(derived, dict):
        cal_ts = derived.get("calibrated_at")
        if cal_ts:
            return cal_ts

    return payload.get("calibrated_at") or None


def read_valid_until(payload: Any) -> Any:
    """
    Read nullable ``valid_until`` for the last applied calibration event.

    AUT-1576: SSOT is ``derived.valid_until`` on the existing blob
    (``sensor_configs.calibration_data`` / session ``calibration_result``).
    No default interval. ``None`` means unset, not expired.
    Who remains ``calibration_sessions.initiated_by`` — never copied here.
    """
    if payload is None or not isinstance(payload, dict):
        return None

    derived = payload.get("derived")
    if isinstance(derived, dict) and "valid_until" in derived:
        return derived.get("valid_until")

    if "valid_until" in payload:
        return payload.get("valid_until")

    return None


def attach_valid_until(payload: dict[str, Any], valid_until: Any) -> dict[str, Any]:
    """
    Attach nullable ``valid_until`` on ``derived`` without inventing an interval.

    Always writes the key (including explicit ``null``) so K3 can distinguish
    unset-after-apply from a missing legacy blob. Past dates are stored as-is.
    """
    derived = payload.get("derived")
    if not isinstance(derived, dict):
        derived = {}
        payload["derived"] = derived

    if valid_until is None:
        derived["valid_until"] = None
        return payload

    if hasattr(valid_until, "isoformat"):
        derived["valid_until"] = valid_until.isoformat()
        return payload

    derived["valid_until"] = str(valid_until) if valid_until else None
    return payload
