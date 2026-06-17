#!/usr/bin/env bash
set -euo pipefail

# Runs the disconnect repro script with artifact validation and emits
# a compact evidence report for fix verification.
#
# Default usage:
#   scripts/hardware/verify_disconnect_fix.sh
#
# Optional:
#   ATTEMPTS=2 CAPTURE_SECONDS=180 scripts/hardware/verify_disconnect_fix.sh
#   scripts/hardware/verify_disconnect_fix.sh --attempts 3 --capture-seconds 210 --profile my-check
#   scripts/hardware/verify_disconnect_fix.sh --actuator-gpios "25,26,27"

ATTEMPTS="${ATTEMPTS:-2}"
CAPTURE_SECONDS_OVERRIDE="${CAPTURE_SECONDS:-180}"
RUN_PROFILE_BASE="${RUN_PROFILE_BASE:-verify-disconnect-fix}"
FLOOD_COUNT_FAST="${FLOOD_COUNT_FAST:-450}"
FLOOD_COUNT_SLOW="${FLOOD_COUNT_SLOW:-300}"
FLOOD_DELAY_SLOW_MS="${FLOOD_DELAY_SLOW_MS:-10}"
ACTUATOR_GPIOS_OVERRIDE="${ACTUATOR_GPIOS:-}"
DEBUG_LOG_PATH="${DEBUG_LOG_PATH:-/home/robin/.cursor/debug-6dd16c.log}"
DEBUG_SESSION_ID="${DEBUG_SESSION_ID:-6dd16c}"
REPRO_SCRIPT="scripts/hardware/repro_disconnect_esp32.sh"
RUN_ROOT="logs/current/hardware/disconnect-repro"
VERIFY_SUMMARY_JSON="${RUN_ROOT}/verify_disconnect_fix_latest.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --attempts)
      ATTEMPTS="$2"
      shift 2
      ;;
    --capture-seconds)
      CAPTURE_SECONDS_OVERRIDE="$2"
      shift 2
      ;;
    --profile)
      RUN_PROFILE_BASE="$2"
      shift 2
      ;;
    --actuator-gpios)
      ACTUATOR_GPIOS_OVERRIDE="$2"
      shift 2
      ;;
    *)
      echo "Unbekanntes Argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -x "${REPRO_SCRIPT}" ]]; then
  if [[ -f "${REPRO_SCRIPT}" ]]; then
    chmod +x "${REPRO_SCRIPT}"
  else
    echo "Repro-Skript nicht gefunden: ${REPRO_SCRIPT}" >&2
    exit 1
  fi
fi

mkdir -p "${RUN_ROOT}"

list_latest_run_dir() {
  ls -1 "${RUN_ROOT}" 2>/dev/null | awk '/^[0-9]{8}_[0-9]{6}$/' | sort | tail -n 1
}

extract_run_dir_from_log() {
  local log_file="$1"
  python3 - "$log_file" <<'PY'
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
if not log_path.exists():
    print("")
    raise SystemExit(0)

run_dir = ""
for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
    m = re.search(r"^Output:\s+(logs/current/hardware/disconnect-repro/\d{8}_\d{6})\s*$", line.strip())
    if m:
        run_dir = m.group(1)

print(run_dir)
PY
}

