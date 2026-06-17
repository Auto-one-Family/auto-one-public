"""
Sensor Message Formatters
Einheitliche, menschenverstandliche Sensor-Messages fur alle Events.

Server-Centric: Single Source of Truth fur Sensor-Darstellung.
Wird verwendet von:
- SensorHandler (WebSocket-Broadcast)
- EventAggregatorService (API/DB Events)

Format: "[SENSOR-NAME] GPIO [X]: [WERT][EINHEIT]"
Beispiel: "Temperatur GPIO 4: 25.3°C"
"""

from typing import Optional

# Sensor-Type -> Deutscher Display-Name
SENSOR_DISPLAY_NAMES = {
    # DS18B20 (1-Wire Temperature)
    "ds18b20": "Temperatur",
    "ds18b20_temp": "Temperatur",
    # DHT22 (Temp + Humidity)
    "dht22": "Temp./Luftfeuchtigkeit",
    "dht22_temp": "Temperatur",
    "dht22_humidity": "Luftfeuchtigkeit",
    # SHT31 (Temp + Humidity)
    "sht31": "Temp./Luftfeuchtigkeit",
    "sht31_temp": "Temperatur",
    "sht31_humidity": "Luftfeuchtigkeit",
    # BME280 (Temp + Humidity + Pressure)
    "bme280": "Umweltsensor",
    "bme280_temp": "Temperatur",
    "bme280_humidity": "Luftfeuchtigkeit",
    "bme280_pressure": "Luftdruck",
    # Soil sensors
    "capacitive_soil": "Bodenfeuchtigkeit",
    "soil_moisture": "Bodenfeuchtigkeit",
    # pH sensor
    "ph_sensor": "pH-Wert",
    "ph": "pH-Wert",
    # Light sensor
    "bh1750": "Lichtintensitat",
    "light": "Lichtintensitat",
    # Generic
    "analog": "Analoger Sensor",
    "digital": "Digitaler Sensor",
    "unknown": "Sensor",
}

# Sensor-Type -> Technischer Name (fur Details/Debugging)
SENSOR_TECHNICAL_NAMES = {
    "ds18b20": "DS18B20",
    "ds18b20_temp": "DS18B20",
    "dht22": "DHT22",
    "dht22_temp": "DHT22",
    "dht22_humidity": "DHT22",
    "sht31": "SHT31",
    "sht31_temp": "SHT31",
    "sht31_humidity": "SHT31",
    "bme280": "BME280",
    "bme280_temp": "BME280",
    "bme280_humidity": "BME280",
    "bme280_pressure": "BME280",
    "capacitive_soil": "Capacitive",
    "soil_moisture": "Soil Sensor",
    "ph_sensor": "pH-4502C",
    "ph": "pH-4502C",
    "bh1750": "BH1750",
    "light": "Light Sensor",
}

# Default Decimal Places pro Sensor-Type
SENSOR_DECIMAL_PLACES = {
    "ds18b20": 1,
    "ds18b20_temp": 1,
    "dht22_temp": 1,
    "dht22_humidity": 0,
    "sht31_temp": 1,
    "sht31_humidity": 0,
    "bme280_temp": 1,
    "bme280_humidity": 0,
    "bme280_pressure": 0,
    "capacitive_soil": 0,
    "soil_moisture": 0,
    "ph_sensor": 2,
    "ph": 2,
    "bh1750": 0,
    "light": 0,
}


def format_sensor_message(
    sensor_type: str,
    gpio: int,
    value: float,
    unit: Optional[str] = None,
    decimal_places: Optional[int] = None,
    include_technical_name: bool = False,
) -> str:
    """
    Formatiert Sensor-Message einheitlich und menschenverstandlich.

    Args:
        sensor_type: Sensor-Type (z.B. "ds18b20")
        gpio: GPIO-Pin-Nummer
        value: Gemessener Wert
        unit: Einheit (z.B. "degC", "%", "lux")
        decimal_places: Nachkommastellen (Default: aus SENSOR_DECIMAL_PLACES)
        include_technical_name: Zeige technischen Namen (Default: False)

    Returns:
        Formatierte Message: "Temperatur GPIO 4: 25.3degC"

    Examples:
        >>> format_sensor_message("ds18b20", 4, 25.34, "degC")
        "Temperatur GPIO 4: 25.3degC"

        >>> format_sensor_message("ds18b20", 4, 25.34, "degC", include_technical_name=True)
        "Temperatur (DS18B20) GPIO 4: 25.3degC"

        >>> format_sensor_message("ph_sensor", 33, 6.847, "pH")
        "pH-Wert GPIO 33: 6.85 pH"
    """
    # Deutscher Display-Name
    sensor_key = sensor_type.lower() if sensor_type else "unknown"
    display_name = SENSOR_DISPLAY_NAMES.get(
        sensor_key, sensor_type.replace("_", " ").title() if sensor_type else "Sensor"
    )

    # Nachkommastellen
    if decimal_places is None:
        decimal_places = SENSOR_DECIMAL_PLACES.get(sensor_key, 1)

    # Wert formatieren
    if value is None:
        formatted_value = "?"
    elif isinstance(value, float):
        formatted_value = f"{value:.{decimal_places}f}"
    else:
        formatted_value = str(value)

    # Einheit formatieren
    value_with_unit = _format_value_with_unit(formatted_value, unit)

    # Message zusammenbauen
    if include_technical_name:
        tech_name = SENSOR_TECHNICAL_NAMES.get(
            sensor_key, sensor_type.upper() if sensor_type else "UNKNOWN"
        )
        message = f"{display_name} ({tech_name}) GPIO {gpio}: {value_with_unit}"
    else:
        message = f"{display_name} GPIO {gpio}: {value_with_unit}"

    return message


