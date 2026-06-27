from __future__ import annotations

import argparse
import csv
import random
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = PROJECT_ROOT / "scenario8_50.routes.xml"
CONFLICT_GROUP_PATH = PROJECT_ROOT / "data" / "scenario8_conflict_groups.csv"

VEHICLE_COUNT = 50
CONFLICT_GROUP_COUNT = 15
RANDOM_SEED = 8408
VEHICLE_SPEED_MPS = 13.89
TARGET_JUNCTION_ID = "cluster_255722000_4115305935"

VTYPE = {
    "id": "scenario8_collision_car",
    "vClass": "passenger",
    "guiShape": "passenger",
    "length": "5.00",
    "width": "1.80",
    "minGap": "0",
    "maxSpeed": f"{VEHICLE_SPEED_MPS:.2f}",
    "speedFactor": "1.0",
    "speedDev": "0",
    "accel": "6.0",
    "decel": "9.0",
    "emergencyDecel": "12.0",
    "apparentDecel": "12.0",
    "tau": "0.1",
    "sigma": "0",
    "lcStrategic": "0",
    "lcCooperative": "0",
    "lcSpeedGain": "0",
    "lcKeepRight": "0",
    "lcAssertive": "10",
    "jmIgnoreFoeProb": "1",
    "jmIgnoreJunctionFoeProb": "1",
    "jmIgnoreFoeSpeed": "100",
    "jmIgnoreKeepClearTime": "0",
    "jmStoplineGap": "0",
    "collisionMinGapFactor": "0",
}

SAFE_VTYPE_OVERRIDES = {
    "minGap": "2.50",
    "maxSpeed": "11.11",
    "speedFactor": "1.0",
    "speedDev": "0.05",
    "accel": "3.0",
    "decel": "4.5",
    "emergencyDecel": "9.0",
    "apparentDecel": "4.5",
    "tau": "1.0",
    "sigma": "0.2",
    "lcStrategic": "1",
    "lcCooperative": "1",
    "lcSpeedGain": "1",
    "lcKeepRight": "1",
    "lcAssertive": "1",
    "jmIgnoreFoeProb": "0",
    "jmIgnoreJunctionFoeProb": "0",
    "jmIgnoreFoeSpeed": "0",
    "jmIgnoreKeepClearTime": "0",
    "jmStoplineGap": "2.5",
    "collisionMinGapFactor": "1",
}

MOVEMENTS = {
    "east_to_west": {
        "edges": "179750964#5 858712304#0",
        "depart_lane": "1",
        "approach_time_s": 8.7,
        "color": "red",
    },
    "east_to_south": {
        "edges": "179750964#5 179750980#0",
        "depart_lane": "0",
        "approach_time_s": 8.0,
        "color": "orange",
    },
    "south_to_east": {
        "edges": "1274037341#1 409634167#3",
        "depart_lane": "0",
        "approach_time_s": 5.3,
        "color": "cyan",
    },
    "south_to_north": {
        "edges": "1274037341#1 179750980#0",
        "depart_lane": "0",
        "approach_time_s": 6.5,
        "color": "blue",
    },
    "south_to_west": {
        "edges": "1274037341#1 858712304#0",
        "depart_lane": "0",
        "approach_time_s": 5.3,
        "color": "magenta",
    },
    "west_to_east": {
        "edges": "409634167#1 409634167#3",
        "depart_lane": "0",
        "approach_time_s": 3.4,
        "color": "yellow",
    },
    "west_to_south": {
        "edges": "409634167#1 179750980#0",
        "depart_lane": "1",
        "approach_time_s": 3.4,
        "color": "green",
    },
}


