# Scenario8 Thesis Demo Setup

Scenario8 is the professor-facing Task 5 demo for the V2X project. It runs a
SUMO traffic simulation, reads live vehicle states through TraCI, uses the
trained LSTM trajectory model to predict future vehicle positions, estimates
arrival-time collision risk, and publishes LOW/HIGH alert notifications through
MQTT.

The recommended demo mode is:

```text
Scenario = realtime
ControlMode = visual
VehicleCount = configurable
```

This mode is designed to look realistic in SUMO-GUI: vehicles enter the map,
move through the intersection, leave the network, and alert notifications appear
when the model detects risk. Vehicles are not forcibly stopped in this mode.

## Short Explanation

The simulation has three parts:

1. The MQTT alert engine starts SUMO and receives live vehicle positions from
   TraCI.
2. The engine loads the trained LSTM model from `models/`, predicts future
   trajectories, detects LOW/HIGH arrival-time risks, and publishes alerts to
   the MQTT broker.
3. The subscriber-controller receives MQTT alerts and shows temporary LOW/HIGH
   labels in SUMO-GUI near the affected vehicles.

The data flow is:

```text
SUMO live vehicle states
  -> trained LSTM trajectory model
  -> risk detection
  -> MQTT broker
  -> subscriber-controller
  -> SUMO-GUI alert labels + CSV logs
```

## Are We Using the Trained Model?

Yes. The realtime simulation still uses the trained trajectory prediction model.

The engine loads these artifacts at startup:

```text
models/best_trajectory_model.keras
models/feature_scaler.joblib
models/target_scaler.joblib
models/task5_model_metadata.json
```

The model is loaded inside:

```text
scripts/mqtt_alert_engine_multiclient.py
scripts/v2x_task5_common.py
```

The route generator only creates SUMO traffic. It does not replace the model.
The live engine still performs model inference on SUMO vehicle states before
publishing MQTT alerts.

## Important Modes

Use `visual` mode for the thesis/professor demo.

```text
visual mode:
- cars keep moving naturally;
- LOW/HIGH alert labels appear in SUMO-GUI;
- MQTT alerts are printed in the terminal;
- CSV alert logs are written;
- no stop/release collision-control gate is applied.
```

Use `protect` mode only for the stricter collision-avoidance experiment.

```text
protect mode:
- HIGH alerts can trigger TraCI speed control;
- vehicles are grouped by approach, like traffic-signal phases;
- one approach receives a short green phase while conflicting approaches wait;
- several vehicles from the same approach can move through as a realistic queue;
- a short all-red clearance is inserted before switching approaches;
- useful for showing collision-avoidance logic under heavy traffic.
```

## Main Files

```text
run_scenario8_mqtt_subscriber_control.ps1   Windows launcher
run_scenario8_mqtt_subscriber_control.sh    macOS/Linux launcher
scripts/create_scenario8_routes.py          route generator
scripts/mqtt_alert_engine_multiclient.py     realtime model + MQTT alert engine
scripts/mqtt_alert_subscriber_traci_controller.py MQTT subscriber + GUI labels
osm_realtime.sumocfg                         realtime SUMO config
scenario8_realtime.routes.xml                regenerated realtime route file
docker-compose.mqtt.yml                      Mosquitto MQTT broker
```

## Setup Requirements

Install or verify:

```text
Python 3.10+
SUMO with sumo and sumo-gui available in PATH
Docker Desktop or another way to run Mosquitto
Python packages from requirements-task5.txt
```

First-time setup notes:

```text
Windows:
- Install SUMO and make sure sumo.exe and sumo-gui.exe are available in PATH.
- Install Docker Desktop if you want to run Mosquitto with docker compose.
- Install Python dependencies with python -m pip install -r requirements-task5.txt.

macOS:
- Install SUMO so the commands sumo and sumo-gui work from Terminal.
- Install Docker Desktop or another MQTT broker setup.
- Install Python dependencies with python3 -m pip install -r requirements-task5.txt.
```

