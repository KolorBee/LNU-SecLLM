#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
MAP_DIR="${1:-$FAN_ROOT/maps}"
MAP_NAME="${2:-go2_fan_$STAMP}"
RTABMAP_DB="${RTABMAP_DB:-$HOME/.ros/rtabmap.db}"

set +u
source "$FAN_ROOT/scripts/setup_env.sh"
set -u

mkdir -p "$MAP_DIR"

echo "[save_maps] saving 2D occupancy map to $MAP_DIR/$MAP_NAME.{yaml,pgm}"
ros2 run nav2_map_server map_saver_cli -f "$MAP_DIR/$MAP_NAME"

if [[ -f "$RTABMAP_DB" ]]; then
  echo "[save_maps] copying RTAB-Map database to $MAP_DIR/${MAP_NAME}.db"
  cp "$RTABMAP_DB" "$MAP_DIR/${MAP_NAME}.db"
else
  echo "[save_maps] RTAB-Map database not found at $RTABMAP_DB" >&2
fi

echo "[save_maps] done"