def add_vehicle(
    vehicles: list[dict[str, object]],
    movement_name: str,
    conflict_time_s: float,
    group_id: str,
    purpose: str,
    depart_jitter_s: float = 0.0,
) -> None:
    movement = MOVEMENTS[movement_name]
    depart = max(0.0, conflict_time_s - float(movement["approach_time_s"]) + depart_jitter_s)
    vehicles.append(
        {
            "type": VTYPE["id"],
            "depart": round(depart, 1),
            "departLane": movement["depart_lane"],
            "departPos": "0",
            "departSpeed": f"{VEHICLE_SPEED_MPS:.2f}",
            "color": movement["color"],
            "edges": movement["edges"],
            "movement": movement_name,
            "expected_conflict_time_s": round(conflict_time_s, 1),
            "group_id": group_id,
            "purpose": purpose,
        }
    )


def is_depart_slot_available(
    vehicles: list[dict[str, object]],
    movement_name: str,
    depart_s: float,
    min_gap_s: float = 3.0,
) -> bool:
    for vehicle in vehicles:
        if vehicle["movement"] != movement_name:
            continue
        if abs(float(vehicle["depart"]) - depart_s) < min_gap_s:
            return False
    return True


def make_random_conflict_times(
    rng: random.Random,
    conflict_group_count: int = CONFLICT_GROUP_COUNT,
    end_time_s: float | None = None,
) -> list[float]:
    start_s = rng.uniform(42.0, 48.0)
    if end_time_s is not None:
        end_s = max(start_s + 20.0, float(end_time_s) - 45.0)
        gap_s = max(4.0, (end_s - start_s) / max(conflict_group_count - 1, 1))
        jitter_s = min(1.5, gap_s * 0.25)
    elif conflict_group_count <= CONFLICT_GROUP_COUNT:
        gap_s = 14.0
        jitter_s = 1.5
    else:
        end_s = 270.0
        gap_s = max(2.5, (end_s - start_s) / max(conflict_group_count - 1, 1))
        jitter_s = min(1.2, gap_s * 0.25)
    times = [
        round(start_s + index * gap_s + rng.uniform(-jitter_s, jitter_s), 1)
        for index in range(conflict_group_count)
    ]
    return sorted(times)


def estimated_arrival_time(vehicle: dict[str, object]) -> float:
    expected = vehicle.get("expected_conflict_time_s", "")
    if expected != "":
        return float(expected)
    return float(vehicle["depart"]) + float(MOVEMENTS[str(vehicle["movement"])]["approach_time_s"])


def is_background_arrival_clear(
    movement_name: str,
    depart_s: float,
    conflict_times: list[float],
    vehicles: list[dict[str, object]],
    conflict_buffer_s: float = 6.0,
    traffic_buffer_s: float = 4.0,
) -> bool:
    arrival_s = depart_s + float(MOVEMENTS[movement_name]["approach_time_s"])
    if any(abs(arrival_s - conflict_time) <= conflict_buffer_s for conflict_time in conflict_times):
        return False
    return all(abs(arrival_s - estimated_arrival_time(vehicle)) > traffic_buffer_s for vehicle in vehicles)


def make_background_arrival_times(
    rng: random.Random,
    conflict_times: list[float],
    count: int,
    dense: bool = False,
    end_time_s: float | None = None,
) -> list[float]:
    end_s = float(end_time_s) if end_time_s is not None else 300.0
    if dense:
        return sorted(round(rng.uniform(12.0, max(13.0, end_s - 8.0)), 1) for _ in range(count))

    candidates = [
        float(slot)
        for slot in range(12, max(13, int(end_s) - 14), 3)
        if all(abs(float(slot) - conflict_time) > 4.0 for conflict_time in conflict_times)
    ]
    if len(candidates) < count:
        raise RuntimeError("Not enough safe random background slots are available.")
    selected = sorted(rng.sample(candidates, count))
    return [round(value + rng.uniform(-0.8, 0.8), 1) for value in selected]


