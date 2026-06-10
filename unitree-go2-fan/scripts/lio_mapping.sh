#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source "$FAN_ROOT/scripts/setup_env.sh"
set -u

if [ "${UNITREE_GO2_FAN_KEEP_CYCLONEDDS_URI:-0}" != "1" ] \
  && [ -n "${CYCLONEDDS_URI:-}" ] \
  && [[ "$CYCLONEDDS_URI" == *'NetworkInterface name="eno1"'* ]] \
  && command -v ip >/dev/null 2>&1 \
  && ip -br addr show eno1 2>/dev/null | grep -q 'DOWN'; then
  unset CYCLONEDDS_URI
  echo "[unitree-go2-fan] eno1 is DOWN; unset CYCLONEDDS_URI for FAST-LIO2 local bring-up."
fi

ros2 launch go2_slam_nav fast_lio2.launch.py \
  use_rviz:=true \
  start_lidar_driver:=true \
  "$@"
