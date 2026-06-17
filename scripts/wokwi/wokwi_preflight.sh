#!/usr/bin/env bash
set -euo pipefail

# Fast, hard-fail preflight for local and CI execution.
# Exit codes:
# 10 = wokwi-cli missing
# 11 = version mismatch
# 12 = token missing

EXPECTED_VERSION="${1:-${WOKWI_CLI_VERSION:-}}"
REPORT_PATH="${2:-}"

log() {
  echo "[$(date +%H:%M:%S)] $*"
}

append_report() {
  if [[ -n "${REPORT_PATH}" ]]; then
    mkdir -p "$(dirname "${REPORT_PATH}")"
    echo "$*" >> "${REPORT_PATH}"
  fi
}

log "Wokwi preflight start"
append_report "# Wokwi Preflight"
append_report ""
append_report "- Start: $(date -Iseconds)"

if ! command -v wokwi-cli >/dev/null 2>&1; then
  log "FAIL: wokwi-cli missing"
  append_report "- CLI present: no"
  exit 10
fi

CLI_VERSION="$(wokwi-cli --short-version 2>/dev/null || true)"
if [[ -z "${CLI_VERSION}" ]]; then
  CLI_VERSION="$(wokwi-cli --version | awk '{print $NF}' | tr -d '\r' || true)"
fi

log "CLI version: ${CLI_VERSION}"
append_report "- CLI present: yes"
append_report "- CLI version: ${CLI_VERSION}"

if [[ -n "${EXPECTED_VERSION}" && "${CLI_VERSION}" != "${EXPECTED_VERSION}" ]]; then
  log "FAIL: expected=${EXPECTED_VERSION}, got=${CLI_VERSION}"
  append_report "- Version check: fail (expected ${EXPECTED_VERSION})"
  exit 11
fi

if [[ -n "${EXPECTED_VERSION}" ]]; then
  append_report "- Version check: ok (${EXPECTED_VERSION})"
else
  append_report "- Version check: skipped (no expected version provided)"
fi

if [[ -z "${WOKWI_CLI_TOKEN:-}" ]]; then
  log "FAIL: WOKWI_CLI_TOKEN missing"
  append_report "- Token present: no"
  exit 12
fi

TOKEN_PREFIX="${WOKWI_CLI_TOKEN:0:4}"
TOKEN_LEN="${#WOKWI_CLI_TOKEN}"
log "Token present (prefix=${TOKEN_PREFIX}***, len=${TOKEN_LEN})"
append_report "- Token present: yes (prefix ${TOKEN_PREFIX}***, len ${TOKEN_LEN})"

append_report "- Result: PASS"
append_report "- End: $(date -Iseconds)"
log "Preflight PASS"
