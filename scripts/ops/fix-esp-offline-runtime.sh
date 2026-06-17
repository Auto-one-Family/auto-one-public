#!/usr/bin/env bash
set -euo pipefail

MODE=""
DEVICE_ID="ESP_EA5484"
KAISER_ID="god"
WATCH_SECONDS=120
WATCH_STEP=30
FORCE=0

usage() {
  cat <<'EOF'
fix-esp-offline-runtime.sh --dry-run|--apply [--device ESP_ID] [--kaiser KAISER_ID] [--watch-seconds N] [--force]

Behebt "ESP offline trotz Heartbeats/Approval" per Runtime-Maßnahmen:
1) Diagnose (DB + MQTT retained checks)
2) Fix (status/last_seen korrigieren, stale retained LWT löschen)
3) Post-Check (kurzer Watch auf Re-Flap)

Optionen:
  --dry-run            Nur Diagnose + geplante Aktionen anzeigen
  --apply              Aktionen wirklich ausführen
  --device <id>        Zielgerät (Default: ESP_EA5484)
  --kaiser <id>        Kaiser-ID für MQTT-Topics (Default: god)
  --watch-seconds <n>  Post-Check Dauer in Sekunden (Default: 120)
  --force              Update auch ohne Stale/Offline-Indikator erzwingen
  -h, --help           Hilfe
EOF
}

log() { printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }
die() { log "ERROR: $*"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) MODE="dry-run"; shift ;;
    --apply) MODE="apply"; shift ;;
    --device) DEVICE_ID="${2:-}"; shift 2 ;;
    --kaiser) KAISER_ID="${2:-}"; shift 2 ;;
    --watch-seconds) WATCH_SECONDS="${2:-}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unbekanntes Argument: $1" ;;
  esac
done

[[ -n "$MODE" ]] || die "Bitte --dry-run oder --apply angeben."
[[ "$WATCH_SECONDS" =~ ^[0-9]+$ ]] || die "--watch-seconds muss numerisch sein."

ROOT_DIR="/home/robin/autoone"
cd "$ROOT_DIR"

command -v docker >/dev/null 2>&1 || die "docker nicht gefunden."

compose() {
  docker compose "$@"
}

sql() {
  local query="$1"
  compose exec -T postgres sh -lc "psql -At -F '|' -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"$query\""
}

service_running() {
  local svc="$1"
  compose ps --status running --services | awk -v target="$svc" '$0 == target { found=1 } END { exit(found ? 0 : 1) }'
}

require_service() {
  local svc="$1"
  service_running "$svc" || die "Service '$svc' ist nicht running."
}

require_service "postgres"
require_service "mqtt-broker"

log "=== Diagnose: Ausgangslage ==="

ESP_ROW_QUERY="SELECT id,status,COALESCE(last_seen::text,''),COALESCE(updated_at::text,''),COALESCE(device_metadata::text,'{}') FROM esp_devices WHERE device_id = '$DEVICE_ID';"
ESP_ROW="$(sql "$ESP_ROW_QUERY" || true)"
[[ -n "$ESP_ROW" ]] || die "Device '$DEVICE_ID' nicht in esp_devices gefunden."

ESP_UUID="$(printf '%s' "$ESP_ROW" | cut -d'|' -f1)"
STATUS_BEFORE="$(printf '%s' "$ESP_ROW" | cut -d'|' -f2)"
LAST_SEEN_BEFORE="$(printf '%s' "$ESP_ROW" | cut -d'|' -f3)"
UPDATED_BEFORE="$(printf '%s' "$ESP_ROW" | cut -d'|' -f4)"
METADATA_BEFORE="$(printf '%s' "$ESP_ROW" | cut -d'|' -f5-)"

AGE_SECONDS="$(sql "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - last_seen))::bigint,-1) FROM esp_devices WHERE device_id = '$DEVICE_ID';")"
[[ -n "$AGE_SECONDS" ]] || AGE_SECONDS="-1"

HEARTBEAT_TIMEOUT="$(sql "SELECT COALESCE(NULLIF(details->>'timeout_threshold_seconds','')::int,120) FROM audit_logs WHERE source_id = '$DEVICE_ID' AND event_type = 'device_offline' ORDER BY created_at DESC LIMIT 1;")"
[[ -n "$HEARTBEAT_TIMEOUT" ]] || HEARTBEAT_TIMEOUT="120"

LAST_DISCONNECT_SOURCE="$(sql "SELECT COALESCE(device_metadata::jsonb->'last_disconnect'->>'source','') FROM esp_devices WHERE device_id = '$DEVICE_ID';")"
LAST_DISCONNECT_TS="$(sql "SELECT COALESCE(device_metadata::jsonb->'last_disconnect'->>'timestamp','') FROM esp_devices WHERE device_id = '$DEVICE_ID';")"

