#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/common.sh"
require_environment
unset HF_HUB_OFFLINE TRANSFORMERS_OFFLINE
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/manage_models.py" "$@"
