#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$FAN_ROOT/src/go2_slam_nav/config/hesai_jt128.yaml"
HESAI_ROOT="$FAN_ROOT/src/HesaiLidar_ROS_2.0"

if [ ! -f "$CONFIG" ]; then
  echo "[configure_hesai_paths] missing config: $CONFIG" >&2
  exit 1
fi

if [ ! -d "$HESAI_ROOT" ]; then
  echo "[configure_hesai_paths] missing Hesai source: $HESAI_ROOT" >&2
  exit 1
fi

python3 - "$CONFIG" "$HESAI_ROOT" <<'PY'
import re
import sys
from pathlib import Path

config = Path(sys.argv[1])
hesai_root = Path(sys.argv[2])
text = config.read_text()
pattern = r'"/[^"]*/HesaiLidar_ROS_2\.0/src/driver/HesaiLidar_SDK_2\.0/correction/'
replacement = f'"{hesai_root}/src/driver/HesaiLidar_SDK_2.0/correction/'
text = re.sub(pattern, replacement, text)
config.write_text(text)
PY

echo "[configure_hesai_paths] updated $CONFIG"
