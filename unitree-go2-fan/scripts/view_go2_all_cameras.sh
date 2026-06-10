#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pids=()
cleanup() {
  local pid
  for pid in "${pids[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT INT TERM

echo "[unitree-go2-fan] Starting D435i SSH viewer..."
"$FAN_ROOT/scripts/view_d435i_over_ssh.sh" "$@" &
pids+=("$!")

echo "[unitree-go2-fan] Starting Go2 built-in WebRTC camera viewer..."
"$FAN_ROOT/scripts/start_go2_webrtc_camera.sh" &
pids+=("$!")

wait -n "${pids[@]}"
