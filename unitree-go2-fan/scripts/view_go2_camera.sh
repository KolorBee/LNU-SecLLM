#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source "$FAN_ROOT/scripts/setup_env.sh"
set -u

TOPIC="${1:-auto}"

ros2 run go2_slam_nav go2_camera_viewer \
  --ros-args \
  -p image_topic:="$TOPIC" \
  "${@:2}"
