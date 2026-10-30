"""Generate reproducible SUMO demand files for experiment scenarios."""

from __future__ import annotations

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


def _assign_vehicle_types(route_file: Path, penetration: float, seed: int) -> int:
    tree = ET.parse(route_file)
    root = tree.getroot()
    vehicles = root.findall("vehicle")
    cav_count = round(len(vehicles) * penetration)
    cav_ids = {vehicle.get("id") for vehicle in vehicles}
    selected = set(random.Random(seed).sample(sorted(cav_ids), cav_count))

    for vehicle in vehicles:
        vehicle.set("type", "CAV" if vehicle.get("id") in selected else "HDV")

    for vehicle_type in reversed(root.findall("vType")):
        root.remove(vehicle_type)
    root.insert(
        0,
        ET.Element(
            "vType",
            {
                "id": "HDV",
                "vClass": "passenger",
                "carFollowModel": "Krauss",
                "accel": "2.6",
                "decel": "4.5",
                "tau": "1.0",
            },
        ),
    )
    root.insert(
        1,
        ET.Element(
            "vType",
            {
                "id": "CAV",
                "vClass": "passenger",
                "carFollowModel": "Krauss",
                "accel": "2.6",
                "decel": "4.5",
                "tau": "0.5",
            },
        ),
    )
    ET.indent(tree, space="    ")
    tree.write(route_file, encoding="utf-8", xml_declaration=True)
    return cav_count


def generate_demand(
    network_file: Path,
    output_file: Path,
    period: float,
    begin: float,
    end: float,
    seed: int,
    cav_penetration: float,
) -> dict[str, int | float | str]:
    """Generate and validate one deterministic route file."""
    if not 0.0 <= cav_penetration <= 1.0:
        raise ValueError("cav_penetration must be between 0 and 1")
    if period <= 0 or end <= begin:
        raise ValueError("period must be positive and end must be greater than begin")

    network_file = network_file.resolve()
    network_edges = validate_network(network_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

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
                str(period),
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

    route_tree = ET.parse(output_file)
    route_edges = {
        edge
        for route in route_tree.getroot().findall(".//route")
        for edge in route.get("edges", "").split()
    }
    unknown_edges = route_edges - network_edges
    if unknown_edges:
        raise ValueError(f"Generated routes reference unknown edges: {sorted(unknown_edges)}")

    cav_count = _assign_vehicle_types(output_file, cav_penetration, seed)
    vehicle_count = len(route_tree.getroot().findall("vehicle"))
    return {
        "network": str(network_file),
        "network_sha256": hashlib.sha256(network_file.read_bytes()).hexdigest(),
        "seed": seed,
        "period_s": period,
        "begin_s": begin,
        "end_s": end,
        "vehicle_count": vehicle_count,
        "cav_penetration": cav_penetration,
        "cav_count": cav_count,
        "hdv_count": vehicle_count - cav_count,
    }
