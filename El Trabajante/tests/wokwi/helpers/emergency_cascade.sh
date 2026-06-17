#!/bin/bash
# Emergency Cascade MQTT Injection Script
# Used by CI Job 16 for error_emergency_cascade.yaml scenario.
#
# Sends 5 MQTT messages with precise timing to test the safety state machine:
#   1. Config: 1 sensor + 1 actuator
#   2. Actuator ON command
#   3. Broadcast emergency stop
#   4. Emergency clear
#   5. Second broadcast emergency stop (rapid re-trigger)
#
# Usage: ./emergency_cascade.sh [broker_host]
# Default broker: localhost

BROKER="${1:-localhost}"
BASE_TOPIC="kaiser/god/esp/ESP_00000001"

# Step 1: Configure sensor + actuator
mosquitto_pub -h "$BROKER" -t "$BASE_TOPIC/config" \
  -m '{"sensors":[{"gpio":4,"sensor_type":"ds18b20","sensor_name":"S1","active":true}],"actuators":[{"gpio":5,"actuator_type":"led","actuator_name":"A1","active":true}]}'
sleep 2

# Step 2: Activate actuator (LED on GPIO 5)
mosquitto_pub -h "$BROKER" -t "$BASE_TOPIC/actuator/5/command" \
  -m '{"command":"ON","value":1.0}'
sleep 1

# Step 3: Broadcast emergency stop (God-Kaiser authority)
mosquitto_pub -h "$BROKER" -t "kaiser/broadcast/emergency" \
  -m '{"auth_token":"master_token"}'
sleep 1

# Step 4: Clear emergency via ESP-specific topic
mosquitto_pub -h "$BROKER" -t "$BASE_TOPIC/actuator/emergency" \
  -m '{"command":"clear_emergency","auth_token":"ESP_00000001"}'
sleep 1

# Step 5: Second broadcast emergency stop (rapid re-trigger)
mosquitto_pub -h "$BROKER" -t "kaiser/broadcast/emergency" \
  -m '{"auth_token":"master_token"}'
