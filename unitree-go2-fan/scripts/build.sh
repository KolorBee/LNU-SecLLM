#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
unset PYTHONHOME
export Python3_EXECUTABLE=/usr/bin/python3

set +u
source /opt/ros/humble/setup.bash
set -u
if [ -f /home/star/unitree_ros2/setup_go2.sh ]; then
  set +u
  source /home/star/unitree_ros2/setup_go2.sh
  set -u
fi

"$FAN_ROOT/scripts/configure_hesai_paths.sh"
cd "$FAN_ROOT"
colcon build --symlink-install "$@"
