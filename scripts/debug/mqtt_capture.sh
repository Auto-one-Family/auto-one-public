#!/bin/bash
# ============================================
# MQTT Debug Capture — Payload-Level Mitschnitt
# ============================================
# Purpose: Captures MQTT message payloads for debugging.
#          Mosquitto logs only connection events, not payloads.
#          This script fills that gap using mosquitto_sub.
#
# Usage:
#   ./mqtt_capture.sh                         # All kaiser/# topics
#   ./mqtt_capture.sh "kaiser/god/esp/+/sensor/+/data"  # Sensor data only
#   ./mqtt_capture.sh "kaiser/#" custom_output.log       # Custom output file
#
# Prerequisites:
#   - MQTT broker running: docker compose up -d mqtt-broker
#   - mosquitto_sub available (installed via mosquitto-clients package)
#
# Output format:
#   [2026-02-23T12:00:00Z] topic payload
# ============================================

set -euo pipefail

TOPIC="${1:-kaiser/#}"
OUTPUT="${2:-logs/current/mqtt_capture_$(date +%Y%m%d_%H%M%S).log}"

# Resolve project root (script is in scripts/debug/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Make output path absolute if relative
if [[ "$OUTPUT" != /* ]]; then
  OUTPUT="$PROJECT_ROOT/$OUTPUT"
fi

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT")"

echo "============================================"
echo "  MQTT Debug Capture"
echo "============================================"
echo "Topic filter: $TOPIC"
echo "Output file:  $OUTPUT"
echo "Press Ctrl+C to stop"
echo "============================================"

# Use docker compose exec to run mosquitto_sub inside the broker container
# This avoids requiring mosquitto-clients on the host
cd "$PROJECT_ROOT"
docker compose exec -T mqtt-broker mosquitto_sub -v -t "$TOPIC" 2>/dev/null | \
  while IFS= read -r line; do
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $line"
  done | tee "$OUTPUT"
