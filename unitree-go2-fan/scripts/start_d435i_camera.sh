#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE="${D435I_MODE:-auto}"
ACTION="start"
VIEW="${D435I_VIEW:-true}"
ORIN_HOST_WAS_SET=0
if [ -n "${ORIN_HOST+x}" ]; then
  ORIN_HOST_WAS_SET=1
fi
ORIN_HOST="${ORIN_HOST:-192.168.123.18}"
ORIN_FALLBACK_HOSTS="${ORIN_FALLBACK_HOSTS:-}"
ORIN_USER="${ORIN_USER:-unitree}"
ORIN_ROS_SETUP="${ORIN_ROS_SETUP:-/opt/ros/humble/setup.bash}"
ORIN_EXTRA_SETUP="${ORIN_EXTRA_SETUP:-}"
REMOTE_BACKEND="${D435I_REMOTE_BACKEND:-ssh_stream}"
VIEW_TOPIC="${D435I_VIEW_TOPIC:-/camera/color/image_raw}"
WAIT_SECONDS="${D435I_WAIT_SECONDS:-30}"
REMOTE_LOG="${D435I_REMOTE_LOG:-/tmp/go2_d435i_camera.log}"
LOCAL_LOG="${D435I_LOCAL_LOG:-/tmp/go2_d435i_camera.log}"

CAMERA_NAMESPACE="${D435I_CAMERA_NAMESPACE:-}"
CAMERA_NAME="${D435I_CAMERA_NAME:-camera}"
DEVICE_TYPE="${D435I_DEVICE_TYPE:-d435i}"
SERIAL_NO="${D435I_SERIAL_NO:-}"
USB_PORT_ID="${D435I_USB_PORT_ID:-}"
COLOR_PROFILE="${D435I_COLOR_PROFILE:-640,480,15}"
DEPTH_PROFILE="${D435I_DEPTH_PROFILE:-640,480,15}"
ENABLE_COLOR="${D435I_ENABLE_COLOR:-true}"
ENABLE_DEPTH="${D435I_ENABLE_DEPTH:-true}"
ENABLE_INFRA1="${D435I_ENABLE_INFRA1:-false}"
ENABLE_INFRA2="${D435I_ENABLE_INFRA2:-false}"
ENABLE_GYRO="${D435I_ENABLE_GYRO:-true}"
ENABLE_ACCEL="${D435I_ENABLE_ACCEL:-true}"
ENABLE_SYNC="${D435I_ENABLE_SYNC:-true}"
ENABLE_RGBD="${D435I_ENABLE_RGBD:-true}"
ALIGN_DEPTH="${D435I_ALIGN_DEPTH:-true}"
POINTCLOUD_ENABLE="${D435I_POINTCLOUD:-true}"
UNITE_IMU_METHOD="${D435I_UNITE_IMU_METHOD:-2}"
INITIAL_RESET="${D435I_INITIAL_RESET:-true}"
PUBLISH_TF="${D435I_PUBLISH_TF:-true}"

USER_RS_ARGS=()

