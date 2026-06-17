#!/usr/bin/env bash
set -euo pipefail

# Reproduce and analyze ESP32 MQTT disconnects with:
# 1) automatic serial port detection
# 2) synchronized serial/broker/server captures
# 3) MQTT flood phases against the ESP command topic
# 4) timeline extraction for yesterday's disconnect events
#
# Usage examples:
#   ./scripts/hardware/repro_disconnect_esp32.sh
#   ./scripts/hardware/repro_disconnect_esp32.sh --esp-id ESP_EA5484 --capture-seconds 240
#   ACTUATOR_GPIOS="25,26,27" ./scripts/hardware/repro_disconnect_esp32.sh

ESP_ID="${ESP_ID:-ESP_EA5484}"
SERIAL_PORT="${SERIAL_PORT:-}"
BAUD="${BAUD:-115200}"
CAPTURE_SECONDS="${CAPTURE_SECONDS:-180}"
FLOOD_COUNT_FAST="${FLOOD_COUNT_FAST:-300}"
FLOOD_COUNT_SLOW="${FLOOD_COUNT_SLOW:-200}"
FLOOD_DELAY_SLOW_MS="${FLOOD_DELAY_SLOW_MS:-25}"
HEARTBEAT_INTERVAL_SECONDS="${HEARTBEAT_INTERVAL_SECONDS:-10}"
PROBE_BEFORE_FLOOD="${PROBE_BEFORE_FLOOD:-1}"
PROBE_VERIFY_TIMEOUT_SECONDS="${PROBE_VERIFY_TIMEOUT_SECONDS:-8}"
PROBE_SLEEP_BETWEEN_GPIOS_SECONDS="${PROBE_SLEEP_BETWEEN_GPIOS_SECONDS:-1}"
PROBE_POST_CONFIG_SETTLE_SECONDS="${PROBE_POST_CONFIG_SETTLE_SECONDS:-6}"
MQTT_ONLINE_WAIT_SECONDS="${MQTT_ONLINE_WAIT_SECONDS:-30}"
DIRECT_PROBE_MODE="${DIRECT_PROBE_MODE:-0}"
DIRECT_PROBE_ONLY_EXIT="${DIRECT_PROBE_ONLY_EXIT:-0}"
LOAD_FAST_START_PCT="${LOAD_FAST_START_PCT:-20}"
LOAD_SLOW_START_PCT="${LOAD_SLOW_START_PCT:-55}"
EARLY_SERIAL_MIN_BYTES="${EARLY_SERIAL_MIN_BYTES:-16}"
EARLY_SERIAL_CHECK_REQUIRED="${EARLY_SERIAL_CHECK_REQUIRED:-1}"
EARLY_SERIAL_GRACE_SECONDS="${EARLY_SERIAL_GRACE_SECONDS:-12}"
EARLY_SERIAL_RECHECK_INTERVAL_SECONDS="${EARLY_SERIAL_RECHECK_INTERVAL_SECONDS:-3}"
EARLY_SERIAL_MAX_WARMUP_SECONDS="${EARLY_SERIAL_MAX_WARMUP_SECONDS:-45}"
KAISER_ID="${KAISER_ID:-god}"
GPIO="${GPIO:-25}"
ACTUATOR_GPIOS="${ACTUATOR_GPIOS:-}"
RUN_PROFILE="${RUN_PROFILE:-default}"
DEBUG_LOG_PATH="${DEBUG_LOG_PATH:-/home/robin/.cursor/debug-6dd16c.log}"
DEBUG_SESSION_ID="${DEBUG_SESSION_ID:-6dd16c}"
FRONTEND_DEVICE_SAVE_CMD="${FRONTEND_DEVICE_SAVE_CMD:-}"
FRONTEND_API_BASE_URL="${FRONTEND_API_BASE_URL:-http://localhost:8000}"
FRONTEND_USERNAME="${FRONTEND_USERNAME:-}"
FRONTEND_PASSWORD="${FRONTEND_PASSWORD:-}"
FRONTEND_USERNAME_FALLBACK="${FRONTEND_USERNAME_FALLBACK:-Robin}"
FRONTEND_PASSWORD_FALLBACK="${FRONTEND_PASSWORD_FALLBACK:-AutoOne2026!}"
FRONTEND_ACTUATOR_SAVE_PAYLOAD_JSON="${FRONTEND_ACTUATOR_SAVE_PAYLOAD_JSON:-}"
POST_FLASH_PAUSE_SECONDS="${POST_FLASH_PAUSE_SECONDS:-3}"
SKIP_FRONTEND_ACTUATOR_SAVE="${SKIP_FRONTEND_ACTUATOR_SAVE:-0}"
ACTUATOR_GPIOS_EFFECTIVE=""
TOPIC_CMD=""
declare -a ACTUATOR_GPIO_LIST=()
declare -a TOPIC_CMD_LIST=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --esp-id)
      ESP_ID="$2"
      shift 2
      ;;
    --serial-port)
      SERIAL_PORT="$2"
      shift 2
      ;;
    --baud)
      BAUD="$2"
      shift 2
      ;;
    --capture-seconds)
      CAPTURE_SECONDS="$2"
      shift 2
      ;;
    --flood-fast)
      FLOOD_COUNT_FAST="$2"
      shift 2
      ;;
    --flood-slow)
      FLOOD_COUNT_SLOW="$2"
      shift 2
      ;;
    --flood-delay-ms)
      FLOOD_DELAY_SLOW_MS="$2"
      shift 2
      ;;
    --gpio)
      GPIO="$2"
      shift 2
      ;;
    --profile)
      RUN_PROFILE="$2"
      shift 2
      ;;
    *)
      echo "Unbekanntes Argument: $1" >&2
      exit 1
      ;;
  esac
done

resolve_actuator_targets() {
  local source_raw="${ACTUATOR_GPIOS}"
  local source_trimmed="${source_raw//[[:space:]]/}"
  local entry=""
  local cleaned=""
  declare -A seen=()
  ACTUATOR_GPIO_LIST=()
  TOPIC_CMD_LIST=()

  if [[ -z "${source_trimmed}" ]]; then
    source_raw="${GPIO}"
  fi

  IFS=',' read -r -a entries <<<"${source_raw}"
  for entry in "${entries[@]}"; do
    cleaned="${entry//[[:space:]]/}"
    if [[ -z "${cleaned}" ]]; then
      continue
    fi
    if [[ ! "${cleaned}" =~ ^[0-9]+$ ]]; then
      echo "Warnung: Ungueltiger GPIO-Eintrag ignoriert: '${entry}'" >&2
      continue
    fi
    if [[ -n "${seen[${cleaned}]:-}" ]]; then
      continue
    fi
    seen["${cleaned}"]=1
    ACTUATOR_GPIO_LIST+=("${cleaned}")
  done

  if (( ${#ACTUATOR_GPIO_LIST[@]} == 0 )); then
    if [[ "${GPIO}" =~ ^[0-9]+$ ]]; then
      ACTUATOR_GPIO_LIST=("${GPIO}")
    else
      echo "Keine gueltigen Aktor-GPIOs konfiguriert (GPIO='${GPIO}', ACTUATOR_GPIOS='${ACTUATOR_GPIOS}')." >&2
      exit 1
    fi
  fi

  ACTUATOR_GPIOS_EFFECTIVE="$(IFS=,; echo "${ACTUATOR_GPIO_LIST[*]}")"
  for cleaned in "${ACTUATOR_GPIO_LIST[@]}"; do
    TOPIC_CMD_LIST+=("kaiser/${KAISER_ID}/esp/${ESP_ID}/actuator/${cleaned}/command")
  done
  TOPIC_CMD="${TOPIC_CMD_LIST[0]}"
}

detect_serial_port() {
  if [[ -n "${SERIAL_PORT}" ]]; then
    echo "${SERIAL_PORT}"
    return 0
  fi

  if [[ -d /dev/serial/by-id ]]; then
    local first_link
    first_link="$(ls -1 /dev/serial/by-id/* 2>/dev/null | head -n 1 || true)"
    if [[ -n "${first_link}" ]]; then
      readlink -f "${first_link}"
      return 0
    fi
  fi

  if [[ -e /dev/ttyUSB0 ]]; then
    echo "/dev/ttyUSB0"
    return 0
  fi
  if [[ -e /dev/ttyACM0 ]]; then
    echo "/dev/ttyACM0"
    return 0
  fi

  return 1
}

SERIAL_PORT="$(detect_serial_port || true)"
if [[ -z "${SERIAL_PORT}" ]]; then
  echo "Kein ESP-Serial-Port gefunden. Bitte --serial-port setzen." >&2
  exit 1
fi

if [[ ! -e "${SERIAL_PORT}" ]]; then
  echo "Serial-Port existiert nicht: ${SERIAL_PORT}" >&2
  exit 1
fi

RUN_ID="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="logs/current/hardware/disconnect-repro/${RUN_ID}"
mkdir -p "${OUT_DIR}"

SERIAL_LOG="${OUT_DIR}/esp32_serial.log"
BROKER_LOG="${OUT_DIR}/mqtt_broker.log"
SERVER_LOG="${OUT_DIR}/server.log"
YESTERDAY_JSON="${OUT_DIR}/yesterday_disconnects.json"
SUMMARY_MD="${OUT_DIR}/SUMMARY.md"
RUN_META="${OUT_DIR}/run_meta.txt"
RUN_SUMMARY_JSON="${OUT_DIR}/run_summary.json"

resolve_actuator_targets

# region agent log
debug_log() {
  local hypothesis_id="$1"
  local message="$2"
  local data_json="${3:-{}}"
  python3 - "$DEBUG_LOG_PATH" "$DEBUG_SESSION_ID" "$RUN_ID" "$hypothesis_id" "$message" "$data_json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
session_id = sys.argv[2]
run_id = sys.argv[3]
hypothesis_id = sys.argv[4]
message = sys.argv[5]
raw_data = sys.argv[6]

try:
    data = json.loads(raw_data)
except Exception:
    data = {"raw": raw_data}

entry = {
    "sessionId": session_id,
    "runId": run_id,
    "hypothesisId": hypothesis_id,
    "location": "scripts/hardware/repro_disconnect_esp32.sh:debug_log",
    "message": message,
    "data": data,
    "timestamp": __import__("time").time_ns() // 1_000_000,
}
with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=True) + "\n")
PY
}
# endregion

json_bool() {
  if [[ "$1" -eq 0 ]]; then
    echo "false"
  else
    echo "true"
  fi
}

run_frontend_save() {
  local save_name="$1"
  local save_cmd="$2"
  local hypothesis_id="$3"
  local save_output=""
  local save_exit=0
  local http_code=""
  local auth_or_syntax_error=0
  local has_http_code=0
  local http_ok=1
  local exit_ok=1

  # region agent log
  debug_log "${hypothesis_id}" "frontend_save_start" "{\"save\":\"${save_name}\"}"
  # endregion

  if ! save_output="$(bash -lc "${save_cmd}" 2>&1)"; then
    save_exit=$?
  fi

  if [[ "${save_output}" =~ ([0-9]{3})[[:space:]]*$ ]]; then
    http_code="${BASH_REMATCH[1]}"
    has_http_code=1
  fi

  if [[ "${save_output}" == *"SyntaxError"* || "${save_output}" == *"Unauthorized"* || "${http_code}" == "401" ]]; then
    auth_or_syntax_error=1
  fi

  if [[ "${save_exit}" -ne 0 ]]; then
    exit_ok=0
  fi

  if [[ "${has_http_code}" -eq 1 && ! "${http_code}" =~ ^2[0-9][0-9]$ ]]; then
    http_ok=0
  fi

  # region agent log
  debug_log "${hypothesis_id}" "frontend_save_result" "{\"save\":\"${save_name}\",\"exit_code\":${save_exit},\"has_http_code\":$(json_bool "${has_http_code}"),\"http_code\":\"${http_code}\",\"http_ok\":$(json_bool "${http_ok}"),\"exit_ok\":$(json_bool "${exit_ok}"),\"auth_or_syntax_error\":$(json_bool "${auth_or_syntax_error}"),\"output_len\":${#save_output}}"
  # endregion

  if [[ "${exit_ok}" -ne 1 || "${http_ok}" -ne 1 ]]; then
    echo "${save_output}" >&2
    return 1
  fi

  if [[ -n "${save_output}" ]]; then
    echo "${save_output}"
  fi
  return 0
}

run_frontend_actuator_save_api() {
  local hypothesis_id="$1"
  local actuator_gpio="$2"
  local api_result=""
  local api_exit=0
  local api_ok=""
  local login_status=""
  local save_status=""
  local error_text=""
  local payload_override_set=0

  if [[ -n "${FRONTEND_ACTUATOR_SAVE_PAYLOAD_JSON}" ]]; then
    payload_override_set=1
  fi

  # region agent log
  debug_log "${hypothesis_id}" "frontend_actuator_api_save_start" "{\"base_url\":\"${FRONTEND_API_BASE_URL}\",\"esp_id\":\"${ESP_ID}\",\"gpio\":${actuator_gpio},\"payload_override_set\":$(json_bool "${payload_override_set}")}"
  # endregion

  if ! api_result="$(
    python3 - "$FRONTEND_API_BASE_URL" "$FRONTEND_USERNAME" "$FRONTEND_PASSWORD" "$ESP_ID" "$actuator_gpio" "$FRONTEND_ACTUATOR_SAVE_PAYLOAD_JSON" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base_url, username, password, esp_id, gpio_raw, payload_override_raw = sys.argv[1:7]
gpio = int(gpio_raw)

def post_json(url: str, payload: dict, token: str | None = None):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body

result = {"ok": False, "login_status": 0, "save_status": 0, "error": ""}

login_status, login_body = post_json(
    f"{base_url}/api/v1/auth/login",
    {"username": username, "password": password},
)
result["login_status"] = int(login_status or 0)
if not (200 <= login_status < 300):
    result["error"] = "login_failed"
    print(json.dumps(result, ensure_ascii=True))
    sys.exit(0)

try:
    token = json.loads(login_body)["tokens"]["access_token"]
except Exception:
    result["error"] = "token_parse_failed"
    print(json.dumps(result, ensure_ascii=True))
    sys.exit(0)

if payload_override_raw:
    try:
        actuator_payload = json.loads(payload_override_raw)
    except Exception:
        result["error"] = "payload_override_invalid_json"
        print(json.dumps(result, ensure_ascii=True))
        sys.exit(0)
    if not isinstance(actuator_payload, dict):
        result["error"] = "payload_override_not_object"
        print(json.dumps(result, ensure_ascii=True))
        sys.exit(0)
    actuator_payload.setdefault("esp_id", esp_id)
    actuator_payload["gpio"] = gpio
else:
    actuator_payload = {
        "esp_id": esp_id,
        "gpio": gpio,
        "actuator_type": "relay",
        "hardware_type": "relay",
        "name": "",
        "enabled": True,
        "max_runtime_seconds": 3600,
        "cooldown_seconds": 30,
        "metadata": {"created_via": "disconnect_repro_script"},
        "fail_safe_on_disconnect": None,
    }

save_status, save_body = post_json(
    f"{base_url}/api/v1/actuators/{esp_id}/{gpio}",
    actuator_payload,
    token=token,
)
result["save_status"] = int(save_status or 0)
if 200 <= save_status < 300:
    result["ok"] = True
else:
    result["error"] = "actuator_save_failed"

print(json.dumps(result, ensure_ascii=True))
PY
  )"; then
    api_exit=$?
  fi

  api_ok="$(python3 -c 'import json,sys; print("true" if json.loads(sys.stdin.read() or "{}").get("ok") else "false")' <<<"${api_result}" 2>/dev/null || echo "false")"
  login_status="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("login_status",0))' <<<"${api_result}" 2>/dev/null || echo "0")"
  save_status="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("save_status",0))' <<<"${api_result}" 2>/dev/null || echo "0")"
  error_text="$(python3 -c 'import json,sys; print(str(json.loads(sys.stdin.read() or "{}").get("error","")))' <<<"${api_result}" 2>/dev/null || echo "parse_error")"

  # region agent log
  debug_log "${hypothesis_id}" "frontend_actuator_api_save_result" "{\"gpio\":${actuator_gpio},\"exit_code\":${api_exit},\"login_status\":${login_status},\"save_status\":${save_status},\"ok\":${api_ok},\"error\":\"${error_text}\"}"
  # endregion

  if [[ "${api_exit}" -ne 0 || "${api_ok}" != "true" ]]; then
    echo "Actuator-API-Save fehlgeschlagen fuer GPIO ${actuator_gpio} (login=${login_status}, save=${save_status}, error=${error_text})." >&2
    return 1
  fi

  return 0
}

