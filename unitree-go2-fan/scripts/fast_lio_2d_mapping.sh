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
  echo "[unitree-go2-fan] eno1 is DOWN; unset CYCLONEDDS_URI for local FAST-LIO bring-up."
fi

args=()
replace_existing=false

for arg in "$@"; do
  case "$arg" in
    replace_existing:=true|replace_existing:=1|replace_existing:=yes|replace_existing:=on)
      replace_existing=true
      ;;
    replace_existing:=false|replace_existing:=0|replace_existing:=no|replace_existing:=off)
      replace_existing=false
      ;;
    replace_existing:=*)
      echo "[unitree-go2-fan] Unsupported replace_existing value: ${arg#replace_existing:=}" >&2
      echo "[unitree-go2-fan] Use replace_existing:=true or replace_existing:=false." >&2
      exit 2
      ;;
    *)
      args+=("$arg")
      ;;
  esac
done

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

launch_arg_value() {
  local name="$1"
  local arg
  for arg in "${args[@]}"; do
    if [[ "$arg" == "$name:="* ]]; then
      printf '%s\n' "${arg#"$name":=}"
      return 0
    fi
  done
  return 1
}

find_existing_mapping_pids() {
  local start_lidar_driver_value="${1:-true}"
  local pattern='[r]os2 launch go2_slam_nav fast_lio_2d_mapping.launch.py|[s]park_lio_mapping|[g]o2_lio_cloud_map_accumulator|[g]o2_lio_grid_mapper'
  if [[ "$start_lidar_driver_value" != "false" ]]; then
    pattern+='|[h]esai_ros_driver_node'
  fi
  pgrep -f "$pattern" || true
}

stop_existing_mapping_stack() {
  local pids=("$@")
  [ "${#pids[@]}" -gt 0 ] || return 0

  echo "[unitree-go2-fan] Stopping existing FAST-LIO mapping stack: ${pids[*]}"
  kill -INT "${pids[@]}" 2>/dev/null || true
  sleep 3

  local remaining=()
  local pid
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      remaining+=("$pid")
    fi
  done
  if [ "${#remaining[@]}" -gt 0 ]; then
    kill -TERM "${remaining[@]}" 2>/dev/null || true
    sleep 2
  fi

  remaining=()
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      remaining+=("$pid")
    fi
  done
  if [ "${#remaining[@]}" -gt 0 ]; then
    echo "[unitree-go2-fan] Force stopping stale FAST-LIO mapping processes: ${remaining[*]}"
    kill -KILL "${remaining[@]}" 2>/dev/null || true
  fi
}

launch_args=()
has_launch_arg use_rviz || launch_args+=("use_rviz:=true")
has_launch_arg start_lidar_driver || launch_args+=("start_lidar_driver:=true")
has_launch_arg restart_map || launch_args+=("restart_map:=true")

start_lidar_driver_value="$(launch_arg_value start_lidar_driver || true)"
start_lidar_driver_value="${start_lidar_driver_value:-true}"
mapfile -t existing_pids < <(find_existing_mapping_pids "$start_lidar_driver_value")

if [ "${#existing_pids[@]}" -gt 0 ]; then
  if [ "$replace_existing" = "true" ]; then
    stop_existing_mapping_stack "${existing_pids[@]}"
  else
    echo "[unitree-go2-fan] Existing FAST-LIO mapping processes are still running:" >&2
    ps -p "$(IFS=,; echo "${existing_pids[*]}")" -o pid=,args= >&2 || true
    echo >&2
    echo "[unitree-go2-fan] Stop the old mapping terminal first, or start a fresh map with:" >&2
    echo "[unitree-go2-fan]   ./scripts/fast_lio_2d_mapping.sh replace_existing:=true restart_map:=true" >&2
    echo >&2
    echo "[unitree-go2-fan] This guard prevents RViz from showing the previous in-memory map." >&2
    exit 2
  fi
fi

ros2 launch go2_slam_nav fast_lio_2d_mapping.launch.py \
  "${launch_args[@]}" \
  "${args[@]}"
