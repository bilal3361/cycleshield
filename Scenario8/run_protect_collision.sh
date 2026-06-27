#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
exec ./run_scenario4_protected_mqtt.sh "$@"