resolve_frontend_credentials() {
  local source="explicit_env"

  if [[ -z "${FRONTEND_USERNAME}" && -n "${AUTOONE_API_USERNAME:-}" ]]; then
    FRONTEND_USERNAME="${AUTOONE_API_USERNAME}"
    source="autoone_api_env"
  fi
  if [[ -z "${FRONTEND_PASSWORD}" && -n "${AUTOONE_API_PASSWORD:-}" ]]; then
    FRONTEND_PASSWORD="${AUTOONE_API_PASSWORD}"
    source="autoone_api_env"
  fi

  if [[ -z "${FRONTEND_USERNAME}" ]]; then
    FRONTEND_USERNAME="${FRONTEND_USERNAME_FALLBACK}"
    source="fallback_defaults"
  fi
  if [[ -z "${FRONTEND_PASSWORD}" ]]; then
    FRONTEND_PASSWORD="${FRONTEND_PASSWORD_FALLBACK}"
    source="fallback_defaults"
  fi

  local username_set=0
  local password_set=0
  if [[ -n "${FRONTEND_USERNAME}" ]]; then
    username_set=1
  fi
  if [[ -n "${FRONTEND_PASSWORD}" ]]; then
    password_set=1
  fi
  # region agent log
  debug_log "H58" "frontend_credentials_resolved" "{\"source\":\"${source}\",\"username_set\":$(json_bool "${username_set}"),\"password_set\":$(json_bool "${password_set}")}"
  # endregion
}

is_capture_exit_ok() {
  local exit_code="$1"
  # `timeout` returns 124 when the capture duration elapsed normally.
  [[ "${exit_code}" -eq 0 || "${exit_code}" -eq 124 ]]
}

assert_capture_running() {
  local name="$1"
  local pid="$2"
  local log_path="$3"

  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "Capture '${name}' ist bereits beendet (pid=${pid}). Run wird abgebrochen." >&2
    echo "Log: ${log_path}" >&2
    # region agent log
    debug_log "H90" "capture_process_died_early" "{\"capture\":\"${name}\",\"pid\":${pid},\"log\":\"${log_path}\"}"
    # endregion
    exit 1
  fi
}

wait_for_capture() {
  local name="$1"
  local pid="$2"
  local log_path="$3"
  local exit_code=0

  if ! wait "${pid}"; then
    exit_code=$?
  fi

  if is_capture_exit_ok "${exit_code}"; then
    return 0
  fi

  echo "Capture '${name}' ist mit Exit-Code ${exit_code} fehlgeschlagen." >&2
  echo "Log: ${log_path}" >&2
  # region agent log
  debug_log "H91" "capture_process_failed" "{\"capture\":\"${name}\",\"pid\":${pid},\"exit_code\":${exit_code},\"log\":\"${log_path}\"}"
  # endregion
  exit 1
}

heartbeat_sleep() {
  local total_seconds="$1"
  local label="$2"
  local remaining="${total_seconds}"

  if (( total_seconds <= 0 )); then
    return 0
  fi

  while (( remaining > 0 )); do
    local chunk="${HEARTBEAT_INTERVAL_SECONDS}"
    if (( chunk <= 0 )); then
      chunk=1
    fi
    if (( chunk > remaining )); then
      chunk="${remaining}"
    fi
    echo "[Heartbeat] ${label} | verbleibend: ${remaining}s"
    sleep "${chunk}"
    remaining=$((remaining - chunk))
  done
}

serial_log_bytes() {
  if [[ ! -f "${SERIAL_LOG}" ]]; then
    echo "0"
    return 0
  fi
  wc -c < "${SERIAL_LOG}" | tr -d '[:space:]'
}

broker_esp_event_count() {
  if [[ ! -f "${BROKER_LOG}" ]]; then
    echo "0"
    return 0
  fi
  python3 - "${BROKER_LOG}" "${ESP_ID}" <<'PY'
import re
import sys
from pathlib import Path

broker_log = Path(sys.argv[1])
esp_id = sys.argv[2]
line_rx = re.compile(
    rf"(New client connected .* as {re.escape(esp_id)}\b|Client {re.escape(esp_id)} .* disconnected)",
    re.IGNORECASE,
)
count = 0
for line in broker_log.read_text(encoding="utf-8", errors="ignore").splitlines():
    if line_rx.search(line):
        count += 1
print(count)
PY
}

send_fast_flood() {
  echo "Phase A: schneller Flood (${FLOOD_COUNT_FAST} msgs, ohne Delay, GPIOs=${ACTUATOR_GPIOS_EFFECTIVE})"
  python3 - "$FLOOD_COUNT_FAST" "$ACTUATOR_GPIOS_EFFECTIVE" "$KAISER_ID" "$ESP_ID" <<'PY'
import sys

n = int(sys.argv[1])
gpios = [g.strip() for g in sys.argv[2].split(",") if g.strip()]
kaiser_id = sys.argv[3]
esp_id = sys.argv[4]
preview_count = min(n, len(gpios) * 2, 12)
for i in range(1, preview_count + 1):
    gpio = gpios[(i - 1) % len(gpios)]
    topic = f"kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command"
    print(f"  RR-Preview fast msg#{i}: gpio={gpio} topic={topic}")
PY
  python3 - "$FLOOD_COUNT_FAST" "$ACTUATOR_GPIOS_EFFECTIVE" "$KAISER_ID" "$ESP_ID" <<'PY' | docker compose exec -T mqtt-broker sh -lc 'while IFS="$(printf "\t")" read -r topic payload; do [ -z "$topic" ] && continue; mosquitto_pub -h localhost -p 1883 -t "$topic" -q 1 -m "$payload"; done'
import json
import sys

n = int(sys.argv[1])
gpios = [g.strip() for g in sys.argv[2].split(",") if g.strip()]
kaiser_id = sys.argv[3]
esp_id = sys.argv[4]
for i in range(1, n + 1):
    cmd = "ON" if i % 2 else "OFF"
    gpio = gpios[(i - 1) % len(gpios)]
    topic = f"kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command"
    payload = {
        "command": cmd,
        "request_id": f"repro-fast-{i}",
        "correlation_id": "repro-fast",
        "source": "disconnect_repro_script",
        "target_gpio": int(gpio),
    }
    print(f"{topic}\t{json.dumps(payload, separators=(',', ':'))}")
PY
}

send_slow_flood() {
  echo "Phase B: langsamer Flood (${FLOOD_COUNT_SLOW} msgs, ${FLOOD_DELAY_SLOW_MS}ms Delay, GPIOs=${ACTUATOR_GPIOS_EFFECTIVE})"
  python3 - "$FLOOD_COUNT_SLOW" "$ACTUATOR_GPIOS_EFFECTIVE" "$KAISER_ID" "$ESP_ID" <<'PY'
import sys

n = int(sys.argv[1])
gpios = [g.strip() for g in sys.argv[2].split(",") if g.strip()]
kaiser_id = sys.argv[3]
esp_id = sys.argv[4]
preview_count = min(n, len(gpios) * 2, 12)
for i in range(1, preview_count + 1):
    gpio = gpios[(i - 1) % len(gpios)]
    topic = f"kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command"
    print(f"  RR-Preview slow msg#{i}: gpio={gpio} topic={topic}")
PY
  python3 - "$FLOOD_COUNT_SLOW" "$FLOOD_DELAY_SLOW_MS" "$ACTUATOR_GPIOS_EFFECTIVE" "$KAISER_ID" "$ESP_ID" <<'PY' | docker compose exec -T mqtt-broker sh -lc 'while IFS="$(printf "\t")" read -r topic payload; do [ -z "$topic" ] && continue; mosquitto_pub -h localhost -p 1883 -t "$topic" -q 1 -m "$payload"; done'
import json
import sys
import time

n = int(sys.argv[1])
delay_ms = int(sys.argv[2])
gpios = [g.strip() for g in sys.argv[3].split(",") if g.strip()]
kaiser_id = sys.argv[4]
esp_id = sys.argv[5]
delay_s = delay_ms / 1000.0

for i in range(1, n + 1):
    cmd = "ON" if i % 2 else "OFF"
    gpio = gpios[(i - 1) % len(gpios)]
    topic = f"kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command"
    payload = {
        "command": cmd,
        "request_id": f"repro-slow-{i}",
        "correlation_id": "repro-slow",
        "source": "disconnect_repro_script",
        "target_gpio": int(gpio),
    }
    print(f"{topic}\t{json.dumps(payload, separators=(',', ':'))}")
    time.sleep(delay_s)
PY
}

