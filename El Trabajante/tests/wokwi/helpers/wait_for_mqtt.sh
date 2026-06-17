#!/bin/bash
# Wait for ESP32 MQTT connection in Wokwi serial log
# Usage: source wait_for_mqtt.sh <log-file> [timeout_seconds]
#
# Returns: 0 if MQTT connected, 1 if timeout
# The script polls the serial log file for MQTT connection messages.

LOG_FILE="${1:-/tmp/wokwi_serial.log}"
TIMEOUT="${2:-60}"

echo "Waiting for MQTT connection (log: $LOG_FILE, timeout: ${TIMEOUT}s)..."

for i in $(seq 1 "$TIMEOUT"); do
    if [ -f "$LOG_FILE" ]; then
        # Check for various MQTT connection success patterns
        if grep -q "MQTT connected\|MQTT: Connected\|mqtt_connected.*true\|Phase 2: Communication Layer READY" "$LOG_FILE" 2>/dev/null; then
            echo "MQTT connected after ${i}s"
            return 0 2>/dev/null || exit 0
        fi
        # Check for fatal errors (no point waiting further)
        if grep -q "MQTT: Fatal error\|WiFi: DISCONNECTED.*permanent\|BOOT FAILED" "$LOG_FILE" 2>/dev/null; then
            echo "FATAL: Boot failed after ${i}s"
            return 1 2>/dev/null || exit 1
        fi
    fi
    sleep 1
done

echo "TIMEOUT: MQTT connection not detected after ${TIMEOUT}s"
return 1 2>/dev/null || exit 1
