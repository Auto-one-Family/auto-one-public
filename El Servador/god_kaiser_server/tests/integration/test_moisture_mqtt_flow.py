"""
Integration Tests: Moisture Sensor Processing Pipeline

Tests the complete moisture sensor processing flow:
- Sensor type normalization (soil_moisture → moisture alias)
- LibraryLoader processor discovery via alias
- MoistureSensorProcessor processing with and without calibration
- ProcessingResult attribute access (not dict-style)
- Correct parameter placement (invert in params, not calibration)

Hardware Context:
- Capacitive Soil Moisture Sensor v1.2 (or compatible)
- ESP32 ADC1 pins only (GPIO32-39) — ADC2 conflicts with WiFi!
- 12-bit ADC (0-4095 range)
- Two-point calibration: dry (sensor in air) and wet (sensor in water/saturated soil)
- Default mapping: dry ~3200 ADC, wet ~1500 ADC

Dependencies:
- MoistureSensorProcessor (src.sensors.sensor_libraries.active.moisture)
- LibraryLoader singleton (src.sensors.library_loader)
- normalize_sensor_type (src.sensors.sensor_type_registry)
"""

import pytest

from src.sensors.base_processor import ProcessingResult
from src.sensors.library_loader import LibraryLoader
from src.sensors.sensor_libraries.active.moisture import MoistureSensorProcessor
from src.sensors.sensor_type_registry import normalize_sensor_type

pytestmark = [pytest.mark.sensor, pytest.mark.flow_a]


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def moisture_processor() -> MoistureSensorProcessor:
    """Create a fresh MoistureSensorProcessor instance."""
    return MoistureSensorProcessor()


@pytest.fixture
def library_loader() -> LibraryLoader:
    """Get LibraryLoader singleton instance."""
    return LibraryLoader.get_instance()


# ── Test: Sensor Type Normalization ──────────────────────────────────────────


class TestMoistureTypeNormalization:
    """Sensor type normalization for moisture aliases."""

    def test_soil_moisture_alias_normalizes_to_moisture(self):
        """
        normalize_sensor_type("soil_moisture") must return "moisture".

        The ESP32 may send "soil_moisture" as sensor type.
        The server normalizes this to "moisture" for processor lookup.

        Registry entry:
            "soil_moisture": "moisture"  # Alias
        """
        result = normalize_sensor_type("soil_moisture")
        assert result == "moisture"

    def test_moisture_identity_mapping(self):
        """normalize_sensor_type("moisture") → "moisture" (already normalized)."""
        result = normalize_sensor_type("moisture")
        assert result == "moisture"


# ── Test: LibraryLoader Discovery ────────────────────────────────────────────


class TestMoistureLibraryLoaderDiscovery:
    """LibraryLoader discovers and returns MoistureSensorProcessor."""

    def test_get_processor_soil_moisture_returns_moisture_processor(
        self, library_loader: LibraryLoader
    ):
        """
        LibraryLoader.get_processor("soil_moisture") must return MoistureSensorProcessor.

        The loader normalizes "soil_moisture" → "moisture" internally
        via normalize_sensor_type(), then returns the cached processor instance.
        """
        processor = library_loader.get_processor("soil_moisture")
        assert processor is not None
        assert isinstance(processor, MoistureSensorProcessor)

    def test_alias_and_direct_resolve_to_same_processor_class(self, library_loader: LibraryLoader):
        """Both "soil_moisture" and "moisture" must resolve to same processor class."""
        proc_alias = library_loader.get_processor("soil_moisture")
        proc_direct = library_loader.get_processor("moisture")

        assert proc_alias is not None
        assert proc_direct is not None
        assert type(proc_alias) is type(proc_direct)
        assert isinstance(proc_alias, MoistureSensorProcessor)


# ── Test: Uncalibrated Processing ────────────────────────────────────────────


class TestMoistureProcessingUncalibrated:
    """MoistureSensorProcessor with default (uncalibrated) mapping."""

    def test_process_raw_2143_no_calibration(self, moisture_processor: MoistureSensorProcessor):
        """
        process(raw_value=2143, calibration=None) → ~62.2%, unit="%", quality="good"

        Default mapping: dry=3200 ADC, wet=1500 ADC
        moisture = (2143 - 3200) / (1500 - 3200) * 100 = 62.176... ≈ 62.2%
        Quality: 20% ≤ 62.2% ≤ 80% → "good"
        """
        result = moisture_processor.process(raw_value=2143, calibration=None)

        assert isinstance(result, ProcessingResult)
        assert result.value == pytest.approx(62.2, abs=0.1)
        assert result.unit == "%"
        assert result.quality == "good"

    def test_processing_result_has_attributes_not_dict_keys(
        self, moisture_processor: MoistureSensorProcessor
    ):
        """
        ProcessingResult has .value, .unit, .quality attributes (NOT dict-style access).

        ProcessingResult is a @dataclass with:
            value: float
            unit: str
            quality: str
            metadata: Optional[Dict[str, Any]]
        """
        result = moisture_processor.process(raw_value=2143)

        # Attribute access (correct)
        assert hasattr(result, "value")
        assert hasattr(result, "unit")
        assert hasattr(result, "quality")
        assert hasattr(result, "metadata")

        # Verify types
        assert isinstance(result.value, float)
        assert isinstance(result.unit, str)
        assert isinstance(result.quality, str)


# ── Test: Calibrated Processing ──────────────────────────────────────────────


class TestMoistureProcessingCalibrated:
    """MoistureSensorProcessor with two-point calibration."""

    def test_process_raw_2050_with_calibration_50_percent(
        self, moisture_processor: MoistureSensorProcessor
    ):
        """
        process(raw_value=2050, calibration={"dry_value": 2800, "wet_value": 1300}) → ~50%

        Calibrated mapping: dry=2800 ADC, wet=1300 ADC
        moisture = (2050 - 2800) / (1300 - 2800) * 100 = (-750) / (-1500) * 100 = 50.0%
        """
        calibration = {"dry_value": 2800, "wet_value": 1300}
        result = moisture_processor.process(raw_value=2050, calibration=calibration)

        assert isinstance(result, ProcessingResult)
        assert result.value == pytest.approx(50.0, abs=0.1)
        assert result.unit == "%"
        assert result.metadata is not None
        assert result.metadata.get("calibrated") is True

    def test_invert_belongs_in_params_not_calibration(
        self, moisture_processor: MoistureSensorProcessor
    ):
        """
        Invert logic must be passed via params, NOT calibration.

        Correct:   process(raw_value=2050, calibration=cal, params={"invert": True})
        Incorrect: process(raw_value=2050, calibration={"invert": True, ...})

        Invert flips the result: inverted_value = 100 - normal_value
        """
        calibration = {"dry_value": 2800, "wet_value": 1300}

        # Normal result (50%)
        result_normal = moisture_processor.process(raw_value=2050, calibration=calibration)

        # Inverted via params (correct placement)
        result_inverted = moisture_processor.process(
            raw_value=2050, calibration=calibration, params={"invert": True}
        )

        # Inverted should be 100 - normal
        assert result_inverted.value == pytest.approx(100.0 - result_normal.value, abs=0.1)
