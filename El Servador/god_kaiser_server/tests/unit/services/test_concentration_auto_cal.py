"""AUT-1371 K2: auto-cal merge policy + seed step boundedness."""

from src.services.concentration_auto_cal import (
    AUTO_CAL_SETTLE_SECONDS,
    _build_seed_steps,
    merge_concentration_update,
)


def test_merge_initial_when_current_null():
    value, reason, hist = merge_concentration_update(None, 12.5, [])
    assert value == 12.5
    assert reason == "initial"
    assert hist == [12.5]


def test_merge_rejects_outlier_over_50_percent():
    value, reason, hist = merge_concentration_update(10.0, 16.0, [10.0])
    assert value is None
    assert reason == "outlier_rejected"
    assert hist == [10.0]


def test_merge_ewma_under_three_samples():
    value, reason, hist = merge_concentration_update(10.0, 12.0, [10.0])
    assert reason == "ewma"
    assert hist == [10.0, 12.0]
    # α=0.3 → 0.7*10 + 0.3*12 = 10.6
    assert abs(value - 10.6) < 1e-9


def test_merge_median_window_at_three_samples():
    value, reason, hist = merge_concentration_update(10.0, 11.0, [9.0, 10.0])
    assert reason == "median_window"
    assert hist == [9.0, 10.0, 11.0]
    assert value == 10.0


def test_seed_steps_use_bounded_mix_on_no_separate_off():
    pumps = [
        {
            "dose_role": "part_a",
            "action": {
                "type": "actuator",
                "esp_id": "ESP_AEAE64",
                "gpio": 12,
                "command": "ON",
                "duration_seconds": 5,
            },
        },
        {
            "dose_role": "part_b",
            "action": {
                "type": "actuator",
                "esp_id": "ESP_AEAE64",
                "gpio": 16,
                "command": "ON",
                "duration_seconds": 5,
            },
        },
    ]
    steps = _build_seed_steps(pumps, "ESP_AEAE64", 13, AUTO_CAL_SETTLE_SECONDS)

    on_steps = [
        s
        for s in steps
        if isinstance(s.get("action"), dict) and str(s["action"].get("command", "")).upper() == "ON"
    ]
    off_steps = [
        s
        for s in steps
        if isinstance(s.get("action"), dict)
        and str(s["action"].get("command", "")).upper() == "OFF"
    ]
    assert not off_steps, "Revision 3: no separate OFF steps"

    # A, MixA, B, MixB → 4 bounded ON
    assert len(on_steps) == 4
    for step in on_steps:
        dur = step["action"].get("duration_seconds")
        assert dur is not None and float(dur) > 0

    mix_ons = [s for s in on_steps if s["action"].get("gpio") == 13]
    assert len(mix_ons) == 2
    assert all(s["action"]["duration_seconds"] == AUTO_CAL_SETTLE_SECONDS for s in mix_ons)

    delays = [s["delay_seconds"] for s in steps if "delay_seconds" in s and "action" not in s]
    assert delays == [AUTO_CAL_SETTLE_SECONDS, AUTO_CAL_SETTLE_SECONDS]


def test_settle_constant_is_300_not_operative_120():
    assert AUTO_CAL_SETTLE_SECONDS == 300
