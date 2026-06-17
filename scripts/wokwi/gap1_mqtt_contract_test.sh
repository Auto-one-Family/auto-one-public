#!/usr/bin/env bash
# ============================================
# Gap 1: MQTT Docker-Wokwi Contract Verifikation
# ============================================
# Fuehrt 3 Testtypen durch:
#   1. Smoke Connectivity Test
#   2. Injection Roundtrip Test
#   3. Stabilitaetstest (3 Wiederholungen)
#
# Voraussetzungen:
#   - Docker Stack laeuft (make up)
#   - Wokwi CLI installiert + WOKWI_CLI_TOKEN gesetzt
#   - Database geseeded (make wokwi-seed)
#   - Firmware gebaut (make wokwi-build)
#
# Usage:
#   bash scripts/wokwi/gap1_mqtt_contract_test.sh
#   bash scripts/wokwi/gap1_mqtt_contract_test.sh --smoke-only
#   bash scripts/wokwi/gap1_mqtt_contract_test.sh --repeat 5

set -euo pipefail

# --- Konfiguration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs/wokwi"
SERIAL_LOG_DIR="$LOG_DIR/serial/gap1"
MQTT_LOG_DIR="$LOG_DIR/mqtt/gap1"
REPORT_DIR="$LOG_DIR/reports/gap1"
FIRMWARE_DIR="$PROJECT_ROOT/El Trabajante"
BOOT_SCENARIO="tests/wokwi/scenarios/01-boot/boot_full.yaml"
CONFIG_SCENARIO="tests/wokwi/scenarios/06-config/config_sensor_add.yaml"
WOKWI_TIMEOUT=90000
PROCESS_TIMEOUT=120
MQTT_WAIT_MAX=60
BROKER_WAIT_MAX=30
REPEAT_COUNT=3
SMOKE_ONLY=false
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case $1 in
    --smoke-only) SMOKE_ONLY=true; shift ;;
    --repeat) REPEAT_COUNT="$2"; shift 2 ;;
    *) echo "Unbekanntes Argument: $1"; exit 1 ;;
  esac
done

# --- Hilfsfunktionen ---
log_info()  { echo "[INFO]  $(date +%H:%M:%S) $*"; }
log_pass()  { echo "[PASS]  $(date +%H:%M:%S) $*"; }
log_fail()  { echo "[FAIL]  $(date +%H:%M:%S) $*"; }
log_warn()  { echo "[WARN]  $(date +%H:%M:%S) $*"; }

check_signature() {
  local logfile="$1"
  local pattern="$2"
  local label="$3"
  if grep -q "$pattern" "$logfile" 2>/dev/null; then
    log_pass "Signatur gefunden: $label"
    return 0
  else
    log_fail "Signatur FEHLT: $label"
    return 1
  fi
}

write_run_header() {
  local logfile="$1"
  local scenario="$2"
  cat >> "$logfile" << EOF
---
Startzeit: $(date -Iseconds)
Branch: $BRANCH
Commit: $COMMIT
Szenario: $scenario
---
EOF
}

# --- Preflight Checks ---
log_info "=== Gap 1: MQTT Docker-Wokwi Contract Test ==="
log_info "Projekt: $PROJECT_ROOT"
log_info "Branch: $BRANCH | Commit: $COMMIT"
log_info "Timestamp: $TIMESTAMP"

mkdir -p "$SERIAL_LOG_DIR" "$MQTT_LOG_DIR" "$REPORT_DIR"

# Pruefen: Docker laeuft?
if ! docker info >/dev/null 2>&1; then
  log_fail "Docker Daemon nicht erreichbar."
  exit 1
fi

# Pruefen: Broker Container vorhanden?
if ! docker ps --format "{{.Names}}" | grep -q "automationone-mqtt" 2>/dev/null; then
  log_fail "Kein MQTT-Broker Container 'automationone-mqtt' gefunden. 'docker compose up -d' ausfuehren."
  exit 1
fi

