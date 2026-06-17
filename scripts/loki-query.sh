#!/bin/bash
# =============================================================================
# AutomationOne — Loki Query Helper
# =============================================================================
# Convenience wrapper for Loki API queries.
# Designed for agent use (make loki-*) and manual debugging.
# Windows-compatible: no GNU date extensions, uses date +%s + arithmetic.
#
# Usage:
#   loki-query.sh errors [minutes]       — Recent errors (default: 5 min)
#   loki-query.sh trace <correlation-id> — Correlation-ID trace (cross-service)
#   loki-query.sh esp <esp-id>           — All logs for a specific ESP32
#   loki-query.sh health                 — Loki health and active streams
# =============================================================================

LOKI_URL="${LOKI_URL:-http://localhost:3100}"

case "$1" in
  errors)
    MINUTES="${2:-5}"
    NOW=$(date +%s)
    START=$(( NOW - MINUTES * 60 ))
    echo "=== Errors (last ${MINUTES}min) ==="
    curl -sG "${LOKI_URL}/loki/api/v1/query_range" \
      --data-urlencode "query={compose_service=~\".+\"} | level=\"ERROR\"" \
      --data-urlencode "start=${START}000000000" \
      --data-urlencode "end=${NOW}000000000" \
      --data-urlencode "limit=50" \
    | jq -r '.data.result[] | .stream.compose_service as $svc | .values[] | "\(.[0] | tonumber / 1000000000 | strftime("%H:%M:%S")) [\($svc)] \(.[1])"' 2>/dev/null \
    || echo "(no errors or Loki not reachable)"
    ;;

  trace)
    CID="$2"
    if [ -z "$CID" ]; then
      echo "Usage: loki-query.sh trace <correlation-id>"
      exit 1
    fi
    echo "=== Correlation Trace: ${CID} ==="
    curl -sG "${LOKI_URL}/loki/api/v1/query_range" \
      --data-urlencode "query={compose_service=~\".+\"} |= \"${CID}\"" \
      --data-urlencode "limit=100" \
    | jq -r '.data.result[] | .stream.compose_service as $svc | .values[] | "\(.[0] | tonumber / 1000000000 | strftime("%H:%M:%S")) [\($svc)] \(.[1])"' 2>/dev/null \
    || echo "(no results or Loki not reachable)"
    ;;

  esp)
    ESP_ID="$2"
    if [ -z "$ESP_ID" ]; then
      echo "Usage: loki-query.sh esp <esp-id>"
      exit 1
    fi
    echo "=== ESP Logs: ${ESP_ID} ==="
    curl -sG "${LOKI_URL}/loki/api/v1/query_range" \
      --data-urlencode "query={compose_service=~\".+\"} |= \"${ESP_ID}\"" \
      --data-urlencode "limit=100" \
    | jq -r '.data.result[] | .stream.compose_service as $svc | .values[] | "\(.[0] | tonumber / 1000000000 | strftime("%H:%M:%S")) [\($svc)] \(.[1])"' 2>/dev/null \
    || echo "(no results or Loki not reachable)"
    ;;

  health)
    echo "=== Loki Ready ==="
    READY=$(curl -s "${LOKI_URL}/ready" 2>/dev/null)
    if [ "$READY" = "ready" ]; then
      echo "OK: Loki is ready"
    else
      echo "FAIL: Loki not ready (response: ${READY:-no response})"
    fi

    echo ""
    echo "=== Active Streams ==="
    curl -s "${LOKI_URL}/loki/api/v1/label/compose_service/values" 2>/dev/null \
    | jq -r '.data[]' 2>/dev/null \
    || echo "(Loki not reachable)"

    echo ""
    echo "=== Error Count (5min) ==="
    curl -sG "${LOKI_URL}/loki/api/v1/query" \
      --data-urlencode "query=count_over_time({compose_service=~\".+\"} | level=\"ERROR\" [5m])" 2>/dev/null \
    | jq -r '.data.result[] | "\(.stream.compose_service): \(.value[1]) errors"' 2>/dev/null \
    || echo "(no data or Loki not reachable)"
    ;;

  *)
    echo "AutomationOne Loki Query Helper"
    echo ""
    echo "Usage: loki-query.sh {errors|trace|esp|health} [args]"
    echo ""
    echo "  errors [minutes]       — Recent errors (default: 5 min)"
    echo "  trace <correlation-id> — Correlation-ID trace (cross-service)"
    echo "  esp <esp-id>           — All logs for a specific ESP32"
    echo "  health                 — Loki health, active streams, error count"
    echo ""
    echo "Environment: LOKI_URL (default: http://localhost:3100)"
    ;;
esac
