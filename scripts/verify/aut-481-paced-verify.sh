#!/usr/bin/env bash
# AUT-481 P1: Post-change verification helpers (paced 20× OFF/ON acceptance).
# Usage:
#   ./scripts/verify/aut-481-paced-verify.sh metrics
#   ./scripts/verify/aut-481-paced-verify.sh paced-storm   # requires AUTH_TOKEN, API base
set -euo pipefail

ESP_ID="${ESP_ID:-ESP_698EB4}"
GPIO="${GPIO:-14}"
API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
AUTH_TOKEN="${AUTH_TOKEN:-}"

metrics() {
  echo "=== open_with_terminal_outcome (expect 0) ==="
  docker exec automationone-postgres psql -U god_kaiser -d god_kaiser_db -c "
SELECT count(*) AS open_with_terminal_outcome
FROM command_intents i
JOIN command_outcomes o ON o.intent_id = i.intent_id
WHERE i.esp_id = '${ESP_ID}'
  AND i.orchestration_state IN ('sent','accepted','ack_pending')
  AND o.outcome IN ('applied','failed','rejected','expired');"

  echo ""
  echo "=== Recent LWT (last 20) ==="
  if [[ -f logs/server/god_kaiser.log ]]; then
    grep "LWT received: ESP ${ESP_ID}" logs/server/god_kaiser.log | tail -20 || true
  else
    echo "logs/server/god_kaiser.log not found (skip)"
  fi

  echo ""
  echo "=== MQTT broker disconnects (30m) ==="
  docker compose logs --since=30m mqtt-broker 2>&1 | grep "${ESP_ID}" | grep -i disconnect || echo "(none)"
}

paced_storm() {
  if [[ -z "${AUTH_TOKEN}" ]]; then
    echo "AUTH_TOKEN required for paced-storm (export JWT from UI login)" >&2
    exit 1
  fi
  echo "20× paced OFF/ON on ${ESP_ID} GPIO ${GPIO} (≥2s between commands)"
  for i in $(seq 1 20); do
    echo "Cycle ${i}/20 OFF"
    curl -sf -X POST "${API_BASE}/actuators/${ESP_ID}/${GPIO}/command" \
      -H "Authorization: Bearer ${AUTH_TOKEN}" \
      -H "Content-Type: application/json" \
      -d '{"command":"OFF","value":0}' >/dev/null
    sleep 2
    echo "Cycle ${i}/20 ON"
    curl -sf -X POST "${API_BASE}/actuators/${ESP_ID}/${GPIO}/command" \
      -H "Authorization: Bearer ${AUTH_TOKEN}" \
      -H "Content-Type: application/json" \
      -d '{"command":"ON","value":1}' >/dev/null
    sleep 2
  done
  echo "Storm complete — run: $0 metrics"
}

cmd="${1:-metrics}"
case "${cmd}" in
  metrics) metrics ;;
  paced-storm) paced_storm ;;
  *)
    echo "Usage: $0 {metrics|paced-storm}" >&2
    exit 1
    ;;
esac