OFFLINE_TIMEOUT_COUNT="$(sql "SELECT COUNT(*) FROM audit_logs WHERE source_id = '$DEVICE_ID' AND event_type='device_offline' AND details->>'reason'='heartbeat_timeout' AND created_at > (now() - interval '6 hours');")"
LWT_COUNT="$(sql "SELECT COUNT(*) FROM audit_logs WHERE source_id = '$DEVICE_ID' AND event_type='lwt_received' AND created_at > (now() - interval '24 hours');")"

log "Device: $DEVICE_ID (uuid=$ESP_UUID)"
log "Status vorher: status=$STATUS_BEFORE last_seen=$LAST_SEEN_BEFORE updated_at=$UPDATED_BEFORE"
log "Indikatoren: age_seconds=$AGE_SECONDS heartbeat_timeout=$HEARTBEAT_TIMEOUT offline_timeout_6h=$OFFLINE_TIMEOUT_COUNT lwt_24h=$LWT_COUNT"
log "last_disconnect: source=${LAST_DISCONNECT_SOURCE:-n/a} ts=${LAST_DISCONNECT_TS:-n/a}"

LWT_TOPIC="kaiser/${KAISER_ID}/esp/${DEVICE_ID}/system/will"
SERVER_STATUS_TOPIC="kaiser/${KAISER_ID}/server/status"

set +e
RETAINED_LWT_RAW="$(compose exec -T mqtt-broker sh -lc "timeout 3 mosquitto_sub -h localhost -p 1883 -t '$LWT_TOPIC' -C 1 -F '%r|%p'" 2>/dev/null)"
LWT_RC=$?
SERVER_STATUS_RAW="$(compose exec -T mqtt-broker sh -lc "timeout 3 mosquitto_sub -h localhost -p 1883 -t '$SERVER_STATUS_TOPIC' -C 1 -F '%r|%p'" 2>/dev/null)"
SERVER_RC=$?
set -e

HAS_RETAINED_LWT=0
if [[ $LWT_RC -eq 0 && "$RETAINED_LWT_RAW" == 1\|* ]]; then
  HAS_RETAINED_LWT=1
fi

log "MQTT server/status: ${SERVER_STATUS_RAW:-<kein retained oder timeout>}"
if [[ $HAS_RETAINED_LWT -eq 1 ]]; then
  log "MQTT LWT retained erkannt: $RETAINED_LWT_RAW"
else
  log "MQTT LWT retained: nicht erkannt (rc=$LWT_RC)"
fi

NEEDS_DB_FIX=0
if [[ "$STATUS_BEFORE" != "online" ]]; then
  NEEDS_DB_FIX=1
elif [[ "$AGE_SECONDS" -ge 0 && "$AGE_SECONDS" -gt "$HEARTBEAT_TIMEOUT" ]]; then
  NEEDS_DB_FIX=1
elif [[ "$OFFLINE_TIMEOUT_COUNT" -gt 0 && "$LAST_DISCONNECT_SOURCE" == "lwt" && "$LAST_DISCONNECT_TS" == "0" ]]; then
  NEEDS_DB_FIX=1
fi

if [[ $FORCE -eq 1 ]]; then
  NEEDS_DB_FIX=1
fi

log "Entscheidung: needs_db_fix=$NEEDS_DB_FIX, retained_lwt_fix=$HAS_RETAINED_LWT"

if [[ "$MODE" == "dry-run" ]]; then
  log "--- DRY RUN ---"
  if [[ $NEEDS_DB_FIX -eq 1 ]]; then
    log "Plan DB-Fix: status='online', last_seen=now(), updated_at=now(), last_disconnect neutralisieren (runtime_fix)."
  else
    log "Plan DB-Fix: nicht erforderlich."
  fi
  if [[ $HAS_RETAINED_LWT -eq 1 ]]; then
    log "Plan MQTT-Fix: retained LWT auf '$LWT_TOPIC' mit leerem retained Publish löschen."
  else
    log "Plan MQTT-Fix: nicht erforderlich."
  fi
  log "Rollback-Hinweis:"
  printf "UPDATE esp_devices SET status='%s', last_seen=%s, updated_at=%s, device_metadata='%s'::json WHERE device_id='%s';\n" \
    "$STATUS_BEFORE" \
    "$( [[ -n "$LAST_SEEN_BEFORE" ]] && printf "'%s'" "$LAST_SEEN_BEFORE" || printf "NULL" )" \
    "$( [[ -n "$UPDATED_BEFORE" ]] && printf "'%s'" "$UPDATED_BEFORE" || printf "NULL" )" \
    "$(printf '%s' "$METADATA_BEFORE" | sed "s/'/''/g")" \
    "$DEVICE_ID"
  exit 0
fi

log "--- APPLY ---"
if [[ $NEEDS_DB_FIX -eq 1 ]]; then
  sql "UPDATE esp_devices
       SET status='online',
           last_seen=now(),
           updated_at=now(),
           device_metadata=jsonb_set(
             jsonb_set(
               COALESCE(device_metadata::jsonb,'{}'::jsonb),
               '{last_disconnect,source}',
               to_jsonb('runtime_fix'::text),
               true
             ),
             '{last_disconnect,timestamp}',
             to_jsonb(EXTRACT(EPOCH FROM now())::bigint),
             true
           )::json
       WHERE device_id='$DEVICE_ID';" >/dev/null
  log "DB-Fix angewendet."
