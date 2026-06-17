"""Unit tests for sensor delete tombstone expansion (AUT-527 CO2 UART)."""

from src.api.v1.sensors import _build_sensor_delete_tombstones


def test_co2_delete_emits_both_uart1_gpios() -> None:
    entries = _build_sensor_delete_tombstones(
        gpio=18,
        sensor_type="co2",
        sensor_name="Greenhouse CO2",
        onewire_address="",
        i2c_address=0,
    )
    gpios = {e["gpio"] for e in entries}
    assert gpios == {17, 18}
    assert all(e["active"] is False for e in entries)
    assert all(e["sensor_type"] == "co2" for e in entries)
    assert entries[0]["uart_rx_pin"] == 18
    assert entries[0]["uart_tx_pin"] == 17


def test_non_co2_delete_single_tombstone() -> None:
    entries = _build_sensor_delete_tombstones(
        gpio=34,
        sensor_type="ph",
        sensor_name="pH",
        onewire_address="",
        i2c_address=0,
    )
    assert len(entries) == 1
    assert entries[0]["gpio"] == 34
