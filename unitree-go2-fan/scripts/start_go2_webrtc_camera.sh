#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_ROOT="${GO2_ROS2_SDK_ROOT:-/home/star/go2_ros2_sdk}"

ACTION="start"
VIEW="${GO2_WEBRTC_VIEW:-true}"
ROBOT_IP="${ROBOT_IP:-${GO2_IP:-192.168.123.161}}"
VIEW_TOPIC="${GO2_WEBRTC_VIEW_TOPIC:-/camera/image_raw}"
WAIT_SECONDS="${GO2_WEBRTC_WAIT_SECONDS:-30}"
LOG_FILE="${GO2_WEBRTC_LOG:-/tmp/go2_webrtc_camera.log}"

truthy() {
  case "${1,,}" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

usage() {
  cat <<EOF
Usage:
  ./scripts/start_go2_webrtc_camera.sh [view:=true|false] [stop:=true] [robot_ip:=IP]

This starts go2_ros2_sdk over WebRTC and displays the Go2 front color camera.
It does not use SSH and does not start the D435i RealSense driver.

Default:
  ROBOT_IP=${ROBOT_IP}
  topic=${VIEW_TOPIC}

Examples:
  ./scripts/start_go2_webrtc_camera.sh
  ROBOT_IP=192.168.123.161 ./scripts/start_go2_webrtc_camera.sh
  ./scripts/start_go2_webrtc_camera.sh view:=false
  ./scripts/start_go2_webrtc_camera.sh stop:=true
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help|help)
      usage
      exit 0
      ;;
    stop|stop:=true)
      ACTION="stop"
      ;;
    view:=*)
      VIEW="${arg#view:=}"
      ;;
    robot_ip:=*)
      ROBOT_IP="${arg#robot_ip:=}"
      ;;
    view_topic:=*)
      VIEW_TOPIC="${arg#view_topic:=}"
      ;;
    *)
      echo "[unitree-go2-fan] Unknown argument: $arg" >&2
      usage
      exit 2
      ;;
  esac
done

source_sdk_env() {
  if [ ! -f "$SDK_ROOT/install/setup.bash" ]; then
    echo "[unitree-go2-fan] $SDK_ROOT/install/setup.bash not found."
    echo "[unitree-go2-fan] Build go2_ros2_sdk first."
    exit 1
  fi

  set +u
  # shellcheck source=/dev/null
  source /opt/ros/humble/setup.bash
  # shellcheck source=/dev/null
  source "$SDK_ROOT/install/setup.bash"
  set -u

  if ! ros2 pkg prefix go2_robot_sdk >/dev/null 2>&1; then
    echo "[unitree-go2-fan] go2_robot_sdk is not available in $SDK_ROOT/install."
    exit 1
  fi
}

source_fan_env() {
  set +u
  # shellcheck source=/dev/null
  source "$FAN_ROOT/scripts/setup_env.sh"
  set -u
}

stop_driver() {
  pkill -f "ros2 run go2_robot_sdk go2_driver_node" >/dev/null 2>&1 || true
  pkill -f "go2_robot_sdk.*go2_driver_node" >/dev/null 2>&1 || true
}

wait_for_topic() {
  local elapsed=0
  echo "[unitree-go2-fan] Waiting up to ${WAIT_SECONDS}s for first image on ${VIEW_TOPIC}"
  while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
    if timeout 1 ros2 topic echo "$VIEW_TOPIC" --once --field header >/dev/null 2>&1; then
      echo "[unitree-go2-fan] Received first image on ${VIEW_TOPIC}"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  if ros2 topic list 2>/dev/null | grep -Fxq "$VIEW_TOPIC"; then
    echo "[unitree-go2-fan] WARNING: ${VIEW_TOPIC} exists, but no image frame arrived within ${WAIT_SECONDS}s."
  else
    echo "[unitree-go2-fan] WARNING: ${VIEW_TOPIC} did not appear within ${WAIT_SECONDS}s."
  fi
  echo "[unitree-go2-fan] Driver log: ${LOG_FILE}"
}

start_driver_background() {
  source_sdk_env
  export ROBOT_IP
  export GO2_IP="${GO2_IP:-$ROBOT_IP}"
  export CONN_TYPE=webrtc
  export GO2_ENABLE_VIDEO=true
  export GO2_DECODE_LIDAR=false

  stop_driver
  echo "[unitree-go2-fan] Starting go2_ros2_sdk WebRTC camera at ROBOT_IP=${ROBOT_IP}"
  echo "[unitree-go2-fan] Log: ${LOG_FILE}"
  "$FAN_ROOT/scripts/go2_webrtc_driver.sh" >"$LOG_FILE" 2>&1 &
  DRIVER_PID=$!
}

if [ "$ACTION" = "stop" ]; then
  stop_driver
  exit 0
fi

if truthy "$VIEW"; then
  start_driver_background
  trap 'kill "$DRIVER_PID" >/dev/null 2>&1 || true' EXIT
  source_fan_env
  wait_for_topic
  "$FAN_ROOT/scripts/view_go2_camera.sh" "$VIEW_TOPIC"
else
  source_sdk_env
  export ROBOT_IP
  export GO2_IP="${GO2_IP:-$ROBOT_IP}"
  export CONN_TYPE=webrtc
  export GO2_ENABLE_VIDEO=true
  export GO2_DECODE_LIDAR=false
  exec "$FAN_ROOT/scripts/go2_webrtc_driver.sh"
fi