run_actuator_probe() {
  local timeout_s="${PROBE_VERIFY_TIMEOUT_SECONDS}"
  local sleep_between="${PROBE_SLEEP_BETWEEN_GPIOS_SECONDS}"
  local gpio=""
  local topic=""
  local payload=""
  local probe_ok=0
  local probe_failed=0
  local probe_output=""
  local probe_rc=0
  local probe_attempt=0
  local max_probe_attempts=3
  local probe_tap_log=""
  local probe_tap_pid=0
  local probe_mqtt_log=""
  local probe_mqtt_pid=0
  local status_topic=""
  local response_topic=""
  local mqtt_hit=0
  local probe_tap_bytes=0
  local probe_tap_merged=0

  if [[ "${PROBE_BEFORE_FLOOD}" != "1" ]]; then
    echo "Probe vor Flood deaktiviert (PROBE_BEFORE_FLOOD=${PROBE_BEFORE_FLOOD})."
    return 0
  fi

  if (( timeout_s <= 0 )); then
    timeout_s=1
  fi
  if (( sleep_between < 0 )); then
    sleep_between=0
  fi

  echo "Probe: Prüfe Aktor-Ingress/Execute vor Last (Timeout ${timeout_s}s je GPIO)..."

  for gpio in "${ACTUATOR_GPIO_LIST[@]}"; do
    topic="kaiser/${KAISER_ID}/esp/${ESP_ID}/actuator/${gpio}/command"
    status_topic="kaiser/${KAISER_ID}/esp/${ESP_ID}/actuator/${gpio}/status"
    response_topic="kaiser/${KAISER_ID}/esp/${ESP_ID}/actuator/${gpio}/response"
    payload="{\"command\":\"ON\",\"request_id\":\"probe-${RUN_ID}-${gpio}\",\"correlation_id\":\"probe-${RUN_ID}\",\"source\":\"disconnect_repro_probe\",\"target_gpio\":${gpio}}"

    probe_output="missing"
    probe_rc=4

    for ((probe_attempt=1; probe_attempt<=max_probe_attempts; probe_attempt++)); do
      echo "  Probe-Send GPIO ${gpio} (Versuch ${probe_attempt}/${max_probe_attempts}) -> ${topic}"
      probe_tap_log="$(mktemp)"
      timeout "${timeout_s}"s sh -c "cat \"${SERIAL_PORT}\"" 2>/dev/null | tr -d '\r' > "${probe_tap_log}" &
      probe_tap_pid=$!
      probe_mqtt_log="$(mktemp)"
      timeout "${timeout_s}"s docker compose exec -T mqtt-broker sh -lc \
        "mosquitto_sub -h localhost -p 1883 -v -W ${timeout_s} -C 2 -t '${status_topic}' -t '${response_topic}'" \
        > "${probe_mqtt_log}" 2>/dev/null &
      probe_mqtt_pid=$!
      sleep 1
      docker compose exec -T mqtt-broker sh -lc "mosquitto_pub -h localhost -p 1883 -t '${topic}' -q 1 -m '${payload}'" >/dev/null
      wait "${probe_tap_pid}" 2>/dev/null || true
      wait "${probe_mqtt_pid}" 2>/dev/null || true

      probe_tap_bytes="$(wc -c < "${probe_tap_log}" | tr -d '[:space:]')"
      if [[ -z "${probe_tap_bytes}" ]]; then
        probe_tap_bytes=0
      fi
      probe_tap_merged=0
      if (( probe_tap_bytes > 0 )); then
        awk '{ cmd="date -Iseconds"; cmd | getline ts; close(cmd); print "[" ts "] [PROBE-TAP] " $0; fflush(); }' "${probe_tap_log}" >> "${SERIAL_LOG}"
        probe_tap_merged=1
      fi

      probe_rc=0
      probe_output="$(python3 - "${SERIAL_LOG}" "${probe_tap_log}" "${gpio}" <<'PY'
import re
import sys
from pathlib import Path

main_log = Path(sys.argv[1])
tap_log = Path(sys.argv[2])
gpio = sys.argv[3]

ingress_rx = re.compile(rf"actuator/{re.escape(gpio)}/command", re.IGNORECASE)
exec_ok_rx = re.compile(
    rf"(PumpActuator GPIO {re.escape(gpio)} (ON|OFF)|Actuator command executed: GPIO {re.escape(gpio)} |actuator execute result ok=1)",
    re.IGNORECASE,
)
unconfigured_rx = re.compile(rf"No actuator configured on GPIO {re.escape(gpio)}", re.IGNORECASE)
disconnect_rx = re.compile(r"MQTT_EVENT_DISCONNECTED|tls timeout|processPublishQueue skipped disconnected", re.IGNORECASE)

ingress_hit = False
exec_hit = False
unconfigured_hit = False
disconnect_hit = False

main_lines = main_log.read_text(encoding="utf-8", errors="ignore").splitlines() if main_log.exists() else []
tap_lines = tap_log.read_text(encoding="utf-8", errors="ignore").splitlines() if tap_log.exists() else []
lines = main_lines[-400:] + tap_lines[-400:]

for line in lines:
    if ingress_rx.search(line):
        ingress_hit = True
    if exec_ok_rx.search(line):
        exec_hit = True
    if unconfigured_rx.search(line):
        unconfigured_hit = True
    if disconnect_rx.search(line):
        disconnect_hit = True

if ingress_hit and exec_hit:
    print("ok")
    sys.exit(0)
if unconfigured_hit:
    print("unconfigured")
    sys.exit(2)

if disconnect_hit and not ingress_hit:
    print("offline")
    sys.exit(5)
if ingress_hit:
    print("ingress_only")
    sys.exit(3)
print("missing")
sys.exit(4)
PY
)" || probe_rc=$?

      mqtt_hit="$(python3 - "${probe_mqtt_log}" "${status_topic}" "${response_topic}" <<'PY'
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
status_topic = sys.argv[2]
response_topic = sys.argv[3]
text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
print(1 if status_topic in text or response_topic in text else 0)
PY
)"
      # region agent log
      debug_log "H73" "probe_attempt_evidence" "{\"gpio\":${gpio},\"attempt\":${probe_attempt},\"serial_probe\":\"${probe_output}\",\"serial_rc\":${probe_rc},\"mqtt_hit\":${mqtt_hit},\"probe_tap_bytes\":${probe_tap_bytes},\"probe_tap_merged\":$(json_bool "${probe_tap_merged}")}"
      # endregion

      rm -f "${probe_tap_log}" 2>/dev/null || true
      probe_tap_log=""
      rm -f "${probe_mqtt_log}" 2>/dev/null || true
      probe_mqtt_log=""

      if [[ "${probe_rc}" -eq 0 && "${probe_output}" == "ok" ]]; then
        break
      fi
      if [[ "${mqtt_hit}" == "1" ]]; then
        probe_output="mqtt_only"
        probe_rc=0
        break
      fi
      if [[ "${probe_output}" == "unconfigured" ]]; then
        break
      fi
      if [[ "${probe_output}" == "offline" ]]; then
        break
      fi
      sleep 1
    done

    if [[ "${probe_rc}" -eq 0 && "${probe_output}" == "ok" ]]; then
      echo "  Probe OK GPIO ${gpio}: command ingress + execute bestätigt."
      probe_ok=$((probe_ok + 1))
    elif [[ "${probe_output}" == "mqtt_only" ]]; then
      echo "  Probe OK GPIO ${gpio}: command via MQTT status/response bestätigt (Serial ohne Ingress)." >&2
      probe_ok=$((probe_ok + 1))
    elif [[ "${probe_output}" == "ingress_only" ]]; then
      echo "  Probe WARN GPIO ${gpio}: command ingress erkannt, execute-log nicht eindeutig." >&2
      probe_ok=$((probe_ok + 1))
    else
      probe_failed=$((probe_failed + 1))
      if [[ "${probe_output}" == "unconfigured" ]]; then
        echo "  Probe FEHLER GPIO ${gpio}: Aktor nicht konfiguriert." >&2
      elif [[ "${probe_output}" == "offline" ]]; then
        echo "  Probe FEHLER GPIO ${gpio}: ESP aktuell MQTT-offline (disconnect/tls-timeout)." >&2
      elif [[ "${probe_output}" == "ingress_only" ]]; then
        echo "  Probe FEHLER GPIO ${gpio}: Command ingress ja, Execute nein." >&2
      else
        echo "  Probe FEHLER GPIO ${gpio}: kein Command-Ingress im Serial-Log." >&2
      fi
    fi

    probe_rc=0
    if (( sleep_between > 0 )); then
      sleep "${sleep_between}"
    fi
  done

  if (( probe_ok == 0 )); then
    echo "Probe fehlgeschlagen: Kein Ziel-GPIO wurde ausführbar bestätigt. Lauf wird abgebrochen." >&2
    return 1
  fi

  if (( probe_failed > 0 )); then
    echo "Warnung: Probe teilweise fehlgeschlagen (${probe_failed} fehlerhaft, ${probe_ok} ok)." >&2
  fi

  return 0
}

wait_for_mqtt_online_before_probe() {
  local wait_s="${MQTT_ONLINE_WAIT_SECONDS}"
  local elapsed=0
  local serial_ready=0
  local broker_ready=0
  local broker_global_ready=0
  local sleep_step=2

  if (( wait_s <= 0 )); then
    return 0
  fi

  echo "Warte auf MQTT-Online vor Probe (max ${wait_s}s)..."
  while (( elapsed < wait_s )); do
    serial_ready="$(python3 - "${SERIAL_LOG}" <<'PY'
import re
import sys
from pathlib import Path
p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
rx = re.compile(r"MQTT_EVENT_CONNECTED|heartbeat ack accepted|mqtt_connected=1", re.IGNORECASE)
print(1 if rx.search(text) else 0)
PY
)"
    broker_ready="$(python3 - "${BROKER_LOG}" "${ESP_ID}" <<'PY'
import re
import sys
from pathlib import Path
p = Path(sys.argv[1])
esp_id = sys.argv[2]
text = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
rx = re.compile(rf"New client connected .* as {re.escape(esp_id)}\b", re.IGNORECASE)
print(1 if rx.search(text) else 0)
PY
)"
    broker_global_ready="$(docker logs --since 10m automationone-mqtt 2>&1 | python3 - "${ESP_ID}" <<'PY'
import re
import sys

esp_id = sys.argv[1]
connect_rx = re.compile(rf"New client connected .* as {re.escape(esp_id)}\b", re.IGNORECASE)
disconnect_rx = re.compile(rf"Client {re.escape(esp_id)} .* disconnected", re.IGNORECASE)
state = "unknown"
for line in sys.stdin:
    if connect_rx.search(line):
        state = "connected"
    if disconnect_rx.search(line):
        state = "disconnected"
print(1 if state == "connected" else 0)
PY
)"
    if [[ "${serial_ready}" == "1" || "${broker_ready}" == "1" || "${broker_global_ready}" == "1" ]]; then
      echo "MQTT-Online erkannt (serial=${serial_ready}, broker_runlog=${broker_ready}, broker_global=${broker_global_ready})."
      return 0
    fi
    sleep "${sleep_step}"
    elapsed=$((elapsed + sleep_step))
  done

  echo "MQTT-Online nicht innerhalb ${wait_s}s erkannt (serial=${serial_ready}, broker_runlog=${broker_ready}, broker_global=${broker_global_ready})." >&2
  return 1
}

