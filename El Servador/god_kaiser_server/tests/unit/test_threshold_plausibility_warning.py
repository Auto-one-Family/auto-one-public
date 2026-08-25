"""AUT-1274: non-blocking threshold plausibility warnings on rule save path."""

from unittest.mock import MagicMock

from src.sensors.sensor_type_registry import (
    get_plausible_range_for_sensor_type,
    get_unit_for_sensor_type,
)
from src.services.logic_service import LogicService


def test_ssot_canonical_units():
    assert get_unit_for_sensor_type("ec") == "µS/cm"
    assert get_unit_for_sensor_type("ph") == "pH"
    assert get_unit_for_sensor_type("ds18b20") == "°C"


def test_ssot_plausible_range_ec_catches_ms_magnitude():
    rng = get_plausible_range_for_sensor_type("ec")
    assert rng is not None
    assert 1.6 < rng["min"]
    assert 1600 >= rng["min"]
    assert 1600 <= rng["max"]


def test_check_threshold_plausibility_warns_on_ec_1_6():
    service = LogicService(logic_repo=MagicMock())
    warnings = service._check_threshold_plausibility(
        [
            {
                "type": "hysteresis",
                "sensor_type": "ec",
                "activate_below": 1.6,
                "deactivate_above": 1.7,
            }
        ]
    )
    assert len(warnings) >= 1
    assert any("1.6" in w and "ec" in w.lower() for w in warnings)


def test_check_threshold_plausibility_silent_for_ec_1600():
    service = LogicService(logic_repo=MagicMock())
    warnings = service._check_threshold_plausibility(
        [
            {
                "type": "hysteresis",
                "sensor_type": "ec",
                "activate_below": 1600,
                "deactivate_above": 1700,
            }
        ]
    )
    assert warnings == []


def test_check_threshold_plausibility_silent_for_ph():
    service = LogicService(logic_repo=MagicMock())
    warnings = service._check_threshold_plausibility(
        [
            {
                "type": "hysteresis",
                "sensor_type": "ph",
                "activate_above": 6.3,
                "deactivate_below": 5.9,
            }
        ]
    )
    assert warnings == []
