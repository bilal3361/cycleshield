from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import mqtt_alert_engine_protect_collision as protection
from v2x_task5_common import DATA_DIR, INTERSECTION_ID, PROJECT_ROOT, utc_now_iso


DEFAULT_PROTECTION_LOG_PATH = DATA_DIR / "scenario8_subscriber_controller_protection_log.csv"
DEFAULT_RECEIVED_LOG_PATH = DATA_DIR / "scenario8_subscriber_controller_received_alert_log.csv"
DEFAULT_TOPIC = "v2x/alerts"
DEFAULT_TRACI_PORT = 8873
ALERT_VISUAL_DURATION_S = 6.0
ALERT_LABEL_OFFSET_M = 4.0
HIGH_ALERT_COLOR = (255, 40, 40, 255)
LOW_ALERT_COLOR = (255, 230, 0, 255)

RECEIVED_LOG_FIELDS = [
    "received_at_utc",
    "protocol",
    "alert_id",
    "topic",
    "simulation_time",
    "risk_level",
    "episode_status",
    "vehicle_1",
    "vehicle_2",
    "arrival_time_difference_s",
    "latency_ms",
    "controller_action",
    "payload_json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Subscribe to MQTT alerts and control SUMO vehicles through TraCI."
    )
    parser.add_argument("--broker-host", default="localhost")
    parser.add_argument("--broker-port", type=int, default=1883)
    parser.add_argument("--client-id", default="v2x-scenario8-subscriber-controller")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--traci-host", default="localhost")
    parser.add_argument("--traci-port", type=int, default=DEFAULT_TRACI_PORT)
    parser.add_argument("--traci-client-order", type=int, default=2)
    parser.add_argument("--junction-id", default=INTERSECTION_ID)
    parser.add_argument(
        "--control-mode",
        choices=["visual", "protect"],
        default="protect",
        help=(
            "visual shows MQTT alert labels in SUMO without changing vehicle speeds; "
            "protect also applies the stop/release collision-avoidance gate."
        ),
    )
    parser.add_argument("--alert-memory-s", type=float, default=60.0)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--protection-log", type=Path, default=DEFAULT_PROTECTION_LOG_PATH)
    parser.add_argument("--received-log", type=Path, default=DEFAULT_RECEIVED_LOG_PATH)
    args, _unknown = parser.parse_known_args()
    return args


def import_runtime_dependencies() -> tuple[Any, Any]:
    try:
        import traci
    except Exception as exc:
        raise RuntimeError("TraCI is required. Install SUMO and ensure its Python tools are available.") from exc

    try:
        import paho.mqtt.client as mqtt
    except Exception as exc:
        raise RuntimeError("paho-mqtt is required. Install it with: pip install paho-mqtt") from exc

    return traci, mqtt


def make_mqtt_client(mqtt: Any, client_id: str) -> Any:
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    return mqtt.Client(client_id=client_id)


def open_received_log(path: Path) -> tuple[Any, csv.DictWriter]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", newline="", encoding="utf-8")
    writer = csv.DictWriter(handle, fieldnames=RECEIVED_LOG_FIELDS)
    writer.writeheader()
    handle.flush()
    return handle, writer


def calculate_latency_ms(payload: dict[str, Any]) -> float | None:
    sent_perf_time = payload.get("sent_perf_time")
    try:
        return (time.perf_counter() - float(sent_perf_time)) * 1000.0
    except (TypeError, ValueError):
        return None


def normalize_pair(vehicle_1: str, vehicle_2: str) -> tuple[str, str]:
    pair = sorted([str(vehicle_1), str(vehicle_2)])
    return pair[0], pair[1]


def gate_has_pending_work(gate_state: dict[str, Any]) -> bool:
    return bool(
        gate_state.get("current_priority_vehicle_id")
        or gate_state.get("controlled")
        or gate_state.get("reservation_queue")
        or gate_state.get("conflict_zone_vehicle_ids")
    )


