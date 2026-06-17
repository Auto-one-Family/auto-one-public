"""
Database Enums for AutomationOne Framework

Centralized enum definitions for database models.
"""

from enum import Enum


class DataSource(str, Enum):
    """
    Data source indicator for time-series data.

    Used to distinguish between production, mock, test, and simulation data.
    This enables filtering in queries and proper data retention policies.

    Values:
        PRODUCTION: Real ESP32 devices in production
        MOCK: MockESP32Client or Debug API generated data
        TEST: Temporary test data (auto-cleanup candidates)
        SIMULATION: Wokwi or other simulator generated data
    """

    PRODUCTION = "production"
    MOCK = "mock"
    TEST = "test"
    SIMULATION = "simulation"

    @classmethod
    def from_string(cls, value: str) -> "DataSource":
        """
        Convert string to DataSource enum.

        Args:
            value: String value to convert

        Returns:
            DataSource enum value, defaults to PRODUCTION if not found
        """
        try:
            return cls(value.lower())
        except (ValueError, AttributeError):
            return cls.PRODUCTION

    @classmethod
    def is_test_data(cls, source: "DataSource") -> bool:
        """
        Check if data source is considered test data (eligible for cleanup).

        Args:
            source: DataSource to check

        Returns:
            True if source is MOCK, TEST, or SIMULATION
        """
        return source in (cls.MOCK, cls.TEST, cls.SIMULATION)


class SensorOperatingMode(str, Enum):
    """
    Operating mode for sensor measurement behavior.

    Determines how and when a sensor performs measurements:
    - CONTINUOUS: Automatic measurements at regular intervals (default)
    - ON_DEMAND: Manual measurements only (user-triggered via MQTT command)
    - SCHEDULED: Measurements at specific times (cron-based)
    - PAUSED: Temporarily disabled (no measurements, no timeout warnings)

    Use Cases:
        - CONTINUOUS: Temperature, humidity sensors (always-on monitoring)
        - ON_DEMAND: pH meters, EC meters (point measurements)
        - SCHEDULED: Daily calibration checks, periodic water quality tests
        - PAUSED: Sensor maintenance, calibration in progress
    """

    CONTINUOUS = "continuous"
    ON_DEMAND = "on_demand"
    SCHEDULED = "scheduled"
    PAUSED = "paused"

    @classmethod
    def from_string(cls, value: str) -> "SensorOperatingMode":
        """
        Convert string to SensorOperatingMode enum.

        Args:
            value: String value to convert

        Returns:
            SensorOperatingMode enum value, defaults to CONTINUOUS if not found
        """
        try:
            return cls(value.lower())
        except (ValueError, AttributeError):
            return cls.CONTINUOUS

    @classmethod
    def requires_timeout(cls, mode: "SensorOperatingMode") -> bool:
        """
        Check if operating mode requires timeout monitoring.

        Args:
            mode: SensorOperatingMode to check

        Returns:
            True if mode should trigger stale warnings on timeout
        """
        return mode == cls.CONTINUOUS

    @classmethod
    def requires_freshness_check(cls, mode: "SensorOperatingMode") -> bool:
        """
        Check if operating mode requires measurement freshness monitoring.

        On-demand and scheduled sensors don't have timeouts but need
        freshness checks to warn when measurement values are too old.

        Returns:
            True if mode should trigger freshness warnings
        """
        return mode in (cls.ON_DEMAND, cls.SCHEDULED)

    @classmethod
    def is_active_mode(cls, mode: "SensorOperatingMode") -> bool:
        """
        Check if operating mode allows measurements.

        Args:
            mode: SensorOperatingMode to check

        Returns:
            True if sensor can/should take measurements in this mode
        """
        return mode != cls.PAUSED
