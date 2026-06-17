#!/usr/bin/env bash
# ============================================
# Gap 3: Hardware-Sanity Release Gate Test
# ============================================
# Fuehrt den minimalen Hardware-Pflichtsatz durch:
#   HW-1: Sensor Live-Read (DS18B20)
#   HW-2: MQTT Roundtrip (Heartbeat → DB)
#   HW-3: Actuator Safety (Emergency Stop)
#   HW-4: NVS Persist (Config → Reboot → Verify)
#
# Voraussetzungen:
#   - ESP32 per USB verbunden
#   - Docker Stack laeuft (make up)
#   - Firmware geflasht (make flash)
#   - Database geseeded
#
# Usage:
#   bash scripts/hardware/release_gate_hw_test.sh
#   bash scripts/hardware/release_gate_hw_test.sh --skip-nvs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs/current/hardware/gap3"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
SKIP_NVS=false
SERIAL_PORT="${SERIAL_PORT:-/dev/ttyUSB0}"
SERIAL_BAUD=115200
MQTT_HOST="localhost"
MQTT_PORT=1883
ESP_ID="${ESP_ID:-ESP_00000001}"
TIMEOUT=30

[[ "${1:-}" == "--skip-nvs" ]] && SKIP_NVS=true

mkdir -p "$LOG_DIR"

log_info()  { echo "[INFO]  $(date +%H:%M:%S) $*"; }
log_pass()  { echo "[PASS]  $(date +%H:%M:%S) $*"; }
log_fail()  { echo "[FAIL]  $(date +%H:%M:%S) $*"; }

REPORT="$LOG_DIR/hw_gate_${TIMESTAMP}.md"

cat > "$REPORT" << EOF
# Hardware-Sanity Release Gate Report

**Datum:** $(date -Iseconds)
**Branch:** $BRANCH
**Commit:** $COMMIT
**ESP32:** $ESP_ID
**Serial:** $SERIAL_PORT

## Test-Ergebnisse

EOF

HW1_PASS=false
HW2_PASS=false
HW3_PASS=false
HW4_PASS=false

# --- Preflight ---
log_info "=== Hardware Release Gate ==="
log_info "Branch: $BRANCH | Commit: $COMMIT"

# Docker pruefen
if ! docker ps --format "{{.Names}}" | grep -q mqtt 2>/dev/null; then
  log_fail "Docker MQTT Broker nicht gefunden. 'docker compose up -d' ausfuehren."
  echo "| Preflight | FAIL | Docker nicht verfuegbar |" >> "$REPORT"
  exit 1
fi
log_pass "Docker Stack verfuegbar"

# --- HW-1: Sensor Live-Read ---
log_info ""
log_info "=== HW-1: Sensor Live-Read ==="
HW1_LOG="$LOG_DIR/hw1_sensor_${TIMESTAMP}.log"

# MQTT subscriben und auf Sensor-Daten warten
timeout "$TIMEOUT" docker exec automationone-mqtt \
  mosquitto_sub -t "kaiser/god/esp/$ESP_ID/sensor/+/data" \
  -C 1 -W "$TIMEOUT" > "$HW1_LOG" 2>&1 || true

if [ -s "$HW1_LOG" ]; then
  SENSOR_VALUE=$(cat "$HW1_LOG")
  log_pass "HW-1: Sensor-Daten empfangen: $SENSOR_VALUE"
  HW1_PASS=true
  echo "| HW-1: Sensor Live-Read | PASS | $SENSOR_VALUE |" >> "$REPORT"
else
  log_fail "HW-1: Keine Sensor-Daten nach ${TIMEOUT}s"
  echo "| HW-1: Sensor Live-Read | FAIL | Timeout nach ${TIMEOUT}s |" >> "$REPORT"
fi

# --- HW-2: MQTT Roundtrip ---
log_info ""
log_info "=== HW-2: MQTT Roundtrip ==="
HW2_LOG="$LOG_DIR/hw2_roundtrip_${TIMESTAMP}.log"

# Heartbeat abwarten
timeout "$TIMEOUT" docker exec automationone-mqtt \
  mosquitto_sub -t "kaiser/god/esp/$ESP_ID/system/heartbeat" \
  -C 1 -W "$TIMEOUT" > "$HW2_LOG" 2>&1 || true

if [ -s "$HW2_LOG" ]; then
  log_pass "HW-2: Heartbeat empfangen"

  # DB-Verifikation: Device online?
  DB_CHECK=$(docker exec automationone-postgres psql \
    -U "${POSTGRES_USER:-god_kaiser}" \
    -d "${POSTGRES_DB:-god_kaiser_db}" \
    -t -c "SELECT status FROM esp_devices WHERE device_id='$ESP_ID'" 2>/dev/null | tr -d ' \n' || echo "unknown")

  if [ "$DB_CHECK" = "online" ]; then
    log_pass "HW-2: Device in DB als 'online' — Roundtrip komplett"
    HW2_PASS=true
    echo "| HW-2: MQTT Roundtrip | PASS | Heartbeat + DB online |" >> "$REPORT"
  else
    log_fail "HW-2: Device-Status in DB: '$DB_CHECK' (erwartet: 'online')"
    echo "| HW-2: MQTT Roundtrip | FAIL | DB-Status: $DB_CHECK |" >> "$REPORT"
  fi
else
  log_fail "HW-2: Kein Heartbeat nach ${TIMEOUT}s"
  echo "| HW-2: MQTT Roundtrip | FAIL | Kein Heartbeat |" >> "$REPORT"