# Pruefen: Port 1883 erreichbar?
MQTT_PORT_CHECK=$(docker ps --format "{{.Names}}\t{{.Ports}}" | grep mqtt || true)
if echo "$MQTT_PORT_CHECK" | grep -q "0.0.0.0:1883"; then
  log_pass "MQTT Port 1883 korrekt published: $MQTT_PORT_CHECK"
else
  log_fail "MQTT Port 1883 nicht korrekt published. Aktuell: $MQTT_PORT_CHECK"
  exit 1
fi

# Pruefen: Broker Healthcheck (loop-basiert)
BROKER_READY=false
for i in $(seq 1 "$BROKER_WAIT_MAX"); do
  if docker exec automationone-mqtt mosquitto_pub -t 'test/gap1/ping' -m "pong-$i" 2>/dev/null; then
    log_pass "MQTT Broker Healthcheck bestanden (nach ${i}s)"
    BROKER_READY=true
    break
  fi
  sleep 1
done
if [ "$BROKER_READY" != "true" ]; then
  log_fail "MQTT Broker antwortet nicht innerhalb ${BROKER_WAIT_MAX}s auf Healthcheck"
  docker logs --tail 150 automationone-mqtt || true
  exit 1
fi

# Pruefen: Wokwi CLI verfuegbar?
if ! command -v wokwi-cli &>/dev/null; then
  log_fail "wokwi-cli nicht gefunden. Installation: https://docs.wokwi.com/wokwi-ci/getting-started"
  exit 1
fi

# Pruefen: Wokwi Token vorhanden?
if [ -z "${WOKWI_CLI_TOKEN:-}" ]; then
  log_fail "WOKWI_CLI_TOKEN ist nicht gesetzt."
  exit 1
fi

# Pruefen: Firmware vorhanden?
if [ ! -f "$FIRMWARE_DIR/.pio/build/wokwi_simulation/firmware.bin" ]; then
  log_fail "Firmware nicht gefunden. 'make wokwi-build' ausfuehren."
  exit 1
fi

log_info "Preflight Checks bestanden."

# --- Test 1: Smoke Connectivity ---
log_info ""
log_info "=== TEST 1: Smoke Connectivity ==="
SMOKE_LOG="$SERIAL_LOG_DIR/smoke_${TIMESTAMP}.log"
SMOKE_PASS=false

cd "$FIRMWARE_DIR"
write_run_header "$SMOKE_LOG" "$BOOT_SCENARIO"

timeout "$PROCESS_TIMEOUT" wokwi-cli . \
  --timeout "$WOKWI_TIMEOUT" \
  --scenario "$BOOT_SCENARIO" \
  >> "$SMOKE_LOG" 2>&1
SMOKE_EXIT=$?

echo "Exit-Code: $SMOKE_EXIT" >> "$SMOKE_LOG"

SMOKE_SIGS=0
check_signature "$SMOKE_LOG" "ESP32 Sensor Network" "Boot gestartet" && ((SMOKE_SIGS++)) || true
check_signature "$SMOKE_LOG" "MQTT connected" "MQTT verbunden" && ((SMOKE_SIGS++)) || true
check_signature "$SMOKE_LOG" "heartbeat" "Heartbeat gesendet" && ((SMOKE_SIGS++)) || true

if [ "$SMOKE_EXIT" -eq 0 ] && [ "$SMOKE_SIGS" -ge 3 ]; then
  log_pass "Smoke Test BESTANDEN (Exit: $SMOKE_EXIT, Signaturen: $SMOKE_SIGS/3)"
  SMOKE_PASS=true
else
  log_fail "Smoke Test FEHLGESCHLAGEN (Exit: $SMOKE_EXIT, Signaturen: $SMOKE_SIGS/3)"
fi

if [ "$SMOKE_ONLY" = true ]; then
  log_info "Smoke-only Modus — Tests beendet."
  exit $( [ "$SMOKE_PASS" = true ] && echo 0 || echo 1 )
fi

# --- Test 2: Injection Roundtrip ---
log_info ""
log_info "=== TEST 2: Injection Roundtrip ==="
INJECT_LOG="$SERIAL_LOG_DIR/injection_${TIMESTAMP}.log"
INJECT_MQTT_LOG="$MQTT_LOG_DIR/injection_${TIMESTAMP}.log"
INJECT_PASS=false