truthy() {
  case "${1,,}" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

has_local_realsense_usb() {
  command -v lsusb >/dev/null 2>&1 && lsusb | grep -qiE 'RealSense|8086:0b|8086:0ad|Intel.*Depth'
}

usage() {
  cat <<EOF
Usage:
  ./scripts/start_d435i_camera.sh [mode:=auto|local|ssh] [view:=true|false] [stop:=true] [realsense_arg:=value ...]

Common examples:
  ./scripts/start_d435i_camera.sh
  ORIN_HOST=192.168.123.18 ORIN_USER=unitree ./scripts/start_d435i_camera.sh
  ./scripts/start_d435i_camera.sh view:=false
  ./scripts/start_d435i_camera.sh stop:=true

Default remote display windows with D435I_REMOTE_BACKEND=ssh_stream:
  d435i_color, d435i_depth, d435i_infra1

ROS2 topics are only created by local mode or D435I_REMOTE_BACKEND=ros2:
  ${VIEW_TOPIC}
  /camera/depth/image_rect_raw
  /camera/depth/color/points
  /camera/imu

Environment knobs:
  ORIN_HOST, ORIN_FALLBACK_HOSTS, ORIN_USER, ORIN_ROS_SETUP, ORIN_EXTRA_SETUP
  D435I_REMOTE_BACKEND=ssh_stream|ros2
  D435I_WIDTH, D435I_HEIGHT, D435I_FPS, D435I_STREAMS, D435I_JPEG_QUALITY
  D435I_COLOR_PROFILE, D435I_DEPTH_PROFILE, D435I_POINTCLOUD, D435I_VIEW_TOPIC

Note:
  Go2 EDU D435i is attached to the Orin at 192.168.123.18. By default this
  script displays it over SSH because the Orin has ROS1 Noetic RealSense
  installed, not a ROS2 RealSense node.
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
    mode:=*)
      MODE="${arg#mode:=}"
      ;;
    view:=*)
      VIEW="${arg#view:=}"
      ;;
    orin_host:=*)
      ORIN_HOST="${arg#orin_host:=}"
      ORIN_HOST_WAS_SET=1
      ;;
    orin_user:=*)
      ORIN_USER="${arg#orin_user:=}"
      ;;
    view_topic:=*)
      VIEW_TOPIC="${arg#view_topic:=}"
      ;;
    *)
      USER_RS_ARGS+=("$arg")
      ;;
  esac
done

source_local_env() {
  set +u
  # shellcheck source=/dev/null
  source "$FAN_ROOT/scripts/setup_env.sh"
  set -u
}

build_rs_args() {
  RS_ARGS=(
    ros2 run realsense2_camera realsense2_camera_node
    --ros-args
    -r "__node:=${CAMERA_NAME}"
    -p "device_type:=${DEVICE_TYPE}"
    -p "initial_reset:=${INITIAL_RESET}"
    -p "enable_color:=${ENABLE_COLOR}"
    -p "enable_depth:=${ENABLE_DEPTH}"
    -p "enable_infra1:=${ENABLE_INFRA1}"
    -p "enable_infra2:=${ENABLE_INFRA2}"
    -p "enable_gyro:=${ENABLE_GYRO}"
    -p "enable_accel:=${ENABLE_ACCEL}"
    -p "enable_sync:=${ENABLE_SYNC}"
    -p "enable_rgbd:=${ENABLE_RGBD}"
    -p "unite_imu_method:=${UNITE_IMU_METHOD}"
    -p "rgb_camera.color_profile:=${COLOR_PROFILE}"
    -p "depth_module.depth_profile:=${DEPTH_PROFILE}"
    -p "align_depth.enable:=${ALIGN_DEPTH}"
    -p "pointcloud.enable:=${POINTCLOUD_ENABLE}"
    -p "publish_tf:=${PUBLISH_TF}"
  )
  if [ -n "$CAMERA_NAMESPACE" ]; then
    RS_ARGS+=(-r "__ns:=${CAMERA_NAMESPACE}")
  fi
  if [ -n "$SERIAL_NO" ]; then
    RS_ARGS+=(-p "serial_no:=${SERIAL_NO}")
  fi
  if [ -n "$USB_PORT_ID" ]; then
    RS_ARGS+=(-p "usb_port_id:=${USB_PORT_ID}")
  fi
  local arg
  for arg in "${USER_RS_ARGS[@]}"; do
    if [[ "$arg" == *":="* ]]; then
      RS_ARGS+=(-p "$arg")
    else
      RS_ARGS+=("$arg")
    fi
  done
}

shell_join() {
  local out=()
  local arg
  for arg in "$@"; do
    out+=("$(printf "%q" "$arg")")
  done
  printf "%s " "${out[@]}"
}

