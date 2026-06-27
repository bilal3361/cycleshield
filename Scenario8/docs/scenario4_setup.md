# Scenario4 Setup

Scenario4 is a small two-vehicle MQTT collision/protection experiment.

The active target intersection is:

```text
cluster_255722000_4115305935
```

## Vehicles

The route file `scenario4_collision.routes.xml` contains exactly two vehicles:

- `targeted_red`
- `targeted_blue`

Both vehicles use the same crossing routes and departure times in the baseline
and protected runs. The baseline keeps SUMO safety relaxed so the vehicles can
collide. The protected run keeps the same route and traffic conditions, but the
engine applies TraCI control when the LSTM predicts an arrival-time conflict.

## Model

Scenario4 is self-contained and uses copied Scenario3 inference artifacts:

- `models/best_trajectory_model.keras`
- `models/feature_scaler.joblib`
- `models/target_scaler.joblib`
- `models/task5_model_metadata.json`

The model and scalers are not retrained or modified. The sequence settings are:

```text
INPUT_LEN = 30
PRED_LEN = 40
DT_SECONDS = 0.1
```

That means the engine uses 3 seconds of observed history and predicts 4 seconds
of future `(x, y)` trajectory points.

## Run Baseline

```bash
cd /Users/admin/V2X_Project2/Scenario4
./run_scenario4_collision.sh
```

This warning-only run publishes MQTT alerts but does not slow or stop vehicles.
The expected result is one collision between the two vehicles.

Original-style alias:

```bash
./run_collision_test.sh
```

## Run Protected

```bash
cd /Users/admin/V2X_Project2/Scenario4
./run_scenario4_protected_mqtt.sh
```

The protected run uses the same LSTM prediction and HIGH/LOW arrival-risk logic.
When a HIGH-risk conflict is detected, the engine gives one vehicle priority and
makes the other yield close to the junction entry. After the conflict zone is
clear, the yielding vehicle is released with normal SUMO speed control.

Protection actions are written to:

```text
data/scenario4_mqtt_protection_log.csv
```

Collision diagnosis rows are written to:

```text
data/scenario4_collision_diagnosis_log.csv
```

Original-style alias:

```bash
./run_protect_collision.sh
```

## Validation Result

Headless baseline SUMO reports one collision at about `11.70s` between
`targeted_red` and `targeted_blue`. A headless protected MQTT run with the same
route/config completed with `collision_diagnoses=0`.