write_run_header "$INJECT_LOG" "$CONFIG_SCENARIO"

# Wokwi im Hintergrund starten
timeout "$PROCESS_TIMEOUT" wokwi-cli . \
  --timeout "$WOKWI_TIMEOUT" \
  --scenario "$CONFIG_SCENARIO" \
  > "$INJECT_LOG" 2>&1 &
WOKWI_PID=$!

# Dynamic Wait auf MQTT-Verbindung
MQTT_READY=false
for i in $(seq 1 $MQTT_WAIT_MAX); do
  if grep -q "MQTT connected" "$INJECT_LOG" 2>/dev/null; then
    log_info "MQTT connected nach ${i}s"
    MQTT_READY=true
    break
  fi
  sleep 1
done

if [ "$MQTT_READY" != "true" ]; then
  log_fail "MQTT nicht verbunden nach ${MQTT_WAIT_MAX}s"
  kill $WOKWI_PID 2>/dev/null || true
  wait $WOKWI_PID 2>/dev/null || true
  echo "MQTT_READY=false nach ${MQTT_WAIT_MAX}s" >> "$INJECT_LOG"
  {
    echo "----- Letzte 120 Zeilen Injection-Log -----"
    tail -n 120 "$INJECT_LOG" || true
    echo "----- Ende Injection-Log -----"
  } >> "$INJECT_LOG"
else
  sleep 2  # Buffer

  # MQTT-Injection: Sensor-Config
  INJECT_TOPIC="kaiser/god/esp/ESP_00000001/config"
  INJECT_PAYLOAD='{"sensors":[{"gpio":4,"sensor_type":"temp_ds18b20","sensor_name":"Gap1TestSensor","active":true,"raw_mode":true}],"actuators":[]}'

  log_info "Injiziere MQTT: $INJECT_TOPIC"
  echo "$(date -Iseconds) PUB $INJECT_TOPIC $INJECT_PAYLOAD" >> "$INJECT_MQTT_LOG"

  docker exec automationone-mqtt mosquitto_pub \
    -t "$INJECT_TOPIC" \
    -m "$INJECT_PAYLOAD" 2>&1 | tee -a "$INJECT_MQTT_LOG"

  # Wokwi abwarten
  wait $WOKWI_PID
  INJECT_EXIT=$?
  echo "Exit-Code: $INJECT_EXIT" >> "$INJECT_LOG"

  INJECT_SIGS=0
  check_signature "$INJECT_LOG" "MQTT connected" "MQTT verbunden" && ((INJECT_SIGS++)) || true
  check_signature "$INJECT_LOG" "ConfigResponse published" "Config verarbeitet" && ((INJECT_SIGS++)) || true

  if [ "$INJECT_EXIT" -eq 0 ] && [ "$INJECT_SIGS" -ge 2 ]; then
    log_pass "Injection Roundtrip BESTANDEN (Exit: $INJECT_EXIT, Signaturen: $INJECT_SIGS/2)"
    INJECT_PASS=true
  else
    log_fail "Injection Roundtrip FEHLGESCHLAGEN (Exit: $INJECT_EXIT, Signaturen: $INJECT_SIGS/2)"
  fi
fi

# --- Test 3: Stabilitaetstest ---
log_info ""
log_info "=== TEST 3: Stabilitaetstest ($REPEAT_COUNT Wiederholungen) ==="
STABILITY_PASSES=0

