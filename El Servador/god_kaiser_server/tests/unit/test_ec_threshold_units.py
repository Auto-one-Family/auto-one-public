"""AUT-1270: EC hysteresis threshold migration to µS/cm."""

from src.services.logic.ec_threshold_units import migrate_ec_hysteresis_conditions


def test_migrate_ec_hysteresis_ms_magnitude_to_us_cm():
    conditions = [
        {
            "type": "hysteresis",
            "esp_id": "ESP_AEAE64",
            "gpio": 0,
            "sensor_type": "ec",
            "activate_below": 1.6,
            "deactivate_above": 1.7,
        }
    ]
    migrated, changes = migrate_ec_hysteresis_conditions(conditions)
    assert migrated[0]["activate_below"] == 1600.0
    assert migrated[0]["deactivate_above"] == 1700.0
    assert len(changes) == 2


def test_migrate_ec_hysteresis_idempotent_for_us_cm():
    conditions = [
        {
            "type": "hysteresis",
            "sensor_type": "ec",
            "activate_below": 1600,
            "deactivate_above": 1700,
        }
    ]
    migrated, changes = migrate_ec_hysteresis_conditions(conditions)
    assert migrated[0]["activate_below"] == 1600
    assert migrated[0]["deactivate_above"] == 1700
    assert changes == []


def test_migrate_leaves_ph_untouched():
    conditions = [
        {
            "type": "hysteresis",
            "sensor_type": "ph",
            "activate_above": 6.3,
            "deactivate_below": 5.9,
        }
    ]
    migrated, changes = migrate_ec_hysteresis_conditions(conditions)
    assert migrated[0]["activate_above"] == 6.3
    assert changes == []