choose_mode() {
  case "$MODE" in
    local|ssh)
      printf "%s" "$MODE"
      ;;
    auto)
      if has_local_realsense_usb; then
        printf "local"
      else
        printf "ssh"
      fi
      ;;
    *)
      echo "[unitree-go2-fan] unknown mode: $MODE" >&2
      exit 2
      ;;
  esac
}

tcp_ssh_open() {
  local host="$1"
  timeout 1 bash -c ":</dev/tcp/${host}/22" >/dev/null 2>&1
}

select_remote_host() {
  local candidate
  if [ "$ORIN_HOST_WAS_SET" = "1" ]; then
    printf "%s" "$ORIN_HOST"
    return 0
  fi

  for candidate in "$ORIN_HOST" $ORIN_FALLBACK_HOSTS; do
    if tcp_ssh_open "$candidate"; then
      if [ "$candidate" != "$ORIN_HOST" ]; then
        echo "[unitree-go2-fan] ${ORIN_HOST}:22 is not open; falling back to ${candidate}" >&2
      fi
      printf "%s" "$candidate"
      return 0
    fi
  done

  echo "[unitree-go2-fan] WARNING: no SSH port detected on ${ORIN_HOST} ${ORIN_FALLBACK_HOSTS}; using ${ORIN_HOST}" >&2
  printf "%s" "$ORIN_HOST"
}

stop_local() {
  pkill -f "ros2 run realsense2_camera realsense2_camera_node" >/dev/null 2>&1 || true
  pkill -f "realsense2_camera realsense2_camera_node" >/dev/null 2>&1 || true
  pkill -f "realsense2_camera_node" >/dev/null 2>&1 || true
}

stop_remote() {
  local host target
  host="$(select_remote_host)"
  target="${ORIN_USER}@${host}"
  local remote_script
  remote_script='pkill -f "/tmp/go2_d435i_streamer" >/dev/null 2>&1 || true; pkill -f "ros2 run realsense2_camera realsense2_camera_node" >/dev/null 2>&1 || true; pkill -f "realsense2_camera realsense2_camera_node" >/dev/null 2>&1 || true; pkill -f "realsense2_camera_node" >/dev/null 2>&1 || true; echo "[go2-d435i] stopped remote RealSense processes"'
  ssh -t "$target" "bash -lc $(printf "%q" "$remote_script")"
}

start_local() {
  source_local_env
  if ! ros2 pkg prefix realsense2_camera >/dev/null 2>&1; then
    echo "[unitree-go2-fan] realsense2_camera is not installed locally."
    echo "Install it with: sudo apt install ros-humble-realsense2-camera"
    exit 3
  fi
  if ! has_local_realsense_usb; then
    echo "[unitree-go2-fan] WARNING: no local RealSense USB device was detected."
    echo "[unitree-go2-fan] The driver will wait for a device unless you stop it."
  fi

  build_rs_args
  if truthy "$VIEW"; then
    stop_local
    echo "[unitree-go2-fan] Starting local D435i driver; log: $LOCAL_LOG"
    "${RS_ARGS[@]}" >"$LOCAL_LOG" 2>&1 &
    LOCAL_PID=$!
    trap 'kill "$LOCAL_PID" >/dev/null 2>&1 || true' EXIT
    wait_for_topic
    "$FAN_ROOT/scripts/view_go2_camera.sh" "$VIEW_TOPIC"
  else
    exec "${RS_ARGS[@]}"
  fi
}

