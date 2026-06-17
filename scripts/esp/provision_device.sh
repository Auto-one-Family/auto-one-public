#!/usr/bin/env bash
# Provision an ESP in AP mode from the Pi (pi-home workflow).
# Requires: ESP in provisioning AP (AutoOne-ESP_<ID>), nmcli, curl.
#
# Usage:
#   export ESP_WIFI_SSID="${ESP_WIFI_SSID:-Vodafone-6F44}"
#   export ESP_WIFI_PASSWORD='your-wlan-password'
#   export ESP_SERVER_ADDRESS="${ESP_SERVER_ADDRESS:-192.168.0.2}"
#   export ESP_MQTT_PORT="${ESP_MQTT_PORT:-1883}"
#   ./scripts/esp/provision_device.sh ESP_698EB4
#
# Serial safety: clears CH340 DTR/RTS before any serial use (GPIO0 boot-button trap).

set -euo pipefail

ESP_ID="${1:?ESP device id required, e.g. ESP_698EB4}"
ESP_WIFI_SSID="${ESP_WIFI_SSID:-Vodafone-6F44}"
ESP_WIFI_PASSWORD="${ESP_WIFI_PASSWORD:-}"
ESP_SERVER_ADDRESS="${ESP_SERVER_ADDRESS:-192.168.0.2}"
ESP_MQTT_PORT="${ESP_MQTT_PORT:-1883}"
AP_SSID="AutoOne-${ESP_ID}"
AP_PASSWORD="provision"
AP_URL="http://192.168.4.1"

if [[ -z "${ESP_WIFI_PASSWORD}" ]]; then
  echo "FEHLER: ESP_WIFI_PASSWORD ist nicht gesetzt." >&2
  exit 1
fi

clear_serial_lines() {
  python3 - <<'PY'
import fcntl, struct
try:
    import serial
except ImportError:
    raise SystemExit(0)
PORT = "/dev/ttyUSB0"
TIOCM_DTR, TIOCM_RTS = 0x002, 0x004
TIOCMBIC = 0x5417
try:
    ser = serial.Serial(PORT, 115200, timeout=0.2)
    fcntl.ioctl(ser.fd, TIOCMBIC, struct.pack("I", TIOCM_DTR | TIOCM_RTS))
    ser.close()
except Exception:
    pass
PY
}

echo "Clearing USB serial DTR/RTS (GPIO0 safety)..."
clear_serial_lines

echo "Connecting Pi wlan0 to ${AP_SSID} (Pi may lose upstream WiFi briefly)..."
nmcli device wifi connect "${AP_SSID}" password "${AP_PASSWORD}" ifname wlan0

sleep 2
echo "POST ${AP_URL}/provision ..."
HTTP_CODE=$(curl -sS -m 15 -o /tmp/esp_provision_response.json -w "%{http_code}" \
  -X POST "${AP_URL}/provision" \
  -H "Content-Type: application/json" \
  -d "$(python3 - <<PY
import json, os
print(json.dumps({
    "ssid": os.environ["ESP_WIFI_SSID"],
    "password": os.environ["ESP_WIFI_PASSWORD"],
    "server_address": os.environ["ESP_SERVER_ADDRESS"],
    "mqtt_port": int(os.environ["ESP_MQTT_PORT"]),
    "mqtt_username": os.environ.get("ESP_MQTT_USERNAME", ""),
    "mqtt_password": os.environ.get("ESP_MQTT_PASSWORD", ""),
    "kaiser_id": os.environ.get("ESP_KAISER_ID", "god"),
}))
PY
)")

echo "HTTP ${HTTP_CODE}"
cat /tmp/esp_provision_response.json
echo

if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "Provisioning fehlgeschlagen." >&2
  exit 2
fi

echo "Reconnecting Pi to home WiFi (${ESP_WIFI_SSID})..."
nmcli device wifi connect "${ESP_WIFI_SSID}" password "${ESP_WIFI_PASSWORD}" ifname wlan0 || true

echo "Warte 30s auf ESP-Reboot und MQTT..."
sleep 30
docker exec automationone-mqtt mosquitto_sub -h localhost -p 1883 \
  -t "kaiser/god/esp/${ESP_ID}/heartbeat" -C 1 -W 20 && echo "Heartbeat OK" || echo "WARN: kein Heartbeat in 20s"
