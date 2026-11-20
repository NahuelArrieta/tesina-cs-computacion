"""Generate reproducible shared SUMO route definitions."""

from __future__ import annotations

import os
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


def generate_base_routes(
    network_file: Path,
    output_file: Path,
    begin: float,
    end: float,
    period: float,
    seed: int,
) -> list[dict[str, str]]:
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
    generated = ET.parse(output_file)
    source_vehicles = generated.getroot().findall("vehicle")
    route_ids: dict[str, str] = {}
    vehicle_specs: list[dict[str, str]] = []
    for vehicle in source_vehicles:
        route = vehicle.find("route")
        if route is None:
            raise ValueError(f"Generated vehicle has no route: {vehicle.get('id')}")
        edges = " ".join(route.get("edges", "").split())
        if not edges:
            raise ValueError(f"Generated vehicle has no route edges: {vehicle.get('id')}")
        route_id = route_ids.setdefault(edges, f"route_{len(route_ids):05d}")
        vehicle_specs.append(
            {
                "id": str(vehicle.get("id", "")),
                "depart": str(vehicle.get("depart", "")),
                "departLane": str(vehicle.get("departLane", "best")),
                "departSpeed": str(vehicle.get("departSpeed", "max")),
                "route": route_id,
            }
        )

    root = ET.Element(
        "routes",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation":
                "http://sumo.dlr.de/xsd/routes_file.xsd",
        },
    )
    for edges, route_id in route_ids.items():
        ET.SubElement(root, "route", {"id": route_id, "edges": edges})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    return vehicle_specs


def validate_routes(
    network_file: Path,
    route_file: Path,
) -> None:
    network_edges = validate_network(network_file)
    root = ET.parse(route_file).getroot()
    route_edges = {
        edge
        for route in root.findall("route")
        for edge in route.get("edges", "").split()
    }
    unknown_edges = route_edges - network_edges
    if unknown_edges:
        raise ValueError(
            f"Generated routes reference unknown edges: {sorted(unknown_edges)}"
        )