analyze_run() {
  local run_dir="$1"
  python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
summary = run_dir / "SUMMARY.md"
serial_log = run_dir / "esp32_serial.log"
server_log = run_dir / "server.log"
broker_log = run_dir / "mqtt_broker.log"
meta_file = run_dir / "run_meta.txt"

result = {
    "run_dir": str(run_dir),
    "summary_exists": summary.exists(),
    "serial_exists": serial_log.exists(),
    "server_exists": server_log.exists(),
    "broker_exists": broker_log.exists(),
    "serial_size": serial_log.stat().st_size if serial_log.exists() else -1,
    "mqtt_disconnected_count": None,
    "write_timeout_classified_count": None,
    "direct_ack_stale_defer_count": 0,
    "queue_ack_stale_defer_count": 0,
    "disconnect_uptime_ms": None,
    "sock_errno11_count": 0,
    "intent_outcome_invalid_count": 0,
    "intent_outcome_json_error_count": 0,
    "profile": "",
    "run_summary_json_exists": False,
    "run_unusable": None,
    "run_unusable_reasons": [],
}

if meta_file.exists():
    for line in meta_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("profile="):
            result["profile"] = line.split("=", 1)[1]

if serial_log.exists():
    serial_lines = serial_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    result["direct_ack_stale_defer_count"] = sum("direct publish deferred ack stale" in l for l in serial_lines)
    result["queue_ack_stale_defer_count"] = sum("queue drain deferred ack stale" in l for l in serial_lines)
    result["sock_errno11_count"] = sum("sock_errno=11" in l for l in serial_lines)
    m = re.search(r"disconnect event context uptime_ms=(\d+)",
                  "\n".join(serial_lines))
    if m:
        result["disconnect_uptime_ms"] = int(m.group(1))

if server_log.exists():
    s_lines = server_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    result["intent_outcome_invalid_count"] = sum("Invalid intent_outcome payload" in l for l in s_lines)
    result["intent_outcome_json_error_count"] = sum("Invalid JSON payload on topic" in l for l in s_lines)

if summary.exists():
    text = summary.read_text(encoding="utf-8", errors="ignore")
    def parse_marker(name: str):
        m = re.search(rf"-\s+{re.escape(name)}:\s+(\d+)", text)
        return int(m.group(1)) if m else None
    result["mqtt_disconnected_count"] = parse_marker("mqtt_disconnected")
    result["write_timeout_classified_count"] = parse_marker("write_timeout_classified")

run_summary_json = run_dir / "run_summary.json"
if run_summary_json.exists():
    result["run_summary_json_exists"] = True
    try:
        parsed = json.loads(run_summary_json.read_text(encoding="utf-8", errors="ignore"))
        result["run_unusable"] = bool(parsed.get("unusable"))
        result["run_unusable_reasons"] = list(parsed.get("unusable_reasons", []))
    except Exception:
        result["run_unusable"] = True
        result["run_unusable_reasons"] = ["run_summary_json_parse_error"]

print(json.dumps(result, ensure_ascii=True))
PY
}

render_report() {
  local report_path="$1"
  local json_payload="$2"
  python3 - "$report_path" "$json_payload" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
data = json.loads(sys.argv[2])

lines = []
lines.append("# Disconnect Fix Verification Report")
lines.append("")
lines.append(f"- Run: `{Path(data['run_dir']).name}`")
lines.append(f"- Profile: `{data.get('profile','')}`")
lines.append(f"- Summary vorhanden: `{data['summary_exists']}`")
lines.append(f"- Serial-Log Größe: `{data['serial_size']}` Bytes")
lines.append(f"- mqtt_disconnected: `{data['mqtt_disconnected_count']}`")
lines.append(f"- write_timeout_classified: `{data['write_timeout_classified_count']}`")
lines.append(f"- defer marker (direct ack stale): `{data['direct_ack_stale_defer_count']}`")
lines.append(f"- defer marker (queue ack stale): `{data['queue_ack_stale_defer_count']}`")
lines.append(f"- sock_errno=11 count: `{data['sock_errno11_count']}`")
lines.append(f"- disconnect uptime_ms: `{data['disconnect_uptime_ms']}`")
lines.append(f"- server invalid intent_outcome: `{data['intent_outcome_invalid_count']}`")
lines.append(f"- server invalid JSON intent_outcome: `{data['intent_outcome_json_error_count']}`")
lines.append(f"- run_summary.json vorhanden: `{data.get('run_summary_json_exists')}`")
lines.append(f"- Lauf als unverwertbar markiert: `{data.get('run_unusable')}`")
if data.get("run_unusable_reasons"):
    lines.append(f"- Unverwertbar-Gründe: `{', '.join(data['run_unusable_reasons'])}`")
lines.append("")
if data["serial_size"] <= 0:
    lines.append("## Ergebnis")
    lines.append("Serial-Capture ist leer. Lauf nicht verwertbar; erneut starten.")
else:
    lines.append("## Ergebnis")
    if data["direct_ack_stale_defer_count"] > 0:
        lines.append("Fix-Marker für direkten ACK-stale-Defer wurde beobachtet.")
    else:
        lines.append("Kein direkter ACK-stale-Defer-Marker beobachtet.")
    if (data["mqtt_disconnected_count"] or 0) > 0:
        lines.append("Disconnect trat weiterhin auf.")
    else:
        lines.append("Kein Disconnect im Lauf beobachtet.")

report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(str(report_path))
PY
}

echo "Starte Verifikation (max attempts=${ATTEMPTS}, capture_seconds=${CAPTURE_SECONDS_OVERRIDE})"
if [[ -n "${ACTUATOR_GPIOS_OVERRIDE}" ]]; then
  echo "Aktor-GPIOs (override): ${ACTUATOR_GPIOS_OVERRIDE}"
fi
echo "Debug log: ${DEBUG_LOG_PATH}"

