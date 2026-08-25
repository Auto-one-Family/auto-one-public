#!/usr/bin/env bash
#
# Host dual-homing: eth0 as secondary LAN (DHCP), no default route.
# wlan0 remains the sole internet and SSH path.
#
# Prerequisite: Ethernet cable on eth0, link must be LOWER_UP (no NO-CARRIER).
#
# Run: sudo ./scripts/network/setup_secondary_lan.sh
#
set -euo pipefail

CON_NAME="ao-secondary-lan"
IFACE="eth0"

die() { echo "FEHLER: $*" >&2; exit 1; }

if [[ "${EUID:-0}" -ne 0 ]]; then
  die "Root nötig — bitte: sudo $0"
fi

command -v nmcli >/dev/null 2>&1 || die "nmcli nicht gefunden (NetworkManager installiert?)"
command -v ip >/dev/null 2>&1 || die "ip nicht gefunden"

[[ -d "/sys/class/net/${IFACE}" ]] || die "Interface ${IFACE} existiert nicht"

if ip link show "${IFACE}" 2>/dev/null | grep -q "NO-CARRIER"; then
  die "Interface ${IFACE}: NO-CARRIER — LAN-Kabel anschließen und erneut ausführen."
fi
if [[ -r "/sys/class/net/${IFACE}/carrier" ]]; then
  c="$(cat "/sys/class/net/${IFACE}/carrier" 2>/dev/null || echo 0)"
  [[ "$c" == "1" ]] || die "Kein Ethernet-Link auf ${IFACE} (carrier=0). Kabel prüfen."
fi

echo "==> Profil ${CON_NAME} auf ${IFACE} (DHCP, ipv4.never-default=yes, IPv6 aus)"

if nmcli -t -f NAME connection show 2>/dev/null | grep -qx "${CON_NAME}"; then
  nmcli connection modify "${CON_NAME}" \
    connection.interface-name "${IFACE}" \
    ipv4.method auto \
    ipv4.never-default yes \
    ipv6.method ignore \
    connection.autoconnect yes
else
  nmcli connection add type ethernet con-name "${CON_NAME}" ifname "${IFACE}" \
    ipv4.method auto \
    ipv4.never-default yes \
    ipv6.method ignore \
    connection.autoconnect yes
fi

nmcli connection up "${CON_NAME}" ifname "${IFACE}"

echo ""
echo "==> Adresse ${IFACE}"
ip -4 addr show "${IFACE}" || true

echo ""
echo "==> Default-Routen (soll NICHT dev eth0 enthalten)"
ip -4 route show default || true

if ip -4 route show default | grep -q "dev ${IFACE}"; then
  die "Default-Route zeigt auf ${IFACE} — Abbruch. Prüfe ipv4.never-default am Profil ${CON_NAME}."
fi

if ! ip -4 route show default | grep -q .; then
  die "Keine Default-Route gefunden — Internet wäre weg. wlan0 prüfen."
fi

ETH_IP="$(ip -4 -o addr show "${IFACE}" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)"
echo ""
echo "OK — Dual-Homing aktiv (Default-Route unverändert, ${IFACE} nur LAN)."
if [[ -n "${ETH_IP}" ]]; then
  echo ""
  echo "Host im secondary LAN (eth0): ${ETH_IP}"
  echo "ESP MQTT/Server-Adresse (NVS): ${ETH_IP}  (nicht die wlan0-Adresse)"
  echo ""
  echo ".env (Beispiel, Anführungszeichen beachten):"
  echo "  VITE_API_URL=http://${ETH_IP}:8000"
  echo "  VITE_WS_URL=ws://${ETH_IP}:8000"
  echo "  CORS_ALLOWED_ORIGINS=[\"http://localhost:5173\",\"http://localhost:3000\",\"http://${ETH_IP}:5173\"]"
  echo ""
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  echo "Danach: cd ${PROJECT_ROOT} && docker compose up -d"
fi
