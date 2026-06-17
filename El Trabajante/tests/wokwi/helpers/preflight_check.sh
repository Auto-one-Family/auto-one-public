#!/bin/bash
# Wokwi MQTT Pre-Flight Check
# Verifies all prerequisites for Wokwi MQTT connectivity
# Usage: bash preflight_check.sh
#
# 3 Prerequisites:
# 1. No local Mosquitto service blocking port 1883
# 2. Docker Mosquitto with port 1883 PUBLISHED (not just exposed)
# 3. MQTT broker reachable on localhost:1883

set -e

PASS=0
FAIL=0
WARN=0

echo "=== Wokwi MQTT Pre-Flight Check ==="
echo ""

# Check 1: Local Mosquitto service
echo -n "[1/3] Local Mosquitto service... "
if command -v pgrep &>/dev/null && pgrep -x mosquitto &>/dev/null; then
    echo "FAIL - Local Mosquitto running (stop with: net stop mosquitto)"
    FAIL=$((FAIL + 1))
elif command -v tasklist.exe &>/dev/null && tasklist.exe 2>/dev/null | grep -qi "mosquitto.exe"; then
    echo "FAIL - Mosquitto.exe running (stop in Services or: net stop mosquitto)"
    FAIL=$((FAIL + 1))
else
    echo "OK - No local Mosquitto detected"
    PASS=$((PASS + 1))
fi

# Check 2: Docker Mosquitto port published
echo -n "[2/3] Docker Mosquitto port 1883... "
if ! command -v docker &>/dev/null; then
    echo "WARN - Docker not found in PATH"
    WARN=$((WARN + 1))
elif ! docker info &>/dev/null 2>&1; then
    echo "WARN - Docker not running"
    WARN=$((WARN + 1))
else
    DOCKER_PORT=$(docker ps --format '{{.Ports}}' --filter 'name=mosquitto' 2>/dev/null | grep '0.0.0.0:1883')
    if [ -z "$DOCKER_PORT" ]; then
        # Also check by image name
        DOCKER_PORT=$(docker ps --format '{{.Ports}}' --filter 'ancestor=eclipse-mosquitto' 2>/dev/null | grep '0.0.0.0:1883')
    fi
    if [ -n "$DOCKER_PORT" ]; then
        echo "OK - $DOCKER_PORT"
        PASS=$((PASS + 1))
    else
        echo "FAIL - Port 1883 not published. Run: docker compose up -d mqtt-broker"
        FAIL=$((FAIL + 1))
    fi
fi

# Check 3: MQTT connectivity
echo -n "[3/3] MQTT connectivity... "
if command -v mosquitto_pub &>/dev/null; then
    if mosquitto_pub -h localhost -p 1883 -t "wokwi/preflight" -m "check" 2>/dev/null; then
        echo "OK - MQTT broker reachable"
        PASS=$((PASS + 1))
    else
        echo "FAIL - Cannot connect. Check firewall (port 1883 inbound)"
        FAIL=$((FAIL + 1))
    fi
else
    echo "WARN - mosquitto_pub not installed (install: apt install mosquitto-clients)"
    WARN=$((WARN + 1))
fi

echo ""
echo "=== Result: $PASS/3 passed, $FAIL failed, $WARN warnings ==="

if [ $FAIL -gt 0 ]; then
    echo "ABORT - Fix issues above before running Wokwi tests"
    exit 1
fi

if [ $WARN -gt 0 ]; then
    echo "CAUTION - Warnings present, tests may fail"
    exit 0
fi

echo "READY - All checks passed"
exit 0
