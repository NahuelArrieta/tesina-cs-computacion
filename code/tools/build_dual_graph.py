"""Build a dual graph from SUMO network and route XML files."""

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import sumolib

# When this file is executed directly, Python puts ``code/tools`` on
# sys.path rather than the project ``code`` directory.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.dual_graph_handler import (
    assign_turning_probabilities,
    build_dual_graph,
    export_dual_graph,
    validate_graph,
)

def parse_network_xml(net_xml_path: str) -> dict[str, Any]:
    """Read a SUMO network XML file into plain Python data."""
    if not os.path.exists(net_xml_path):
        raise FileNotFoundError(f"Network file not found: {net_xml_path}")

    network = sumolib.net.readNet(net_xml_path, withInternal=False)
    edges = []
    connections = []

    for edge in network.getEdges(withInternal=False):
        shape = edge.getShape()
        dx, dy = _get_edge_direction(shape)
        length = float(edge.getLength())
        midpoint_x = (shape[0][0] + shape[-1][0]) / 2.0
        midpoint_y = (shape[0][1] + shape[-1][1]) / 2.0
        edges.append(
            {
                "id": edge.getID(),
                "length_m": length,
                "speed_limit_mps": float(edge.getSpeed()),
                "num_lanes": int(edge.getLaneNumber()),
                "x": float(round(midpoint_x, 2) * 2 + dx * 10),
                "y": -float(round(midpoint_y, 2) * 2 + dy * 10),
                "dx": dx,
                "dy": dy,
            }
        )

        for target_edge, edge_connections in edge.getOutgoing().items():
            if target_edge.getID().startswith(":"):
                continue
            connections.append(
                {
                    "from": edge.getID(),
                    "to": target_edge.getID(),
                    "direction": str(edge_connections[0].getDirection()),
                }
            )

    return {"edges": edges, "connections": connections}


def parse_routes_xml(routes_xml_path: str) -> dict[tuple[str, str], int]:
    """Read route XML and count transitions between consecutive edges."""
    if not os.path.exists(routes_xml_path):
        raise FileNotFoundError(f"Routes file not found: {routes_xml_path}")

    transition_counts: dict[tuple[str, str], int] = {}
    context = ET.iterparse(routes_xml_path, events=("end",))
    for _, element in context:
        edges_string = None
        if element.tag == "vehicle":
            route = element.find("route")
            if route is not None:
                edges_string = route.get("edges")
        elif element.tag == "route":
            edges_string = element.get("edges")

        if edges_string:
            route_edges = edges_string.strip().split()
            for source, target in zip(route_edges, route_edges[1:]):
                pair = (source, target)
                transition_counts[pair] = transition_counts.get(pair, 0) + 1
        element.clear()

    return transition_counts


def _get_edge_direction(shape: list[tuple[float, float]]) -> tuple[int, int]:
    if len(shape) < 2:
        return 0, 0
    x1, y1 = shape[0]
    x2, y2 = shape[-1]
    return (
        1 if x2 > x1 else -1 if x2 < x1 else 0,
        1 if y2 > y1 else -1 if y2 < y1 else 0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline dual graph builder from SUMO network and routes."
    )
    parser.add_argument("--net", required=True, help="Path to grid.net.xml")
    parser.add_argument("--routes", required=True, help="Path to routes.rou.xml")
    parser.add_argument(
        "--output",
        default="data/dual_graph.graphml",
        help="Path to output GraphML file",
    )
    args = parser.parse_args()

    print("--- Reading Dual Graph Input Data ---")
    network_data = parse_network_xml(args.net)
    turning_counts = parse_routes_xml(args.routes)

    print("--- Building Dual Graph Topology ---")
    graph = build_dual_graph(network_data)
    print(
        f"Topological base built: {graph.number_of_nodes()} nodes, "
        f"{graph.number_of_edges()} edges."
    )
    print(f"Distinct maneuvers with observed demand: {len(turning_counts)}")

    print("--- Assigning Static Turning Ratios (Weights) ---")
    assign_turning_probabilities(graph, turning_counts)
    if not validate_graph(graph):
        print(
            "[ERROR] Graph validation failed: some nodes have turning "
            "probabilities that do not sum to 1.0"
        )
        raise SystemExit(1)

    print("--- Exporting GraphML ---")
    export_dual_graph(graph, args.output)


if __name__ == "__main__":
    main()