def build_vehicles(
    vehicle_count: int = VEHICLE_COUNT,
    conflict_group_count: int = CONFLICT_GROUP_COUNT,
    random_seed: int = RANDOM_SEED,
    dense: bool = False,
    end_time_s: float | None = None,
) -> list[dict[str, object]]:
    if vehicle_count < conflict_group_count * 2:
        raise ValueError("vehicle_count must be at least twice conflict_group_count.")

    rng = random.Random(random_seed)
    vehicles: list[dict[str, object]] = []

    # Random-looking conflict pairs: the pair timing repeats the proven
    # Scenario4 collision pattern, but the pair times are jittered across the
    # full run.
    conflict_times = make_random_conflict_times(rng, conflict_group_count, end_time_s=end_time_s)
    for group_index, conflict_time in enumerate(conflict_times, start=1):
        group_id = f"scenario4_style_pair_{group_index:02d}"
        for movement_name in ["east_to_west", "south_to_north"]:
            add_vehicle(
                vehicles,
                movement_name,
                conflict_time,
                group_id,
                "intentional_conflict",
                depart_jitter_s=rng.uniform(-0.15, 0.15),
            )

    background_movements = list(MOVEMENTS)
    background_count = vehicle_count - len(vehicles)
    for arrival_time in make_background_arrival_times(
        rng,
        conflict_times,
        background_count,
        dense=dense,
        end_time_s=end_time_s,
    ):
        movement_name = rng.choice(background_movements)
        for _attempt in range(20):
            movement = MOVEMENTS[movement_name]
            depart = round(max(0.0, arrival_time - float(movement["approach_time_s"])), 1)
            if is_depart_slot_available(vehicles, movement_name, depart):
                break
            movement_name = rng.choice(background_movements)
        else:
            raise RuntimeError("Could not assign a background vehicle movement with enough depart spacing.")
        movement = MOVEMENTS[movement_name]
        vehicles.append(
            {
                "type": VTYPE["id"],
                "depart": depart,
                "departLane": movement["depart_lane"],
                "departPos": "0",
                "departSpeed": f"{VEHICLE_SPEED_MPS:.2f}",
                "color": movement["color"],
                "edges": movement["edges"],
                "movement": movement_name,
                "expected_conflict_time_s": "",
                "group_id": "random_background",
                "purpose": "random_background",
            }
        )

    if len(vehicles) != vehicle_count:
        raise RuntimeError(f"Expected {vehicle_count} vehicles, generated {len(vehicles)}")

    vehicles = sorted(vehicles, key=lambda item: (float(item["depart"]), str(item["movement"])))
    for index, vehicle in enumerate(vehicles, start=1):
        vehicle["id"] = f"targeted_vehicle_{index:03d}"
    return vehicles


def write_routes(
    vehicles: list[dict[str, object]],
    route_path: Path = ROUTE_PATH,
    safe_behavior: bool = False,
) -> None:
    routes = ET.Element(
        "routes",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://sumo.dlr.de/xsd/routes_file.xsd",
        },
    )
    vtype = dict(VTYPE)
    if safe_behavior:
        vtype.update(SAFE_VTYPE_OVERRIDES)
    ET.SubElement(routes, "vType", vtype)

    for vehicle in vehicles:
        vehicle_attrs = {
            key: str(vehicle[key])
            for key in ["id", "type", "depart", "departLane", "departPos", "departSpeed", "color"]
        }
        if safe_behavior:
            vehicle_attrs["departSpeed"] = "max"
        vehicle_el = ET.SubElement(routes, "vehicle", vehicle_attrs)
        ET.SubElement(vehicle_el, "route", {"edges": vehicle["edges"]})

    tree = ET.ElementTree(routes)
    ET.indent(tree, space="    ")
    tree.write(route_path, encoding="UTF-8", xml_declaration=True)