for run in $(seq 1 "$REPEAT_COUNT"); do
  log_info "--- Wiederholung $run/$REPEAT_COUNT ---"
  RUN_LOG="$SERIAL_LOG_DIR/stability_run${run}_${TIMESTAMP}.log"
  write_run_header "$RUN_LOG" "$BOOT_SCENARIO"

  timeout "$PROCESS_TIMEOUT" wokwi-cli . \
    --timeout "$WOKWI_TIMEOUT" \
    --scenario "$BOOT_SCENARIO" \
    >> "$RUN_LOG" 2>&1
  RUN_EXIT=$?
  echo "Exit-Code: $RUN_EXIT" >> "$RUN_LOG"

  RUN_SIGS=0
  check_signature "$RUN_LOG" "ESP32 Sensor Network" "Boot" && ((RUN_SIGS++)) || true
  check_signature "$RUN_LOG" "MQTT connected" "MQTT" && ((RUN_SIGS++)) || true
  check_signature "$RUN_LOG" "heartbeat" "Heartbeat" && ((RUN_SIGS++)) || true

  if [ "$RUN_EXIT" -eq 0 ] && [ "$RUN_SIGS" -ge 3 ]; then
    log_pass "Run $run: BESTANDEN"
    ((STABILITY_PASSES++))
  else
    log_fail "Run $run: FEHLGESCHLAGEN (Exit: $RUN_EXIT, Sigs: $RUN_SIGS/3)"
  fi
done

STABILITY_PASS=false
if [ "$STABILITY_PASSES" -eq "$REPEAT_COUNT" ]; then
  log_pass "Stabilitaetstest: $STABILITY_PASSES/$REPEAT_COUNT BESTANDEN"
  STABILITY_PASS=true
else
  log_fail "Stabilitaetstest: $STABILITY_PASSES/$REPEAT_COUNT bestanden (NICHT STABIL)"
fi

# --- Zusammenfassung ---
log_info ""
log_info "=== ZUSAMMENFASSUNG ==="
log_info "Smoke Connectivity:   $( [ "$SMOKE_PASS" = true ] && echo 'PASS' || echo 'FAIL' )"
log_info "Injection Roundtrip:  $( [ "$INJECT_PASS" = true ] && echo 'PASS' || echo 'FAIL' )"
log_info "Stabilitaet ($REPEAT_COUNT/$REPEAT_COUNT): $( [ "$STABILITY_PASS" = true ] && echo 'PASS' || echo 'FAIL' )"

# Report schreiben
REPORT="$REPORT_DIR/gap1_contract_test_${TIMESTAMP}.md"
cat > "$REPORT" << EOF
# Gap 1: MQTT Docker-Wokwi Contract Test Report

**Datum:** $(date -Iseconds)
**Branch:** $BRANCH
**Commit:** $COMMIT
**Testtyp:** $( [ "$SMOKE_ONLY" = true ] && echo "smoke-only" || echo "full-contract" )
**Wiederholungen:** $REPEAT_COUNT

## Ergebnisse

| Test | Status | Details |
|------|--------|---------|
| Smoke Connectivity | $( [ "$SMOKE_PASS" = true ] && echo 'PASS' || echo 'FAIL' ) | Boot + MQTT + Heartbeat |
| Injection Roundtrip | $( [ "$INJECT_PASS" = true ] && echo 'PASS' || echo 'FAIL' ) | Config-Push + ConfigResponse |
| Stabilitaet | $STABILITY_PASSES/$REPEAT_COUNT | $REPEAT_COUNT Wiederholungen Boot-Test |

## Signaturen

- Boot: \`ESP32 Sensor Network\`
- MQTT: \`MQTT connected\` / \`MQTT connected successfully\`
- Heartbeat: \`heartbeat\`
- Config: \`ConfigResponse published\`

## Log-Dateien

- Serial: \`$SERIAL_LOG_DIR/\`
- MQTT: \`$MQTT_LOG_DIR/\`
- Report: \`$REPORT\`

## Contract-Status

$( [ "$SMOKE_PASS" = true ] && [ "$INJECT_PASS" = true ] && [ "$STABILITY_PASS" = true ] && echo '**BESTANDEN** — Contract verifiziert.' || echo '**NICHT BESTANDEN** — Restblocker vorhanden.' )
EOF

log_info "Report geschrieben: $REPORT"

# Exit-Code
if [ "$SMOKE_PASS" = true ] && [ "$INJECT_PASS" = true ] && [ "$STABILITY_PASS" = true ]; then
  log_pass "=== Gap 1 Contract Test: GESAMT BESTANDEN ==="
  exit 0
else
  log_fail "=== Gap 1 Contract Test: GESAMT FEHLGESCHLAGEN ==="
  exit 1
fi