last_json=""
attempt=1
attempts_json="[]"
while (( attempt <= ATTEMPTS )); do
  before_latest="$(list_latest_run_dir || true)"
  run_profile="${RUN_PROFILE_BASE}-attempt${attempt}"
  attempt_log="${RUN_ROOT}/verify_attempt_${run_profile}.log"
  echo
  echo "[Attempt ${attempt}/${ATTEMPTS}] Profile=${run_profile}"

  set +e
  DEBUG_LOG_PATH="${DEBUG_LOG_PATH}" \
  DEBUG_SESSION_ID="${DEBUG_SESSION_ID}" \
  RUN_PROFILE="${run_profile}" \
  CAPTURE_SECONDS="${CAPTURE_SECONDS_OVERRIDE}" \
  FLOOD_COUNT_FAST="${FLOOD_COUNT_FAST}" \
  FLOOD_COUNT_SLOW="${FLOOD_COUNT_SLOW}" \
  FLOOD_DELAY_SLOW_MS="${FLOOD_DELAY_SLOW_MS}" \
  ACTUATOR_GPIOS="${ACTUATOR_GPIOS_OVERRIDE}" \
  bash "${REPRO_SCRIPT}" 2>&1 | tee "${attempt_log}"
  repro_exit=${PIPESTATUS[0]}
  set -e

  run_dir="$(extract_run_dir_from_log "${attempt_log}")"
  if [[ -z "${run_dir}" ]]; then
    after_latest="$(list_latest_run_dir || true)"
    if [[ -z "${after_latest}" ]]; then
      echo "Kein Run-Verzeichnis gefunden." >&2
      exit 1
    fi
    if [[ "${after_latest}" == "${before_latest}" ]]; then
      echo "Kein neues Run-Verzeichnis erzeugt." >&2
      exit 1
    fi
    run_dir="${RUN_ROOT}/${after_latest}"
    echo "Hinweis: Run-Verzeichnis aus Fallback ermittelt (${run_dir})."
  fi
  echo "Auswertung: ${run_dir}"
  last_json="$(analyze_run "${run_dir}")"
  echo "Analyse: ${last_json}"

  serial_size="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["serial_size"])' "${last_json}")"
  summary_exists="$(python3 -c 'import json,sys; print("1" if json.loads(sys.argv[1])["summary_exists"] else "0")' "${last_json}")"
  run_unusable="$(python3 -c 'import json,sys; print("1" if json.loads(sys.argv[1]).get("run_unusable") else "0")' "${last_json}")"

  report_file="${run_dir}/VERIFY_FIX_REPORT.md"
  render_report "${report_file}" "${last_json}" >/dev/null
  echo "Report: ${report_file}"

  attempts_json="$(python3 -c 'import json,sys; arr=json.loads(sys.argv[1]); arr.append(json.loads(sys.argv[2])); print(json.dumps(arr, ensure_ascii=True))' "${attempts_json}" "${last_json}")"

  if [[ "${summary_exists}" == "1" && "${serial_size}" -gt 0 && "${run_unusable}" == "0" && "${repro_exit}" -eq 0 ]]; then
    echo "Verwertbarer Lauf abgeschlossen."
    break
  fi

  echo "Lauf nicht verwertbar (exit=${repro_exit}, summary=${summary_exists}, serial_size=${serial_size}, run_unusable=${run_unusable})"
  attempt=$((attempt + 1))
done

if [[ -z "${last_json}" ]]; then
  echo "Keine Analyse erzeugt." >&2
  exit 1
fi

final_serial_size="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["serial_size"])' "${last_json}")"
if [[ "${final_serial_size}" -le 0 ]]; then
  echo "Alle Versuche mit leerem Serial-Log beendet. Fix nicht belegbar." >&2
  exit 2
fi

mkdir -p "${RUN_ROOT}"
python3 - "${VERIFY_SUMMARY_JSON}" "${ATTEMPTS}" "${CAPTURE_SECONDS_OVERRIDE}" "${attempts_json}" "${last_json}" <<'PY'
import json
import sys
from pathlib import Path

out_path = Path(sys.argv[1])
attempts_max = int(sys.argv[2])
capture_seconds = int(sys.argv[3])
attempts = json.loads(sys.argv[4])
last_result = json.loads(sys.argv[5])

payload = {
    "attempts_max": attempts_max,
    "capture_seconds": capture_seconds,
    "attempt_count": len(attempts),
    "attempts": attempts,
    "final_result": last_result,
    "final_run_dir": last_result.get("run_dir"),
    "final_profile": last_result.get("profile"),
}
out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
print(str(out_path))
PY

echo "Finale Analyse abgeschlossen."
echo "Maschinenlesbare Zusammenfassung: ${VERIFY_SUMMARY_JSON}"