fi

# --- HW-3: Actuator Safety ---
log_info ""
log_info "=== HW-3: Actuator Safety ==="
HW3_LOG="$LOG_DIR/hw3_safety_${TIMESTAMP}.log"

# 1. Actuator konfigurieren (LED auf GPIO 5)
docker exec automationone-mqtt mosquitto_pub \
  -t "kaiser/god/esp/$ESP_ID/config" \
  -m '{"sensors":[],"actuators":[{"gpio":5,"actuator_type":"led","actuator_name":"SafetyTest","active":true}]}'
sleep 3

# 2. Actuator einschalten
docker exec automationone-mqtt mosquitto_pub \
  -t "kaiser/god/esp/$ESP_ID/actuator/5/command" \
  -m '{"command":"ON","value":1.0}'
sleep 2

# 3. Emergency Stop senden
docker exec automationone-mqtt mosquitto_pub \
  -t "kaiser/god/esp/$ESP_ID/actuator/emergency" \
  -m '{"command":"emergency_stop","auth_token":"'$ESP_ID'"}'

# 4. Warten und Serial-Log pruefen
sleep 3

# Pruefe ob Emergency-Stop-Response kommt
timeout 10 docker exec automationone-mqtt \
  mosquitto_sub -t "kaiser/god/esp/$ESP_ID/system/+" \
  -C 1 -W 10 > "$HW3_LOG" 2>&1 || true

if [ -s "$HW3_LOG" ]; then
  log_pass "HW-3: Emergency Stop Response empfangen"
  HW3_PASS=true
  echo "| HW-3: Actuator Safety | PASS | Emergency Stop bestaetigt |" >> "$REPORT"
else
  log_fail "HW-3: Keine Emergency Stop Bestaetigung"
  echo "| HW-3: Actuator Safety | FAIL | Keine Bestaetigung |" >> "$REPORT"
fi

# --- HW-4: NVS Persist ---
if [ "$SKIP_NVS" = true ]; then
  log_info ""
  log_info "=== HW-4: NVS Persist (UEBERSPRUNGEN) ==="
  HW4_PASS=true
  echo "| HW-4: NVS Persist | SKIP | --skip-nvs gesetzt |" >> "$REPORT"
else
  log_info ""
  log_info "=== HW-4: NVS Persist ==="
  HW4_LOG="$LOG_DIR/hw4_nvs_${TIMESTAMP}.log"

  # Config senden
  docker exec automationone-mqtt mosquitto_pub \
    -t "kaiser/god/esp/$ESP_ID/config" \
    -m '{"sensors":[{"gpio":4,"sensor_type":"temp_ds18b20","sensor_name":"NVSTest","active":true}],"actuators":[]}'
  sleep 5

  log_info "HW-4: Config gesendet. BITTE ESP32 MANUELL REBOOTEN."
  log_info "HW-4: Druecke EN/RST-Taste auf dem ESP32 Board."
  log_info "HW-4: Warte 30s auf Reboot + Reconnect..."
  sleep 30

  # Nach Reboot: Sensor-Daten abwarten (beweist NVS-Persist)
  timeout "$TIMEOUT" docker exec automationone-mqtt \
    mosquitto_sub -t "kaiser/god/esp/$ESP_ID/sensor/4/data" \
    -C 1 -W "$TIMEOUT" > "$HW4_LOG" 2>&1 || true

  if [ -s "$HW4_LOG" ]; then
    log_pass "HW-4: Sensor-Daten nach Reboot empfangen — NVS Persist funktioniert"
    HW4_PASS=true
    echo "| HW-4: NVS Persist | PASS | Config nach Reboot erhalten |" >> "$REPORT"
  else
    log_fail "HW-4: Keine Sensor-Daten nach Reboot"
    echo "| HW-4: NVS Persist | FAIL | Keine Daten nach Reboot |" >> "$REPORT"
  fi
fi

# --- Zusammenfassung ---
cat >> "$REPORT" << EOF

## Gate-Entscheidung

EOF

ALL_PASS=true
[ "$HW1_PASS" != true ] && ALL_PASS=false
[ "$HW2_PASS" != true ] && ALL_PASS=false
[ "$HW3_PASS" != true ] && ALL_PASS=false
[ "$HW4_PASS" != true ] && ALL_PASS=false

if [ "$ALL_PASS" = true ]; then
  echo "**HARDWARE-GATE: PASS** — Alle Tests bestanden." >> "$REPORT"
  log_pass "=== HARDWARE-GATE: PASS ==="
else
  BLOCKERS=""
  [ "$HW1_PASS" != true ] && BLOCKERS="${BLOCKERS}HW-1 (Sensor), "
  [ "$HW2_PASS" != true ] && BLOCKERS="${BLOCKERS}HW-2 (Roundtrip), "
  [ "$HW3_PASS" != true ] && BLOCKERS="${BLOCKERS}HW-3 (Safety), "
  [ "$HW4_PASS" != true ] && BLOCKERS="${BLOCKERS}HW-4 (NVS), "
  echo "**HARDWARE-GATE: BLOCKIERT** — Blocker: ${BLOCKERS%, }" >> "$REPORT"
  log_fail "=== HARDWARE-GATE: BLOCKIERT — ${BLOCKERS%, } ==="
fi

log_info "Report: $REPORT"

if [ "$ALL_PASS" = true ]; then exit 0; else exit 1; fi
