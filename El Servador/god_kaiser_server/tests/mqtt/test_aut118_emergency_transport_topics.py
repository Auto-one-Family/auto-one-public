"""AUT-118: emergency ACK + recovery_confirm topic helpers."""

from src.mqtt.topics import TopicBuilder


def test_build_emergency_ack_topic_matches_parse() -> None:
    t = TopicBuilder.build_emergency_ack_topic("ESP_00001", kaiser_id="god")
    assert t == "kaiser/god/esp/ESP_00001/actuator/emergency/ack"
    parsed = TopicBuilder.parse_emergency_ack_topic(t)
    assert parsed is not None
    assert parsed["esp_id"] == "ESP_00001"
    assert parsed["type"] == "emergency_ack"


def test_build_recovery_confirm_topic_matches_parse() -> None:
    t = TopicBuilder.build_recovery_confirm_topic("ESP_00002", kaiser_id="kal")
    assert t == "kaiser/kal/esp/ESP_00002/actuator/recovery_confirm"
    parsed = TopicBuilder.parse_recovery_confirm_topic(t)
    assert parsed is not None
    assert parsed["esp_id"] == "ESP_00002"
    assert parsed["type"] == "recovery_confirm"


def test_parse_generic_topic_router_includes_aut118_types() -> None:
    ack = TopicBuilder.build_emergency_ack_topic("ESP_ZZ", kaiser_id="god")
    rc = TopicBuilder.build_recovery_confirm_topic("ESP_ZZ", kaiser_id="god")
    assert TopicBuilder.parse_topic(ack)["type"] == "emergency_ack"  # type: ignore[index]
    assert TopicBuilder.parse_topic(rc)["type"] == "recovery_confirm"  # type: ignore[index]
