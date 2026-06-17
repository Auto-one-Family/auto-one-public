#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ci_mqtt_contract.sh start-broker [--job <github_job>] [--template basis|extended] [--timeout-seconds 30]

Notes:
  - If --template is set, it wins.
  - If only --job is set, template is mapped by contract policy.
EOF
}

log() {
  echo "[contract][$(date +%H:%M:%S)] $*"
}

map_template_from_job() {
  local job_name="$1"
  case "$job_name" in
    boot-tests|sensor-tests|mqtt-connection-test|gpio-core-tests|i2c-core-tests|nvs-core-tests|pwm-core-tests)
      echo "basis"
      ;;
    *)
      echo "extended"
      ;;
  esac
}

write_config() {
  local template="$1"
  mkdir -p /tmp/mosquitto
  case "$template" in
    basis)
      cat > /tmp/mosquitto/mosquitto.conf <<'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
      ;;
    extended)
      cat > /tmp/mosquitto/mosquitto.conf <<'EOF'
listener 1883 0.0.0.0
allow_anonymous true
log_type all
connection_messages true
EOF
      ;;
    *)
      echo "Unknown template: $template" >&2
      exit 2
      ;;
  esac
}

wait_for_broker() {
  local timeout_seconds="$1"
  local probe_topic="health/check"
  local ready="false"

  for i in $(seq 1 "$timeout_seconds"); do
    if docker exec mosquitto mosquitto_pub -t "$probe_topic" -m "ping-$i" >/tmp/mqtt-contract-ready.log 2>&1; then
      ready="true"
      log "Broker ready after ${i}s"
      break
    fi
    sleep 1
  done

  if [[ "$ready" != "true" ]]; then
    log "Broker readiness timeout after ${timeout_seconds}s"
    docker ps -a --filter name=mosquitto || true
    docker logs --tail 200 mosquitto || true
    exit 30
  fi
}

start_broker() {
  local job_name=""
  local template=""
  local timeout_seconds=30

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --job)
        job_name="${2:-}"
        shift 2
        ;;
      --template)
        template="${2:-}"
        shift 2
        ;;
      --timeout-seconds)
        timeout_seconds="${2:-30}"
        shift 2
        ;;
      *)
        echo "Unknown argument: $1" >&2
        exit 2
        ;;
    esac
  done

  if [[ -z "$template" ]]; then
    template="$(map_template_from_job "$job_name")"
  fi

  log "Starting broker with template=$template job=${job_name:-unknown}"

  docker rm -f mosquitto >/dev/null 2>&1 || true
  write_config "$template"
  docker run -d \
    --name mosquitto \
    -p 1883:1883 \
    -v /tmp/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro \
    eclipse-mosquitto:2 >/tmp/mqtt-contract-container-id.txt

  wait_for_broker "$timeout_seconds"
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

command="$1"
shift
case "$command" in
  start-broker)
    start_broker "$@"
    ;;
  *)
    usage
    exit 2
    ;;
esac