else
  log "DB-Fix übersprungen (nicht erforderlich)."
fi

if [[ $HAS_RETAINED_LWT -eq 1 ]]; then
  compose exec -T mqtt-broker sh -lc "mosquitto_pub -h localhost -p 1883 -t '$LWT_TOPIC' -r -n"
  log "Retained LWT gelöscht: $LWT_TOPIC"
else
  log "LWT-Löschung übersprungen."
fi

log "--- Post-Check (watch=${WATCH_SECONDS}s) ---"
START_TS="$(date +%s)"
BASE_OFFLINE_COUNT="$(sql "SELECT COUNT(*) FROM audit_logs WHERE source_id = '$DEVICE_ID' AND event_type='device_offline' AND details->>'reason'='heartbeat_timeout' AND created_at > (now() - interval '30 minutes');")"
while true; do
  NOW_TS="$(date +%s)"
  ELAPSED=$((NOW_TS - START_TS))
  if [[ $ELAPSED -ge $WATCH_SECONDS ]]; then
    break
  fi
  STATUS_NOW="$(sql "SELECT status FROM esp_devices WHERE device_id='$DEVICE_ID';")"
  LAST_SEEN_NOW="$(sql "SELECT COALESCE(last_seen::text,'') FROM esp_devices WHERE device_id='$DEVICE_ID';")"
  AGE_NOW="$(sql "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - last_seen))::bigint,-1) FROM esp_devices WHERE device_id='$DEVICE_ID';")"
  OFFLINE_NOW="$(sql "SELECT COUNT(*) FROM audit_logs WHERE source_id = '$DEVICE_ID' AND event_type='device_offline' AND details->>'reason'='heartbeat_timeout' AND created_at > (now() - interval '30 minutes');")"
  log "watch t=${ELAPSED}s status=$STATUS_NOW age_s=$AGE_NOW last_seen=$LAST_SEEN_NOW offline_timeout_30m=$OFFLINE_NOW"
  sleep "$WATCH_STEP"
done

STATUS_AFTER="$(sql "SELECT status FROM esp_devices WHERE device_id='$DEVICE_ID';")"
LAST_SEEN_AFTER="$(sql "SELECT COALESCE(last_seen::text,'') FROM esp_devices WHERE device_id='$DEVICE_ID';")"
AGE_AFTER="$(sql "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - last_seen))::bigint,-1) FROM esp_devices WHERE device_id='$DEVICE_ID';")"
OFFLINE_AFTER="$(sql "SELECT COUNT(*) FROM audit_logs WHERE source_id = '$DEVICE_ID' AND event_type='device_offline' AND details->>'reason'='heartbeat_timeout' AND created_at > (now() - interval '30 minutes');")"
LWT_AFTER="$(sql "SELECT COUNT(*) FROM audit_logs WHERE source_id = '$DEVICE_ID' AND event_type='lwt_received' AND created_at > (now() - interval '30 minutes');")"

log "=== Ergebnis ==="
log "Status nachher: status=$STATUS_AFTER last_seen=$LAST_SEEN_AFTER age_seconds=$AGE_AFTER"
log "Audit nachher: offline_timeout_30m=$OFFLINE_AFTER (vorher=$BASE_OFFLINE_COUNT), lwt_30m=$LWT_AFTER"

if [[ "$STATUS_AFTER" != "online" ]]; then
  die "Post-Check fehlgeschlagen: Device ist nicht online."
fi

if [[ "$AGE_AFTER" -gt "$HEARTBEAT_TIMEOUT" ]]; then
  die "Post-Check fehlgeschlagen: last_seen weiterhin stale (age>$HEARTBEAT_TIMEOUT)."
fi

if [[ "$OFFLINE_AFTER" -gt "$BASE_OFFLINE_COUNT" ]]; then
  die "Post-Check Warnung: neue heartbeat_timeout-Offline-Events im Watch-Fenster."
fi

log "Post-Check bestanden."
log "Rollback-Hinweis:"
printf "UPDATE esp_devices SET status='%s', last_seen=%s, updated_at=%s, device_metadata='%s'::json WHERE device_id='%s';\n" \
  "$STATUS_BEFORE" \
  "$( [[ -n "$LAST_SEEN_BEFORE" ]] && printf "'%s'" "$LAST_SEEN_BEFORE" || printf "NULL" )" \
  "$( [[ -n "$UPDATED_BEFORE" ]] && printf "'%s'" "$UPDATED_BEFORE" || printf "NULL" )" \
  "$(printf '%s' "$METADATA_BEFORE" | sed "s/'/''/g")" \
  "$DEVICE_ID"
