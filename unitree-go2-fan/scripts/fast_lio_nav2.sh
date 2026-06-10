#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source "$FAN_ROOT/scripts/setup_env.sh"
set -u

args=("$@")

has_launch_arg() {
  local name="$1"
  local arg
  for arg in "${args[@]}"; do
    if [[ "$arg" == "$name:="* ]]; then
      return 0
    fi
  done
  return 1
}

launch_args=()
has_launch_arg use_rviz || launch_args+=("use_rviz:=true")
has_launch_arg start_lidar_driver || launch_args+=("start_lidar_driver:=true")
has_launch_arg start_go2_cmd_bridge || launch_args+=("start_go2_cmd_bridge:=false")

ros2 launch go2_slam_nav fast_lio_nav2.launch.py \
  "${launch_args[@]}" \
  "${args[@]}"