run_direct_probe_sequence() {
  local timeout_s="${PROBE_VERIFY_TIMEOUT_SECONDS}"
  local sleep_between="${PROBE_SLEEP_BETWEEN_GPIOS_SECONDS}"
  local gpio=""
  local topic=""
  local payload=""
  local probe_log=""
  local ok_count=0
  local fail_count=0

  if (( timeout_s <= 0 )); then
    timeout_s=1
  fi

  echo "Direct-Probe: exklusiver Serial-Check (ein Reader) für GPIOs ${ACTUATOR_GPIOS_EFFECTIVE}"

  for gpio in "${ACTUATOR_GPIO_LIST[@]}"; do
    topic="kaiser/${KAISER_ID}/esp/${ESP_ID}/actuator/${gpio}/command"
    payload="{\"command\":\"ON\",\"request_id\":\"direct-probe-${RUN_ID}-${gpio}\",\"correlation_id\":\"direct-probe-${RUN_ID}\",\"source\":\"disconnect_repro_direct_probe\",\"target_gpio\":${gpio}}"
    probe_log="${OUT_DIR}/direct_probe_gpio_${gpio}.log"

    echo "  Direct-Probe GPIO ${gpio} -> ${topic}"
    stty -F "${SERIAL_PORT}" "${BAUD}" cs8 -cstopb -parenb -ixon -ixoff -echo raw || true
    timeout "${timeout_s}"s sh -c "cat \"${SERIAL_PORT}\"" 2>/dev/null | tr -d '\r' > "${probe_log}" &
    probe_pid=$!
    sleep 1
    docker compose exec -T mqtt-broker sh -lc "mosquitto_pub -h localhost -p 1883 -t '${topic}' -q 1 -m '${payload}'" >/dev/null
    wait "${probe_pid}" 2>/dev/null || true

    if python3 - "${probe_log}" "${gpio}" <<'PY'
import re
import sys
from pathlib import Path

log = Path(sys.argv[1])
gpio = sys.argv[2]
text = log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""

ingress = re.search(rf"actuator/{re.escape(gpio)}/command", text, re.IGNORECASE) is not None
exec_ok = re.search(
    rf"(Actuator command executed: GPIO {re.escape(gpio)}|actuator execute result ok=1|PumpActuator GPIO {re.escape(gpio)} (ON|OFF))",
    text,
    re.IGNORECASE,
) is not None
unconfigured = re.search(rf"No actuator configured on GPIO {re.escape(gpio)}", text, re.IGNORECASE) is not None

if ingress and exec_ok:
    sys.exit(0)
if unconfigured:
    sys.exit(2)
if ingress:
    sys.exit(3)
sys.exit(4)
PY
    then
      echo "  Direct-Probe OK GPIO ${gpio}: ingress+execute bestätigt."
      ok_count=$((ok_count + 1))
    else
      rc=$?
      fail_count=$((fail_count + 1))
      if [[ "${rc}" -eq 2 ]]; then
        echo "  Direct-Probe FEHLER GPIO ${gpio}: Aktor nicht konfiguriert." >&2
      elif [[ "${rc}" -eq 3 ]]; then
        echo "  Direct-Probe FEHLER GPIO ${gpio}: ingress erkannt, execute fehlt." >&2
      else
        echo "  Direct-Probe FEHLER GPIO ${gpio}: kein ingress erkannt." >&2
      fi
    fi

    if (( sleep_between > 0 )); then
      sleep "${sleep_between}"
    fi
  done

  if (( ok_count == 0 )); then
    return 1
  fi
  if (( fail_count > 0 )); then
    echo "Warnung: Direct-Probe teilweise fehlgeschlagen (${fail_count} fehlerhaft, ${ok_count} ok)." >&2
  fi
  return 0
}

run_load_schedule() {
  local fast_delay="$1"
  local slow_delay="$2"
  local delta_to_slow=$((slow_delay - fast_delay))

  heartbeat_sleep "${fast_delay}" "Warte bis Last-Phase A startet"
  send_fast_flood

  if (( delta_to_slow > 0 )); then
    heartbeat_sleep "${delta_to_slow}" "Warte bis Last-Phase B startet"
  fi
  send_slow_flood
}

collect_network_snapshot_json() {
  local wlan_conn eth_conn wlan_ip eth_ip default_dev default_gw
  wlan_conn="$(nmcli -t -f DEVICE,CONNECTION device status 2>/dev/null | awk -F: '$1=="wlan0"{print $2; exit}')"
  eth_conn="$(nmcli -t -f DEVICE,CONNECTION device status 2>/dev/null | awk -F: '$1=="eth0"{print $2; exit}')"
  wlan_ip="$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
  eth_ip="$(ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
  default_dev="$(ip -4 route show default 2>/dev/null | awk '/^default/{print $5; exit}')"
  default_gw="$(ip -4 route show default 2>/dev/null | awk '/^default/{print $3; exit}')"
  printf '{"wlan_connection":"%s","eth_connection":"%s","wlan_ip":"%s","eth_ip":"%s","default_dev":"%s","default_gw":"%s"}' \
    "${wlan_conn:-}" "${eth_conn:-}" "${wlan_ip:-}" "${eth_ip:-}" "${default_dev:-}" "${default_gw:-}"
}

monitor_capture_heartbeat() {
  local started_epoch="$1"
  local expected_end=$((started_epoch + CAPTURE_SECONDS))

  while true; do
    local now_epoch
    now_epoch="$(date +%s)"
    local remaining=$((expected_end - now_epoch))
    if (( remaining < 0 )); then
      remaining=0
    fi

    local broker_alive=0
    local server_alive=0
    local serial_alive=0
    kill -0 "${BROKER_PID}" 2>/dev/null && broker_alive=1
    kill -0 "${SERVER_PID}" 2>/dev/null && server_alive=1
    kill -0 "${SERIAL_PID}" 2>/dev/null && serial_alive=1
    local serial_bytes
    serial_bytes="$(serial_log_bytes)"

    echo "[Heartbeat] Capture verbleibend: ${remaining}s | serial=${serial_bytes}B | broker=${broker_alive} server=${server_alive} serial_capture=${serial_alive}"

    if (( broker_alive == 0 && server_alive == 0 && serial_alive == 0 )); then
      break
    fi

    local sleep_chunk="${HEARTBEAT_INTERVAL_SECONDS}"
    if (( sleep_chunk <= 0 )); then
      sleep_chunk=1
    fi
    if (( remaining > 0 && sleep_chunk > remaining )); then
      sleep_chunk="${remaining}"
      (( sleep_chunk < 1 )) && sleep_chunk=1
    fi
    sleep "${sleep_chunk}"
  done
}

preflight_environment() {
  local strict_mode="${PREFLIGHT_STRICT_MODE:-0}"
  local broker_window_seconds="${PREFLIGHT_BROKER_WINDOW_SECONDS:-180}"
  local serial_probe_seconds="${PREFLIGHT_SERIAL_PROBE_SECONDS:-2}"

  if [[ ! -e "${SERIAL_PORT}" ]]; then
    echo "Preflight fehlgeschlagen: Serial-Port nicht gefunden (${SERIAL_PORT})." >&2
    # region agent log
    debug_log "H97" "preflight_failed" "{\"reason\":\"serial_port_missing\",\"serial_port\":\"${SERIAL_PORT}\",\"strict\":${strict_mode}}"
    # endregion
    return 1
  fi

  local broker_running="false"
  if [[ "$(docker inspect -f '{{.State.Running}}' automationone-mqtt 2>/dev/null || true)" == "true" ]]; then
    broker_running="true"
  fi

  local recent_esp_events=0
  recent_esp_events="$(docker logs --since "${broker_window_seconds}s" automationone-mqtt 2>&1 | python3 - "${ESP_ID}" <<'PY'
import re
import sys

esp_id = sys.argv[1]
pattern = re.compile(rf"(New client connected .* as {re.escape(esp_id)}\b|Client {re.escape(esp_id)} .* disconnected)", re.IGNORECASE)
count = 0
for line in sys.stdin:
    if pattern.search(line):
        count += 1
print(count)
PY
)"

  local serial_probe_bytes=0
  serial_probe_bytes="$(timeout "${serial_probe_seconds}"s sh -c "dd if='${SERIAL_PORT}' bs=1 count=256 status=none 2>/dev/null | wc -c" 2>/dev/null || true)"
  if [[ -z "${serial_probe_bytes}" ]]; then
    serial_probe_bytes=0
  fi
  serial_probe_bytes="${serial_probe_bytes//[[:space:]]/}"
  if [[ -z "${serial_probe_bytes}" ]]; then
    serial_probe_bytes=0
  fi

  # region agent log
  debug_log "H97" "preflight_status" "{\"serial_port\":\"${SERIAL_PORT}\",\"broker_running\":${broker_running},\"recent_esp_events\":${recent_esp_events},\"serial_probe_bytes\":${serial_probe_bytes},\"strict\":${strict_mode},\"broker_window_seconds\":${broker_window_seconds}}"
  # endregion

  if [[ "${strict_mode}" == "1" ]]; then
    if [[ "${broker_running}" != "true" ]]; then
      echo "Preflight fehlgeschlagen (strict): MQTT-Broker läuft nicht." >&2
      # region agent log
      debug_log "H97" "preflight_failed" "{\"reason\":\"broker_not_running\",\"strict\":true}"
      # endregion
      return 1
    fi
    if [[ "${recent_esp_events}" -eq 0 && "${serial_probe_bytes}" -eq 0 ]]; then
      echo "Preflight fehlgeschlagen (strict): ESP derzeit vermutlich offline (keine Broker-Events + keine Serial-Bytes)." >&2
      # region agent log
      debug_log "H97" "preflight_failed" "{\"reason\":\"esp_offline_suspected\",\"recent_esp_events\":${recent_esp_events},\"serial_probe_bytes\":${serial_probe_bytes},\"strict\":true}"
      # endregion
      return 1
    fi
  fi

  if [[ "${recent_esp_events}" -eq 0 && "${serial_probe_bytes}" -eq 0 ]]; then
    echo "Warnung: Preflight sieht keine frischen ESP-Aktivitäten (Broker+Serial). Run kann unzuverlässig sein. Setze PREFLIGHT_STRICT_MODE=1 zum harten Abbruch." >&2
  fi

  return 0
}

echo "run_id=${RUN_ID}" > "${RUN_META}"
echo "esp_id=${ESP_ID}" >> "${RUN_META}"
echo "serial_port=${SERIAL_PORT}" >> "${RUN_META}"
echo "baud=${BAUD}" >> "${RUN_META}"
echo "capture_seconds=${CAPTURE_SECONDS}" >> "${RUN_META}"
echo "topic_cmd=${TOPIC_CMD}" >> "${RUN_META}"
echo "actuator_gpios=${ACTUATOR_GPIOS_EFFECTIVE}" >> "${RUN_META}"
echo "profile=${RUN_PROFILE}" >> "${RUN_META}"

echo "Starte Repro-Lauf ${RUN_ID}"
echo "ESP: ${ESP_ID}"
echo "Port: ${SERIAL_PORT}"
echo "Output: ${OUT_DIR}"
echo "Profil: ${RUN_PROFILE}"
echo "Aktor-GPIOs: ${ACTUATOR_GPIOS_EFFECTIVE}"

if ! preflight_environment; then
  exit 1
fi

# region agent log
debug_log "H0" "repro_started" "{\"esp_id\":\"${ESP_ID}\",\"serial_port\":\"${SERIAL_PORT}\",\"capture_seconds\":${CAPTURE_SECONDS},\"flood_fast\":${FLOOD_COUNT_FAST},\"flood_slow\":${FLOOD_COUNT_SLOW},\"flood_delay_ms\":${FLOOD_DELAY_SLOW_MS},\"profile\":\"${RUN_PROFILE}\",\"actuator_gpios\":\"${ACTUATOR_GPIOS_EFFECTIVE}\"}"
# endregion

# region agent log
debug_log "H71" "network_snapshot_before_run" "$(collect_network_snapshot_json)"
# endregion

resolve_frontend_credentials

echo "Pre-Run Pflichtschritt: Frontend-API Save (Aktoren)"
echo "Warte ${POST_FLASH_PAUSE_SECONDS}s auf Stabilisierung nach Flash/Boot..."
sleep "${POST_FLASH_PAUSE_SECONDS}"

if [[ -n "${FRONTEND_DEVICE_SAVE_CMD}" ]]; then
  echo "- Optionaler Geräte-Call wird ausgeführt..."
  if ! run_frontend_save "device" "${FRONTEND_DEVICE_SAVE_CMD}" "H52"; then
    # region agent log
    debug_log "H52" "frontend_device_save_failed" "{\"save\":\"device\"}"
    # endregion
    echo "Frontend Device-Save fehlgeschlagen (optional) — Run wird fortgesetzt." >&2
  fi
else
  # region agent log
  debug_log "H54" "frontend_device_save_skipped" "{\"reason\":\"optional_not_set\"}"
  # endregion
fi

if [[ "${SKIP_FRONTEND_ACTUATOR_SAVE}" == "1" ]]; then
  echo "- Aktoren-Call wird übersprungen (SKIP_FRONTEND_ACTUATOR_SAVE=1)."
  # region agent log
  debug_log "H56" "frontend_actuator_save_skipped" "{\"reason\":\"skip_env\",\"skip\":true}"
  # endregion