start_remote() {
  local host target
  local launch_cmd remote_script ros_domain rmw

  source_local_env
  host="$(select_remote_host)"
  target="${ORIN_USER}@${host}"

  if [ "$REMOTE_BACKEND" = "ssh_stream" ]; then
    if ! truthy "$VIEW"; then
      echo "[unitree-go2-fan] D435I_REMOTE_BACKEND=ssh_stream is a viewer backend; ignoring view:=false."
    fi
    echo "[unitree-go2-fan] Displaying Orin-attached D435i over SSH from ${target}"
    echo "[unitree-go2-fan] If SSH asks for a password, enter the Orin password."
    exec "$FAN_ROOT/scripts/view_d435i_over_ssh.sh" --host "$host" --user "$ORIN_USER"
  fi

  if [ "$REMOTE_BACKEND" != "ros2" ]; then
    echo "[unitree-go2-fan] unknown D435I_REMOTE_BACKEND: $REMOTE_BACKEND" >&2
    exit 2
  fi

  build_rs_args
  launch_cmd="$(shell_join "${RS_ARGS[@]}")"
  ros_domain="${ROS_DOMAIN_ID:-0}"
  rmw="${RMW_IMPLEMENTATION:-}"

  remote_script=$(cat <<EOF
set -euo pipefail
if [ ! -f "$ORIN_ROS_SETUP" ]; then
  echo "[go2-d435i] ROS setup not found on Orin: $ORIN_ROS_SETUP"
  exit 4
fi
set +u
source "$ORIN_ROS_SETUP"
if [ -n "$ORIN_EXTRA_SETUP" ] && [ -f "$ORIN_EXTRA_SETUP" ]; then
  source "$ORIN_EXTRA_SETUP"
fi
set -u
export ROS_DOMAIN_ID="$ros_domain"
if [ -n "$rmw" ]; then export RMW_IMPLEMENTATION="$rmw"; fi
if ! ros2 pkg prefix realsense2_camera >/dev/null 2>&1; then
  echo "[go2-d435i] realsense2_camera is not installed on Orin."
  echo "[go2-d435i] Install on Orin: sudo apt install ros-humble-realsense2-camera"
  exit 5
fi
if command -v lsusb >/dev/null 2>&1 && ! lsusb | grep -qiE 'RealSense|8086:0b|8086:0ad|Intel.*Depth'; then
  echo "[go2-d435i] WARNING: no RealSense USB device detected on Orin."
fi
pkill -f "ros2 run realsense2_camera realsense2_camera_node" >/dev/null 2>&1 || true
pkill -f "realsense2_camera realsense2_camera_node" >/dev/null 2>&1 || true
pkill -f "realsense2_camera_node" >/dev/null 2>&1 || true
nohup bash -lc 'exec $launch_cmd' > "$REMOTE_LOG" 2>&1 < /dev/null &
echo "[go2-d435i] started remote D435i driver on $target"
echo "[go2-d435i] remote log: $REMOTE_LOG"
EOF
)

  echo "[unitree-go2-fan] Starting D435i driver on ${target}"
  echo "[unitree-go2-fan] If SSH asks for a password, enter the Orin password."
  ssh -t "$target" "bash -lc $(printf "%q" "$remote_script")"

  if truthy "$VIEW"; then
    wait_for_topic
    "$FAN_ROOT/scripts/view_go2_camera.sh" "$VIEW_TOPIC"
  else
    echo "[unitree-go2-fan] View disabled. Check topics with:"
    echo "  ros2 topic list | grep -E 'camera|depth|infra|color|imu'"
  fi
}

wait_for_topic() {
  local elapsed=0
  echo "[unitree-go2-fan] Waiting up to ${WAIT_SECONDS}s for ${VIEW_TOPIC}"
  while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
    if ros2 topic list 2>/dev/null | grep -Fxq "$VIEW_TOPIC"; then
      echo "[unitree-go2-fan] Found ${VIEW_TOPIC}"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  echo "[unitree-go2-fan] WARNING: ${VIEW_TOPIC} did not appear within ${WAIT_SECONDS}s."
  echo "[unitree-go2-fan] The viewer will still start; use Ctrl+C to close it."
}

RUN_MODE="$(choose_mode)"

if [ "$ACTION" = "stop" ]; then
  if [ "$RUN_MODE" = "local" ]; then
    source_local_env
    stop_local
  else
    stop_remote
  fi
  exit 0
fi

if [ "$RUN_MODE" = "local" ]; then
  start_local
else
  start_remote
fi
