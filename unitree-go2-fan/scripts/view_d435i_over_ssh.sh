#!/usr/bin/env bash
set -euo pipefail

FAN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec /usr/bin/python3 "$FAN_ROOT/tools/d435i_ssh_viewer.py" "$@"
