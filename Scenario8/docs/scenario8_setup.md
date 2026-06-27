# Scenario8 Setup

Scenario8 is a 50-vehicle MQTT subscriber-controlled protection experiment.

It copies the Scenario4 road, MQTT scripts, and Scenario3/Scenario4 model
artifacts into a new folder, then creates a 50-vehicle collision-risk route set
on the copied road network.

```text
MQTT alert engine -> MQTT broker -> MQTT subscriber-controller -> TraCI vehicle control
```

## Main idea

In previous protected scripts, the same protected engine both generated the
HIGH alert and controlled SUMO vehicles.

In Scenario8, the alert engine remains warning/publisher-side logic. A separate
MQTT subscriber receives HIGH alerts and then controls the vehicle through TraCI.
This is closer to a real V2X deployment where a vehicle or roadside controller
subscribes to alerts and applies braking or speed control.

## Files

- `scripts/mqtt_alert_engine_multiclient.py`
- `scripts/mqtt_alert_subscriber_traci_controller.py`
- `run_scenario8_mqtt_subscriber_control.sh`
- `run_scenario8_warning_only.sh`
- `data/scenario8_subscriber_controller_received_alert_log.csv`
- `data/scenario8_subscriber_controller_protection_log.csv`

## How it works

1. `mqtt_alert_engine_multiclient.py` starts SUMO in TraCI multi-client mode.
2. The engine loads the unchanged LSTM model and publishes MQTT alerts.
3. `mqtt_alert_subscriber_traci_controller.py` subscribes to `v2x/alerts`.
4. When it receives a HIGH alert, it queues the conflicting vehicles.
5. The subscriber-controller shows a `LOW ALERT` or `HIGH ALERT` label beside
   the affected vehicles in SUMO-GUI, like a driver warning display.
6. The subscriber-controller uses TraCI to slow/yield non-priority vehicles.
7. When the conflict zone clears, it releases one vehicle with normal SUMO speed.

## Vehicle Scenario

- Exactly 50 vehicles are generated in `scenario8_50.routes.xml`.
- Vehicle IDs run from `targeted_vehicle_001` to `targeted_vehicle_050`.
- The active SUMO config is `osm.sumocfg`.
- Simulation time is `0` to `220` seconds with `step-length = 0.1`.
- Vehicles are generated with a fixed random seed in
  `scripts/create_scenario8_routes.py`.
- The route file mixes 20 random background vehicles with 15 randomized
  Scenario4-style two-vehicle conflict pairs at
  `cluster_255722000_4115305935`.
- The conflict pairs are inserted at jittered times so traffic does not appear
  as simple route blocks.
- Conflict group metadata is written to
  `data/scenario8_conflict_groups.csv`.

The warning-only run shows the collision-risk baseline. The protected run keeps
the same traffic but moves vehicle control into the MQTT subscriber-controller.

Latest headless validation:

- Warning-only baseline: 50 inserted, 0 teleports, 15 collisions.
- Protected subscriber-control run: 50 inserted, 0 teleports, 4 collisions,
  29 MQTT alerts published, 39 protection actions.

In GUI mode, received alerts are displayed as temporary labels beside the
affected vehicles only:

- `HIGH ALERT`
- `LOW ALERT`

No extra status text is shown on the map. The terminal output remains verbose
for debugging, including subscriber status, detailed HIGH-alert lines,
protection counts, and release counts. Detailed alert, latency, and protection
information is also saved in the CSV logs.

## Run

Start the MQTT broker first if it is not already running:

```bash
cd /Users/admin/V2X_Project2/Scenario8
docker compose -f docker-compose.mqtt.yml up -d
```

Run the subscriber-controlled protected experiment:

```bash
cd /Users/admin/V2X_Project2/Scenario8
./run_scenario8_mqtt_subscriber_control.sh
```

Run the warning-only baseline:

```bash
./run_scenario8_warning_only.sh
```

## Notes

- Do not run another SUMO/TraCI scenario at the same time on port `8873`.
- This folder is independent. Scenario3, Scenario4, and other folders are not modified.
- The model, scalers, metadata, LSTM prediction logic, and risk thresholds are copied unchanged.
