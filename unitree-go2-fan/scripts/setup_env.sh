#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source_if_exists() {
  local file="$1"
  if [ -f "$file" ]; then
    set +u
    # shellcheck source=/dev/null
    source "$file"
    set -u
  fi
}

source_if_exists /opt/ros/humble/setup.bash
source_if_exists /home/star/unitree_ros2/setup_go2.sh
source_if_exists "$FAN_ROOT/install/setup.bash"

export UNITREE_GO2_FAN_ROOT="$FAN_ROOT"
echo "[unitree-go2-fan] root=$FAN_ROOT"

if [ "${UNITREE_GO2_FAN_SKIP_NET_CHECK:-0}" != "1" ] && command -v ip >/dev/null 2>&1; then
  HESAI_ROUTE="$(ip route get "${HESAI_LIDAR_IP:-192.168.1.201}" 2>/dev/null || true)"
  if [[ "$HESAI_ROUTE" != *"dev ${HESAI_IFACE:-eno1}"* || "$HESAI_ROUTE" != *"src ${HESAI_HOST_IP:-192.168.1.100}"* ]]; then
    echo "[unitree-go2-fan] WARNING: Hesai lidar route is not ready:"
    echo "[unitree-go2-fan]   $HESAI_ROUTE"
    echo "[unitree-go2-fan] Run: $FAN_ROOT/scripts/setup_hesai_network.sh"
  fi
fi