else
  echo "- Aktoren-Call wird ausgeführt (GPIOs: ${ACTUATOR_GPIOS_EFFECTIVE})..."
  actuator_save_success=0
  actuator_save_failed=0
  for actuator_gpio in "${ACTUATOR_GPIO_LIST[@]}"; do
    if run_frontend_actuator_save_api "H56" "${actuator_gpio}"; then
      actuator_save_success=$((actuator_save_success + 1))
    else
      actuator_save_failed=$((actuator_save_failed + 1))
      # region agent log
      debug_log "H56" "frontend_actuator_save_failed" "{\"save\":\"actuator\",\"mode\":\"api\",\"gpio\":${actuator_gpio}}"
      # endregion
      echo "Warnung: Frontend Actuator-Save via API fehlgeschlagen fuer GPIO ${actuator_gpio}." >&2
    fi
  done
  if (( actuator_save_failed > 0 )); then
    echo "Warnung: ${actuator_save_failed} Aktor-Saves fehlgeschlagen, ${actuator_save_success} erfolgreich." >&2
  fi
  if (( actuator_save_success == 0 )); then
    echo "Frontend Actuator-Save via API fuer alle Ziel-GPIOs fehlgeschlagen. Run wird abgebrochen." >&2
    exit 1
  fi
fi

if [[ -n "${FRONTEND_ACTUATOR_SAVE_CMD:-}" ]]; then
  # region agent log
  debug_log "H57" "frontend_actuator_legacy_cmd_ignored" "{\"reason\":\"api_mode_forced\"}"
  # endregion
fi

device_call_set=0
if [[ -n "${FRONTEND_DEVICE_SAVE_CMD}" ]]; then
  device_call_set=1
fi
# region agent log
actuator_call_set=1
if [[ "${SKIP_FRONTEND_ACTUATOR_SAVE}" == "1" ]]; then
  actuator_call_set=0
fi
debug_log "H55" "frontend_presave_completed" "{\"device_call_set\":$(json_bool "${device_call_set}"),\"actuator_call_set\":$(json_bool "${actuator_call_set}"),\"actuator_mode\":\"api_forced\",\"post_flash_pause_seconds\":${POST_FLASH_PAUSE_SECONDS},\"skip_actuator_save\":$(json_bool "${SKIP_FRONTEND_ACTUATOR_SAVE}")}"
# endregion

if [[ "${DIRECT_PROBE_MODE}" == "1" ]]; then
  if ! run_direct_probe_sequence; then
    echo "Direct-Probe fehlgeschlagen." >&2
    exit 1
  fi
  if [[ "${DIRECT_PROBE_ONLY_EXIT}" == "1" ]]; then
    echo "Direct-Probe abgeschlossen (DIRECT_PROBE_ONLY_EXIT=1)."
    exit 0
  fi
fi

# Yesterday window (UTC-based)
Y_START="$(date -u -d 'yesterday 00:00:00' +%Y-%m-%dT%H:%M:%SZ)"
Y_END="$(date -u -d 'today 00:00:00' +%Y-%m-%dT%H:%M:%SZ)"

