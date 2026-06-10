#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
# shellcheck source=/dev/null
source "$FAN_ROOT/scripts/setup_env.sh"
set -u

section() {
  printf '\n==== %s ====\n' "$1"
}

try() {
  echo "+ $*"
  "$@" || true
}

section "Environment"
echo "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-unset}"
echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-unset}"
echo "CYCLONEDDS_URI=${CYCLONEDDS_URI:-unset}"
try ip route get 192.168.123.161
try ip route get 192.168.123.18

section "Core Topics"
try timeout 5 ros2 topic list

section "Unitree DDS"
try timeout 5 ros2 topic info /api/sport/request -v
try timeout 5 ros2 topic echo /sportmodestate --once --field position

section "Nav2 Nodes"
try timeout 5 ros2 node list
for node in \
  /controller_server \
  /planner_server \
  /behavior_server \
  /bt_navigator \
  /velocity_smoother \
  /lifecycle_manager_navigation; do
  try timeout 5 ros2 lifecycle get "$node"
done

section "Nav2 Actions"
try timeout 5 ros2 action list
try timeout 5 ros2 action info /navigate_to_pose

section "Command Chain"
for topic in /goal_pose /cmd_vel_nav /cmd_vel /api/sport/request /lio_odom /map /lidar_points_nav; do
  try timeout 5 ros2 topic info "$topic" -v
done

section "Bridge Node"
try timeout 5 ros2 node info /sport_ctrl

cat <<'EOF'

Interpretation:
- If /navigate_to_pose has no server or Nav2 lifecycle nodes are not active, RViz goals will do nothing.
- If /cmd_vel has no publisher after sending a goal, Nav2 accepted no path or controller did not run.
- If /sport_ctrl exists and /cmd_vel has data, but /api/sport/request has no Unitree subscriber, the dog will not move.
- If all of the above are healthy and the dog still does not move, check sport lease / robot mode on the handheld controller or app.
EOF