def _format_value_with_unit(value: str, unit: Optional[str]) -> str:
    """
    Formatiert Wert mit Einheit (korrekte Abstande).

    Args:
        value: Formatierter Wert-String
        unit: Einheit

    Returns:
        Wert mit Einheit: "25.3degC" oder "1200 lux"
    """
    if not unit:
        return value

    # Einheiten die direkt angehangt werden (kein Leerzeichen)
    no_space_units = {"%", "°C", "°F", "degC", "degF"}

    if unit in no_space_units:
        return f"{value}{unit}"
    else:
        # lux, ppm, hPa, pH etc. mit Leerzeichen
        return f"{value} {unit}"


def format_sensor_title(sensor_type: str, device_id: str) -> str:
    """
    Formatiert Event-Titel fur Sensor.

    Args:
        sensor_type: Sensor-Type
        device_id: ESP Device ID

    Returns:
        "ESP_ZONE1: Temperatur"
    """
    display_name = get_sensor_display_name(sensor_type)
    return f"{device_id}: {display_name}"


def get_sensor_display_name(sensor_type: str) -> str:
    """
    Gibt deutschen Display-Namen fur Sensor-Type zuruck.

    Args:
        sensor_type: Sensor-Type (z.B. "ds18b20")

    Returns:
        "Temperatur", "pH-Wert", etc.
    """
    sensor_key = sensor_type.lower() if sensor_type else "unknown"
    return SENSOR_DISPLAY_NAMES.get(
        sensor_key, sensor_type.replace("_", " ").title() if sensor_type else "Sensor"
    )


def get_sensor_decimal_places(sensor_type: str) -> int:
    """
    Gibt Standard-Nachkommastellen fur Sensor-Type zuruck.

    Args:
        sensor_type: Sensor-Type

    Returns:
        Nachkommastellen (Default: 1)
    """
    sensor_key = sensor_type.lower() if sensor_type else "unknown"
    return SENSOR_DECIMAL_PLACES.get(sensor_key, 1)


def determine_sensor_severity(
    sensor_type: str,
    value: float,
    thresholds: Optional[dict] = None,
) -> str:
    """
    Bestimmt Severity basierend auf Sensor-Schwellwerten.

    Args:
        sensor_type: Sensor-Type
        value: Gemessener Wert
        thresholds: Custom Schwellwerte (optional)

    Returns:
        "info", "warning", "error", "critical"

    Example:
        >>> determine_sensor_severity("ds18b20", 35.0)
        "warning"  # Temperatur zu hoch

        >>> determine_sensor_severity("ph_sensor", 4.5)
        "warning"  # pH zu niedrig
    """
    if value is None:
        return "warning"

    # Standard-Schwellwerte (konnen uber thresholds uberschrieben werden)
    default_thresholds = {
        "ds18b20": {  # Temperatur
            "critical_low": 0,
            "warning_low": 10,
            "warning_high": 35,
            "critical_high": 45,
        },
        "ds18b20_temp": {
            "critical_low": 0,
            "warning_low": 10,
            "warning_high": 35,
            "critical_high": 45,
        },
        "dht22_humidity": {
            "warning_low": 30,
            "warning_high": 80,
            "critical_high": 95,
        },
        "sht31_humidity": {
            "warning_low": 30,
            "warning_high": 80,
            "critical_high": 95,
        },
        "ph_sensor": {
            "critical_low": 4.0,
            "warning_low": 5.5,
            "warning_high": 7.5,
            "critical_high": 9.0,
        },
        "ph": {
            "critical_low": 4.0,
            "warning_low": 5.5,
            "warning_high": 7.5,
            "critical_high": 9.0,
        },
        "capacitive_soil": {
            "critical_low": 10,
            "warning_low": 30,
        },
    }

    sensor_key = sensor_type.lower() if sensor_type else "unknown"
    config = thresholds or default_thresholds.get(sensor_key, {})

    # Critical-Checks
    if "critical_low" in config and value < config["critical_low"]:
        return "critical"
    if "critical_high" in config and value > config["critical_high"]:
        return "critical"

    # Warning-Checks
    if "warning_low" in config and value < config["warning_low"]:
        return "warning"
    if "warning_high" in config and value > config["warning_high"]:
        return "warning"

    # Normal
    return "info"
