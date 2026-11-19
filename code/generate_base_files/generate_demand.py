"""Generate reproducible SUMO demand route files."""

from __future__ import annotations

import copy
import hashlib
import os
import random
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence


def validate_network(network_file: Path) -> set[str]:
    """Return external edge ids and reject an empty or malformed network."""
    root = ET.parse(network_file).getroot()
    edge_ids = {
        edge_id
        for edge in root.findall("edge")
        if not (edge_id := edge.get("id", "")).startswith(":")
    }
    if not edge_ids:
        raise ValueError(f"Network contains no external edges: {network_file}")
    if any(not edge.findall("lane") for edge in root.findall("edge")):
        raise ValueError(f"Network contains an edge without lanes: {network_file}")
    return edge_ids


def _run(command: Sequence[str], cwd: Path | None = None) -> None:
    subprocess.run(command, check=True, cwd=cwd, stdout=subprocess.DEVNULL)


def _sumo_tool(name: str) -> Path:
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        raise RuntimeError("SUMO_HOME must point to the SUMO installation")
    tool = Path(sumo_home) / "tools" / name
    if not tool.is_file():
        raise FileNotFoundError(f"SUMO tool not found: {tool}")
    return tool


def _generate_base_routes(
    network_file: Path,
    output_file: Path,
    begin: float,
    end: float,
    period: float,
    seed: int,
) -> None:
    """Generate base SUMO trips and route them through the network."""
    with tempfile.TemporaryDirectory(prefix="sumo-demand-") as temporary_directory:
        trips_file = Path(temporary_directory) / "trips.xml"
        _run(
            [
                sys.executable,
                str(_sumo_tool("randomTrips.py")),
                "--net-file",
                str(network_file),
                "--route-file",
                str(trips_file),
                "--begin",
                str(begin),
                "--end",
                str(end),
                "--period",
                f"{period:.12g}",
                "--seed",
                str(seed),
                "--trip-attributes",
                'departLane="best" departSpeed="max"',
            ],
            cwd=Path(temporary_directory),
        )
        _run(
            [
                "duarouter",
                "--net-file",
                str(network_file),
                "--route-files",
                str(trips_file),
                "--output-file",
                str(output_file),
                "--alternatives-output",
                os.devnull,
                "--seed",
                str(seed),
                "--ignore-errors",
            ]
        )


def _load_human_distributions(vtypes_file: Path) -> list[ET.Element]:
    vtypes_root = ET.parse(vtypes_file).getroot()
    distributions = vtypes_root.findall("vTypeDistribution")
    if not distributions:
        raise ValueError(f"VTypes file contains no distributions: {vtypes_file}")
    if any(not distribution.get("id") for distribution in distributions):
        raise ValueError(f"VTypes distributions have no id: {vtypes_file}")
    return distributions


def _select_cav_vehicles(
    vehicles: list[ET.Element],
    penetration: float,
    seed: int,
) -> set[str]:
    cav_count = round(len(vehicles) * penetration)
    vehicle_ids = {
        vehicle_id
        for vehicle in vehicles
        if (vehicle_id := vehicle.get("id"))
    }
    if cav_count > len(vehicle_ids):
        raise ValueError("CAV count cannot exceed generated vehicle count")
    return set(random.Random(seed).sample(sorted(vehicle_ids), cav_count))


def _assign_cav_types(
    vehicles: list[ET.Element],
    selected_vehicle_ids: set[str],
) -> None:
    for vehicle in vehicles:
        if vehicle.get("id") in selected_vehicle_ids:
            vehicle.set("type", "CAV")


def _assign_human_types(
    vehicles: list[ET.Element],
    selected_vehicle_ids: set[str],
    distributions: list[ET.Element],
    seed: int,
) -> None:
    distribution_ids = [
        distribution_id
        for distribution in distributions
        if (distribution_id := distribution.get("id"))
    ]
    human_rng = random.Random(seed)
    for vehicle in vehicles:
        if vehicle.get("id") not in selected_vehicle_ids:
            vehicle.set("type", human_rng.choice(distribution_ids))


def _create_cav_type() -> ET.Element:
    return ET.Element(
        "vType",
        {
            "id": "CAV",
            "vClass": "passenger",
            "carFollowModel": "Krauss",
            "accel": "2.6",
            "decel": "4.5",
            "tau": "0.5",
            "sigma": "0.5",
        },
    )


def _replace_vehicle_types(
    root: ET.Element,
    distributions: list[ET.Element],
) -> None:
    for vehicle_type in reversed(root.findall("vType")):
        root.remove(vehicle_type)
    for distribution in reversed(root.findall("vTypeDistribution")):
        root.remove(distribution)

    root.insert(0, _create_cav_type())
    insert_at = 1
    for distribution in distributions:
        root.insert(insert_at, copy.deepcopy(distribution))
        insert_at += 1


def _assign_vehicle_types(
    route_file: Path,
    penetration: float,
    seed: int,
    vtypes_file: Path,
) -> int:
    tree = ET.parse(route_file)
    root = tree.getroot()
    vehicles = root.findall("vehicle")
    distributions = _load_human_distributions(vtypes_file)
    selected_cav_ids = _select_cav_vehicles(vehicles, penetration, seed)

    _assign_cav_types(vehicles, selected_cav_ids)
    _assign_human_types(
        vehicles,
        selected_cav_ids,
        distributions,
        seed,
    )
    _replace_vehicle_types(root, distributions)

    ET.indent(tree, space="    ")
    tree.write(route_file, encoding="utf-8", xml_declaration=True)
    return len(selected_cav_ids)


def generate_demand(
    network_file: Path,
    output_file: Path,
    begin: float,
    end: float,
    period: float,
    seed: int,
    cav_penetration: float,
    vtypes_file: Path,
) -> dict[str, int | float | str]:
    """Generate and validate one deterministic route file."""
    if not 0.0 <= cav_penetration <= 1.0:
        raise ValueError("cav_penetration must be between 0 and 1")
    if period <= 0:
        raise ValueError("period must be positive")
    if end <= begin:
        raise ValueError("end must be greater than begin")

    network_file = network_file.resolve()
    network_edges = validate_network(network_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    _generate_base_routes(
        network_file,
        output_file,
        begin,
        end,
        period,
        seed,
    )

    route_tree = ET.parse(output_file)
    route_edges = {
        edge
        for route in route_tree.getroot().findall(".//route")
        for edge in route.get("edges", "").split()
    }
    unknown_edges = route_edges - network_edges
    if unknown_edges:
        raise ValueError(
            f"Generated routes reference unknown edges: {sorted(unknown_edges)}"
        )

    cav_count = _assign_vehicle_types(
        output_file,
        cav_penetration,
        seed,
        vtypes_file,
    )
    vehicle_count = len(route_tree.getroot().findall("vehicle"))
    return {
        "network": str(network_file),
        "network_sha256": hashlib.sha256(network_file.read_bytes()).hexdigest(),
        "seed": seed,
        "begin_s": begin,
        "end_s": end,
        "period_s": period,
        "vehicle_count": vehicle_count,
        "cav_penetration": cav_penetration,
        "cav_count": cav_count,
        "hdv_count": vehicle_count - cav_count,
    }
