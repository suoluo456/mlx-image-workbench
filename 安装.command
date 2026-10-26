#!/bin/bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec /bin/bash "$ROOT/scripts/macos-launcher.sh" install
