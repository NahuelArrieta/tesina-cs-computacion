"""Generate all offline artifacts required by the simulation stage."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
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


def _load_base_manifest(manifest_file: Path) -> dict[str, dict[str, str]]:
    entries = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"Base manifest must contain a list: {manifest_file}")
    scenarios = {}
    for entry in entries:
        scenario = str(entry.get("scenario", ""))
        route = entry.get("routes")
        network = entry.get("network")
        if not scenario or not route or not network:
            raise ValueError(
                f"Base manifest entry requires scenario, routes and network: {entry}"
            )
        scenarios[scenario] = {"routes": str(route), "network": str(network)}
    return scenarios


def _write_sumo_config(
    output_file: Path,
    network_file: Path,
    routes_file: Path,
    detectors_file: Path,
    simulation: dict[str, Any],
) -> None:
    root = ET.Element("configuration")
    input_node = ET.SubElement(root, "input")
    ET.SubElement(input_node, "net-file", {"value": str(network_file)})
    ET.SubElement(input_node, "route-files", {"value": str(routes_file)})
    ET.SubElement(input_node, "additional-files", {"value": str(detectors_file)})
    time_node = ET.SubElement(root, "time")
    for key, config_key in (
        ("begin", "begin_s"),
        ("end", "end_s"),
        ("step-length", "step_length_s"),
    ):
        ET.SubElement(time_node, key, {"value": str(simulation[config_key])})
    ET.indent(root, space="    ")
    output_file.write_text(
        ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8"
    )


def generate_artifacts(config_file: Path) -> list[dict[str, Any]]:
    """Generate Stage 2 artifacts for every route file in the configuration."""
    config_file = config_file.resolve()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    base_manifest_file = (config_file.parent / config["base_manifest"]).resolve()
    scenarios = _load_base_manifest(base_manifest_file)
    output_root = (config_file.parent / config["output_directory"]).resolve()
    results: list[dict[str, Any]] = []

    for experiment in config["experiments"]:
        experiment_name = str(experiment["name"])
        experiment_output = output_root / experiment_name
        experiment_output.mkdir(parents=True, exist_ok=True)
        simulation = experiment["simulation"]
        incident = experiment["incident"]
        detectors = experiment["detectors"]
        subgraph_config = experiment["subgraph"]
        scenario = str(experiment["scenario"])
        scenario_input = scenarios.get(scenario)
        if scenario_input is None:
            raise KeyError(f"Scenario not found in base manifest: {scenario}")
        routes_file = Path(scenario_input["routes"]).resolve()
        network_file = Path(scenario_input["network"]).resolve()

        graph = _build_graph(network_file, routes_file)
        graph_file = experiment_output / "graph.graphml"
        export_dual_graph(graph, str(graph_file))

        detectors_file = experiment_output / "detectors.add.xml"
        generate_e2_detectors(
            str(network_file),
            str(detectors_file),
            detector_freq=int(detectors["frequency_s"]),
            end_offset=float(detectors["end_offset_m"]),
            start_pos=float(detectors["start_pos_m"]),
            output_xml_target="e2_output.xml",
        )

        subgraph = extract_upstream_subgraph(
            graph,
            incident_edge=str(incident["edge"]),
            min_prob_threshold=float(subgraph_config["min_probability"]),
            max_seconds_travel=float(subgraph_config["max_travel_time_s"]),
            intersection_delay=float(subgraph_config["intersection_delay_s"]),
        )
        subgraph_file = experiment_output / "subgraph.graphml"
        export_dual_graph(subgraph, str(subgraph_file))
        sumo_config_file = experiment_output / f"{experiment_name}.sumocfg"
        _write_sumo_config(
            sumo_config_file,
            network_file,
            routes_file,
            detectors_file,
            simulation,
        )
        experiment_result = {
            "experiment": experiment_name,
            "scenario": scenario,
            "routes": str(routes_file),
            "graph": str(graph_file),
            "detectors": str(detectors_file),
            "sumocfg": str(sumo_config_file),
            "incident": incident,
            "subgraph": str(subgraph_file),
            "graph_nodes": graph.number_of_nodes(),
            "graph_edges": graph.number_of_edges(),
            "subgraph_nodes": subgraph.number_of_nodes(),
            "subgraph_edges": subgraph.number_of_edges(),
        }
        (experiment_output / "manifest.json").write_text(
            json.dumps(experiment_result, indent=2) + "\n", encoding="utf-8"
        )
        results.append(experiment_result)

    output_root.mkdir(parents=True, exist_ok=True)
    manifest = output_root / "manifest.json"
    manifest.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate offline artifacts for SUMO experiments"
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    results = generate_artifacts(args.config)
    print(f"Generated offline artifacts for {len(results)} scenarios")


if __name__ == "__main__":
    main()
