#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

set +u
# shellcheck source=/dev/null
source "$FAN_ROOT/scripts/setup_env.sh" >/dev/null
set -u

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'EOF'
Usage:
  ./scripts/record_lio_debug_bag.sh [duration_seconds] [output_bag_dir]

Examples:
  ./scripts/record_lio_debug_bag.sh
  ./scripts/record_lio_debug_bag.sh 60
  ./scripts/record_lio_debug_bag.sh 0 /home/star/go2_maps/debug_bags/manual_lio

Run this after the FAST-LIO2 launch is already running.
EOF
  exit 0
fi

duration="${1:-30}"
output="${2:-/home/star/go2_maps/debug_bags/fast_lio2_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$(dirname "$output")"

topics=(
  /lidar_points
  /points_raw
  /utlidar/imu
  /imu_lio
  /utlidar/robot_odom
  /odom_unitree_reference
  /lio_odom
  /lio_path
  /lio_cloud_registered
  /lio_cloud_base
  /tf
  /tf_static
  /joint_states
  /robot_description
)

echo "[record-lio] Output: $output"
echo "[record-lio] Duration: ${duration}s (0 means until Ctrl-C)"
echo "[record-lio] Tip: while recording, slowly walk or yaw the Go2 once if you are debugging direction/drift."

if [ "$duration" = "0" ]; then
  ros2 bag record -o "$output" "${topics[@]}"
else
  timeout "$duration" ros2 bag record -o "$output" "${topics[@]}"
fi
