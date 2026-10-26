#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/common.sh"
check_platform
require_environment
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/doctor.py" "$@"
