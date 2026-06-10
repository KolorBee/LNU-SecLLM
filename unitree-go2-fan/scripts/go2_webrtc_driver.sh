#!/usr/bin/env bash
set -euo pipefail

SDK_ROOT="${GO2_ROS2_SDK_ROOT:-/home/star/go2_ros2_sdk}"

case "${1:-}" in
  -h|--help|help)
    cat <<EOF
Usage:
  ./scripts/go2_webrtc_driver.sh [--ros-args ...]

Starts go2_ros2_sdk go2_driver_node over WebRTC.

Defaults:
  ROBOT_IP=${ROBOT_IP:-${GO2_IP:-192.168.123.161}}
  CONN_TYPE=webrtc
  GO2_ENABLE_VIDEO=true
  GO2_DECODE_LIDAR=false

For camera viewing, prefer:
  ./scripts/start_go2_webrtc_camera.sh
EOF
    exit 0
    ;;
esac

if [ ! -f "$SDK_ROOT/install/setup.bash" ]; then
  echo "[unitree-go2-fan] $SDK_ROOT/install/setup.bash not found."
  echo "[unitree-go2-fan] Build go2_ros2_sdk first, then run this script again."
  exit 1
fi

export ROBOT_IP="${ROBOT_IP:-${GO2_IP:-192.168.123.161}}"
export GO2_IP="${GO2_IP:-$ROBOT_IP}"

set +u
source /opt/ros/humble/setup.bash
source "$SDK_ROOT/install/setup.bash"
set -u

if ! ros2 pkg prefix go2_robot_sdk >/dev/null 2>&1; then
  echo "[unitree-go2-fan] go2_robot_sdk is not built in $SDK_ROOT/install."
  echo "[unitree-go2-fan] Build it with:"
  echo "  cd $SDK_ROOT"
  echo "  source /opt/ros/humble/setup.bash"
  echo "  colcon build --symlink-install --packages-select go2_robot_sdk"
  exit 1
fi

export CONN_TYPE="${CONN_TYPE:-webrtc}"

ros2 run go2_robot_sdk go2_driver_node \
  --ros-args \
  -p conn_type:="$CONN_TYPE" \
  -p enable_video:="${GO2_ENABLE_VIDEO:-true}" \
  -p decode_lidar:="${GO2_DECODE_LIDAR:-false}" \
  "$@"