if ! curl -sG "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode "query={compose_service=\"mqtt-broker\"} |= \"${ESP_ID}\"" \
  --data-urlencode "start=${Y_START}" \
  --data-urlencode "end=${Y_END}" \
  --data-urlencode "limit=5000" > "${YESTERDAY_JSON}"; then
  echo "Warnung: Loki-Abfrage fehlgeschlagen, Analyse läuft ohne Yesterday-Events weiter." >&2
  # region agent log
  debug_log "H92" "loki_query_failed" "{\"url\":\"http://localhost:3100/loki/api/v1/query_range\",\"esp_id\":\"${ESP_ID}\"}"
  # endregion
fi

START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "start_utc=${START_UTC}" >> "${RUN_META}"

# Capture broker/server in background
timeout "${CAPTURE_SECONDS}"s docker logs -f --since "${START_UTC}" automationone-mqtt > "${BROKER_LOG}" 2>&1 &
BROKER_PID=$!
timeout "${CAPTURE_SECONDS}"s docker logs -f --since "${START_UTC}" automationone-server > "${SERVER_LOG}" 2>&1 &
SERVER_PID=$!

# Serial capture (non-interactive safe) via raw tty stream.
stty -F "${SERIAL_PORT}" "${BAUD}" cs8 -cstopb -parenb -ixon -ixoff -echo raw || true
timeout "${CAPTURE_SECONDS}"s sh -c "cat \"${SERIAL_PORT}\"" 2>/dev/null \
  | tr -d '\r' \
  | awk '{ cmd="date -Iseconds"; cmd | getline ts; close(cmd); print "[" ts "] " $0; fflush(); }' \
  > "${SERIAL_LOG}" &
SERIAL_PID=$!

HEALTHCHECK_DELAY=5
if (( CAPTURE_SECONDS <= HEALTHCHECK_DELAY )); then
  HEALTHCHECK_DELAY=$(( CAPTURE_SECONDS / 2 ))
  (( HEALTHCHECK_DELAY < 1 )) && HEALTHCHECK_DELAY=1
fi
heartbeat_sleep "${HEALTHCHECK_DELAY}" "Initiale Capture-Stabilisierung"

# Capture health check should only run when enough runtime remains.
if (( CAPTURE_SECONDS > (HEALTHCHECK_DELAY + 1) )); then
  assert_capture_running "mqtt_broker" "${BROKER_PID}" "${BROKER_LOG}"
  assert_capture_running "server" "${SERVER_PID}" "${SERVER_LOG}"
  assert_capture_running "serial" "${SERIAL_PID}" "${SERIAL_LOG}"
fi

early_serial_bytes="$(serial_log_bytes)"
if (( EARLY_SERIAL_CHECK_REQUIRED == 1 && early_serial_bytes < EARLY_SERIAL_MIN_BYTES )); then
  echo "Warnung: Early-Serial unter Schwellwert (${early_serial_bytes}B < ${EARLY_SERIAL_MIN_BYTES}B) - starte Warmup-Recheck (grace=${EARLY_SERIAL_GRACE_SECONDS}s, max=${EARLY_SERIAL_MAX_WARMUP_SECONDS}s)." >&2
  local_remaining="${EARLY_SERIAL_MAX_WARMUP_SECONDS}"
  serial_or_broker_ready=0
  while (( local_remaining > 0 )); do
    sleep_chunk="${EARLY_SERIAL_RECHECK_INTERVAL_SECONDS}"
    if (( sleep_chunk <= 0 )); then
      sleep_chunk=1
    fi
    if (( sleep_chunk > local_remaining )); then
      sleep_chunk="${local_remaining}"
    fi
    heartbeat_sleep "${sleep_chunk}" "Early-Serial Warmup-Recheck"
    early_serial_bytes="$(serial_log_bytes)"
    broker_events="$(broker_esp_event_count)"
    if (( early_serial_bytes >= EARLY_SERIAL_MIN_BYTES || broker_events > 0 )); then
      serial_or_broker_ready=1
      break
    fi
    local_remaining=$((local_remaining - sleep_chunk))
  done

  if (( serial_or_broker_ready == 0 )); then
    serial_alive=0
    broker_alive=0
    server_alive=0
    kill -0 "${SERIAL_PID}" 2>/dev/null && serial_alive=1
    kill -0 "${BROKER_PID}" 2>/dev/null && broker_alive=1
    kill -0 "${SERVER_PID}" 2>/dev/null && server_alive=1

    if (( serial_alive == 0 || (broker_alive == 0 && server_alive == 0) )); then
      echo "Run nicht verwertbar: keine fruehen Aktivitaetsindikatoren (serial=${early_serial_bytes}B, broker_events=${broker_events}) und Capture-Prozess frueh beendet." >&2
      echo "Hinweis: Pruefe USB-Port, ESP-Boot und Baudrate (${BAUD})." >&2
      exit 2
    fi

    echo "Warnung: Keine fruehen Aktivitaetsindikatoren (serial=${early_serial_bytes}B, broker_events=${broker_events}) nach Warmup; Lauf wird fortgesetzt und am Ende streng ueber run_summary validiert." >&2
  else
    if (( early_serial_bytes < EARLY_SERIAL_MIN_BYTES )); then
      echo "Info: Early-Serial weiter unter Schwellwert (${early_serial_bytes}B), aber Broker-ESP-Aktivitaet erkannt (events=${broker_events}) -> Lauf wird fortgesetzt." >&2
    else
      echo "Info: Early-Serial-Schwelle erreicht (${early_serial_bytes}B)." >&2
    fi
  fi
fi

early_serial_bytes="$(serial_log_bytes)"
if (( EARLY_SERIAL_CHECK_REQUIRED == 1 && early_serial_bytes < EARLY_SERIAL_MIN_BYTES )); then
  serial_alive=0
  kill -0 "${SERIAL_PID}" 2>/dev/null && serial_alive=1
  if (( serial_alive == 0 )); then
    echo "Run nicht verwertbar: Serial-Capture ist frueh beendet und blieb unter Mindestmenge (${early_serial_bytes}B < ${EARLY_SERIAL_MIN_BYTES}B)." >&2
    exit 2
  fi
fi

if [[ "${PROBE_BEFORE_FLOOD}" == "1" && "${PROBE_POST_CONFIG_SETTLE_SECONDS}" -gt 0 ]]; then
  heartbeat_sleep "${PROBE_POST_CONFIG_SETTLE_SECONDS}" "Warte auf Config-Settle vor Probe"
fi

# Probe requires active captures. On short CAPTURE_SECONDS windows the capture
# can already end before probe starts (e.g. long warmup/online-wait), which
# would create false negatives ("kein Command-Ingress").
assert_capture_running "serial" "${SERIAL_PID}" "${SERIAL_LOG}"
assert_capture_running "mqtt_broker" "${BROKER_PID}" "${BROKER_LOG}"
assert_capture_running "server" "${SERVER_PID}" "${SERVER_LOG}"

if ! wait_for_mqtt_online_before_probe; then
  echo "Warnung: MQTT-Online-Gate nicht eindeutig; Probe wird trotzdem ausgeführt." >&2
fi

if ! run_actuator_probe; then
  exit 1
fi

LOAD_FAST_DELAY=$(( CAPTURE_SECONDS * LOAD_FAST_START_PCT / 100 ))
LOAD_SLOW_DELAY=$(( CAPTURE_SECONDS * LOAD_SLOW_START_PCT / 100 ))
if (( LOAD_FAST_DELAY < 0 )); then
  LOAD_FAST_DELAY=0
fi
if (( LOAD_SLOW_DELAY < LOAD_FAST_DELAY )); then
  LOAD_SLOW_DELAY="${LOAD_FAST_DELAY}"
fi

echo "Load-Schedule: Phase A nach ${LOAD_FAST_DELAY}s, Phase B nach ${LOAD_SLOW_DELAY}s im Capture-Fenster."
run_load_schedule "${LOAD_FAST_DELAY}" "${LOAD_SLOW_DELAY}" &
LOAD_PID=$!

capture_started_epoch="$(date +%s)"
echo "Warte auf Capture-Ende (mit Heartbeats)..."
monitor_capture_heartbeat "${capture_started_epoch}"

if ! wait "${LOAD_PID}"; then
  echo "Last-Injektion fehlgeschlagen (pid=${LOAD_PID})." >&2
  exit 1
fi

wait_for_capture "serial" "${SERIAL_PID}" "${SERIAL_LOG}"
wait_for_capture "mqtt_broker" "${BROKER_PID}" "${BROKER_LOG}"
wait_for_capture "server" "${SERVER_PID}" "${SERVER_LOG}"

python3 - "$YESTERDAY_JSON" "$BROKER_LOG" "$SERVER_LOG" "$SERIAL_LOG" "$SUMMARY_MD" "$RUN_SUMMARY_JSON" "$ESP_ID" "$DEBUG_LOG_PATH" "$DEBUG_SESSION_ID" "$RUN_PROFILE" <<'PY'
import json
import re
import sys
from pathlib import Path
import time

yesterday_json = Path(sys.argv[1])
broker_log = Path(sys.argv[2])
server_log = Path(sys.argv[3])
serial_log = Path(sys.argv[4])
summary_md = Path(sys.argv[5])
run_summary_json = Path(sys.argv[6])
esp_id = sys.argv[7]
debug_log_path = Path(sys.argv[8])
debug_session_id = sys.argv[9]
run_profile = sys.argv[10]
run_id = serial_log.parent.name

serial_markers = {
    "eagain": re.compile(r"EAGAIN|EWOULDBLOCK", re.IGNORECASE),
    "outbox_full": re.compile(r"OUTBOX full|outbox[^\\n]*full|Publish queue full", re.IGNORECASE),
    "cb_open": re.compile(r"Circuit Breaker|Service DOWN|CB OPEN", re.IGNORECASE),
    "mqtt_disconnected": re.compile(r"MQTT_EVENT_DISCONNECTED|disconnected", re.IGNORECASE),
    "queue_pressure": re.compile(r"queue_pressure|Queue pressure", re.IGNORECASE),
    "outbox_lock_timeout": re.compile(r"Outbox lock timeout", re.IGNORECASE),
    "managed_reconnect": re.compile(r"managed reconnect scheduled", re.IGNORECASE),
    "wifi_disconnected": re.compile(r"WiFi disconnected", re.IGNORECASE),
    "write_timeout_classified": re.compile(r"classified=write_timeout", re.IGNORECASE),
    "reconnect_failed_reason": re.compile(r"reason=esp_mqtt_client_reconnect_failed|managed reconnect request failed|reconnect failed -> defer manual retry|reconnect failed -> suspend manual reconnect", re.IGNORECASE),
    "dbg_reconnect_schedule": re.compile(r"\[DBG5126ae\] reconnect schedule request", re.IGNORECASE),
    "dbg_reconnect_gate": re.compile(r"\[DBG5126ae\] reconnect attempt gate", re.IGNORECASE),
    "dbg_disconnect_context": re.compile(r"\[DBG5126ae\] disconnect event context", re.IGNORECASE),
    "dbg_transport_context": re.compile(r"\[DBG5126ae\] transport error context", re.IGNORECASE),
    "dbg_transport_outbox_context": re.compile(r"\[DBG5126ae\] transport error context.*outbox_inflight=", re.IGNORECASE),
    "dbg_heartbeat_publish_state": re.compile(r"\[DBG5126ae\] heartbeat publish state", re.IGNORECASE),
    "dbg_heartbeat_ack_accepted": re.compile(r"\[DBG5126ae\] heartbeat ack accepted", re.IGNORECASE),
    "dbg_heartbeat_ack_rejected": re.compile(r"\[DBG5126ae\] heartbeat ack rejected", re.IGNORECASE),
    "dbg_outbox_lock_acquire_timeout": re.compile(r"\[DBG5126ae\] outbox lock acquire timeout", re.IGNORECASE),
    "dbg_outbox_lock_hold": re.compile(r"\[DBG5126ae\] outbox lock hold", re.IGNORECASE),
    "dbg_comm_loop_gap": re.compile(r"\[DBG5126ae\] comm loop gap", re.IGNORECASE),
    "dbg_comm_mqtt_loop_slow": re.compile(r"\[DBG5126ae\] comm mqtt loop slow", re.IGNORECASE),
    "dbg_comm_wifi_loop_slow": re.compile(r"\[DBG5126ae\] comm wifi loop slow", re.IGNORECASE),
    "dbg_comm_process_queue_slow": re.compile(r"\[DBG5126ae\] comm processPublishQueue slow", re.IGNORECASE),
    "dbg_comm_queue_hyst_slow": re.compile(r"\[DBG5126ae\] comm queuePressureHysteresis slow", re.IGNORECASE),
    "dbg_comm_op_cycle_slow": re.compile(r"\[DBG5126ae\] comm op cycle slow", re.IGNORECASE),
    "dbg_queue_drain_publish_call_slow": re.compile(r"\[DBG5126ae\] queue drain publish call slow", re.IGNORECASE),
    "dbg_direct_publish_call_slow": re.compile(r"\[DBG5126ae\] direct publish call slow", re.IGNORECASE),
    "dbg_safety_loop_gap": re.compile(r"\[DBG5126ae\] safety loop gap", re.IGNORECASE),
    "dbg_safety_op_cycle_slow": re.compile(r"\[DBG5126ae\] safety op cycle slow", re.IGNORECASE),
    "dbg_queue_drain_skipped_disconnected": re.compile(r"\[DBG5126ae\] queue drain skipped disconnected", re.IGNORECASE),
    "dbg_queue_drain_publish_invoked_disconnected": re.compile(r"\[DBG5126ae\] queue drain publish invoked disconnected", re.IGNORECASE),
    "dbg_queue_drain_deferred_disconnected": re.compile(r"\[DBG5126ae\] queue drain deferred disconnected", re.IGNORECASE),
    "dbg_process_publish_queue_skipped_disconnected": re.compile(r"\[DBG5126ae\] processPublishQueue skipped disconnected", re.IGNORECASE),
    "dbg_replay_prepare_state": re.compile(r"\[DBG5126ae\] replay prepare state", re.IGNORECASE),
    "dbg_replay_publish_result": re.compile(r"\[DBG5126ae\] replay publish result", re.IGNORECASE),
    "dbg_replay_commit_state": re.compile(r"\[DBG5126ae\] replay commit state", re.IGNORECASE),
    "dbg_outbox_null_string_field": re.compile(r"\[DBG5126ae\] outbox null string field", re.IGNORECASE),
    "dbg_replay_backoff_active": re.compile(r"\[DBG5126ae\] replay backoff active", re.IGNORECASE),
    "dbg_replay_backoff_scheduled": re.compile(r"\[DBG5126ae\] replay backoff scheduled", re.IGNORECASE),
    "dbg_tls_timeout_defer_reconnect": re.compile(r"\[DBG5126ae\] tls timeout defer reconnect to disconnected", re.IGNORECASE),
    "dbg_replay_commit_cost": re.compile(r"\[DBG5126ae\] replay commit cost", re.IGNORECASE),
    "dbg_enqueue_critical_cost": re.compile(r"\[DBG5126ae\] enqueue critical cost", re.IGNORECASE),
    "dbg_outbox_stats_load_cost": re.compile(r"\[DBG5126ae\] outbox stats load cost", re.IGNORECASE),
    "dbg_outbox_save_entry_cost": re.compile(r"\[DBG5126ae\] outbox save entry cost", re.IGNORECASE),
    "dbg_outbox_clear_entry_cost": re.compile(r"\[DBG5126ae\] outbox clear entry cost", re.IGNORECASE),
    "dbg_replay_commit_phase_cost": re.compile(r"\[DBG5126ae\] replay commit phase cost", re.IGNORECASE),
    "dbg_reconnect_hold_decision": re.compile(r"\[DBG5126ae\] reconnect hold decision", re.IGNORECASE),
    "dbg_reconnect_base_decision": re.compile(r"\[DBG5126ae\] reconnect base decision", re.IGNORECASE),
    "dbg_actuator_queue_enqueue": re.compile(r"\[DBG5126ae\] actuator queue enqueue", re.IGNORECASE),
    "dbg_actuator_queue_dequeue": re.compile(r"\[DBG5126ae\] actuator queue dequeue", re.IGNORECASE),
    "dbg_actuator_execute_result": re.compile(r"\[DBG5126ae\] actuator execute result", re.IGNORECASE),
    "dbg_mqtt_data_ingress_command": re.compile(r"\[DBG5126ae\] mqtt data ingress command", re.IGNORECASE),
    "dbg_mqtt_data_route_duration": re.compile(r"\[DBG5126ae\] mqtt data route duration", re.IGNORECASE),
    "err_3012": re.compile(r"\[(ERRTRAK|ERROR)\s*\].*\[3012\]|MQTT-Publish fehlgeschlagen|ERROR_MQTT_PUBLISH_FAILED", re.IGNORECASE),
    "err_4062": re.compile(r"\[(ERRTRAK|ERROR)\s*\].*\[4062\]|Task-Queue voll|ERROR_TASK_QUEUE_FULL|Publish queue full", re.IGNORECASE),
    "publish_failed_connected": re.compile(r"Publish failed \(connected but error\)", re.IGNORECASE),
    "retry_queue_full_backoff": re.compile(r"Publish retry queue full during backoff, dropping", re.IGNORECASE),
    "retry_queue_full_general": re.compile(r"Publish retry queue full, dropping", re.IGNORECASE),
    "publish_dropped_after_retries": re.compile(r"Publish dropped \(backpressure shed\)|Publish dropped after retries", re.IGNORECASE),
    "hm_3012_suppressed": re.compile(r"HealthMonitor: Suppressing 3012 due to transient MQTT state", re.IGNORECASE),
}

broker_markers = {
    "session_taken_over": re.compile(r"session taken over", re.IGNORECASE),
    "exceeded_timeout": re.compile(r"exceeded timeout", re.IGNORECASE),
    "outgoing_dropped": re.compile(r"Outgoing messages are being dropped", re.IGNORECASE),
    "esp_connect": re.compile(rf"New client connected .* as {re.escape(esp_id)}", re.IGNORECASE),
    "esp_disconnect": re.compile(rf"Client {re.escape(esp_id)} .* disconnected", re.IGNORECASE),
}

server_markers = {
    "lwt_unexpected": re.compile(r"LWT received: ESP .* unexpected_disconnect", re.IGNORECASE),
    "queue_pressure": re.compile(r"Queue pressure event", re.IGNORECASE),
    "server_3012": re.compile(r"error_code=3012|MQTT-Publish fehlgeschlagen", re.IGNORECASE),
    "server_4062": re.compile(r"error_code=4062|Task-Queue voll", re.IGNORECASE),
}

# region agent log
def emit_debug(hypothesis_id: str, message: str, data: dict):
    entry = {
        "sessionId": debug_session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": "scripts/hardware/repro_disconnect_esp32.sh:summary_py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with debug_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")
# endregion

def scan(path: Path, marker_map: dict[str, re.Pattern], max_lines: int = 8):
    counts = {k: 0 for k in marker_map}
    samples = {k: [] for k in marker_map}
    first_hits = {k: None for k in marker_map}
    if not path.exists():
        return counts, samples, first_hits
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        for key, rx in marker_map.items():
            if rx.search(raw):
                counts[key] += 1
                if first_hits[key] is None:
                    first_hits[key] = raw
                if len(samples[key]) < max_lines:
                    samples[key].append(raw)
    return counts, samples, first_hits

def parse_yesterday_events(path: Path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    events = []
    streams = data.get("data", {}).get("result", [])
    for stream in streams:
        for ts, line in stream.get("values", []):
            events.append({"ts_ns": ts, "line": line})
    events.sort(key=lambda x: x["ts_ns"])
    return events

def extract_max_duration(lines: list[str], marker_substring: str) -> int:
    max_duration = 0
    rx = re.compile(r"duration_ms=(\d+)")
    for row in lines:
        if marker_substring not in row:
            continue
        m = rx.search(row)
        if not m:
            continue
        value = int(m.group(1))
        if value > max_duration:
            max_duration = value
    return max_duration

def extract_transport_classification(lines: list[str]) -> dict[str, int]:
    counts = {
        "write_timeout_silent": 0,
        "write_timeout_explicit": 0,
        "tls_timeout": 0,
        "tcp_other": 0,
    }
    for row in lines:
        if "[DBG5126ae] transport error context" not in row:
            continue
        if "write_timeout_silent=1" in row:
            counts["write_timeout_silent"] += 1
        elif "write_timeout_explicit=1" in row:
            counts["write_timeout_explicit"] += 1
        elif "tls_timeout=1" in row:
            counts["tls_timeout"] += 1
        else:
            counts["tcp_other"] += 1
    return counts

def extract_esp_keepalive_from_broker(path: Path, esp_id: str):
    if not path.exists():
        return None, None
    rx = re.compile(
        rf"New client connected .* as {re.escape(esp_id)} \([^)]*k(\d+)\)",
        re.IGNORECASE,
    )
    first_line = None
    first_keepalive = None
    for row in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = rx.search(row)
        if not m:
            continue
        first_line = row
        try:
            first_keepalive = int(m.group(1))
        except Exception:
            first_keepalive = None
        break
    return first_keepalive, first_line

def assess_serial_quality(lines: list[str]) -> dict[str, object]:
    ts_rx = re.compile(r"^\[\d{4}-\d{2}-\d{2}T")
    prefixed = 0
    first_garbled = None
    for row in lines:
        if ts_rx.match(row):
            prefixed += 1
        elif first_garbled is None and row.strip():
            first_garbled = row
    total = len(lines)
    garbled = max(total - prefixed, 0)
    ratio = 0.0 if total == 0 else round((prefixed / total) * 100.0, 2)
    return {
        "total_lines": total,
        "timestamp_prefixed_lines": prefixed,
        "garbled_or_fragment_lines": garbled,
        "timestamp_prefix_ratio_pct": ratio,
        "first_garbled_line": first_garbled,
    }

serial_counts, serial_samples, serial_first = scan(serial_log, serial_markers)
broker_counts, broker_samples, broker_first = scan(broker_log, broker_markers)
server_counts, server_samples, server_first = scan(server_log, server_markers)
y_events = parse_yesterday_events(yesterday_json)
serial_lines = serial_log.read_text(encoding="utf-8", errors="ignore").splitlines() if serial_log.exists() else []
transport_classes = extract_transport_classification(serial_lines)
serial_quality = assess_serial_quality(serial_lines)
esp_keepalive_observed, esp_keepalive_line = extract_esp_keepalive_from_broker(broker_log, esp_id)
max_queue_drain_publish_ms = extract_max_duration(serial_lines, "[DBG5126ae] queue drain publish call slow")
max_direct_publish_ms = extract_max_duration(serial_lines, "[DBG5126ae] direct publish call slow")
max_comm_process_queue_ms = extract_max_duration(serial_lines, "[DBG5126ae] comm processPublishQueue slow")
max_mqtt_route_ms = extract_max_duration(serial_lines, "[DBG5126ae] mqtt data route duration")

emit_debug("H1", "queue_overflow_signal", {
    "publish_queue_like_hits": int(sum(1 for row in serial_lines if "Publish queue full" in row or "SafePublish failed" in row)),
    "serial_first_outbox": serial_first.get("outbox_full"),
})
emit_debug("H2", "session_takeover_chain", {
    "broker_session_taken_over_count": broker_counts.get("session_taken_over", 0),
    "broker_exceeded_timeout_count": broker_counts.get("exceeded_timeout", 0),
    "broker_first_session_taken_over": broker_first.get("session_taken_over"),
    "broker_first_exceeded_timeout": broker_first.get("exceeded_timeout"),
    "server_first_lwt_unexpected": server_first.get("lwt_unexpected"),
})
emit_debug("H3", "queue_pressure_vs_server", {
    "serial_queue_pressure_count": serial_counts.get("queue_pressure", 0),
    "server_queue_pressure_count": server_counts.get("queue_pressure", 0),
    "serial_first_queue_pressure": serial_first.get("queue_pressure"),
    "server_first_queue_pressure": server_first.get("queue_pressure"),
})
emit_debug("H4", "crash_signature", {
    "guru_meditation_count": int(len(re.findall(r"Guru Meditation", serial_log.read_text(encoding="utf-8", errors="ignore"), flags=re.IGNORECASE))),
    "stack_canary_count": int(len(re.findall(r"Stack canary", serial_log.read_text(encoding="utf-8", errors="ignore"), flags=re.IGNORECASE))),
})
emit_debug("H5", "historical_timeout_window", {
    "yesterday_events_found": len(y_events),
    "yesterday_last_event": y_events[-1]["line"] if y_events else None,
})
emit_debug("H6", "outbox_lock_contention", {
    "serial_outbox_lock_timeout_count": serial_counts.get("outbox_lock_timeout", 0),
    "serial_first_outbox_lock_timeout": serial_first.get("outbox_lock_timeout"),
})
emit_debug("H7", "transport_disconnect_chain", {
    "serial_mqtt_disconnected_count": serial_counts.get("mqtt_disconnected", 0),
    "serial_wifi_disconnected_count": serial_counts.get("wifi_disconnected", 0),
    "serial_managed_reconnect_count": serial_counts.get("managed_reconnect", 0),
    "serial_first_managed_reconnect": serial_first.get("managed_reconnect"),
})
emit_debug("H8", "circuit_breaker_backpressure", {
    "serial_cb_open_count": serial_counts.get("cb_open", 0),
    "serial_first_cb_open": serial_first.get("cb_open"),
})
emit_debug("H31", "error_code_4062_origin", {
    "serial_4062_count": serial_counts.get("err_4062", 0),
    "serial_first_4062": serial_first.get("err_4062"),
    "server_4062_count": server_counts.get("server_4062", 0),
    "server_first_4062": server_first.get("server_4062"),
})
emit_debug("H32", "error_code_3012_origin", {
    "serial_3012_count": serial_counts.get("err_3012", 0),
    "serial_first_3012": serial_first.get("err_3012"),
    "server_3012_count": server_counts.get("server_3012", 0),
    "server_first_3012": server_first.get("server_3012"),
})
emit_debug("H33", "error_order_4062_before_3012", {
    "first_4062_present": serial_first.get("err_4062") is not None,
    "first_3012_present": serial_first.get("err_3012") is not None,
    "first_4062_line": serial_first.get("err_4062"),
    "first_3012_line": serial_first.get("err_3012"),
})
emit_debug("H60", "publish_fail_paths_vs_3012", {
    "publish_failed_connected_count": serial_counts.get("publish_failed_connected", 0),
    "retry_queue_full_backoff_count": serial_counts.get("retry_queue_full_backoff", 0),
    "retry_queue_full_general_count": serial_counts.get("retry_queue_full_general", 0),
    "publish_dropped_after_retries_count": serial_counts.get("publish_dropped_after_retries", 0),
    "serial_3012_count": serial_counts.get("err_3012", 0),
    "first_publish_failed_connected": serial_first.get("publish_failed_connected"),
    "first_retry_queue_full_backoff": serial_first.get("retry_queue_full_backoff"),
    "first_retry_queue_full_general": serial_first.get("retry_queue_full_general"),
    "first_publish_dropped_after_retries": serial_first.get("publish_dropped_after_retries"),
    "healthmonitor_3012_suppressed_count": serial_counts.get("hm_3012_suppressed", 0),
    "first_healthmonitor_3012_suppressed": serial_first.get("hm_3012_suppressed"),
})
emit_debug("H61", "serial_log_quality", serial_quality)
emit_debug("H9", "transport_timeout_signature", {
    "serial_write_timeout_classified_count": serial_counts.get("write_timeout_classified", 0),
    "serial_first_write_timeout_classified": serial_first.get("write_timeout_classified"),
})
emit_debug("H10", "reconnect_failure_loop", {
    "serial_reconnect_failed_reason_count": serial_counts.get("reconnect_failed_reason", 0),
    "serial_first_reconnect_failed_reason": serial_first.get("reconnect_failed_reason"),
})
emit_debug("H11", "reconnect_schedule_state", {
    "serial_dbg_reconnect_schedule_count": serial_counts.get("dbg_reconnect_schedule", 0),
    "serial_first_dbg_reconnect_schedule": serial_first.get("dbg_reconnect_schedule"),
})
emit_debug("H12", "reconnect_gate_state", {
    "serial_dbg_reconnect_gate_count": serial_counts.get("dbg_reconnect_gate", 0),
    "serial_first_dbg_reconnect_gate": serial_first.get("dbg_reconnect_gate"),
})
emit_debug("H13", "disconnect_event_state", {
    "serial_dbg_disconnect_context_count": serial_counts.get("dbg_disconnect_context", 0),
    "serial_first_dbg_disconnect_context": serial_first.get("dbg_disconnect_context"),
})
emit_debug("H14", "transport_error_state", {
    "serial_dbg_transport_context_count": serial_counts.get("dbg_transport_context", 0),
    "serial_first_dbg_transport_context": serial_first.get("dbg_transport_context"),
})
emit_debug("H15", "transport_outbox_state", {
    "serial_dbg_transport_outbox_context_count": serial_counts.get("dbg_transport_outbox_context", 0),
    "serial_first_dbg_transport_outbox_context": serial_first.get("dbg_transport_outbox_context"),
})
emit_debug("H16", "heartbeat_flow_state", {
    "serial_dbg_heartbeat_publish_state_count": serial_counts.get("dbg_heartbeat_publish_state", 0),
    "serial_dbg_heartbeat_ack_accepted_count": serial_counts.get("dbg_heartbeat_ack_accepted", 0),
    "serial_dbg_heartbeat_ack_rejected_count": serial_counts.get("dbg_heartbeat_ack_rejected", 0),
    "serial_first_dbg_heartbeat_publish_state": serial_first.get("dbg_heartbeat_publish_state"),
    "serial_first_dbg_heartbeat_ack_accepted": serial_first.get("dbg_heartbeat_ack_accepted"),
    "serial_first_dbg_heartbeat_ack_rejected": serial_first.get("dbg_heartbeat_ack_rejected"),
})
emit_debug("H17", "broker_outgoing_drop_state", {
    "broker_outgoing_dropped_count": broker_counts.get("outgoing_dropped", 0),
    "broker_first_outgoing_dropped": broker_first.get("outgoing_dropped"),
})
emit_debug("H18", "outbox_lock_hold_state", {
    "serial_dbg_outbox_lock_acquire_timeout_count": serial_counts.get("dbg_outbox_lock_acquire_timeout", 0),
    "serial_dbg_outbox_lock_hold_count": serial_counts.get("dbg_outbox_lock_hold", 0),
    "serial_first_dbg_outbox_lock_acquire_timeout": serial_first.get("dbg_outbox_lock_acquire_timeout"),
    "serial_first_dbg_outbox_lock_hold": serial_first.get("dbg_outbox_lock_hold"),
})
emit_debug("H19", "comm_loop_starvation_state", {
    "serial_dbg_comm_loop_gap_count": serial_counts.get("dbg_comm_loop_gap", 0),
    "serial_first_dbg_comm_loop_gap": serial_first.get("dbg_comm_loop_gap"),
})
emit_debug("H20", "comm_mqtt_loop_latency_state", {
    "serial_dbg_comm_mqtt_loop_slow_count": serial_counts.get("dbg_comm_mqtt_loop_slow", 0),
    "serial_first_dbg_comm_mqtt_loop_slow": serial_first.get("dbg_comm_mqtt_loop_slow"),
})
emit_debug("H21", "comm_step_latency_state", {
    "serial_dbg_comm_wifi_loop_slow_count": serial_counts.get("dbg_comm_wifi_loop_slow", 0),
    "serial_dbg_comm_process_queue_slow_count": serial_counts.get("dbg_comm_process_queue_slow", 0),
    "serial_dbg_comm_queue_hyst_slow_count": serial_counts.get("dbg_comm_queue_hyst_slow", 0),
    "serial_dbg_comm_op_cycle_slow_count": serial_counts.get("dbg_comm_op_cycle_slow", 0),
    "serial_first_dbg_comm_wifi_loop_slow": serial_first.get("dbg_comm_wifi_loop_slow"),
    "serial_first_dbg_comm_process_queue_slow": serial_first.get("dbg_comm_process_queue_slow"),
    "serial_first_dbg_comm_queue_hyst_slow": serial_first.get("dbg_comm_queue_hyst_slow"),
    "serial_first_dbg_comm_op_cycle_slow": serial_first.get("dbg_comm_op_cycle_slow"),
})
emit_debug("H22", "queue_drain_publish_call_state", {
    "serial_dbg_queue_drain_publish_call_slow_count": serial_counts.get("dbg_queue_drain_publish_call_slow", 0),
    "serial_first_dbg_queue_drain_publish_call_slow": serial_first.get("dbg_queue_drain_publish_call_slow"),
})
emit_debug("H23", "direct_publish_call_state", {
    "serial_dbg_direct_publish_call_slow_count": serial_counts.get("dbg_direct_publish_call_slow", 0),
    "serial_first_dbg_direct_publish_call_slow": serial_first.get("dbg_direct_publish_call_slow"),
})
emit_debug("H24", "safety_scheduler_state", {
    "serial_dbg_safety_loop_gap_count": serial_counts.get("dbg_safety_loop_gap", 0),
    "serial_dbg_safety_op_cycle_slow_count": serial_counts.get("dbg_safety_op_cycle_slow", 0),
    "serial_first_dbg_safety_loop_gap": serial_first.get("dbg_safety_loop_gap"),
    "serial_first_dbg_safety_op_cycle_slow": serial_first.get("dbg_safety_op_cycle_slow"),
})
emit_debug("H25", "queue_drain_disconnected_guard_state", {
    "serial_dbg_queue_drain_skipped_disconnected_count": serial_counts.get("dbg_queue_drain_skipped_disconnected", 0),
    "serial_first_dbg_queue_drain_skipped_disconnected": serial_first.get("dbg_queue_drain_skipped_disconnected"),
})
emit_debug("H26", "queue_drain_invoke_disconnected_state", {
    "serial_dbg_queue_drain_publish_invoked_disconnected_count": serial_counts.get("dbg_queue_drain_publish_invoked_disconnected", 0),
    "serial_first_dbg_queue_drain_publish_invoked_disconnected": serial_first.get("dbg_queue_drain_publish_invoked_disconnected"),
})
emit_debug("H27", "queue_drain_deferred_disconnected_state", {
    "serial_dbg_queue_drain_deferred_disconnected_count": serial_counts.get("dbg_queue_drain_deferred_disconnected", 0),
    "serial_first_dbg_queue_drain_deferred_disconnected": serial_first.get("dbg_queue_drain_deferred_disconnected"),
})
emit_debug("H28", "process_publish_queue_disconnected_gate_state", {
    "serial_dbg_process_publish_queue_skipped_disconnected_count": serial_counts.get("dbg_process_publish_queue_skipped_disconnected", 0),
    "serial_first_dbg_process_publish_queue_skipped_disconnected": serial_first.get("dbg_process_publish_queue_skipped_disconnected"),
})
emit_debug("H29", "replay_prepare_state", {
    "serial_dbg_replay_prepare_state_count": serial_counts.get("dbg_replay_prepare_state", 0),
    "serial_first_dbg_replay_prepare_state": serial_first.get("dbg_replay_prepare_state"),
})
emit_debug("H30", "replay_publish_result_state", {
    "serial_dbg_replay_publish_result_count": serial_counts.get("dbg_replay_publish_result", 0),
    "serial_first_dbg_replay_publish_result": serial_first.get("dbg_replay_publish_result"),
})
emit_debug("H31", "replay_commit_state", {
    "serial_dbg_replay_commit_state_count": serial_counts.get("dbg_replay_commit_state", 0),
    "serial_first_dbg_replay_commit_state": serial_first.get("dbg_replay_commit_state"),
})
emit_debug("H32", "outbox_null_string_field_state", {
    "serial_dbg_outbox_null_string_field_count": serial_counts.get("dbg_outbox_null_string_field", 0),
    "serial_first_dbg_outbox_null_string_field": serial_first.get("dbg_outbox_null_string_field"),
})
emit_debug("H33", "replay_backoff_active_state", {
    "serial_dbg_replay_backoff_active_count": serial_counts.get("dbg_replay_backoff_active", 0),
    "serial_first_dbg_replay_backoff_active": serial_first.get("dbg_replay_backoff_active"),
})
emit_debug("H34", "replay_backoff_scheduled_state", {
    "serial_dbg_replay_backoff_scheduled_count": serial_counts.get("dbg_replay_backoff_scheduled", 0),
    "serial_first_dbg_replay_backoff_scheduled": serial_first.get("dbg_replay_backoff_scheduled"),
})
emit_debug("H35", "tls_timeout_defer_reconnect_state", {
    "serial_dbg_tls_timeout_defer_reconnect_count": serial_counts.get("dbg_tls_timeout_defer_reconnect", 0),
    "serial_first_dbg_tls_timeout_defer_reconnect": serial_first.get("dbg_tls_timeout_defer_reconnect"),
})
emit_debug("H36", "replay_commit_cost_state", {
    "serial_dbg_replay_commit_cost_count": serial_counts.get("dbg_replay_commit_cost", 0),
    "serial_first_dbg_replay_commit_cost": serial_first.get("dbg_replay_commit_cost"),
})
emit_debug("H37", "enqueue_critical_cost_state", {
    "serial_dbg_enqueue_critical_cost_count": serial_counts.get("dbg_enqueue_critical_cost", 0),
    "serial_first_dbg_enqueue_critical_cost": serial_first.get("dbg_enqueue_critical_cost"),
})
emit_debug("H41", "outbox_stats_load_cost_state", {
    "serial_dbg_outbox_stats_load_cost_count": serial_counts.get("dbg_outbox_stats_load_cost", 0),
    "serial_first_dbg_outbox_stats_load_cost": serial_first.get("dbg_outbox_stats_load_cost"),
})
emit_debug("H42", "outbox_save_entry_cost_state", {
    "serial_dbg_outbox_save_entry_cost_count": serial_counts.get("dbg_outbox_save_entry_cost", 0),
    "serial_first_dbg_outbox_save_entry_cost": serial_first.get("dbg_outbox_save_entry_cost"),
})
emit_debug("H43", "outbox_clear_entry_cost_state", {
    "serial_dbg_outbox_clear_entry_cost_count": serial_counts.get("dbg_outbox_clear_entry_cost", 0),
    "serial_first_dbg_outbox_clear_entry_cost": serial_first.get("dbg_outbox_clear_entry_cost"),
})
emit_debug("H44", "replay_commit_phase_cost_state", {
    "serial_dbg_replay_commit_phase_cost_count": serial_counts.get("dbg_replay_commit_phase_cost", 0),
    "serial_first_dbg_replay_commit_phase_cost": serial_first.get("dbg_replay_commit_phase_cost"),
})
emit_debug("H45", "reconnect_hold_decision_state", {
    "serial_dbg_reconnect_hold_decision_count": serial_counts.get("dbg_reconnect_hold_decision", 0),
    "serial_first_dbg_reconnect_hold_decision": serial_first.get("dbg_reconnect_hold_decision"),
})
emit_debug("H46", "reconnect_base_decision_state", {
    "serial_dbg_reconnect_base_decision_count": serial_counts.get("dbg_reconnect_base_decision", 0),
    "serial_first_dbg_reconnect_base_decision": serial_first.get("dbg_reconnect_base_decision"),
})
emit_debug("H47", "actuator_queue_enqueue_state", {
    "serial_dbg_actuator_queue_enqueue_count": serial_counts.get("dbg_actuator_queue_enqueue", 0),
    "serial_first_dbg_actuator_queue_enqueue": serial_first.get("dbg_actuator_queue_enqueue"),
})
emit_debug("H48", "actuator_queue_dequeue_state", {
    "serial_dbg_actuator_queue_dequeue_count": serial_counts.get("dbg_actuator_queue_dequeue", 0),
    "serial_first_dbg_actuator_queue_dequeue": serial_first.get("dbg_actuator_queue_dequeue"),
})
emit_debug("H49", "actuator_execute_result_state", {
    "serial_dbg_actuator_execute_result_count": serial_counts.get("dbg_actuator_execute_result", 0),
    "serial_first_dbg_actuator_execute_result": serial_first.get("dbg_actuator_execute_result"),
})
emit_debug("H50", "mqtt_data_ingress_command_state", {
    "serial_dbg_mqtt_data_ingress_command_count": serial_counts.get("dbg_mqtt_data_ingress_command", 0),
    "serial_first_dbg_mqtt_data_ingress_command": serial_first.get("dbg_mqtt_data_ingress_command"),
})
emit_debug("H51", "mqtt_data_route_duration_state", {
    "serial_dbg_mqtt_data_route_duration_count": serial_counts.get("dbg_mqtt_data_route_duration", 0),
    "serial_first_dbg_mqtt_data_route_duration": serial_first.get("dbg_mqtt_data_route_duration"),
})
emit_debug("H93", "disconnect_blocking_publish_chain", {
    "max_queue_drain_publish_ms": max_queue_drain_publish_ms,
    "max_direct_publish_ms": max_direct_publish_ms,
    "max_comm_process_queue_ms": max_comm_process_queue_ms,
    "disconnect_count": serial_counts.get("mqtt_disconnected", 0),
    "first_disconnect_context": serial_first.get("dbg_disconnect_context"),
})
emit_debug("H94", "disconnect_transport_timeout_class", {
    "write_timeout_silent_count": transport_classes["write_timeout_silent"],
    "write_timeout_explicit_count": transport_classes["write_timeout_explicit"],
    "tls_timeout_count": transport_classes["tls_timeout"],
    "tcp_other_count": transport_classes["tcp_other"],
    "first_transport_context": serial_first.get("dbg_transport_context"),
})
emit_debug("H95", "disconnect_outbox_lock_contention", {
    "outbox_lock_hold_count": serial_counts.get("dbg_outbox_lock_hold", 0),
    "outbox_lock_timeout_count": serial_counts.get("dbg_outbox_lock_acquire_timeout", 0),
    "max_comm_process_queue_ms": max_comm_process_queue_ms,
    "first_outbox_lock_hold": serial_first.get("dbg_outbox_lock_hold"),
})
emit_debug("H96", "disconnect_callback_route_load", {
    "max_mqtt_route_duration_ms": max_mqtt_route_ms,
    "mqtt_data_ingress_count": serial_counts.get("dbg_mqtt_data_ingress_command", 0),
    "direct_publish_slow_count": serial_counts.get("dbg_direct_publish_call_slow", 0),
    "first_mqtt_route_duration": serial_first.get("dbg_mqtt_data_route_duration"),
})
emit_debug("H74", "broker_keepalive_observed", {
    "esp_keepalive_observed": esp_keepalive_observed,
    "first_esp_connect_line": esp_keepalive_line,
})

lines = []
lines.append("# ESP32 Disconnect Repro Summary")
lines.append("")
lines.append("## Konfiguration")
lines.append(f"- ESP-ID: `{esp_id}`")
lines.append(f"- Serial-Log: `{serial_log}`")
lines.append(f"- Broker-Log: `{broker_log}`")
lines.append(f"- Server-Log: `{server_log}`")
lines.append("")
lines.append("## Gestern (Loki mqtt-broker)")
if not y_events:
    lines.append("- Keine Events im Loki-Response gefunden.")
else:
    for ev in y_events[-15:]:
        lines.append(f"- {ev['line']}")
lines.append("")
lines.append("## Marker-Counts")
lines.append("- **Serial**")
for k, v in serial_counts.items():
    lines.append(f"  - {k}: {v}")
lines.append("- **Broker**")
for k, v in broker_counts.items():
    lines.append(f"  - {k}: {v}")
lines.append("- **Server**")
for k, v in server_counts.items():
    lines.append(f"  - {k}: {v}")
lines.append("")
lines.append("## Datenqualität")
lines.append(f"- Serial-Zeilen gesamt: {serial_quality['total_lines']}")
lines.append(f"- Serial-Zeilen mit Timestamp-Präfix: {serial_quality['timestamp_prefixed_lines']} ({serial_quality['timestamp_prefix_ratio_pct']}%)")
lines.append(f"- Serial-Zeilen fragmentiert/garbled: {serial_quality['garbled_or_fragment_lines']}")
if serial_quality["first_garbled_line"]:
    lines.append(f"- Erstes garbled Beispiel: {serial_quality['first_garbled_line']}")
lines.append("")
lines.append("## Auffällige Beispielzeilen")
for section, samples in (("Serial", serial_samples), ("Broker", broker_samples), ("Server", server_samples)):
    lines.append(f"- **{section}**")
    for key, rows in samples.items():
        if rows:
            lines.append(f"  - {key}:")
            for row in rows[:5]:
                lines.append(f"    - {row}")

summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

key_marker_total = (
    serial_counts.get("mqtt_disconnected", 0)
    + serial_counts.get("err_4062", 0)
    + serial_counts.get("write_timeout_classified", 0)
    + serial_counts.get("dbg_transport_context", 0)
    + serial_counts.get("dbg_mqtt_data_ingress_command", 0)
)
unusable_reasons = []
if serial_quality["total_lines"] <= 0:
    unusable_reasons.append("serial_log_empty")
if key_marker_total <= 0:
    unusable_reasons.append("no_key_markers_detected")
if not broker_log.exists() or broker_log.stat().st_size <= 0:
    unusable_reasons.append("broker_log_empty")
if not server_log.exists() or server_log.stat().st_size <= 0:
    unusable_reasons.append("server_log_empty")

run_summary = {
    "run_id": run_id,
    "profile": run_profile,
    "esp_id": esp_id,
    "paths": {
        "serial_log": str(serial_log),
        "broker_log": str(broker_log),
        "server_log": str(server_log),
        "summary_md": str(summary_md),
    },
    "sizes_bytes": {
        "serial_log": serial_log.stat().st_size if serial_log.exists() else 0,
        "broker_log": broker_log.stat().st_size if broker_log.exists() else 0,
        "server_log": server_log.stat().st_size if server_log.exists() else 0,
    },
    "serial_quality": serial_quality,
    "counts": {
        "serial": serial_counts,
        "broker": broker_counts,
        "server": server_counts,
        "transport_classes": transport_classes,
    },
    "max_duration_ms": {
        "queue_drain_publish_call_slow": max_queue_drain_publish_ms,
        "direct_publish_call_slow": max_direct_publish_ms,
        "comm_process_queue_slow": max_comm_process_queue_ms,
        "mqtt_data_route_duration": max_mqtt_route_ms,
    },
    "unusable": len(unusable_reasons) > 0,
    "unusable_reasons": unusable_reasons,
}
run_summary_json.write_text(json.dumps(run_summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
print(summary_md)
PY

run_unusable_flag="$(python3 -c 'import json,sys; print("1" if json.loads(open(sys.argv[1],encoding="utf-8").read() or "{}").get("unusable") else "0")' "${RUN_SUMMARY_JSON}" 2>/dev/null || echo "1")"
if [[ "${run_unusable_flag}" == "1" ]]; then
  echo "Run nicht verwertbar. Details: ${RUN_SUMMARY_JSON}" >&2
  exit 2
fi

echo
echo "Fertig."
echo "Summary: ${SUMMARY_MD}"
echo "Run-JSON: ${RUN_SUMMARY_JSON}"
echo "Nächster Schritt: Summary prüfen und ggf. erneut mit höheren Flood-Werten laufen lassen."

# region agent log
debug_log "H72" "network_snapshot_after_run" "$(collect_network_snapshot_json)"
# endregion
