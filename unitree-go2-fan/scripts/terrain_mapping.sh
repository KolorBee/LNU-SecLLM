#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

set +u
source "${REPO_ROOT}/scripts/setup_env.sh"
set -u

ros2 launch terrain_mapping terrain_mapping.launch.py "$@"