The Python requirements include:

```text
tensorflow  = loads the trained LSTM model
traci       = reads live SUMO vehicle states
paho-mqtt   = publishes/subscribes to MQTT alerts
scikit-learn/joblib = loads the saved feature and target scalers
```

Start from the Scenario8 folder:

```powershell
cd D:\Rana\cycleshield\Scenario8
```

On macOS/Linux:

```bash
cd /path/to/Scenario8
```

Install Python dependencies:

```powershell
python -m pip install -r requirements-task5.txt
```

On macOS/Linux:

```bash
python3 -m pip install -r requirements-task5.txt
```

Start the MQTT broker:

```powershell
docker compose -f docker-compose.mqtt.yml up -d
```

Check SUMO:

```powershell
sumo --version
sumo-gui --version
```

## Simple Run

For the normal thesis demo, use only these commands.

Windows:

```powershell
cd D:\Rana\cycleshield\Scenario8
docker compose -f docker-compose.mqtt.yml up -d
.\run_scenario8_mqtt_subscriber_control.ps1
```

macOS/Linux:

```bash
cd /path/to/Scenario8
docker compose -f docker-compose.mqtt.yml up -d
chmod +x ./run_scenario8_mqtt_subscriber_control.sh
./run_scenario8_mqtt_subscriber_control.sh
```

This default run uses realtime GUI mode, 150 vehicles, the trained LSTM model,
MQTT alerts, and visual LOW/HIGH alert labels.

## Recommended Professor Demo

Use 150 vehicles for the main presentation:

```powershell
.\run_scenario8_mqtt_subscriber_control.ps1
```

macOS/Linux:

```bash
chmod +x ./run_scenario8_mqtt_subscriber_control.sh
./run_scenario8_mqtt_subscriber_control.sh
```

What the professor should see:

```text
- SUMO-GUI opens.
- Vehicles enter and leave the road network continuously.
- The main terminal prints structured MQTT ALERT lines from the engine.
- On Windows, a second subscriber window shows MQTT alerts received by the subscriber-controller.
- SUMO-GUI shows temporary LOW ALERT or HIGH ALERT labels near affected cars.
- The simulation runs at realtime speed instead of racing ahead.
```

Example terminal alert:

```text
MQTT ALERT | HIGH | NEW_HIGH | sim=43.1s | pair=targeted_vehicle_009->targeted_vehicle_010 | arrival_diff=1.00s | predicted_time=45.7s | Issue immediate V2X intersection-arrival warning
```

## Run With Different Vehicle Counts

The realtime launcher regenerates the route automatically for the requested
vehicle count.

Windows:

```powershell
.\run_scenario8_mqtt_subscriber_control.ps1 -VehicleCount 50
.\run_scenario8_mqtt_subscriber_control.ps1 -VehicleCount 100
.\run_scenario8_mqtt_subscriber_control.ps1 -VehicleCount 150
.\run_scenario8_mqtt_subscriber_control.ps1 -VehicleCount 250 -Duration 1000
```

macOS/Linux:

```bash
./run_scenario8_mqtt_subscriber_control.sh --scenario realtime --vehicle-count 50 --mode gui
./run_scenario8_mqtt_subscriber_control.sh --scenario realtime --vehicle-count 100 --mode gui
./run_scenario8_mqtt_subscriber_control.sh --scenario realtime --vehicle-count 150 --mode gui
./run_scenario8_mqtt_subscriber_control.sh --scenario realtime --vehicle-count 250 --duration 1000 --mode gui
```

Suggested demo levels:

```text
50 vehicles  = light traffic
100 vehicles = medium traffic
150 vehicles = recommended professor demo
250 vehicles = heavier traffic demo, use Duration 1000
```

The generator uses seed `8408` by default, so the traffic pattern is
repeatable. Use `-Seed` / `--seed` only if you want a different traffic pattern.

## Fast Test Without GUI

Use this for quick validation before opening SUMO-GUI.

Windows:

