"""Construction, validation, and persistence of dual graphs."""

import math
import os
from typing import Any

import networkx as nx


def get_direction_string(dx: int, dy: int) -> str:
    """Convert a direction vector into its string representation."""
    direction = ""
    if dy > 0:
        direction += "n"
    elif dy < 0:
        direction += "s"

    if dx > 0:
        direction += "e"
    elif dx < 0:
        direction += "w"

    return direction or "_"


def build_dual_graph(
    network_data: dict[str, Any],
    effective_veh_length_m: float = 7.5,
) -> nx.DiGraph:
    """Build a dual graph from parsed network data."""
    graph = nx.DiGraph()

    for edge in network_data["edges"]:
        dx, dy = edge["dx"], edge["dy"]
        length = edge["length_m"]
        graph.add_node(
            edge["id"],
            name=f'{edge["id"]}_{get_direction_string(dx, dy)}',
            length_m=round(length, 2),
            speed_limit_mps=round(edge["speed_limit_mps"], 2),
            num_lanes=edge["num_lanes"],
            capacity_veh=int(
                edge["num_lanes"] * math.floor(length / effective_veh_length_m)
            ),
            x=edge["x"],
            y=edge["y"],
            dx=dx,
            dy=dy,
        )

    for connection in network_data["connections"]:
        source, target = connection["from"], connection["to"]
        if not graph.has_node(target):
            print(
                f"[WARN] Skipping connection from {source} to {target}: "
                "target edge is not in the graph."
            )
            continue
        if graph.has_edge(source, target):
            continue
        graph.add_edge(
            source,
            target,
            raw_count=0,
            weight=0.0,
            direction=connection["direction"],
        )

    return graph


def assign_turning_probabilities(
    graph: nx.DiGraph, turning_counts: dict[tuple[str, str], int]
) -> nx.DiGraph:
    """Assign normalized turning counts to graph edges."""
    for (source, target), count in turning_counts.items():
        if graph.has_edge(source, target):
            graph[source][target]["raw_count"] = int(count)

    for source in graph.nodes():
        successors = list(graph.successors(source))
        if not successors:
            continue

        total_outflow = sum(
            graph[source][target]["raw_count"] for target in successors
        )
        if total_outflow > 0:
            for target in successors:
                graph[source][target]["weight"] = round(
                    graph[source][target]["raw_count"] / float(total_outflow),
                    4,
                )
        else:
            uniform_probability = round(1.0 / len(successors), 4)
            for target in successors:
                graph[source][target]["weight"] = uniform_probability

    return graph


def export_dual_graph(graph: nx.DiGraph, output_graphml_path: str) -> None:
    """Export a dual graph to GraphML."""
    output_directory = os.path.dirname(output_graphml_path)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    nx.write_graphml(graph, output_graphml_path)
    print(f"[OK] Dual graph successfully exported to: {output_graphml_path}")


def load_dual_graph(graphml_path: str) -> nx.DiGraph:
    """Load a GraphML dual graph with typed attributes."""
    if not os.path.exists(graphml_path):
        raise FileNotFoundError(f"GraphML file not found: {graphml_path}")

    raw_graph = nx.read_graphml(graphml_path)
    graph = nx.DiGraph()

    for node, attrs in raw_graph.nodes(data=True):
        graph.add_node(
            node,
            **{
                key: _coerce_node_attribute(key, value)
                for key, value in attrs.items()
            },
        )

    for source, target, attrs in raw_graph.edges(data=True):
        graph.add_edge(
            source,
            target,
            weight=float(attrs.get("weight", 0.0)),
            raw_count=int(attrs.get("raw_count", 0)),
            direction=str(attrs.get("direction", "s")),
        )

    return graph


def _coerce_node_attribute(key: str, value: Any) -> Any:
    if key in {"length_m", "speed_limit_mps", "x", "y"}:
        return float(value)
    if key in {"num_lanes", "capacity_veh", "dx", "dy"}:
        return int(value)
    return str(value)


def validate_graph(graph: nx.DiGraph) -> bool:
    """Check that outgoing turning probabilities sum to one."""
    errors = 0
    for source in graph.nodes():
        successors = list(graph.successors(source))
        if successors:
            total_weight = sum(
                graph[source][target]["weight"] for target in successors
            )
            if not math.isclose(total_weight, 1.0, abs_tol=1e-3):
                print(
                    f"[WARN] Node {source} turning probabilities sum to "
                    f"{total_weight} != 1.0"
                )
                errors += 1
    return errors == 0
