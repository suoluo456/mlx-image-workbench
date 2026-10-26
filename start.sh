#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/common.sh"
check_platform
require_environment
export MLX_WEB_PORT="${MLX_WEB_PORT:-7866}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/start_server.py" "$@"
