#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python3}"
SCENARIO="realtime"
MODE="gui"
CONTROL_MODE="visual"
VEHICLE_COUNT="150"
DURATION=""
CONFLICT_GROUPS=""
SEED="8408"
REGENERATE_REALTIME="true"
FAST="false"
TRACI_PORT="${SCENARIO8_TRACI_PORT:-8873}"
SUMO_BINARY=""
MAX_STEPS=""
REALTIME_FACTOR="${SCENARIO8_REALTIME_FACTOR:-1}"

usage() {
  cat <<'EOF'
Usage: ./run_scenario8_mqtt_subscriber_control.sh [options]

Options:
  --scenario realtime|50|150
                          Route/config to run. Default: realtime
  --mode gui|headless     Use sumo-gui or headless sumo. Default: gui
  --control-mode visual|protect
                          visual shows LOW/HIGH alerts without stopping cars.
                          protect applies adaptive signal-style collision control.
                          Default: visual
  --vehicle-count N       Number of vehicles for --scenario realtime. Default: 150
  --duration SECONDS      Simulation spread for --scenario realtime. Default: auto
  --conflict-groups N     Alert/conflict groups for --scenario realtime. Default: auto
  --seed N                Route generation seed for --scenario realtime. Default: 8408
  --no-regenerate-realtime
                          Reuse existing scenario8_realtime.routes.xml.
  --fast                  Disable real-time pacing.
  --traci-port PORT       TraCI port. Default: 8873
  --sumo-binary NAME      Override SUMO binary.
  --max-steps N           Stop after N simulation steps.
  -h, --help              Show this help.

Examples:
  ./run_scenario8_mqtt_subscriber_control.sh --scenario realtime --vehicle-count 100 --mode gui
  ./run_scenario8_mqtt_subscriber_control.sh --scenario 150 --mode gui --control-mode protect
  ./run_scenario8_mqtt_subscriber_control.sh --scenario 150 --mode headless --fast
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario)
      SCENARIO="${2:?Missing value for --scenario}"
      shift 2
      ;;
    --mode)
      MODE="${2:?Missing value for --mode}"
      shift 2
      ;;
    --control-mode)
      CONTROL_MODE="${2:?Missing value for --control-mode}"
      shift 2
      ;;
    --vehicle-count)
      VEHICLE_COUNT="${2:?Missing value for --vehicle-count}"
      shift 2
      ;;
    --duration)
      DURATION="${2:?Missing value for --duration}"
      shift 2
      ;;
    --conflict-groups)
      CONFLICT_GROUPS="${2:?Missing value for --conflict-groups}"
      shift 2
      ;;
    --seed)
      SEED="${2:?Missing value for --seed}"
      shift 2
      ;;
    --no-regenerate-realtime)
      REGENERATE_REALTIME="false"
      shift
      ;;
    --fast)
      FAST="true"
      shift
      ;;
    --traci-port)
      TRACI_PORT="${2:?Missing value for --traci-port}"
      shift 2
      ;;
    --sumo-binary)
      SUMO_BINARY="${2:?Missing value for --sumo-binary}"
      shift 2
      ;;
    --max-steps)
      MAX_STEPS="${2:?Missing value for --max-steps}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$SCENARIO" in
  realtime) SUMO_CONFIG="osm_realtime.sumocfg" ;;
  50) SUMO_CONFIG="osm.sumocfg" ;;
  150) SUMO_CONFIG="osm_150.sumocfg" ;;
  *)
    echo "--scenario must be realtime, 50, or 150" >&2
    exit 2
    ;;
esac