```powershell
.\run_scenario8_mqtt_subscriber_control.ps1 -Scenario realtime -VehicleCount 150 -Mode headless -Fast
```

macOS/Linux:

```bash
./run_scenario8_mqtt_subscriber_control.sh --scenario realtime --vehicle-count 150 --mode headless --fast
```

## Protection Experiment

This is not the recommended professor visual demo. Use it only if you need to
show the stricter adaptive collision-avoidance controller.

Windows:

```powershell
.\run_scenario8_mqtt_subscriber_control.ps1 -Scenario realtime -VehicleCount 150 -Mode gui -ControlMode protect
```

macOS/Linux:

```bash
./run_scenario8_mqtt_subscriber_control.sh --scenario realtime --vehicle-count 150 --mode gui --control-mode protect
```

In protection mode, cars may stop and queue because the subscriber-controller
uses HIGH MQTT alerts to control the intersection through TraCI. The current
logic is adaptive signal-style protection:

```text
- The predictive model detects HIGH risk pairs.
- The subscriber-controller watches the affected vehicles in real time.
- Vehicles approaching the target junction are grouped by their incoming road.
- The selected approach receives a green phase.
- Vehicles from that same approach may pass in sequence using SUMO car-following.
- Conflicting approaches are slowed or held near the stop line.
- After the green phase, the controller uses a short all-red clearance.
- If another approach waits too long, the next green phase rotates to it.
```

This avoids the earlier problem where one priority vehicle could be released
while a queue behind it or beside it was not handled consistently. It is still
not meant to behave like a full city traffic-light optimizer; it is the
project's V2X protection experiment driven by the trained model and MQTT alerts.

## Logs

The main logs are replaced each session.

```text
data/mqtt_sent_alert_log.csv
data/scenario8_subscriber_controller_received_alert_log.csv
data/scenario8_subscriber_controller_protection_log.csv
data/scenario8_realtime_conflict_groups.csv
```

`mqtt_sent_alert_log.csv` contains alerts published by the engine.

`scenario8_subscriber_controller_received_alert_log.csv` contains alerts
received by the MQTT subscriber-controller, including latency.

`scenario8_subscriber_controller_protection_log.csv` is mainly useful for
`protect` mode. It contains actions such as `PHASE_GREEN_ASSIGNED`,
`PHASE_GREEN_RELEASE`, `PHASE_CLEARANCE`, `PHASE_CLEARANCE_WAIT`,
`SLOW_NEAR_ENTRY`, and `WAIT_AT_STOP_ZONE`. In `visual` mode, protection counts
should stay at zero.

## Troubleshooting

If PowerShell blocks the script:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_scenario8_mqtt_subscriber_control.ps1
```

If SUMO-GUI opens but time runs too fast, make sure you are not using `-Fast`
or `--fast`. GUI demo mode should use realtime pacing.

If you see only one or two vehicles at the beginning, that is normal. Vehicles
appear according to their generated departure times. More vehicles enter as the
simulation time advances.

If the TraCI port is busy, close old SUMO/Python runs or choose another port:

```powershell
.\run_scenario8_mqtt_subscriber_control.ps1 -TraciPort 8874
```

macOS/Linux:

```bash
./run_scenario8_mqtt_subscriber_control.sh --scenario realtime --vehicle-count 150 --mode gui --traci-port 8874
```

If MQTT alerts do not appear, confirm the broker is running:

```powershell
docker compose -f docker-compose.mqtt.yml ps
```

Then restart it if needed:

```powershell
docker compose -f docker-compose.mqtt.yml up -d
```

## What to Tell the Professor

This demo shows a V2X warning pipeline. SUMO provides live vehicle movement,
the trained LSTM model predicts future trajectories, the engine estimates
time/arrival risk, and MQTT delivers warning messages to a subscriber that
shows LOW/HIGH alerts in the simulation. The realtime visual mode is intended
for understandable demonstration. The protection mode is a separate technical
experiment for adaptive signal-style collision avoidance.
