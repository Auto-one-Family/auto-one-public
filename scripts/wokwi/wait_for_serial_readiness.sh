#!/usr/bin/env bash
set -euo pipefail

# Waits for a readiness marker in Wokwi serial logs.
# Supports either explicit --log-file or auto discovery of latest .log.
#
# Exit codes:
# 20 = log file missing
# 21 = timeout (and no fallback)

LOG_FILE=""
AUTO_LATEST=false
PATTERN="MQTT connected successfully"
TIMEOUT_SECONDS=60
POLL_SECONDS=1
FALLBACK_SLEEP_SECONDS=0
REPORT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --log-file)
      LOG_FILE="$2"
      shift 2
      ;;
    --auto-latest-log)
      AUTO_LATEST=true
      shift
      ;;
    --pattern)
      PATTERN="$2"
      shift 2
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --poll-seconds)
      POLL_SECONDS="$2"
      shift 2
      ;;
    --fallback-sleep-seconds)
      FALLBACK_SLEEP_SECONDS="$2"
      shift 2
      ;;
    --report-file)
      REPORT_FILE="$2"
      shift 2
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${AUTO_LATEST}" == "true" && -z "${LOG_FILE}" ]]; then
  LOG_FILE="$(ls -1t ./*.log 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${LOG_FILE}" || ! -f "${LOG_FILE}" ]]; then
  echo "[ERROR] Log file not found for readiness wait: ${LOG_FILE:-<empty>}" >&2
  exit 20
fi

if [[ -n "${REPORT_FILE}" ]]; then
  mkdir -p "$(dirname "${REPORT_FILE}")"
  {
    echo "- Logfile: ${LOG_FILE}"
    echo "- Readiness pattern: \`${PATTERN}\`"
    echo "- Wait start: $(date -Iseconds)"
  } >> "${REPORT_FILE}"
fi

for i in $(seq 1 "${TIMEOUT_SECONDS}"); do
  if grep -q "${PATTERN}" "${LOG_FILE}" 2>/dev/null; then
    TS="$(date -Iseconds)"
    echo "[READY] Pattern matched after ${i}s in ${LOG_FILE}"
    echo "${TS}"
    if [[ -n "${REPORT_FILE}" ]]; then
      {
        echo "- Readiness matched: ${TS}"
        echo "- Wait duration seconds: ${i}"
      } >> "${REPORT_FILE}"
    fi
    exit 0
  fi
  sleep "${POLL_SECONDS}"
done

if [[ "${FALLBACK_SLEEP_SECONDS}" -gt 0 ]]; then
  echo "[WARN] --fallback-sleep-seconds is deprecated and ignored; readiness uses hard timeout."
fi

echo "[ERROR] Readiness timeout after ${TIMEOUT_SECONDS}s (${LOG_FILE})" >&2
exit 21
