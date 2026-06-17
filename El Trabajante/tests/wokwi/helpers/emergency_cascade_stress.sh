#!/bin/bash
# Emergency Cascade MQTT Injection Script
# Usage: bash emergency_cascade_stress.sh [mqtt_host] [esp_id]
#
# Sends 5 rapid emergency/clear sequences to test ESP32 stability
# Requires: mosquitto_pub (mosquitto-clients package)
#
# NOTE: emergency_cascade.sh (same dir) is the CI Job 16 variant.
# This script is for manual stress testing with rapid toggle cycles.

MQTT_HOST="${1:-localhost}"
ESP_ID="${2:-ESP_00000001}"
TOPIC_BASE="kaiser/god/esp/${ESP_ID}"

echo "=== Emergency Cascade Test ==="
echo "Target: $ESP_ID via $MQTT_HOST"
echo ""

# Sequence: 5x Emergency -> Clear with decreasing intervals
DELAYS=(3 2 1 0.5 0.5)
for i in $(seq 0 4); do
    ROUND=$((i + 1))
    DELAY=${DELAYS[$i]}

    echo "[Round $ROUND/5] Emergency STOP..."
    mosquitto_pub -h "$MQTT_HOST" -t "kaiser/broadcast/emergency" \
        -m "{\"action\":\"emergency_stop\",\"source\":\"test\",\"timestamp\":$(date +%s)}" 2>/dev/null

    sleep "$DELAY"

    echo "[Round $ROUND/5] Emergency CLEAR..."
    mosquitto_pub -h "$MQTT_HOST" -t "kaiser/broadcast/emergency" \
        -m "{\"action\":\"emergency_clear\",\"source\":\"test\",\"timestamp\":$(date +%s)}" 2>/dev/null

    sleep "$DELAY"
done

echo ""
echo "=== Cascade complete. Check ESP32 stability in serial log. ==="