def connect_traci_with_retry(traci: Any, host: str, port: int, timeout_s: float = 90.0) -> Any:
    deadline = time.monotonic() + float(timeout_s)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return traci.connect(host=host, port=int(port), numRetries=1)
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Could not connect subscriber-controller to TraCI at {host}:{port}: {last_error}")


def collect_current_states(
    traci: Any,
    active_vehicle_ids: set[str],
    sim_time: float,
    junction_x: float,
    junction_y: float,
) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for vehicle_id in active_vehicle_ids:
        try:
            x, y = traci.vehicle.getPosition(vehicle_id)
            speed = traci.vehicle.getSpeed(vehicle_id)
            acceleration = traci.vehicle.getAcceleration(vehicle_id)
            angle = traci.vehicle.getAngle(vehicle_id)
            lane_position = traci.vehicle.getLanePosition(vehicle_id)
        except Exception:
            continue
        distance = ((float(x) - float(junction_x)) ** 2 + (float(y) - float(junction_y)) ** 2) ** 0.5
        states[vehicle_id] = {
            "time": float(sim_time),
            "vehicle_id": vehicle_id,
            "x": float(x),
            "y": float(y),
            "speed_mps": float(speed),
            "acceleration_mps2": float(acceleration),
            "angle_deg": float(angle),
            "lane_position_m": float(lane_position),
            "distance_to_junction_center_m": float(distance),
        }
    return states


def safe_visual_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value))[:96]


def queue_alert_visual(
    visual_alert_events: list[dict[str, Any]],
    payload: dict[str, Any],
    risk_level: str,
    vehicle_1: str,
    vehicle_2: str,
) -> None:
    if risk_level not in {"HIGH", "LOW"} or not vehicle_1 or not vehicle_2:
        return
    visual_alert_events.append(
        {
            "alert_id": payload.get("alert_id", ""),
            "risk_level": risk_level,
            "vehicle_1": vehicle_1,
            "vehicle_2": vehicle_2,
            "simulation_time": payload.get("simulation_time", ""),
            "arrival_time_difference_s": payload.get("arrival_time_difference_s", ""),
        }
    )


def apply_alert_visual(
    traci: Any,
    visual_state: dict[str, Any],
    alert: dict[str, Any],
    active_vehicle_ids: set[str],
    sim_time: float,
    junction_x: float,
    junction_y: float,
) -> None:
    risk_level = str(alert.get("risk_level", ""))
    vehicle_1 = str(alert.get("vehicle_1", ""))
    vehicle_2 = str(alert.get("vehicle_2", ""))
    expire_time = float(sim_time) + ALERT_VISUAL_DURATION_S
    color = HIGH_ALERT_COLOR if risk_level == "HIGH" else LOW_ALERT_COLOR
    label = f"{risk_level} ALERT"

    for vehicle_id in [vehicle_1, vehicle_2]:
        if vehicle_id not in active_vehicle_ids:
            continue
        poi_id = f"scenario8_vehicle_alert_{safe_visual_id(vehicle_id)}"
        try:
            x, y = traci.vehicle.getPosition(vehicle_id)
            if poi_id in visual_state["vehicle_alert_labels"]:
                traci.poi.setPosition(poi_id, float(x), float(y) + ALERT_LABEL_OFFSET_M)
                traci.poi.setColor(poi_id, color)
                traci.poi.setType(poi_id, label)
            else:
                traci.poi.add(
                    poi_id,
                    float(x),
                    float(y) + ALERT_LABEL_OFFSET_M,
                    color,
                    poiType=label,
                    layer=100,
                )
            visual_state["vehicle_alert_labels"][poi_id] = {
                "vehicle_id": vehicle_id,
                "expire_time": expire_time,
                "label": label,
                "color": color,
            }
        except Exception:
            continue