if [[ "$SCENARIO" == "realtime" && "$REGENERATE_REALTIME" == "true" ]]; then
  if (( VEHICLE_COUNT < 20 || VEHICLE_COUNT > 500 )); then
    echo "--vehicle-count must be between 20 and 500" >&2
    exit 2
  fi
  if [[ -z "$DURATION" ]]; then
    DURATION=$(( VEHICLE_COUNT * 4 ))
    if (( DURATION < 240 )); then DURATION=240; fi
    if (( DURATION > 1200 )); then DURATION=1200; fi
  fi
  if [[ -z "$CONFLICT_GROUPS" ]]; then
    CONFLICT_GROUPS=$(( VEHICLE_COUNT / 6 ))
    if (( CONFLICT_GROUPS < 4 )); then CONFLICT_GROUPS=4; fi
    if (( CONFLICT_GROUPS > 30 )); then CONFLICT_GROUPS=30; fi
  fi
  MAX_CONFLICT_GROUPS=$(( VEHICLE_COUNT / 2 ))
  if (( CONFLICT_GROUPS > MAX_CONFLICT_GROUPS )); then
    CONFLICT_GROUPS="$MAX_CONFLICT_GROUPS"
  fi

  echo "Generating realtime route: vehicles=$VEHICLE_COUNT duration=${DURATION}s conflict_groups=$CONFLICT_GROUPS seed=$SEED"
  "$PYTHON_BIN" scripts/create_scenario8_routes.py \
    --vehicle-count "$VEHICLE_COUNT" \
    --conflict-groups "$CONFLICT_GROUPS" \
    --end-time "$DURATION" \
    --seed "$SEED" \
    --safe-behavior \
    --output-route scenario8_realtime.routes.xml \
    --output-conflict-groups data/scenario8_realtime_conflict_groups.csv
fi

case "$MODE" in
  gui)
    SUMO_BINARY="${SUMO_BINARY:-sumo-gui}"
    ;;
  headless)
    SUMO_BINARY="${SUMO_BINARY:-sumo}"
    FAST="true"
    ;;
  *)
    echo "--mode must be gui or headless" >&2
    exit 2
    ;;
esac

case "$CONTROL_MODE" in
  visual|protect) ;;
  *)
    echo "--control-mode must be visual or protect" >&2
    exit 2
    ;;
esac

REALTIME_ARGS=(--real-time --realtime-factor "$REALTIME_FACTOR")
if [[ "$FAST" == "true" ]]; then
  REALTIME_ARGS=(--no-real-time)
fi

CONTROLLER_ARGS=(
  scripts/mqtt_alert_subscriber_traci_controller.py
  --traci-port "$TRACI_PORT"
  --traci-client-order 2
  --control-mode "$CONTROL_MODE"
)
ENGINE_ARGS=(
  scripts/mqtt_alert_engine_multiclient.py
  --sumo-binary "$SUMO_BINARY"
  --sumo-config "$SUMO_CONFIG"
  --vehicle-groups targeted
  --min-risk LOW
  --prediction-interval-steps 10
  --max-alerts-per-cycle 5
  --alert-mode episode
  --episode-reset-s 3600
  "${REALTIME_ARGS[@]}"
  --traci-num-clients 2
  --traci-client-order 1
)

if [[ -n "$MAX_STEPS" ]]; then
  CONTROLLER_ARGS+=(--max-steps "$MAX_STEPS")
  ENGINE_ARGS+=(--max-steps "$MAX_STEPS")
fi

export SCENARIO8_TRACI_PORT="$TRACI_PORT"
export PYTHONUNBUFFERED=1

ENGINE_PID=""
CONTROLLER_PID=""

cleanup() {
  if [[ -n "$CONTROLLER_PID" ]] && kill -0 "$CONTROLLER_PID" 2>/dev/null; then
    kill "$CONTROLLER_PID" 2>/dev/null || true
  fi
  if [[ -n "$ENGINE_PID" ]] && kill -0 "$ENGINE_PID" 2>/dev/null; then
    kill "$ENGINE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "Scenario8 run: scenario=$SCENARIO mode=$MODE control_mode=$CONTROL_MODE vehicles=$VEHICLE_COUNT sumo_config=$SUMO_CONFIG sumo_binary=$SUMO_BINARY port=$TRACI_PORT"

"$PYTHON_BIN" "${CONTROLLER_ARGS[@]}" &
CONTROLLER_PID=$!

sleep 1

"$PYTHON_BIN" "${ENGINE_ARGS[@]}" &
ENGINE_PID=$!

wait "$ENGINE_PID"
ENGINE_STATUS=$?
wait "$CONTROLLER_PID"
CONTROLLER_STATUS=$?

exit $(( ENGINE_STATUS != 0 ? ENGINE_STATUS : CONTROLLER_STATUS ))
