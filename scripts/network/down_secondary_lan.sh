#!/usr/bin/env bash
# Deactivate the eth0 profile ao-secondary-lan (rollback / end of test).
# Run: sudo ./scripts/network/down_secondary_lan.sh
set -euo pipefail
CON_NAME="ao-secondary-lan"

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "FEHLER: Root nötig — sudo $0" >&2
  exit 1
fi

if nmcli -t -f NAME connection show 2>/dev/null | grep -qx "${CON_NAME}"; then
  nmcli connection down "${CON_NAME}" || true
  echo "Profil ${CON_NAME} ist down."
else
  echo "Profil ${CON_NAME} existiert nicht — nichts zu tun."
fi
