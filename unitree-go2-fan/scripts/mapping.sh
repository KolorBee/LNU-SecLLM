#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source "$FAN_ROOT/scripts/setup_env.sh"
set -u

ros2 launch go2_slam_nav mapping.launch.py \
  use_rviz:=true \
  use_rtabmapviz:=false \
  restart_map:=true \
  localize_only:=false \
  "$@"
