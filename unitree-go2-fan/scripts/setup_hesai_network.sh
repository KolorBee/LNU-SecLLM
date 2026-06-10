#!/usr/bin/env bash
set -euo pipefail

IFACE="${1:-eno1}"
HOST_IP="${HESAI_HOST_IP:-192.168.1.100}"
LIDAR_IP="${HESAI_LIDAR_IP:-192.168.1.201}"

if [ "$(id -u)" -ne 0 ]; then
  exec sudo HESAI_HOST_IP="$HOST_IP" HESAI_LIDAR_IP="$LIDAR_IP" "$0" "$IFACE"
fi

if ! ip link show "$IFACE" >/dev/null 2>&1; then
  echo "[hesai-net] ERROR: interface '$IFACE' not found" >&2
  exit 1
fi

ip link set "$IFACE" up

if ! ip -4 addr show dev "$IFACE" | grep -q "\\b${HOST_IP}/"; then
  ip addr add "${HOST_IP}/24" dev "$IFACE"
fi

ip route replace 192.168.1.0/24 dev "$IFACE" src "$HOST_IP" metric 50

echo "[hesai-net] configured $IFACE with $HOST_IP/24 for lidar $LIDAR_IP"
ip route get "$LIDAR_IP"
