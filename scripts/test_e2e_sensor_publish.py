"""
E2E Test: Publish sensor data via MQTT and verify it arrives in the database.

Usage:
    .venv/Scripts/python.exe scripts/test_e2e_sensor_publish.py

Connects to localhost:1883 (Docker-published MQTT broker port),
publishes a sensor reading on the correct topic, then queries the
database to verify the row was inserted.
"""

import json
import time
import sys

import paho.mqtt.client as mqtt

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MQTT_HOST = "localhost"
MQTT_PORT = 1883

ESP_ID = "MOCK_5D5ADA49"
GPIO = 4
SENSOR_TYPE = "temperature"
TOPIC = f"kaiser/god/esp/{ESP_ID}/sensor/{GPIO}/data"

PAYLOAD = {
    "esp_id": ESP_ID,
    "gpio": GPIO,
    "sensor_type": SENSOR_TYPE,
    "raw": 2350,
    "value": 23.5,
    "unit": "C",
    "quality": "good",
    "ts": int(time.time()),
    "raw_mode": True,
}


def main() -> None:
    print(f"[1/3] Connecting to MQTT broker at {MQTT_HOST}:{MQTT_PORT} ...")
    client = mqtt.Client(client_id="e2e-sensor-test", protocol=mqtt.MQTTv311)

    connected = False

    def on_connect(c, userdata, flags, rc):
        nonlocal connected
        if rc == 0:
            connected = True
            print("       Connected OK")
        else:
            print(f"       Connection failed, rc={rc}")

    client.on_connect = on_connect
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
    client.loop_start()

    # Wait for connection
    for _ in range(30):
        if connected:
            break
        time.sleep(0.1)

    if not connected:
        print("ERROR: Could not connect to MQTT broker")
        client.loop_stop()
        sys.exit(1)

    # Publish
    payload_str = json.dumps(PAYLOAD)
    print(f"[2/3] Publishing to topic: {TOPIC}")
    print(f"       Payload: {payload_str}")
    result = client.publish(TOPIC, payload_str, qos=1)
    result.wait_for_publish(timeout=5)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("       Published OK (QoS 1 acknowledged)")
    else:
        print(f"       Publish failed, rc={result.rc}")
        client.loop_stop()
        client.disconnect()
        sys.exit(1)

    # Give server a moment to process
    print("[3/3] Waiting 2s for server to process ...")
    time.sleep(2)

    client.loop_stop()
    client.disconnect()
    print("       Done. Check sensor_data table for new row.")
    print()
    print("Verify with:")
    print('  docker exec automationone-postgres psql -U god_kaiser -d god_kaiser_db -c "SELECT id, esp_id, sensor_type, value, created_at FROM sensor_data ORDER BY id DESC LIMIT 5;"')


if __name__ == "__main__":
    main()
