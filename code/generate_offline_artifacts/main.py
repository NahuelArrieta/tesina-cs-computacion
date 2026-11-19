"""Generate Stage 2 artifacts for one experiment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import networkx as nx

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_offline_artifacts.build_dual_graph import (
    parse_network_xml,
    parse_routes_xml,
)
from generate_offline_artifacts.generate_detectors import generate_e2_detectors
from utils.dual_graph_handler import (
    assign_turning_probabilities,
    build_dual_graph,
    export_dual_graph,
    validate_graph,
)
from utils.subgraph_extractor import extract_upstream_subgraph


def _build_graph(network_file: Path, routes_file: Path) -> nx.DiGraph:
    graph = build_dual_graph(parse_network_xml(str(network_file)))
    assign_turning_probabilities(graph, parse_routes_xml(str(routes_file)))
    if not validate_graph(graph):
        raise ValueError(f"Dual graph validation failed for {routes_file}")
    return graph


def _load_experiment(manifest_file: Path, experiment_name: str) -> dict[str, Any]:
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("experiment") != experiment_name:
        raise ValueError(
            f"Manifest experiment '{manifest.get('experiment')}' "
            f"does not match '{experiment_name}'"
        )
    required = ("network", "incident", "detectors", "subgraph")
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError(f"Manifest is missing Stage 2 fields: {', '.join(missing)}")
    return manifest


def generate_artifacts(
    manifest_file: Path,
    network_directory: Path,
    experiment_name: str,
) -> dict[str, Any]:
    """Generate shared artifacts and validate every penetration file."""
    manifest_file = manifest_file.resolve()
    experiment_directory = manifest_file.parent
    manifest = _load_experiment(manifest_file, experiment_name)

    network_name = str(manifest["network"])
    network_file = (network_directory / network_name).resolve()
    if not network_file.is_file():
        raise FileNotFoundError(f"Network file not found: {network_file}")

    routes_directory = experiment_directory / "routes"
    base_routes_file = routes_directory / "routes.rou.xml"
    if not base_routes_file.is_file():
        raise FileNotFoundError(f"Shared routes file not found: {base_routes_file}")

    artifacts_directory = experiment_directory / "artifacts"
    artifacts_directory.mkdir(parents=True, exist_ok=True)
    graph = _build_graph(network_file, base_routes_file)
    graph_file = artifacts_directory / "graph.graphml"
    export_dual_graph(graph, str(graph_file))

    detectors = manifest["detectors"]
    detectors_file = artifacts_directory / "detectors.add.xml"
    generate_e2_detectors(
        str(network_file),
        str(detectors_file),
        detector_freq=int(detectors["frequency_s"]),
        end_offset=float(detectors["end_offset_m"]),
        start_pos=float(detectors["start_pos_m"]),
        output_xml_target="e2_output.xml",
    )

    incident = manifest["incident"]
    subgraph_config = manifest["subgraph"]
    subgraph = extract_upstream_subgraph(
        graph,
        incident_edge=str(incident["edge"]),
        min_prob_threshold=float(subgraph_config["min_probability"]),
        max_seconds_travel=float(subgraph_config["max_travel_time_s"]),
        intersection_delay=float(subgraph_config["intersection_delay_s"]),
    )
    subgraph_file = artifacts_directory / "subgraph.graphml"
    export_dual_graph(subgraph, str(subgraph_file))

    result = {
        "experiment": experiment_name,
        "experiment_directory": str(experiment_directory),
        "artifacts_directory": str(artifacts_directory),
        "graph": str(graph_file),
        "subgraph": str(subgraph_file),
        "detectors": str(detectors_file),
        "incident": incident,
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "subgraph_nodes": subgraph.number_of_nodes(),
        "subgraph_edges": subgraph.number_of_edges(),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Stage 2 artifacts for one experiment"
    )
    parser.add_argument("experiment", help="Experiment name")
    args = parser.parse_args()

    experiment_directory = Path(
        os.environ.get(
            "EXPERIMENT_DIR",
            str(Path(__file__).resolve().parents[2] / "experiments"),
        )
    ).expanduser().resolve()
    network_directory = Path(
        os.environ.get(
            "NETWORK_DIR",
            str(Path(__file__).resolve().parents[2] / "source files" / "networks"),
        )
    ).expanduser().resolve()
    manifest_file = experiment_directory / args.experiment / "manifest.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Experiment manifest not found: {manifest_file}")

    result = generate_artifacts(manifest_file, network_directory, args.experiment)
    print(f"Generated Stage 2 artifacts for {result['experiment']}")


if __name__ == "__main__":
    main()