def expire_alert_visuals(
    traci: Any,
    visual_state: dict[str, Any],
    active_vehicle_ids: set[str],
    sim_time: float,
) -> None:
    for poi_id, state in list(visual_state["vehicle_alert_labels"].items()):
        vehicle_id = str(state.get("vehicle_id", ""))
        expire_time = float(state.get("expire_time", 0.0))
        if float(sim_time) < expire_time and vehicle_id in active_vehicle_ids:
            try:
                x, y = traci.vehicle.getPosition(vehicle_id)
                traci.poi.setPosition(poi_id, float(x), float(y) + ALERT_LABEL_OFFSET_M)
            except Exception:
                pass
            continue
        visual_state["vehicle_alert_labels"].pop(poi_id, None)
        try:
            traci.poi.remove(poi_id)
        except Exception:
            pass


def main() -> int:
    args = parse_args()

    protection.TARGET_JUNCTION_ID = str(args.junction_id)
    protection.LANE_LEADS_TO_TARGET_CACHE = {}

    try:
        traci, mqtt = import_runtime_dependencies()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    protection_handle, protection_writer = protection.open_protection_log(args.protection_log)
    received_handle, received_writer = open_received_log(args.received_log)

    alert_lock = threading.Lock()
    high_alerts_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    visual_alert_events: list[dict[str, Any]] = []

    client = make_mqtt_client(mqtt, args.client_id)

    def on_connect(client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        client.subscribe(args.topic, qos=1)
        print(f"Scenario8 subscriber-controller subscribed to {args.topic}")

    def on_message(client: Any, userdata: Any, msg: Any) -> None:
        received_at = utc_now_iso()
        payload_text = msg.payload.decode("utf-8", errors="replace")
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = {"message": payload_text}

        latency_ms = calculate_latency_ms(payload)
        risk_level = str(payload.get("risk_level", ""))
        vehicle_1 = str(payload.get("vehicle_1", ""))
        vehicle_2 = str(payload.get("vehicle_2", ""))
        controller_action = "LOG_ONLY"

        if risk_level in {"HIGH", "LOW"} and vehicle_1 and vehicle_2:
            with alert_lock:
                queue_alert_visual(visual_alert_events, payload, risk_level, vehicle_1, vehicle_2)
            prediction_time = payload.get("prediction_time_s", payload.get("simulation_time"))
            predicted_collision_time = payload.get("predicted_collision_time_s", "")
            print(
                f"{risk_level} alert | prediction_time={prediction_time}s | "
                f"predicted_collision_time={predicted_collision_time}s | "
                f"pair={vehicle_1}->{vehicle_2}"
            )

        if args.control_mode == "protect" and risk_level == "HIGH" and vehicle_1 and vehicle_2:
            with alert_lock:
                payload["_controller_received_perf_time"] = time.perf_counter()
                high_alerts_by_pair[normalize_pair(vehicle_1, vehicle_2)] = payload
            controller_action = "QUEUED_FOR_TRACI_CONTROL"
        elif risk_level in {"HIGH", "LOW"} and vehicle_1 and vehicle_2:
            controller_action = "VISUAL_ALERT_ONLY"

        received_writer.writerow(
            {
                "received_at_utc": received_at,
                "protocol": payload.get("protocol", "mqtt"),
                "alert_id": payload.get("alert_id", ""),
                "topic": msg.topic,
                "simulation_time": payload.get("simulation_time", ""),
                "risk_level": risk_level,
                "episode_status": payload.get("episode_status", ""),
                "vehicle_1": vehicle_1,
                "vehicle_2": vehicle_2,
                "arrival_time_difference_s": payload.get("arrival_time_difference_s", ""),
                "latency_ms": "" if latency_ms is None else round(float(latency_ms), 4),
                "controller_action": controller_action,
                "payload_json": json.dumps(payload, separators=(",", ":")),
            }
        )
        received_handle.flush()

    client.on_connect = on_connect
    client.on_message = on_message

    gate_state: dict[str, Any] = {
        "current_priority_vehicle_id": "",
        "reservation_queue": [],
        "conflict_group_vehicle_ids": [],
        "conflict_zone_vehicle_ids": [],
        "protected_vehicle_ids": set(),
        "controlled": {},
        "release_cooldowns": {},
        "last_release_time_s": -999999.0,
        "last_logged_signature": None,
    }
    visual_state: dict[str, Any] = {
        "vehicle_alert_labels": {},
    }

    step = 0
    protections_applied = 0
    releases = 0

    try:
        client.connect(args.broker_host, args.broker_port, keepalive=60)
        client.loop_start()

        traci = connect_traci_with_retry(traci, args.traci_host, args.traci_port)
        traci.setOrder(int(args.traci_client_order))

        junction_ids = set(traci.junction.getIDList())
        if args.junction_id not in junction_ids:
            raise RuntimeError(f"Junction '{args.junction_id}' was not found in the SUMO network.")

        junction_x, junction_y = traci.junction.getPosition(args.junction_id)
        protection.configure_protected_vehicle_types(traci)

        if args.control_mode == "protect":
            print(
                "Scenario8 subscriber-controller connected to TraCI in protect mode. "
                "It will control vehicles only after receiving HIGH MQTT alerts."
            )
        else:
            print(
                "Scenario8 subscriber-controller connected to TraCI in visual mode. "
                "It will show LOW/HIGH MQTT alert labels without controlling vehicles."
            )

        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            sim_time = float(traci.simulation.getTime())
            active_vehicle_ids = set(map(str, traci.vehicle.getIDList()))
            if args.control_mode == "visual":
                for vehicle_id in active_vehicle_ids:
                    if vehicle_id.startswith("targeted"):
                        protection.apply_protected_vehicle_parameters(traci, vehicle_id)

            with alert_lock:
                high_alerts: list[dict[str, Any]] = []
                new_visual_alerts = list(visual_alert_events)
                visual_alert_events.clear()
                now_perf = time.perf_counter()
                for pair, alert in list(high_alerts_by_pair.items()):
                    age_s = now_perf - float(alert.get("_controller_received_perf_time", now_perf))
                    if age_s > args.alert_memory_s:
                        del high_alerts_by_pair[pair]
                        continue
                    if str(alert.get("vehicle_1", "")) in active_vehicle_ids or str(alert.get("vehicle_2", "")) in active_vehicle_ids:
                        high_alerts.append(dict(alert))

            current_states = collect_current_states(traci, active_vehicle_ids, sim_time, float(junction_x), float(junction_y))

            for alert in new_visual_alerts:
                apply_alert_visual(
                    traci,
                    visual_state,
                    alert,
                    active_vehicle_ids,
                    sim_time,
                    float(junction_x),
                    float(junction_y),
                )
            expire_alert_visuals(traci, visual_state, active_vehicle_ids, sim_time)

            if args.control_mode == "protect" and (high_alerts or gate_has_pending_work(gate_state)):
                new_protections, new_releases = protection.maintain_intersection_gate_controls(
                    traci,
                    protection_writer,
                    protection_handle,
                    gate_state,
                    active_vehicle_ids,
                    current_states,
                    sim_time,
                    float(junction_x),
                    float(junction_y),
                    high_alerts,
                )
                protections_applied += new_protections
                releases += new_releases
            elif args.control_mode == "protect":
                for vehicle_id in list(gate_state.get("controlled", {})):
                    if vehicle_id in active_vehicle_ids:
                        protection.release_gate_vehicle(traci, gate_state, vehicle_id, sim_time)
                        releases += 1

            if step % 20 == 0:
                print(
                    f"Subscriber-controller status | sim={sim_time:.1f} | active={len(active_vehicle_ids)} | "
                    f"mode={args.control_mode} | high_alert_pairs={len(high_alerts)} | "
                    f"protections={protections_applied} | releases={releases}"
                )

            step += 1
            if args.max_steps is not None and step >= args.max_steps:
                break

        print(
            "Scenario8 subscriber-controller finished. "
            f"Steps={step}, protections_applied={protections_applied}, releases={releases}"
        )
        return 0
    except KeyboardInterrupt:
        print("Scenario8 subscriber-controller stopped.")
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        try:
            traci.close()
        except Exception:
            pass
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
        protection_handle.close()
        received_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
