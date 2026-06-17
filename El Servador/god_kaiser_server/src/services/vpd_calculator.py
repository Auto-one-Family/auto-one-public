"""
VPD Calculator — Air-VPD using Magnus-Tetens approximation.

Shared by:
- sensor_handler.py (event-driven VPD persistence)
- zone_kpi_service.py (live zone KPI calculation)
"""

import math
from typing import Optional


def calculate_vpd(temperature_c: float, humidity_rh: float) -> Optional[float]:
    """Calculate Air-VPD (Vapor Pressure Deficit) using Magnus-Tetens formula.

    Returns VPD in kPa, or None if inputs are out of plausible range.

    Args:
        temperature_c: air temperature in degrees Celsius
        humidity_rh:   relative humidity in percent (0-100)
    """
    if not (0 <= humidity_rh <= 100):
        return None
    if not (-40 <= temperature_c <= 80):
        return None
    svp = 0.6108 * math.exp((17.27 * temperature_c) / (temperature_c + 237.3))
    avp = svp * (humidity_rh / 100.0)
    vpd = svp - avp
    return round(vpd, 4)
