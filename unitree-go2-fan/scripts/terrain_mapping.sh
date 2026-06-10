#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

set +u
source "${REPO_ROOT}/scripts/setup_env.sh"
set -u

start_fast_lio=true
replace_existing=false
terrain_args=()
fast_lio_args=()

as_bool_arg() {
  case "$1" in
    true|1|yes|on) return 0 ;;
    false|0|no|off) return 1 ;;
    *)
      echo "[unitree-go2-fan] Unsupported boolean value: $1" >&2
      exit 2
      ;;
  esac
}

topic_has_publisher() {
  local topic="$1"
  local info count
  info="$(ros2 topic info "$topic" 2>/dev/null || true)"
  count="$(printf '%s\n' "$info" | awk '/Publisher count:/ {print $3; exit}')"
  [ -n "$count" ] && [ "$count" -gt 0 ]
}

find_existing_fast_lio_pids() {
  local pattern='[r]os2 launch go2_slam_nav fast_lio_2d_mapping.launch.py|[r]os2 launch go2_slam_nav fast_lio_nav2.launch.py|[s]park_lio_mapping|[g]o2_lio_cloud_map_accumulator|[g]o2_lio_grid_mapper|[h]esai_ros_driver_node'
  pgrep -f "$pattern" || true
}

stop_existing_fast_lio_stack() {
  local pids=("$@")
  [ "${#pids[@]}" -gt 0 ] || return 0

  echo "[unitree-go2-fan] Stopping existing FAST-LIO stack: ${pids[*]}"
  kill -INT "${pids[@]}" 2>/dev/null || true
  sleep 3
  kill -TERM "${pids[@]}" 2>/dev/null || true
  sleep 1
  kill -KILL "${pids[@]}" 2>/dev/null || true
}

has_fast_lio_arg() {
  local name="$1"
  local arg
  for arg in "${fast_lio_args[@]}"; do
    if [[ "$arg" == "$name:="* ]]; then
      return 0
    fi
  done
  return 1
}

for arg in "$@"; do
  case "$arg" in
    start_fast_lio:=*)
      if as_bool_arg "${arg#start_fast_lio:=}"; then
        start_fast_lio=true
      else
        start_fast_lio=false
      fi
      ;;
    replace_existing:=*)
      if as_bool_arg "${arg#replace_existing:=}"; then
        replace_existing=true
      else
        replace_existing=false
      fi
      ;;
    start_lidar_driver:=*|restart_map:=*|lidar_topic:=*|lidar_tf_x:=*|lidar_tf_y:=*|lidar_tf_z:=*|lidar_tf_roll:=*|lidar_tf_pitch:=*|lidar_tf_yaw:=*|publish_static_joint_states:=*|publish_lowstate_joint_states:=*|lowstate_topic:=*|joint_states_topic:=*|lio_cloud_map_topic:=*|lio_cloud_map_input_rate:=*|lio_cloud_map_publish_rate:=*|lio_cloud_map_voxel_size:=*|lio_cloud_map_max_points:=*|save_lio_cloud_map_on_shutdown:=*)
      fast_lio_args+=("$arg")
      ;;
    *)
      terrain_args+=("$arg")
      ;;
  esac
done

fast_lio_pid=""
cleanup() {
  if [ -n "$fast_lio_pid" ] && kill -0 "$fast_lio_pid" 2>/dev/null; then
    echo "[unitree-go2-fan] Stopping terrain-owned FAST-LIO stack..."
    kill -INT "$fast_lio_pid" 2>/dev/null || true
    wait "$fast_lio_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [ "$replace_existing" = "true" ]; then
  mapfile -t existing_pids < <(find_existing_fast_lio_pids)
  stop_existing_fast_lio_stack "${existing_pids[@]}"
fi

if [ "$start_fast_lio" = "true" ]; then
  if topic_has_publisher /lio_cloud_registered || topic_has_publisher /lio_cloud_map; then
    echo "[unitree-go2-fan] Reusing existing FAST-LIO cloud publisher."
  else
    echo "[unitree-go2-fan] No FAST-LIO cloud publisher found; starting FAST-LIO mapping backend."
    has_fast_lio_arg use_rviz || fast_lio_args+=("use_rviz:=false")
    has_fast_lio_arg start_lidar_driver || fast_lio_args+=("start_lidar_driver:=true")
    has_fast_lio_arg restart_map || fast_lio_args+=("restart_map:=true")

    ros2 launch go2_slam_nav fast_lio_2d_mapping.launch.py "${fast_lio_args[@]}" &
    fast_lio_pid="$!"

    for _ in $(seq 1 30); do
      if topic_has_publisher /lio_cloud_registered || topic_has_publisher /lio_cloud_map; then
        break
      fi
      sleep 1
    done
  fi
fi

ros2 launch terrain_mapping terrain_mapping.launch.py "${terrain_args[@]}"