def write_conflict_groups(vehicles: list[dict[str, object]], conflict_group_path: Path = CONFLICT_GROUP_PATH) -> None:
    conflict_group_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "group_id",
        "vehicle_id",
        "movement",
        "route_edges",
        "depart",
        "expected_conflict_time_s",
        "target_junction_id",
        "purpose",
        "note",
    ]
    with conflict_group_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for vehicle in vehicles:
            writer.writerow(
                {
                    "group_id": vehicle["group_id"],
                    "vehicle_id": vehicle["id"],
                    "movement": vehicle["movement"],
                    "route_edges": vehicle["edges"],
                    "depart": vehicle["depart"],
                    "expected_conflict_time_s": vehicle["expected_conflict_time_s"],
                    "target_junction_id": TARGET_JUNCTION_ID,
                    "purpose": vehicle["purpose"],
                    "note": (
                        "Random traffic vehicle."
                        if vehicle["purpose"] == "random_background"
                        else "Randomly placed intentional arrival-time conflict for warning/protection demonstration."
                    ),
                }
            )


def project_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Scenario8 SUMO route files.")
    parser.add_argument("--vehicle-count", type=int, default=VEHICLE_COUNT)
    parser.add_argument("--conflict-groups", type=int, default=None)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument(
        "--end-time",
        type=float,
        default=None,
        help="Spread generated arrivals across this many simulation seconds.",
    )
    parser.add_argument(
        "--safe-behavior",
        action="store_true",
        help="Write SUMO vehicle type settings suitable for natural traffic flow instead of deliberate collision stress.",
    )
    parser.add_argument(
        "--dense",
        action="store_true",
        help="Allow tighter background traffic timing for stress tests.",
    )
    parser.add_argument("--output-route", default=None)
    parser.add_argument("--output-conflict-groups", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conflict_group_count = (
        args.conflict_groups
        if args.conflict_groups is not None
        else (
            max(4, min(30, args.vehicle_count // 6))
            if args.safe_behavior
            else CONFLICT_GROUP_COUNT
            if args.vehicle_count == VEHICLE_COUNT
            else max(CONFLICT_GROUP_COUNT, min(args.vehicle_count // 3, args.vehicle_count // 2))
        )
    )
    default_route = ROUTE_PATH if args.vehicle_count == VEHICLE_COUNT else PROJECT_ROOT / f"scenario8_{args.vehicle_count}.routes.xml"
    default_groups = (
        CONFLICT_GROUP_PATH
        if args.vehicle_count == VEHICLE_COUNT
        else PROJECT_ROOT / "data" / f"scenario8_{args.vehicle_count}_conflict_groups.csv"
    )
    route_path = project_path(args.output_route, default_route)
    conflict_group_path = project_path(args.output_conflict_groups, default_groups)

    vehicles = build_vehicles(
        vehicle_count=args.vehicle_count,
        conflict_group_count=conflict_group_count,
        random_seed=args.seed,
        dense=args.dense,
        end_time_s=args.end_time,
    )
    write_routes(vehicles, route_path, safe_behavior=args.safe_behavior)
    write_conflict_groups(vehicles, conflict_group_path)

    print(f"Wrote {route_path}")
    print(f"Wrote {conflict_group_path}")
    print(f"vehicle_count={len(vehicles)}")
    print(f"conflict_groups={conflict_group_count}")
    print(f"random_seed={args.seed}")
    print(f"dense={bool(args.dense)}")
    print(f"safe_behavior={bool(args.safe_behavior)}")
    print(f"end_time={args.end_time if args.end_time is not None else ''}")
    print(f"vehicle_ids=targeted_vehicle_001..targeted_vehicle_{len(vehicles):03d}")
    print("movement_distribution:")
    for movement_name in MOVEMENTS:
        count = sum(1 for vehicle in vehicles if vehicle["movement"] == movement_name)
        print(f"  {movement_name}: {count}")
    print("purpose_distribution:")
    for purpose in ["intentional_conflict", "random_background"]:
        count = sum(1 for vehicle in vehicles if vehicle["purpose"] == purpose)
        print(f"  {purpose}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
